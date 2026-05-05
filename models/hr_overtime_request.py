from odoo import api, fields, models
from odoo.exceptions import ValidationError

# 法定加班上限（勞基法）
MONTHLY_OT_LIMIT_HOURS = 46
SINGLE_DAY_OT_LIMIT_HOURS = 12


class HrOvertimeRequest(models.Model):
    """PR-034：加班申請模型（hr.overtime.request）"""
    _name = "hr.overtime.request"
    _description = "加班申請"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "overtime_date desc, id desc"

    name = fields.Char(
        string="申請單號",
        copy=False,
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "hr.overtime.request"
        ) or "新申請",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        index=True,
        ondelete="cascade",
    )
    overtime_date = fields.Date(
        string="加班日期",
        required=True,
    )
    overtime_type_id = fields.Many2one(
        "hr.overtime.type",
        string="加班類型",
        required=True,
    )
    start_time = fields.Float(
        string="開始時間（小時）",
        help="格式：8.5 = 08:30",
    )
    end_time = fields.Float(
        string="結束時間（小時）",
    )
    hours = fields.Float(
        string="加班時數",
        compute="_compute_hours",
        store=True,
        digits=(6, 2),
    )
    compensation = fields.Selection(
        selection=[
            ("cash", "加班費"),
            ("leave", "補休假"),
        ],
        string="補償方式",
        default="cash",
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("pending", "待審核"),
            ("approved", "已核准"),
            ("rejected", "已駁回"),
            ("cancelled", "已取消"),
        ],
        string="狀態",
        default="draft",
        tracking=True,
    )
    approver_id = fields.Many2one("res.users", string="審核人", readonly=True)
    approval_date = fields.Datetime(string="審核日期", readonly=True)
    rejection_reason = fields.Text(string="駁回原因", readonly=True)
    remark = fields.Text(string="加班原因")

    # 加班費計算結果（PR-035）
    tax_free_amount = fields.Float(
        string="加班費（免稅）",
        digits=(10, 2),
        compute="_compute_overtime_pay",
        store=True,
    )
    taxable_amount = fields.Float(
        string="加班費（應稅）",
        digits=(10, 2),
        compute="_compute_overtime_pay",
        store=True,
    )
    total_amount = fields.Float(
        string="加班費合計",
        digits=(10, 2),
        compute="_compute_overtime_pay",
        store=True,
    )

    # 補休配額（PR-036）
    compensatory_allocation_id = fields.Many2one(
        "hr.leave.allocation",
        string="補休配額",
        readonly=True,
    )

    @api.depends("start_time", "end_time")
    def _compute_hours(self):
        for req in self:
            if req.end_time and req.start_time:
                req.hours = round(req.end_time - req.start_time, 2)
            else:
                req.hours = 0.0

    @api.depends(
        "hours", "overtime_type_id", "state",
        "employee_id.contract_ids.hour_salary",
        "employee_id.contract_ids.state",
    )
    def _compute_overtime_pay(self):
        """PR-035：呼叫既有加班費計算引擎。"""
        OTCalc = self.env["hr.overtime.calculation"]
        for req in self:
            if req.state not in ("approved",) or not req.hours:
                req.tax_free_amount = 0.0
                req.taxable_amount = 0.0
                req.total_amount = 0.0
                continue

            active_contract = req.employee_id.contract_ids.filtered(
                lambda c: c.state == "open"
            )
            hour_salary = active_contract[0].hour_salary if active_contract else 0.0

            result = OTCalc._calculate(
                ot_type=req.overtime_type_id.code if req.overtime_type_id else "weekday",
                hours=req.hours,
                hour_salary=hour_salary,
            )
            req.tax_free_amount = result.get("tax_free", 0.0)
            req.taxable_amount = result.get("taxable", 0.0)
            req.total_amount = result.get("total", 0.0)

    @api.constrains("hours", "overtime_date", "employee_id")
    def _check_overtime_limits(self):
        for req in self:
            # 單日上限
            if req.hours > SINGLE_DAY_OT_LIMIT_HOURS:
                raise ValidationError(
                    f"單日加班時數不得超過 {SINGLE_DAY_OT_LIMIT_HOURS} 小時！"
                )
            # 外籍員工居留證到期 → 凍結申請
            if req.employee_id.is_no_pr and req.employee_id.permit_expiry:
                today = fields.Date.today()
                if req.employee_id.permit_expiry < today:
                    raise ValidationError(
                        f"員工 {req.employee_id.name} 的居留證已到期，無法申請加班！"
                    )

    def action_submit(self):
        for req in self:
            req.write({"state": "pending"})
            req.message_post(body="加班申請已提交審核。", subtype_xmlid="mail.mt_note")

    def action_approve(self):
        for req in self:
            if req.state != "pending":
                raise ValidationError("只有待審核的申請才能核准！")
            req.write({
                "state": "approved",
                "approver_id": self.env.uid,
                "approval_date": fields.Datetime.now(),
            })
            # PR-036：補休方式 → 建立配額
            if req.compensation == "leave":
                req._create_compensatory_allocation()
            req.message_post(
                body=f"加班申請已核准（{req.hours:.2f} 小時）。",
                subtype_xmlid="mail.mt_note",
            )

    def action_reject(self, reason=""):
        for req in self:
            req.write({"state": "rejected", "rejection_reason": reason})
            body = "加班申請已駁回。"
            if reason:
                body += f"<br/>駁回原因：{reason}"
            req.message_post(body=body, subtype_xmlid="mail.mt_note")

    def _create_compensatory_allocation(self):
        """PR-036：加班轉補休 → 建立補休假配額。"""
        self.ensure_one()
        leave_type = self.env["hr.leave.type"].search(
            [("code", "=", "COMP")], limit=1
        )
        if not leave_type:
            return
        alloc = self.env["hr.leave.allocation"].create({
            "name": f"補休配額（{self.name}）",
            "employee_id": self.employee_id.id,
            "holiday_status_id": leave_type.id,
            "number_of_days": round(self.hours / 8, 2),
            "allocation_type": "fixed",
            "state": "validate",
        })
        self.write({"compensatory_allocation_id": alloc.id})


class HrOvertimeStatisticsRecord(models.Model):
    """PR-037：加班統計報表（月度）"""
    _name = "hr.overtime.statistics.record"
    _description = "加班統計月報"
    _order = "year desc, month desc, employee_id"

    employee_id = fields.Many2one("hr.employee", string="員工", required=True, index=True)
    year = fields.Integer(string="年份", required=True)
    month = fields.Integer(string="月份", required=True)
    period = fields.Char(string="期間", compute="_compute_period", store=True)

    weekday_hours = fields.Float(string="平日加班時數", digits=(6, 2), default=0.0)
    holiday_hours = fields.Float(string="休假日加班時數", digits=(6, 2), default=0.0)
    rest_day_hours = fields.Float(string="例假日加班時數", digits=(6, 2), default=0.0)
    national_holiday_hours = fields.Float(string="國定假日加班時數", digits=(6, 2), default=0.0)
    total_hours = fields.Float(
        string="合計時數",
        compute="_compute_totals",
        store=True,
        digits=(6, 2),
    )
    tax_free_total = fields.Float(string="免稅加班費合計", digits=(10, 2), default=0.0)
    taxable_total = fields.Float(string="應稅加班費合計", digits=(10, 2), default=0.0)

    _sql_constraints = [
        (
            "employee_month_uniq",
            "UNIQUE(employee_id, year, month)",
            "同一員工同月份只能有一筆加班統計！",
        ),
    ]

    @api.depends("year", "month")
    def _compute_period(self):
        for rec in self:
            rec.period = f"{rec.year}-{str(rec.month).zfill(2)}"

    @api.depends("weekday_hours", "holiday_hours", "rest_day_hours", "national_holiday_hours")
    def _compute_totals(self):
        for rec in self:
            rec.total_hours = (
                rec.weekday_hours + rec.holiday_hours
                + rec.rest_day_hours + rec.national_holiday_hours
            )

    @api.model
    def generate_monthly(self, year, month):
        """PR-037：產生月度加班統計。"""
        date_from = f"{year}-{str(month).zfill(2)}-01"
        date_to = (
            f"{year + 1}-01-01" if month == 12
            else f"{year}-{str(month + 1).zfill(2)}-01"
        )
        requests = self.env["hr.overtime.request"].search([
            ("state", "=", "approved"),
            ("overtime_date", ">=", date_from),
            ("overtime_date", "<", date_to),
        ])
        employee_ids = requests.mapped("employee_id.id")
        results = []
        for emp_id in set(employee_ids):
            emp_reqs = requests.filtered(lambda r: r.employee_id.id == emp_id)
            existing = self.search(
                [("employee_id", "=", emp_id), ("year", "=", year), ("month", "=", month)]
            )
            vals = {
                "employee_id": emp_id,
                "year": year,
                "month": month,
                "weekday_hours": sum(
                    r.hours for r in emp_reqs
                    if r.overtime_type_id and r.overtime_type_id.code == "weekday"
                ),
                "holiday_hours": sum(
                    r.hours for r in emp_reqs
                    if r.overtime_type_id and r.overtime_type_id.code == "holiday"
                ),
                "rest_day_hours": sum(
                    r.hours for r in emp_reqs
                    if r.overtime_type_id and r.overtime_type_id.code == "rest_day"
                ),
                "national_holiday_hours": sum(
                    r.hours for r in emp_reqs
                    if r.overtime_type_id and r.overtime_type_id.code == "national"
                ),
                "tax_free_total": sum(emp_reqs.mapped("tax_free_amount")),
                "taxable_total": sum(emp_reqs.mapped("taxable_amount")),
            }
            if existing:
                existing.write(vals)
                results.append(existing)
            else:
                results.append(self.create(vals))
        return results
