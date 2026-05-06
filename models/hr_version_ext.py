"""PR-014/015/016/016b：合約版本擴充欄位、審核工作流（基於 hr.version）

Odoo 19 已將 hr.contract 重構為 hr.version。
本檔案繼承 hr.version，加入台灣法規所需的額外欄位與審核流程。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrVersion(models.Model):
    """PR-014/015/016/016b：hr.version 台灣法規擴充"""
    _inherit = "hr.version"

    # PR-014：合約基本擴充欄位

    change_reason = fields.Selection(
        selection=[
            ("new_hire", "新進"),
            ("promotion", "晉升"),
            ("transfer", "調職"),
            ("salary_adjust", "薪資調整"),
            ("furlough", "留職停薪"),
            ("reinstate", "復職"),
            ("resign", "離職"),
            ("retire", "退休"),
        ],
        string="異動原因",
        tracking=True,
    )
    job_level = fields.Char(
        string="職等",
        help="例如：P1, P2, M1",
    )
    job_class = fields.Char(
        string="職級",
        help="例如：工程師、資深工程師",
    )
    is_part_time = fields.Boolean(
        string="部分工時",
        default=False,
    )
    hour_salary = fields.Float(
        string="時薪",
        digits=(10, 2),
        compute="_compute_hour_salary",
        store=True,
        help="月薪 ÷ 30 ÷ 8",
    )
    hour_leave_salary = fields.Float(
        string="事假時薪",
        digits=(10, 2),
        compute="_compute_hour_salary",
        store=True,
        help="用於事假扣薪計算",
    )
    labor_insurance_premium_employee = fields.Float(
        string="員工勞保費",
        digits=(10, 2),
        default=0.0,
    )
    labor_insurance_premium_employer = fields.Float(
        string="雇主勞保費",
        digits=(10, 2),
        default=0.0,
    )
    health_insurance_premium_employee = fields.Float(
        string="員工健保費",
        digits=(10, 2),
        default=0.0,
    )
    health_insurance_premium_employer = fields.Float(
        string="雇主健保費",
        digits=(10, 2),
        default=0.0,
    )
    pension_employer = fields.Float(
        string="雇主勞退提撥",
        digits=(10, 2),
        default=0.0,
    )
    is_no_pr = fields.Boolean(
        string="無永久居留權",
        default=False,
        help="外籍員工無永久居留權，影響加班申請",
    )
    no_resident = fields.Boolean(
        string="非居住者",
        default=False,
        related="employee_id.no_resident",
        store=True,
    )

    # PR-015：審核流程欄位（hr.version 無原生狀態機，以自訂欄位實現）
    approval_state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("pending", "待審核"),
            ("approved", "已核准"),
            ("rejected", "已駁回"),
        ],
        string="審核狀態",
        default="draft",
        tracking=True,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="核准人",
        readonly=True,
    )
    approval_date = fields.Datetime(
        string="核准日期",
        readonly=True,
    )
    rejection_reason = fields.Text(
        string="駁回原因",
        readonly=True,
    )
    no_seniority = fields.Boolean(
        string="不計年資",
        default=False,
        help="勾選表示此版本期間不計入服務年資（如留停期間）",
    )

    @api.depends("wage")
    def _compute_hour_salary(self):
        for version in self:
            if version.wage and version.wage > 0:
                version.hour_salary = round(version.wage / 30 / 8, 2)
                version.hour_leave_salary = round(version.wage / 30 / 8, 2)
            else:
                version.hour_salary = 0.0
                version.hour_leave_salary = 0.0

    # PR-015：狀態轉換方法

    def action_submit_for_approval(self):
        """提交版本審核"""
        for version in self:
            if version.approval_state != "draft":
                raise ValidationError("只有草稿版本才能提交審核！")
            version.write({"approval_state": "pending"})
            version.message_post(
                body="版本已提交審核，等待主管核准。",
                subtype_xmlid="mail.mt_note",
            )

    # PR-016/016b：審核工作流

    def action_approve(self):
        """主管核准版本"""
        for version in self:
            if version.approval_state != "pending":
                raise ValidationError("只有待審核的版本才能核准！")
            version.write({
                "approval_state": "approved",
                "approver_id": self.env.uid,
                "approval_date": fields.Datetime.now(),
                "rejection_reason": False,
            })
            version.message_post(
                body=f"版本已由 {self.env.user.name} 核准。",
                subtype_xmlid="mail.mt_note",
            )

    def action_reject(self, reason=""):
        """主管駁回版本"""
        for version in self:
            if version.approval_state != "pending":
                raise ValidationError("只有待審核的版本才能駁回！")
            version.write({
                "approval_state": "rejected",
                "rejection_reason": reason,
            })
            body = "版本已駁回。"
            if reason:
                body += f"<br/>駁回原因：{reason}"
            version.message_post(
                body=body,
                subtype_xmlid="mail.mt_note",
            )
