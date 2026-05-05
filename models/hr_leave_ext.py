from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrLeaveType(models.Model):
    """PR-026：假別類型擴充（父子假別、折算、台灣法規欄位）"""
    _inherit = "hr.leave.type"

    code = fields.Char(string="假別代碼", help="例如：ANNUAL, SICK, PERSONAL")
    parent_leave_id = fields.Many2one(
        "hr.leave.type",
        string="父假別",
        help="此假別歸屬於哪個父假別類別",
    )
    child_leave_ids = fields.One2many(
        "hr.leave.type",
        "parent_leave_id",
        string="子假別",
    )
    pay_ratio = fields.Float(
        string="薪資折算比例",
        default=1.0,
        digits=(4, 2),
        help="1.0=全薪，0.5=半薪，0.0=無薪",
    )
    advance_notice_days = fields.Integer(
        string="提前申請天數",
        default=0,
        help="需提前幾天申請，0 表示不限制",
    )
    count_as_attendance = fields.Boolean(
        string="計為正常出勤",
        default=False,
        help="勾選表示請此假不影響全勤判定",
    )
    is_parental_leave = fields.Boolean(
        string="育嬰留停假別",
        default=False,
    )
    is_statutory = fields.Boolean(
        string="法定保障假別",
        default=False,
        help="勾選表示此假別受勞基法保障，不可低於法定額度",
    )
    no_seniority = fields.Boolean(
        string="不計年資",
        default=False,
        help="勾選表示此假別請假期間不計入服務年資",
    )
    auto_allocate = fields.Selection(
        selection=[
            ("none", "不自動配發"),
            ("anniversary", "周年制"),
            ("calendar", "歷年制"),
        ],
        string="自動配發方式",
        default="none",
    )
    withholding_code = fields.Char(
        string="扣繳代號",
        help="所得稅申報用扣繳代號",
    )

    @api.constrains("pay_ratio")
    def _check_pay_ratio(self):
        for lt in self:
            if not (0.0 <= lt.pay_ratio <= 1.0):
                raise ValidationError("薪資折算比例必須在 0.0 到 1.0 之間！")


class HrLeaveAllocation(models.Model):
    """PR-028/029/030：特休假配額自動分配（周年制/歷年制）、留停凍結"""
    _inherit = "hr.leave.allocation"

    is_auto_allocated = fields.Boolean(
        string="系統自動配發",
        default=False,
        readonly=True,
    )
    allocation_year = fields.Integer(
        string="配發年度",
        help="周年制：服務滿幾年的配發；歷年制：哪個自然年",
    )
    carryover_date = fields.Date(
        string="結轉日期",
        help="特休未休部分須於此日期前使用或轉換",
    )
    furlough_freeze_days = fields.Integer(
        string="留停凍結天數",
        default=0,
        readonly=True,
        help="留停期間，結轉日期順延的天數",
    )

    @api.model
    def _auto_allocate_annual(self, employee):
        """PR-028：依年資對照表自動配發特休假（周年制）。"""
        AnnualLeave = self.env["hr.annual.leave"]
        tenure = employee.job_tenure
        days = AnnualLeave.get_leave_days(tenure_years=tenure)
        if days <= 0:
            return

        leave_type = self.env["hr.leave.type"].search(
            [("code", "=", "ANNUAL")], limit=1
        )
        if not leave_type:
            return

        # 避免重複配發同年度
        existing = self.search([
            ("employee_id", "=", employee.id),
            ("holiday_status_id", "=", leave_type.id),
            ("is_auto_allocated", "=", True),
            ("allocation_year", "=", int(tenure)),
        ])
        if existing:
            return

        carryover = employee.conversion_date or fields.Date.today()
        carryover_next = carryover.replace(year=carryover.year + 1)

        self.create({
            "name": f"特休自動配發（年資 {tenure:.1f} 年）",
            "employee_id": employee.id,
            "holiday_status_id": leave_type.id,
            "number_of_days": days,
            "allocation_type": "fixed",
            "state": "validate",
            "is_auto_allocated": True,
            "allocation_year": int(tenure),
            "carryover_date": carryover_next,
        })

    @api.model
    def _auto_allocate_calendar(self, employee, year):
        """PR-029：歷年制按比例分配特休假。"""
        AnnualLeave = self.env["hr.annual.leave"]
        tenure = employee.job_tenure
        days = AnnualLeave.get_leave_days(tenure_years=tenure)
        if days <= 0:
            return

        # 年中到職：按剩餘月份比例
        contract_start = None
        contracts = employee.contract_ids.filtered(
            lambda c: c.state in ("open", "close") and c.date_start
        )
        if contracts:
            contract_start = min(contracts.mapped("date_start"))

        if contract_start and contract_start.year == year:
            month_ratio = (12 - contract_start.month + 1) / 12
            days = round(days * month_ratio, 1)

        leave_type = self.env["hr.leave.type"].search(
            [("code", "=", "ANNUAL")], limit=1
        )
        if not leave_type:
            return

        existing = self.search([
            ("employee_id", "=", employee.id),
            ("holiday_status_id", "=", leave_type.id),
            ("is_auto_allocated", "=", True),
            ("allocation_year", "=", year),
        ])
        if existing:
            return

        self.create({
            "name": f"特休自動配發（{year} 年歷年制）",
            "employee_id": employee.id,
            "holiday_status_id": leave_type.id,
            "number_of_days": days,
            "allocation_type": "fixed",
            "state": "validate",
            "is_auto_allocated": True,
            "allocation_year": year,
            "carryover_date": fields.Date.from_string(f"{year}-12-31"),
        })

    def freeze_for_furlough(self, furlough_days):
        """PR-030：留停 → 結轉日期延後 furlough_days 天。"""
        for alloc in self:
            if alloc.carryover_date:
                new_date = alloc.carryover_date + timedelta(days=furlough_days)
                alloc.write({
                    "carryover_date": new_date,
                    "furlough_freeze_days": alloc.furlough_freeze_days + furlough_days,
                })

    @api.model
    def get_remaining_days(self, employee_id, leave_type_id):
        """PR-032：即時查詢剩餘假別配額。"""
        allocations = self.search([
            ("employee_id", "=", employee_id),
            ("holiday_status_id", "=", leave_type_id),
            ("state", "=", "validate"),
        ])
        total_allocated = sum(allocations.mapped("number_of_days"))
        leaves = self.env["hr.leave"].search([
            ("employee_id", "=", employee_id),
            ("holiday_status_id", "=", leave_type_id),
            ("state", "=", "validate"),
        ])
        total_used = sum(leaves.mapped("number_of_days"))
        return round(total_allocated - total_used, 2)

    @api.model
    def batch_allocate_all_employees(self, mode="anniversary"):
        """PR-033：一鍵全體員工特休分配。"""
        employees = self.env["hr.employee"].search([
            ("contract_ids.state", "=", "open"),
        ])
        year = fields.Date.today().year
        for emp in employees:
            if mode == "anniversary":
                self._auto_allocate_annual(emp)
            else:
                self._auto_allocate_calendar(emp, year)


class HrLeave(models.Model):
    """PR-031：假單申請與審核流程擴充"""
    _inherit = "hr.leave"

    advance_notice_ok = fields.Boolean(
        string="提前申請符合",
        compute="_compute_advance_notice_ok",
        store=True,
    )
    leave_hours = fields.Float(
        string="請假時數",
        compute="_compute_leave_hours",
        store=True,
        digits=(6, 2),
    )

    @api.depends("holiday_status_id", "date_from")
    def _compute_advance_notice_ok(self):
        today = fields.Date.today()
        for leave in self:
            required = leave.holiday_status_id.advance_notice_days
            if not required or not leave.date_from:
                leave.advance_notice_ok = True
                continue
            apply_date = leave.date_from.date() if hasattr(leave.date_from, 'date') else leave.date_from
            days_ahead = (apply_date - today).days
            leave.advance_notice_ok = days_ahead >= required

    @api.depends("date_from", "date_to")
    def _compute_leave_hours(self):
        for leave in self:
            if leave.date_from and leave.date_to:
                delta = leave.date_to - leave.date_from
                leave.leave_hours = round(delta.total_seconds() / 3600, 2)
            else:
                leave.leave_hours = 0.0

    @api.constrains("holiday_status_id", "date_from")
    def _check_advance_notice(self):
        for leave in self:
            if not leave.advance_notice_ok:
                lt = leave.holiday_status_id
                raise ValidationError(
                    f"假別「{lt.name}」需提前 {lt.advance_notice_days} 天申請！"
                )
