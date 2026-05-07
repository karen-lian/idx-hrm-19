from odoo import fields, models


class HrOvertimeRejectWizard(models.TransientModel):
    _name = "hr.overtime.reject.wizard"
    _description = "加班申請拒絕原因"

    overtime_id = fields.Many2one("hr.overtime", required=True, ondelete="cascade")
    reason = fields.Text(string="拒絕原因", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.overtime_id.action_reject(reason=self.reason)
        return {"type": "ir.actions.act_window_close"}
