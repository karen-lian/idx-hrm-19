from datetime import timedelta, timezone
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_UTC8 = timezone(timedelta(hours=8))


class HrAttendance(models.Model):
    """PR-019：出勤打卡擴充（UTC+8 歸屬日、補登旗標、最早進/最晚出）"""
    _inherit = "hr.attendance"

    check_date = fields.Date(
        string="歸屬日期（台灣）",
        compute="_compute_check_date",
        store=True,
        index=True,
        help="以 UTC+8 計算的打卡歸屬日期",
    )
    is_online = fields.Boolean(
        string="補登記錄",
        default=False,
        help="True 表示此筆為補登出勤，非原始打卡",
    )
    online_attendance_id = fields.Many2one(
        "hr.attendance.online",
        string="補登申請",
        readonly=True,
    )
    work_shift = fields.Selection(
        selection=[
            ("day", "日班"),
            ("night", "夜班"),
            ("flexible", "彈性"),
        ],
        string="班別",
        default="day",
    )

    @api.depends("check_in")
    def _compute_check_date(self):
        for att in self:
            if att.check_in:
                local_dt = att.check_in.replace(tzinfo=timezone.utc).astimezone(_UTC8)
                att.check_date = local_dt.date()
            else:
                att.check_date = False

    @api.model
    def get_daily_summary(self, employee_id, date):
        """回傳指定員工指定日期的最早進/最晚出時間（UTC）"""
        records = self.search([
            ("employee_id", "=", employee_id),
            ("check_date", "=", date),
        ])
        if not records:
            return None
        check_ins = records.filtered("check_in").mapped("check_in")
        check_outs = records.filtered("check_out").mapped("check_out")
        return {
            "earliest_in": min(check_ins) if check_ins else None,
            "latest_out": max(check_outs) if check_outs else None,
            "records": records,
        }


class HrAttendanceOnline(models.Model):
    """PR-020/020b：補登出勤申請、審核工作流與稽核軌跡"""
    _name = "hr.attendance.online"
    _description = "補登出勤申請"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "apply_date desc, id desc"

    name = fields.Char(
        string="申請單號",
        copy=False,
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "hr.attendance.online"
        ) or "新申請",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        index=True,
        ondelete="cascade",
    )
    apply_date = fields.Date(
        string="補登日期",
        required=True,
        help="需補登出勤的日期",
    )
    check_in = fields.Datetime(string="補登上班時間", required=True)
    check_out = fields.Datetime(string="補登下班時間")
    reason = fields.Text(string="補登原因", required=True)
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("pending", "待審核"),
            ("approved", "已核准"),
            ("rejected", "已駁回"),
        ],
        string="狀態",
        default="draft",
        tracking=True,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="審核人",
        readonly=True,
    )
    approval_date = fields.Datetime(string="審核日期", readonly=True)
    rejection_reason = fields.Text(string="駁回原因", readonly=True)
    attendance_id = fields.Many2one(
        "hr.attendance",
        string="產生的出勤記錄",
        readonly=True,
    )
    abnormal_record_id = fields.Many2one(
        "hr.attendance.abnormal.absence.record",
        string="對應異常記錄",
        help="補登核准後，對應的異常記錄將標記為已補正",
    )

    @api.constrains("check_in", "check_out")
    def _check_times(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                if rec.check_out <= rec.check_in:
                    raise ValidationError("下班時間必須晚於上班時間！")

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise ValidationError("只有草稿狀態才能提交！")
            rec.write({"state": "pending"})
            rec.message_post(
                body=f"補登申請已提交審核（日期：{rec.apply_date}）",
                subtype_xmlid="mail.mt_note",
            )

    def action_approve(self):
        """PR-020b：核准補登，自動建立 hr.attendance 記錄並關聯異常記錄"""
        for rec in self:
            if rec.state != "pending":
                raise ValidationError("只有待審核的申請才能核准！")
            att = self.env["hr.attendance"].create({
                "employee_id": rec.employee_id.id,
                "check_in": rec.check_in,
                "check_out": rec.check_out,
                "is_online": True,
                "online_attendance_id": rec.id,
            })
            vals = {
                "state": "approved",
                "approver_id": self.env.uid,
                "approval_date": fields.Datetime.now(),
                "attendance_id": att.id,
            }
            if rec.abnormal_record_id:
                rec.abnormal_record_id.write({"is_resolved": True})
            rec.write(vals)
            rec.message_post(
                body=f"補登已由 {self.env.user.name} 核准，出勤記錄已建立。",
                subtype_xmlid="mail.mt_note",
            )

    def action_reject(self, reason=""):
        """PR-020b：駁回補登申請，理由寫入 mail thread（稽核軌跡）"""
        for rec in self:
            if rec.state != "pending":
                raise ValidationError("只有待審核的申請才能駁回！")
            rec.write({
                "state": "rejected",
                "rejection_reason": reason,
            })
            body = "補登申請已駁回。"
            if reason:
                body += f"<br/>駁回原因：{reason}"
            rec.message_post(body=body, subtype_xmlid="mail.mt_note")


class ResourceCalendar(models.Model):
    """擴充 resource.calendar：彈性上下班容許分鐘數（僅 fully_fixed 排班適用）"""
    _inherit = "resource.calendar"

    flexible_attendance_before = fields.Integer(
        string="彈性上班時間-往前",
        default=0,
        help="員工可提前幾分鐘打卡上班（例：30 表示可提前 30 分鐘打卡）",
    )
    flexible_attendance = fields.Integer(
        string="彈性上班時間-往後",
        default=0,
        help="員工可延後幾分鐘打卡上班（例：30 表示可延後 30 分鐘打卡）",
    )
    attendance_overtime = fields.Integer(
        string="容許下班晚打卡",
        default=0,
        help="員工下班後可延後幾分鐘打卡（例：30 表示可延後 30 分鐘打卡下班）",
    )
