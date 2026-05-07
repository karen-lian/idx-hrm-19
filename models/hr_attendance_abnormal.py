from datetime import timedelta, timezone, datetime
from odoo import api, fields, models

_UTC8 = timezone(timedelta(hours=8))

ABNORMAL_TYPES = [
    ("late", "遲到"),
    ("early_leave", "早退"),
    ("forget_checkin", "忘刷進"),
    ("forget_checkout", "忘刷出"),
    ("absent", "曠職"),
    ("overtime_no_apply", "未申請加班"),
    ("leave_no_apply", "未請假"),
    ("short_break", "休息不足"),
    ("holiday_work", "假日出勤未申請"),
    ("double_checkin", "重複打卡"),
    ("cross_midnight", "跨夜班異常"),
    ("other", "其他異常"),
]


class HrAttendanceAbnormalAbsenceRecord(models.Model):
    """PR-022：出勤異常紀錄（12 種類型）"""
    _name = "hr.attendance.abnormal.absence.record"
    _description = "出勤異常紀錄"
    _inherit = ["mail.thread"]
    _order = "abnormal_date desc, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        index=True,
        ondelete="cascade",
    )
    abnormal_date = fields.Date(
        string="異常日期",
        required=True,
        index=True,
    )
    type = fields.Selection(
        selection=ABNORMAL_TYPES,
        string="異常類型",
        required=True,
    )
    minutes = fields.Integer(
        string="分鐘數",
        help="遲到/早退分鐘數（適用 late/early_leave 類型）",
    )
    deduction_amount = fields.Float(
        string="扣款金額",
        digits=(10, 2),
        default=0.0,
    )
    description = fields.Text(string="說明")
    is_resolved = fields.Boolean(
        string="已補正",
        default=False,
        tracking=True,
        help="補登核准後自動標記為 True",
    )
    audit_state = fields.Selection(
        selection=[
            ("pending", "待確認"),
            ("no_action", "無異常"),
            ("leave_apply", "補假單"),
            ("online_apply", "補登申請"),
            ("absent_deduct", "曠職扣薪"),
            ("archived", "已封存"),
        ],
        string="稽核狀態",
        default="pending",
        tracking=True,
    )
    attendance_month_id = fields.Many2one(
        "hr.attendance.month",
        string="月份結算",
        ondelete="set null",
    )

    @api.model
    def _detect_abnormal(self, date_from, date_to, employee_ids=None):
        """PR-022/023：批次偵測異常出勤，回傳已建立的異常記錄 recordset。"""
        AttSetting = self.env["hr.attendance.setting"].search([], limit=1)
        grace = AttSetting.grace_minutes if AttSetting else 0
        work_start_hour = 9  # 預設上班時間 09:00 UTC+8（可改從設定讀）

        domain = [("check_date", ">=", date_from), ("check_date", "<=", date_to)]
        if employee_ids:
            domain.append(("employee_id", "in", employee_ids))

        attendances = self.env["hr.attendance"].search(domain)
        created = self.env["hr.attendance.abnormal.absence.record"]

        processed = set()
        for att in attendances:
            emp = att.employee_id
            if emp.is_no_punch:
                continue

            key = (emp.id, att.check_date)
            if key in processed:
                continue
            processed.add(key)

            # 忘刷進
            if not att.check_in:
                created |= self.create({
                    "employee_id": emp.id,
                    "abnormal_date": att.check_date,
                    "type": "forget_checkin",
                })
                continue

            # 忘刷出
            if not att.check_out:
                created |= self.create({
                    "employee_id": emp.id,
                    "abnormal_date": att.check_date,
                    "type": "forget_checkout",
                })

            # 遲到偵測
            if att.check_in:
                local_in = att.check_in.replace(tzinfo=timezone.utc).astimezone(_UTC8)
                threshold = local_in.replace(
                    hour=work_start_hour, minute=grace, second=0, microsecond=0
                )
                if local_in > threshold:
                    late_min = int((local_in - threshold).total_seconds() / 60)
                    created |= self.create({
                        "employee_id": emp.id,
                        "abnormal_date": att.check_date,
                        "type": "late",
                        "minutes": late_min,
                    })

        return created


class HrAttendanceAudit(models.Model):
    """PR-023：出勤稽核作業流程"""
    _name = "hr.attendance.audit"
    _description = "出勤稽核作業"
    _inherit = ["mail.thread"]

    name = fields.Char(
        string="稽核單號",
        readonly=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "hr.attendance.audit"
        ) or "新稽核",
    )
    date_from = fields.Date(string="稽核起日", required=True)
    date_to = fields.Date(string="稽核迄日", required=True)
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("detecting", "偵測中"),
            ("confirming", "HR 確認中"),
            ("archived", "已封存"),
        ],
        string="狀態",
        default="draft",
        tracking=True,
    )
    abnormal_ids = fields.One2many(
        "hr.attendance.abnormal.absence.record",
        "attendance_month_id",
        string="異常記錄",
    )
    abnormal_count = fields.Integer(
        string="異常筆數",
        compute="_compute_abnormal_count",
    )

    @api.depends("abnormal_ids")
    def _compute_abnormal_count(self):
        for audit in self:
            audit.abnormal_count = len(audit.abnormal_ids)

    def action_detect(self):
        """批次偵測指定期間的異常出勤"""
        for audit in self:
            self.env["hr.attendance.abnormal.absence.record"]._detect_abnormal(
                date_from=str(audit.date_from),
                date_to=str(audit.date_to),
            )
            audit.write({"state": "confirming"})

    def action_archive(self):
        """封存稽核，之後不可修改"""
        for audit in self:
            if audit.state != "confirming":
                return
            audit.abnormal_ids.write({"audit_state": "archived"})
            audit.write({"state": "archived"})


class HrAttendanceMonth(models.Model):
    """PR-024/025：每月出勤結算與全勤獎金判定"""
    _name = "hr.attendance.month"
    _description = "每月出勤結算"
    _inherit = ["mail.thread"]
    _order = "year desc, month desc, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        index=True,
        ondelete="cascade",
    )
    year = fields.Integer(string="年份", required=True)
    month = fields.Integer(
        string="月份",
        required=True,
        help="1~12",
    )
    period = fields.Char(
        string="期間",
        compute="_compute_period",
        store=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("confirmed", "已確認"),
            ("locked", "已鎖定"),
        ],
        string="狀態",
        default="draft",
    )

    # PR-024：出勤統計欄位
    late_count = fields.Integer(string="遲到次數", default=0)
    late_minutes = fields.Integer(string="遲到分鐘數", default=0)
    early_leave_count = fields.Integer(string="早退次數", default=0)
    early_leave_minutes = fields.Integer(string="早退分鐘數", default=0)
    absent_days = fields.Float(string="曠職天數", digits=(6, 1), default=0.0)
    leave_hours = fields.Float(string="請假時數", digits=(6, 2), default=0.0)
    overtime_hours = fields.Float(string="加班時數", digits=(6, 2), default=0.0)
    work_days = fields.Integer(string="出勤天數", default=0)
    deduction_total = fields.Float(
        string="扣款合計",
        digits=(10, 2),
        compute="_compute_deduction_total",
        store=True,
    )

    # PR-025：全勤獎金
    perfect_attendance = fields.Boolean(
        string="全勤",
        compute="_compute_perfect_attendance",
        store=True,
    )
    perfect_attendance_bonus = fields.Float(
        string="全勤獎金",
        digits=(10, 2),
        compute="_compute_perfect_attendance",
        store=True,
    )

    _sql_constraints = [
        (
            "employee_month_uniq",
            "UNIQUE(employee_id, year, month)",
            "同一員工同月份只能有一筆結算記錄！",
        ),
    ]

    @api.depends("year", "month")
    def _compute_period(self):
        for rec in self:
            rec.period = f"{rec.year}-{str(rec.month).zfill(2)}"

    @api.depends(
        "late_count", "late_minutes", "early_leave_minutes", "absent_days"
    )
    def _compute_deduction_total(self):
        for rec in self:
            deduction = 0.0
            # 遲到/早退扣款：查 hr.late.early.criterion
            LEC = self.env["hr.late.early.criterion"]
            if rec.late_minutes > 0:
                criteria = LEC.search(
                    [("minute_from", "<=", rec.late_minutes),
                     ("minute_to", ">=", rec.late_minutes)],
                    limit=1,
                )
                deduction += criteria.deduction if criteria else 0.0
            # 曠職扣款：日薪 × 曠職天數
            current_version = rec.employee_id.current_version_id
            if current_version and rec.absent_days:
                daily = current_version.wage / 30
                deduction += daily * rec.absent_days
            rec.deduction_total = round(deduction, 2)

    @api.depends(
        "late_count", "late_minutes", "early_leave_count",
        "absent_days", "leave_hours",
    )
    def _compute_perfect_attendance(self):
        AttSetting = self.env["hr.attendance.setting"].search([], limit=1)
        enable = AttSetting.enable_perfect_attendance if AttSetting else False
        bonus_amount = AttSetting.perfect_attendance_bonus if AttSetting else 0.0

        for rec in self:
            if not enable:
                rec.perfect_attendance = False
                rec.perfect_attendance_bonus = 0.0
                continue

            # 全勤條件：無遲到、無曠職、請假時數 ≤ 允許值
            # 月中到/離職：不扣（以 work_days > 0 且 < 當月應出勤天數為判斷）
            is_perfect = (
                rec.late_count == 0
                and rec.early_leave_count == 0
                and rec.absent_days == 0.0
                and rec.leave_hours == 0.0
            )
            rec.perfect_attendance = is_perfect
            rec.perfect_attendance_bonus = bonus_amount if is_perfect else 0.0

    @api.model
    def generate(self, employee_id, month_str):
        """PR-024：產生或更新指定員工月份的出勤結算，month_str 格式 'YYYY-MM'。"""
        year, month = map(int, month_str.split("-"))
        existing = self.search(
            [("employee_id", "=", employee_id), ("year", "=", year), ("month", "=", month)]
        )
        if existing:
            return existing

        # 統計異常紀錄
        Abnormal = self.env["hr.attendance.abnormal.absence.record"]
        date_from = f"{year}-{str(month).zfill(2)}-01"
        # 月末
        if month == 12:
            date_to = f"{year + 1}-01-01"
        else:
            date_to = f"{year}-{str(month + 1).zfill(2)}-01"

        late_recs = Abnormal.search([
            ("employee_id", "=", employee_id),
            ("abnormal_date", ">=", date_from),
            ("abnormal_date", "<", date_to),
            ("type", "=", "late"),
        ])
        early_recs = Abnormal.search([
            ("employee_id", "=", employee_id),
            ("abnormal_date", ">=", date_from),
            ("abnormal_date", "<", date_to),
            ("type", "=", "early_leave"),
        ])
        absent_recs = Abnormal.search([
            ("employee_id", "=", employee_id),
            ("abnormal_date", ">=", date_from),
            ("abnormal_date", "<", date_to),
            ("type", "=", "absent"),
        ])

        return self.create({
            "employee_id": employee_id,
            "year": year,
            "month": month,
            "late_count": len(late_recs),
            "late_minutes": sum(late_recs.mapped("minutes")),
            "early_leave_count": len(early_recs),
            "early_leave_minutes": sum(early_recs.mapped("minutes")),
            "absent_days": len(absent_recs),
        })
