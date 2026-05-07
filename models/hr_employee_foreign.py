from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployeeForeign(models.Model):
    """PR-013：外籍員工居留/工作許可欄位與效期管理"""
    _inherit = "hr.employee"

    permit_no = fields.Char(
        string="居留證號碼",
        copy=False,
    )
    permit_expiry = fields.Date(
        string="居留證效期",
    )
    work_permit_no = fields.Char(
        string="工作許可號碼",
        copy=False,
    )
    work_permit_expiry = fields.Date(
        string="工作許可效期",
    )
    is_no_pr = fields.Boolean(
        string="無永久居留權",
        default=False,
        help="外籍員工尚未取得永久居留權，需追蹤效期",
    )
    permit_alert_days = fields.Integer(
        string="效期警示天數",
        default=60,
        help="效期到期前幾天發出警示，預設 60 天",
    )

    @api.constrains("permit_expiry", "work_permit_expiry")
    def _check_permit_dates(self):
        today = fields.Date.today()
        for emp in self:
            if emp.permit_expiry and emp.permit_expiry < today:
                raise ValidationError(
                    f"員工 {emp.name} 的居留證已於 {emp.permit_expiry} 到期！"
                )

    def _cron_check_permit_expiry(self):
        """每日掃描外籍員工效期，到期前 permit_alert_days 天建立 mail.activity 警示。"""
        today = fields.Date.today()
        employees = self.search([
            ("is_no_pr", "=", True),
            "|",
            ("permit_expiry", "!=", False),
            ("work_permit_expiry", "!=", False),
        ])
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for emp in employees:
            for field_name, expiry_date in [
                ("permit_expiry", emp.permit_expiry),
                ("work_permit_expiry", emp.work_permit_expiry),
            ]:
                if not expiry_date:
                    continue
                days_left = (expiry_date - today).days
                if 0 <= days_left <= emp.permit_alert_days:
                    field_label = "居留證" if field_name == "permit_expiry" else "工作許可"
                    existing = self.env["mail.activity"].search([
                        ("res_model", "=", "hr.employee"),
                        ("res_id", "=", emp.id),
                        ("summary", "like", field_label),
                    ])
                    if not existing and activity_type:
                        emp.activity_schedule(
                            activity_type_id=activity_type.id,
                            summary=f"外籍員工{field_label}即將到期（{days_left} 天）",
                            note=f"{emp.name} 的{field_label}將於 {expiry_date} 到期，請儘快辦理續簽。",
                            user_id=emp.hr_responsible_id.user_id.id or self.env.uid,
                        )
