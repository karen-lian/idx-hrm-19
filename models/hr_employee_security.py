"""PR-061：身分證號碼欄位安全（遮罩顯示）"""
from odoo import api, fields, models


class HrEmployee(models.Model):
    """PR-061：非授權用戶讀取身分證號時顯示遮罩"""
    _inherit = "hr.employee"

    identification_id_masked = fields.Char(
        string="身分證字號（遮罩）",
        compute="_compute_id_masked",
        help="非薪資管理員以上權限者，僅顯示遮罩後的身分證號",
    )

    def _compute_id_masked(self):
        is_payroll = self.env.user.has_group(
            "payroll.group_payroll_manager"
        )
        for emp in self:
            id_no = emp.identification_id
            if not id_no:
                emp.identification_id_masked = ""
            elif is_payroll:
                emp.identification_id_masked = id_no
            else:
                # 顯示前 1 碼 + 遮罩 + 最後 1 碼：A*******9
                masked = id_no[0] + "*" * (len(id_no) - 2) + id_no[-1]
                emp.identification_id_masked = masked
