from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

OVERTIME_DAY_TYPE = [
    ("weekday", "平日加班"),
    ("rest_day", "休假日加班"),
    ("mandatory_rest", "例假日加班"),
    ("public_holiday", "國定假日加班"),
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


class HrOvertime(models.Model):
    _name = "hr.overtime"
    _description = "加班申請"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"

    name = fields.Char(
        string="單號",
        copy=False,
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("hr.overtime") or "OVT-新增",
    )
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
        related="employee_id.parent_id", string="管理人", store=True,
    )
    request_date = fields.Date(string="申請日期", required=True, default=fields.Date.today)
    request_hour_from = fields.Float(string="從", digits=(4, 2), help="格式：18.5 = 18:30")
    request_hour_to = fields.Float(string="到", digits=(4, 2))
    hours = fields.Float(
        string="總時數", compute="_compute_hours", store=True, digits=(5, 2),
    )
    type = fields.Selection(
        selection=COMPENSATION_TYPE, string="申請類型", required=True, default="cash", tracking=True,
    )
    overtime_type_id = fields.Many2one(
        "hr.overtime.config.type", string="加班時段", ondelete="restrict",
    )
    leave_validity_start = fields.Date(
        string="補休分配起始日",
        help="申請類型為補休時，假期配額的生效起始日",
    )
    leave_allocation_id = fields.Many2one(
        "hr.leave.allocation", string="休假分配", readonly=True, copy=False,
    )
    attachment = fields.Binary(string="附加文件")
    attachment_name = fields.Char(string="附件名稱")
    description = fields.Text(string="說明", required=True)
    return_reason = fields.Text(string="拒絕原因", readonly=True)
    state = fields.Selection(
        selection=OT_STATE, string="狀態", default="draft", tracking=True, required=True,
    )

    _sql_constraints = [
        (
            "name_uniq",
            "UNIQUE(name)",
            "加班單號必須唯一",
        ),
    ]

    @api.depends("request_hour_from", "request_hour_to")
    def _compute_hours(self):
        for rec in self:
            if rec.request_hour_to and rec.request_hour_from and rec.request_hour_to > rec.request_hour_from:
                rec.hours = round(rec.request_hour_to - rec.request_hour_from, 2)
            else:
                rec.hours = 0.0

    @api.constrains("request_hour_from", "request_hour_to")
    def _check_time_range(self):
        for rec in self:
            if rec.request_hour_from and rec.request_hour_to:
                if rec.request_hour_to <= rec.request_hour_from:
                    raise ValidationError("結束時間必須晚於開始時間")

    @api.constrains("type", "leave_validity_start")
    def _check_leave_validity_start(self):
        for rec in self:
            if rec.type == "leave" and rec.state == "approved" and not rec.leave_validity_start:
                raise ValidationError("申請類型為補休時，必須填寫補休分配起始日")

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("只有草稿狀態可以提交")
            rec.write({"state": "pending"})
            if rec.manager_id:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=rec.manager_id.user_id.id,
                    summary=f"加班申請待審批：{rec.name}",
                    note=f"{rec.employee_id.name} 申請 {rec.request_date} 加班 {rec.hours:.1f} 小時，請審批。",
                )

    def action_approve(self):
        for rec in self:
            if rec.state != "pending":
                raise UserError("只有待批准狀態可以核准")
            rec.write({"state": "approved"})
            if rec.type == "leave":
                rec._create_leave_allocation()
            rec.message_post(
                body=f"加班申請已核准（{rec.hours:.1f} 小時）。",
                partner_ids=rec.employee_id.user_id.partner_id.ids,
            )

    def action_reject(self, reason=""):
        for rec in self:
            if rec.state != "pending":
                raise UserError("只有待批准狀態可以拒絕")
            rec.write({"state": "rejected", "return_reason": reason})
            body = "加班申請已被拒絕。"
            if reason:
                body += f"<br/>原因：{reason}"
            rec.message_post(
                body=body,
                partner_ids=rec.employee_id.user_id.partner_id.ids,
            )

    def action_return(self):
        """員工或管理員將已批准單據退回（state → pending）。"""
        for rec in self:
            if rec.state != "approved":
                raise UserError("只有已批准狀態可以退回")
            if rec.leave_allocation_id:
                alloc = rec.leave_allocation_id
                if alloc.leaves_taken > 0:
                    raise UserError("該張加班補休分配單已使用，不能退回加班單")
                alloc.action_refuse()
                alloc.action_draft()
                alloc.unlink()
                rec.write({"leave_allocation_id": False})
            rec.write({"state": "pending"})

    def _create_leave_allocation(self):
        self.ensure_one()
        leave_type = self.env.ref("idx_hrm_19.leave_type_overtime", raise_if_not_found=False)
        if not leave_type:
            return
        alloc = self.env["hr.leave.allocation"].create({
            "name": f"加班補休分配（{self.name}）",
            "employee_id": self.employee_id.id,
            "holiday_status_id": leave_type.id,
            "number_of_days": round(self.hours / 8, 4),
            "allocation_type": "fixed",
            "date_from": self.leave_validity_start or self.request_date,
        })
        alloc.action_validate()
        self.write({"leave_allocation_id": alloc.id})
