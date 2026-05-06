"""PR-047：年度扣繳憑單（hr.income.tax）"""
from odoo import api, fields, models


class HrIncomeTax(models.Model):
    """PR-047：年度扣繳憑單彙總"""
    _name = "hr.income.tax"
    _description = "年度扣繳憑單"
    _order = "roc_year desc, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        index=True,
        ondelete="cascade",
    )
    roc_year = fields.Integer(
        string="民國年",
        required=True,
        help="例如：115 = 西元 2026",
    )
    ad_year = fields.Integer(
        string="西元年",
        compute="_compute_ad_year",
        store=True,
    )
    identification_card = fields.Char(
        string="身分證/居留證號",
        related="employee_id.identification_id",
        store=True,
    )
    employee_number = fields.Char(
        string="員工編號",
        related="employee_id.employee_number",
        store=True,
    )
    total_salary = fields.Float(
        string="全年薪資所得",
        digits=(10, 0),
        compute="_compute_annual_totals",
        store=True,
    )
    total_tax_withheld = fields.Float(
        string="全年扣繳稅額",
        digits=(10, 0),
        compute="_compute_annual_totals",
        store=True,
    )
    total_tax_free_ot = fields.Float(
        string="全年免稅加班費",
        digits=(10, 0),
        compute="_compute_annual_totals",
        store=True,
    )
    no_resident = fields.Boolean(
        string="非居住者",
        related="employee_id.no_resident",
        store=True,
    )
    withholding_code = fields.Char(
        string="扣繳代號",
        default="50",
        help="薪資所得扣繳代號：50",
    )
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("confirmed", "已確認"),
            ("filed", "已申報"),
        ],
        string="狀態",
        default="draft",
    )

    _sql_constraints = [
        (
            "employee_year_uniq",
            "UNIQUE(employee_id, roc_year)",
            "同一員工同年度只能有一張扣繳憑單！",
        ),
    ]

    @api.depends("roc_year")
    def _compute_ad_year(self):
        for rec in self:
            rec.ad_year = rec.roc_year + 1911 if rec.roc_year else 0

    @api.depends("employee_id", "ad_year")
    def _compute_annual_totals(self):
        """彙總全年薪資單資料（從 hr.payslip.line 依薪資規則代碼聚合）。

        對應規則代碼：
        - add_amount       → 應付合計（A，含應稅+免稅+非固定薪資加項）
        - WITHHOLDincome   → 所得稅扣繳
        - OVT_weekdays / OVT_day_off / OVT_regular_holiday / OVT_holiday
                           → 免稅加班費（合計）
        """
        TAX_FREE_OT_CODES = (
            "OVT_weekdays", "OVT_day_off",
            "OVT_regular_holiday", "OVT_holiday",
        )
        for rec in self:
            if not rec.ad_year:
                rec.total_salary = 0.0
                rec.total_tax_withheld = 0.0
                rec.total_tax_free_ot = 0.0
                continue

            year = rec.ad_year
            date_from = f"{year}-01-01"
            date_to = f"{year}-12-31"
            slips = self.env["hr.payslip"].search([
                ("employee_id", "=", rec.employee_id.id),
                ("state", "=", "done"),
                ("date_from", ">=", date_from),
                ("date_to", "<=", date_to),
            ])
            lines = slips.mapped("line_ids")
            rec.total_salary = sum(
                lines.filtered(lambda l: l.code == "add_amount").mapped("total")
            )
            rec.total_tax_withheld = sum(
                lines.filtered(lambda l: l.code == "WITHHOLDincome").mapped("total")
            )
            rec.total_tax_free_ot = sum(
                lines.filtered(lambda l: l.code in TAX_FREE_OT_CODES).mapped("total")
            )

    @api.model
    def batch_generate(self, roc_year):
        """PR-047：批次產生全體員工扣繳憑單。"""
        employees = self.env["hr.employee"].search([
            ("active", "=", True),
        ])
        created = []
        for emp in employees:
            existing = self.search([
                ("employee_id", "=", emp.id),
                ("roc_year", "=", roc_year),
            ])
            if not existing:
                created.append(self.create({
                    "employee_id": emp.id,
                    "roc_year": roc_year,
                }))
        return created

    @api.model
    def get_roc_year(self, ad_year=None):
        """西元年轉民國年工具方法。"""
        if not ad_year:
            ad_year = fields.Date.today().year
        return ad_year - 1911
