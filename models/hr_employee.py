from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # PR-010：員工基本資料擴充欄位

    employee_number = fields.Char(
        string="員工編號",
        copy=False,
        tracking=True,
    )
    no_resident = fields.Boolean(
        string="非臺灣居住者",
        default=False,
        help="勾選表示非中華民國居住者，適用非居住者扣繳稅率",
    )
    substitute_id = fields.Many2one(
        "hr.employee",
        string="職務代理人",
        domain="[('id', '!=', id)]",
    )
    overtime_manager_id = fields.Many2one(
        "hr.employee",
        string="加班審核主管",
    )
    is_no_punch = fields.Boolean(
        string="免打卡",
        default=False,
        help="勾選後不參與出勤統計",
    )
    conversion_date = fields.Date(
        string="轉正式日期",
        help="試用期員工轉為正式員工的日期",
    )
    job_tenure = fields.Float(
        string="服務年資（年）",
        digits=(6, 3),
        compute="_compute_job_tenure",
        store=True,
        help="以合約起算，排除留停與不計年資假單後的年資",
    )
    is_distribute = fields.Boolean(
        string="薪資分攤",
        default=False,
        help="勾選表示薪資費用分攤至多個成本中心",
    )

    _sql_constraints = [
        (
            "employee_number_uniq",
            "UNIQUE(employee_number)",
            "員工編號不可重複！",
        ),
    ]

    @api.depends(
        "version_ids.contract_date_start",
        "version_ids.is_current",
        "version_ids.is_past",
        "version_ids.no_seniority",
    )
    def _compute_job_tenure(self):
        today = fields.Date.today()
        for emp in self:
            # 取所有有合約起始日的版本（含現行與歷史）
            versions = emp.version_ids.filtered(
                lambda v: v.contract_date_start
            )
            if not versions:
                emp.job_tenure = 0.0
                continue

            earliest = min(versions.mapped("contract_date_start"))
            total_days = (today - earliest).days

            # 扣除 no_seniority 假單天數
            no_sen_leaves = self.env["hr.leave.allocation"].search(
                [
                    ("employee_id", "=", emp.id),
                    ("holiday_status_id.no_seniority", "=", True),
                    ("state", "=", "validate"),
                ]
            )
            deduct_days = sum(
                leave.number_of_days for leave in no_sen_leaves
            )

            # 扣除留停期間（change_reason == 'furlough' 且已結束的版本）
            furlough_versions = emp.version_ids.filtered(
                lambda v: v.change_reason == "furlough"
                and v.is_past
                and v.contract_date_start
                and v.contract_date_end
            )
            for fv in furlough_versions:
                deduct_days += (fv.contract_date_end - fv.contract_date_start).days

            net_days = max(total_days - deduct_days, 0)
            emp.job_tenure = round(net_days / 365.0, 3)

    @api.constrains("substitute_id")
    def _check_substitute_not_self(self):
        for emp in self:
            if emp.substitute_id == emp:
                raise ValidationError("職務代理人不能是員工本人！")
