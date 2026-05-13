from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

OVERTIME_DAY_TYPE = [
    ("weekday", "平日加班"),
    ("day_off", "休息日加班"),
    ("regular_holiday", "例假日加班"),
    ("regular_holiday_national_holiday", "國定假日加班"),
]

COMPENSATION_TYPE = [
    ("cash", "現金"),
    ("leave", "補休"),
]

OT_STATE = [
    ("draft", "草稿"),
    ("pending", "待批准"),
    ("approved", "已批准"),
    ("rejected", "已拒絕"),
]

# float_time 最大值（24:00）
_MAX_HOUR = 24.0


def _float_to_hhmm(val):
    """將 float_time（如 18.5）轉為顯示字串「18:30」。"""
    h = int(val)
    m = round((val - h) * 60)
    return f"{h:02d}:{m:02d}"


def _round_to_unit(hours, unit):
    """依 request_unit 無條件捨去至最小單位，回傳 float。"""
    if unit == "half_an_hour":
        step = 0.5
    else:
        step = 1.0
    import math
    return math.floor(hours / step) * step


class HrOvertime(models.Model):
    _name = "hr.overtime"
    _description = "加班申請"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"

    # ── 單號：儲存時才產生 ──────────────────────────────────────
    name = fields.Char(
        string="單號",
        copy=False,
        readonly=True,
        default="新增",
    )

    # ── 員工 ────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        "hr.employee", string="員工", required=True, index=True,
        default=lambda self: self.env.user.employee_id,
    )
    department_id = fields.Many2one(
        related="employee_id.department_id", string="部門", store=True,
    )
    job_id = fields.Many2one(
        related="employee_id.job_id", string="職稱", store=True,
    )
    manager_id = fields.Many2one(
        related="employee_id.overtime_manager_id", string="加班審核主管", store=True,
    )

    # ── 加班時段（支援跨日） ────────────────────────────────────
    request_date = fields.Date(
        string="加班日期", required=True, default=fields.Date.today,
    )
    request_hour_from = fields.Float(
        string="開始時間", digits=(4, 2),
        help="格式：18.5 = 18:30，範圍 0.0 ~ 24.0",
    )
    # 跨日旗標
    is_cross_day = fields.Boolean(string="跨日", default=False)
    request_date_to = fields.Date(
        string="結束日期",
        compute="_compute_request_date_to", store=True, readonly=False,
    )
    request_hour_to = fields.Float(
        string="結束時間", digits=(4, 2),
        help="格式：18.5 = 18:30，範圍 0.0 ~ 24.0",
    )

    hours = fields.Float(
        string="總時數", compute="_compute_hours", store=True, digits=(5, 2),
    )

    # ── 申請類型 ────────────────────────────────────────────────
    type = fields.Selection(
        selection=COMPENSATION_TYPE, string="申請類型",
        required=True, default="cash", tracking=True,
    )
    overtime_type_id = fields.Many2one(
        "hr.overtime.type", string="加班時段", ondelete="restrict",
    )
    leave_validity_start = fields.Date(
        string="補休分配起始日",
        compute="_compute_leave_validity_start", store=True, readonly=False,
        help="申請類型為補休時，假期配額的生效起始日，預設為加班起始日+1天",
    )
    leave_allocation_id = fields.Many2one(
        "hr.leave.allocation", string="休假分配", readonly=True, copy=False,
    )
    attachment = fields.Binary(string="附加文件")
    attachment_name = fields.Char(string="附件名稱")
    description = fields.Text(string="說明", required=True)
    return_reason = fields.Text(string="拒絕原因", readonly=True)
    state = fields.Selection(
        selection=OT_STATE, string="狀態",
        default="draft", tracking=True, required=True,
    )

    _sql_constraints = [
        (
            "name_uniq",
            "UNIQUE(name)",
            "加班單號必須唯一",
        ),
    ]

    def copy(self, default=None):
        raise UserError("加班申請不允許複製。")

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    f"加班申請（{rec.name}）非草稿狀態，不允許刪除。"
                )
        return super().unlink()

    # ── Default 自動帶入起始時段 ─────────────────────────────────

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # 取今天的星期（0=Mon…6=Sun）
        today = fields.Date.today()
        weekday = today.weekday()  # 0=Mon, 6=Sun
        # 找員工的工作日曆
        employee = self.env.user.employee_id
        calendar = (
            employee.resource_calendar_id
            or (employee.company_id and employee.company_id.resource_calendar_id)
        )
        if calendar:
            # 找今天星期對應的排班，取 hour_to 最大值（即最晚的下班時間）
            work_lines = calendar.attendance_ids.filtered(
                lambda a: int(a.dayofweek) == weekday
                and a.day_period != "lunch"
            )
            if work_lines:
                max_hour_to = max(work_lines.mapped("hour_to"))
                res["request_hour_from"] = max_hour_to
                res["request_hour_to"] = min(max_hour_to + 1.0, 24.0)
        return res

    # ── Compute ─────────────────────────────────────────────────

    @api.depends("is_cross_day", "request_date")
    def _compute_request_date_to(self):
        for rec in self:
            if rec.is_cross_day and rec.request_date:
                rec.request_date_to = rec.request_date + timedelta(days=1)
            else:
                rec.request_date_to = rec.request_date

    @api.depends(
        "request_date", "request_hour_from",
        "is_cross_day", "request_date_to", "request_hour_to",
        "overtime_type_id",
    )
    def _compute_hours(self):
        for rec in self:
            if not rec.request_hour_from or not rec.request_hour_to:
                rec.hours = 0.0
                continue

            date_from = rec.request_date
            date_to = rec.request_date_to or rec.request_date

            # 轉為 datetime 計算分鐘差
            dt_from = datetime.combine(date_from, datetime.min.time()) + timedelta(hours=rec.request_hour_from)
            dt_to = datetime.combine(date_to, datetime.min.time()) + timedelta(hours=rec.request_hour_to)

            if dt_to <= dt_from:
                rec.hours = 0.0
                continue

            raw_hours = (dt_to - dt_from).total_seconds() / 3600.0

            # 依 overtime_type_id.request_unit 取捨至最小單位
            unit = rec.overtime_type_id.request_unit if rec.overtime_type_id else "half_an_hour"
            rec.hours = _round_to_unit(raw_hours, unit)

    # ── Compute ─────────────────────────────────────────────────（補休分配起始日）

    @api.depends("request_date", "type")
    def _compute_leave_validity_start(self):
        for rec in self:
            if rec.type == "leave" and rec.request_date:
                rec.leave_validity_start = rec.request_date + timedelta(days=1)
            else:
                rec.leave_validity_start = False

    # ── onchange ────────────────────────────────────────────────

    @api.onchange("is_cross_day", "request_date")
    def _onchange_cross_day(self):
        if self.is_cross_day and self.request_date:
            self.request_date_to = self.request_date + timedelta(days=1)
        else:
            self.request_date_to = self.request_date

    @api.onchange("request_date", "type")
    def _onchange_auto_overtime_type(self):
        """依據 request_date 與 type 自動帶入加班時段（overtime_type_id）。

        規則：
        - type='leave'：直接取 hr.overtime.type 中 type='leave' 的第一筆。
        - type='cash'：先查 resource.calendar.leaves 有無符合 request_date 的假別，
          若有，以其 leave_type 去比對 hr.overtime.type.overtime_type_date_rule，
          取 type='cash' 的第一筆；若查無假期資料則清空欄位。
        """
        if not self.request_date and self.type != "leave":
            return

        OvertimeType = self.env["hr.overtime.type"]

        if self.type == "leave":
            ot_type = OvertimeType.search([("type", "=", "leave")], limit=1)
            self.overtime_type_id = ot_type or False
            return

        # type == 'cash'：查 request_date 對應的 resource.calendar.leaves
        if not self.request_date:
            return

        date_from_dt = fields.Datetime.from_string(
            f"{self.request_date} 00:00:00"
        )
        date_to_dt = fields.Datetime.from_string(
            f"{self.request_date} 23:59:59"
        )
        calendar_leave = self.env["resource.calendar.leaves"].search(
            [
                ("leave_type", "!=", False),
                ("date_from", "<=", date_to_dt),
                ("date_to", ">=", date_from_dt),
            ],
            limit=1,
        )
        if calendar_leave and calendar_leave.leave_type:
            # 依假日類型找對應的加班時段
            ot_type = OvertimeType.search(
                [
                    ("overtime_type_date_rule", "=", calendar_leave.leave_type),
                    ("type", "=", "cash"),
                ],
                limit=1,
            )
        else:
            # 查無假日記錄 → 視為平日，帶入「平日加班」類型
            ot_type = OvertimeType.search(
                [
                    ("overtime_type_date_rule", "=", "weekday"),
                    ("type", "=", "cash"),
                ],
                limit=1,
            )
        self.overtime_type_id = ot_type or False

    # ── Constrains ──────────────────────────────────────────────

    @api.constrains("request_hour_from", "request_hour_to",
                    "request_date", "request_date_to", "is_cross_day")
    def _check_time_range(self):
        for rec in self:
            h_from = rec.request_hour_from
            h_to = rec.request_hour_to

            # 範圍正規化：0.0 ~ 24.0
            if not (0.0 <= h_from <= _MAX_HOUR):
                raise ValidationError(
                    f"開始時間必須介於 00:00 ~ 24:00，目前值：{_float_to_hhmm(h_from)}"
                )
            if not (0.0 <= h_to <= _MAX_HOUR):
                raise ValidationError(
                    f"結束時間必須介於 00:00 ~ 24:00，目前值：{_float_to_hhmm(h_to)}"
                )

            # 跨日時：結束日必須 = 開始日 + 1
            date_from = rec.request_date
            date_to = rec.request_date_to or date_from
            if rec.is_cross_day and date_to != date_from + timedelta(days=1):
                raise ValidationError("跨日加班：結束日期必須為開始日期的隔天。")

            # 起訖合理性
            dt_from = datetime.combine(date_from, datetime.min.time()) + timedelta(hours=h_from)
            dt_to = datetime.combine(date_to, datetime.min.time()) + timedelta(hours=h_to)
            if dt_to <= dt_from:
                raise ValidationError("結束時間必須晚於開始時間。")

    @api.constrains("type", "leave_validity_start")
    def _check_leave_validity_start(self):
        for rec in self:
            if rec.type == "leave" and rec.state in ("pending", "approved") and not rec.leave_validity_start:
                raise ValidationError("申請類型為補休時，必須填寫補休分配起始日")

    # ── 儲存時產生單號 ───────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "新增":
                vals["name"] = self.env["ir.sequence"].next_by_code("hr.overtime") or "新增"
        return super().create(vals_list)

    # ── 提交前商業邏輯驗證 ──────────────────────────────────────

    def _check_work_schedule_overlap(self):
        """4.1：加班時段不得落在公司表定上班時間內。"""
        self.ensure_one()
        employee = self.employee_id
        # 優先取員工自訂工作日曆，若無則取公司預設日曆
        calendar = (
            employee.resource_calendar_id
            or employee.company_id.resource_calendar_id
        )
        if not calendar:
            return  # 無排班設定，略過
        date_from = self.request_date
        date_to = self.request_date_to or date_from
        dt_ot_from = datetime.combine(date_from, datetime.min.time()) + timedelta(hours=self.request_hour_from)
        dt_ot_to = datetime.combine(date_to, datetime.min.time()) + timedelta(hours=self.request_hour_to)

        # 取出該日的 resource.calendar.attendance 時段
        weekday = date_from.weekday()  # 0=Mon…6=Sun
        work_lines = calendar.attendance_ids.filtered(
            lambda a: int(a.dayofweek) == weekday
        )
        for line in work_lines:
            dt_work_from = datetime.combine(date_from, datetime.min.time()) + timedelta(hours=line.hour_from)
            dt_work_to = datetime.combine(date_from, datetime.min.time()) + timedelta(hours=line.hour_to)
            # 重疊判斷
            if dt_ot_from < dt_work_to and dt_ot_to > dt_work_from:
                raise ValidationError(
                    f"加班時段（{_float_to_hhmm(self.request_hour_from)}～"
                    f"{_float_to_hhmm(self.request_hour_to)}）"
                    f"與公司表定上班時間（{_float_to_hhmm(line.hour_from)}～"
                    f"{_float_to_hhmm(line.hour_to)}）重疊，不能提交加班申請。"
                )

    def _check_duplicate_overlap(self):
        """4.2：不能提交與現有申請時段重疊的加班單。"""
        self.ensure_one()
        date_from = self.request_date
        date_to = self.request_date_to or date_from
        dt_ot_from = datetime.combine(date_from, datetime.min.time()) + timedelta(hours=self.request_hour_from)
        dt_ot_to = datetime.combine(date_to, datetime.min.time()) + timedelta(hours=self.request_hour_to)

        existing = self.env["hr.overtime"].search([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("state", "in", ["pending", "approved"]),
            # 快速過濾：日期有交集才進細查
            ("request_date", "<=", date_to),
            ("request_date_to", ">=", date_from),
        ])
        for rec in existing:
            r_date_to = rec.request_date_to or rec.request_date
            dt_r_from = datetime.combine(rec.request_date, datetime.min.time()) + timedelta(hours=rec.request_hour_from)
            dt_r_to = datetime.combine(r_date_to, datetime.min.time()) + timedelta(hours=rec.request_hour_to)
            if dt_ot_from < dt_r_to and dt_ot_to > dt_r_from:
                raise ValidationError(
                    f"此加班區間已有提交申請（單號：{rec.name}，"
                    f"{rec.request_date} {_float_to_hhmm(rec.request_hour_from)}～"
                    f"{_float_to_hhmm(rec.request_hour_to)}），"
                    "若是時段有誤要修改，請用原單處理。"
                )

    # ── Actions ─────────────────────────────────────────────────

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("只有草稿狀態可以提交")
            if not rec.hours or rec.hours <= 0:
                raise UserError("加班時間未達申請加班的基準!")
            rec._check_work_schedule_overlap()
            rec._check_duplicate_overlap()
            rec.write({"state": "pending"})
            if rec.manager_id:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=rec.manager_id.user_id.id,
                    summary=f"加班申請待審批：{rec.name}",
                    note=(
                        f"{rec.employee_id.name} 申請 {rec.request_date} "
                        f"{_float_to_hhmm(rec.request_hour_from)}～"
                        f"{_float_to_hhmm(rec.request_hour_to)} "
                        f"加班 {rec.hours:.1f} 小時，請審批。"
                    ),
                )

    def action_approve(self):
        for rec in self:
            if rec.state != "pending":
                raise UserError("只有待批准狀態可以核准")
            rec.write({"state": "approved"})
            if rec.type == "leave":
                rec._create_leave_allocation()
            # 自動標記「待審批」活動為完成
            rec.activity_feedback(
                ["mail.mail_activity_data_todo"],
                feedback="加班申請已核准。",
            )
            rec.message_post(
                body=f"加班申請已核准（{rec.hours:.1f} 小時）。",
                partner_ids=rec.employee_id.user_id.partner_id.ids,
            )

    def action_reject(self, reason=""):
        for rec in self:
            if rec.state != "pending":
                raise UserError("只有待批准狀態可以拒絕")
            rec.write({"state": "rejected", "return_reason": reason})
            # 自動標記「待審批」活動為完成
            rec.activity_feedback(
                ["mail.mail_activity_data_todo"],
                feedback=f"加班申請已拒絕。{('原因：' + reason) if reason else ''}",
            )
            body = "加班申請已被拒絕。"
            if reason:
                body += f"<br/>原因：{reason}"
            rec.message_post(
                body=body,
                partner_ids=rec.employee_id.user_id.partner_id.ids,
            )

    def action_return(self):
        """將已批准單據退回草稿（state → draft），取消補休分配。"""
        for rec in self:
            if rec.state != "approved":
                raise UserError("只有已批准狀態可以退回")
            if rec.type == "leave" and rec.leave_allocation_id:
                alloc = rec.leave_allocation_id.sudo()
                if alloc.leaves_taken > 0:
                    raise UserError("員工已經使用加班補休假，不能退回加班申請!")
                # Odoo 19 分配單狀態機：validate → refuse（需 sudo 繞過權限檢查）
                # refuse 後 state=refuse，符合 unlink 條件（confirm/refuse 才可刪）
                alloc.action_refuse()
                alloc.with_context(allocation_skip_state_check=True).unlink()
                rec.write({"leave_allocation_id": False})
            rec.write({"state": "draft"})

    def _create_leave_allocation(self):
        self.ensure_one()
        leave_type = self.env["hr.leave.type"].search(
            [("code", "=", "Overtime")], limit=1
        )
        if not leave_type:
            return
        # Odoo 19：create() 預設 state=confirm，不可帶其他 state
        # 須 sudo 才能執行 _action_validate()（需 hr officer 權限）
        alloc = self.env["hr.leave.allocation"].sudo().create({
            "name": f"加班補休分配（{self.name}）",
            "employee_id": self.employee_id.id,
            "holiday_status_id": leave_type.id,
            "number_of_days": round(self.hours / 8, 4),
            "allocation_type": "regular",
            "date_from": self.leave_validity_start or self.request_date,
        })
        # _action_validate()：直接寫入 state=validate，略過 action_approve 的 can_validate 檢查
        alloc._action_validate()
        self.write({"leave_allocation_id": alloc.id})
