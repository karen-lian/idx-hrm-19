"""PR-038~046：薪資計算完整模組

整合 OCA payroll 的 hr.payslip / hr.payslip.run，
加入台灣法規所需的收入/扣款計算、勞健保費、所得稅、銀行薪轉。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrPayrollStructure(models.Model):
    """PR-038：薪資結構（月薪制/時薪制）"""
    _inherit = "hr.payroll.structure"

    structure_type = fields.Selection(
        selection_add=[
            ("monthly_tw", "月薪制（台灣）"),
            ("hourly_tw", "時薪制（台灣）"),
        ],
        string="薪資制度",
    )
    is_tw_structure = fields.Boolean(
        string="台灣法規薪資結構",
        default=False,
    )


class HrPayslip(models.Model):
    """PR-039~045：薪資單收入/扣款/勞健保/所得稅/作業流程擴充"""
    _inherit = "hr.payslip"

    # PR-039：收入項目
    base_wage = fields.Float(
        string="底薪",
        digits=(10, 2),
        compute="_compute_tw_income",
        store=True,
    )
    meal_allowance = fields.Float(
        string="伙食津貼",
        digits=(10, 2),
        default=2400.0,
        help="台灣法規每月最高 2,400 元免稅",
    )
    perfect_attendance_bonus = fields.Float(
        string="全勤獎金",
        digits=(10, 2),
        compute="_compute_tw_income",
        store=True,
    )
    overtime_tax_free = fields.Float(
        string="加班費（免稅）",
        digits=(10, 2),
        compute="_compute_tw_income",
        store=True,
    )
    overtime_taxable = fields.Float(
        string="加班費（應稅）",
        digits=(10, 2),
        compute="_compute_tw_income",
        store=True,
    )
    other_allowance = fields.Float(
        string="其他津貼",
        digits=(10, 2),
        default=0.0,
    )
    gross_income = fields.Float(
        string="應稅薪資合計",
        digits=(10, 2),
        compute="_compute_gross_income",
        store=True,
    )

    # PR-040：扣款項目
    labor_insurance_deduct = fields.Float(
        string="勞保費（員工）",
        digits=(10, 2),
        compute="_compute_tw_deductions",
        store=True,
    )
    health_insurance_deduct = fields.Float(
        string="健保費（員工）",
        digits=(10, 2),
        compute="_compute_tw_deductions",
        store=True,
    )
    dependent_health_insurance_deduct = fields.Float(
        string="眷屬健保費",
        digits=(10, 2),
        compute="_compute_tw_deductions",
        store=True,
    )
    pension_self_contribute = fields.Float(
        string="勞退自提",
        digits=(10, 2),
        default=0.0,
        help="員工自願提繳比例（0~6%）",
    )
    income_tax_deduct = fields.Float(
        string="應扣所得稅",
        digits=(10, 2),
        compute="_compute_tw_deductions",
        store=True,
    )
    late_deduction = fields.Float(
        string="遲到/早退扣款",
        digits=(10, 2),
        compute="_compute_tw_deductions",
        store=True,
    )
    total_deduction = fields.Float(
        string="扣款合計",
        digits=(10, 2),
        compute="_compute_total_deduction",
        store=True,
    )
    net_salary = fields.Float(
        string="實領薪資",
        digits=(10, 2),
        compute="_compute_net_salary",
        store=True,
    )

    # PR-042：非固定薪資
    unfrequented_ids = fields.One2many(
        "hr.payslip.unfrequented",
        "payslip_id",
        string="非固定薪資項目",
    )

    # PR-046：銀行薪轉
    bank_account_id = fields.Many2one(
        "res.partner.bank",
        string="薪轉帳號",
        related="employee_id.bank_account_id",
        readonly=True,
    )
    transfer_amount = fields.Float(
        string="薪轉金額",
        digits=(10, 2),
        compute="_compute_net_salary",
        store=True,
    )

    @api.depends(
        "contract_id.wage",
        "employee_id.dependents_information_ids.is_active_insured",
        "date_from", "date_to",
    )
    def _compute_tw_income(self):
        """PR-039：計算底薪、全勤獎金、加班費。"""
        for slip in self:
            contract = slip.contract_id
            slip.base_wage = contract.wage if contract else 0.0

            # 全勤獎金：查詢對應月份 hr.attendance.month
            if contract and slip.date_from:
                month_rec = self.env["hr.attendance.month"].search([
                    ("employee_id", "=", slip.employee_id.id),
                    ("year", "=", slip.date_from.year),
                    ("month", "=", slip.date_from.month),
                ], limit=1)
                slip.perfect_attendance_bonus = (
                    month_rec.perfect_attendance_bonus if month_rec else 0.0
                )
            else:
                slip.perfect_attendance_bonus = 0.0

            # 加班費：查詢對應月份已核准的加班申請
            if slip.date_from:
                ot_requests = self.env["hr.overtime.request"].search([
                    ("employee_id", "=", slip.employee_id.id),
                    ("state", "=", "approved"),
                    ("overtime_date", ">=", slip.date_from),
                    ("overtime_date", "<=", slip.date_to),
                ])
                slip.overtime_tax_free = sum(ot_requests.mapped("tax_free_amount"))
                slip.overtime_taxable = sum(ot_requests.mapped("taxable_amount"))
            else:
                slip.overtime_tax_free = 0.0
                slip.overtime_taxable = 0.0

    @api.depends(
        "base_wage", "meal_allowance", "perfect_attendance_bonus",
        "overtime_taxable", "other_allowance",
    )
    def _compute_gross_income(self):
        for slip in self:
            slip.gross_income = (
                slip.base_wage
                + slip.meal_allowance
                + slip.perfect_attendance_bonus
                + slip.overtime_taxable
                + slip.other_allowance
            )

    @api.depends(
        "contract_id.labor_insurance_premium_employee",
        "contract_id.health_insurance_premium_employee",
        "contract_id.dependent_health_insurance_total",
        "gross_income",
        "employee_id.no_resident",
        "date_from",
    )
    def _compute_tw_deductions(self):
        """PR-040/043/044：計算勞健保、所得稅、遲到扣款。"""
        for slip in self:
            contract = slip.contract_id
            if not contract:
                slip.labor_insurance_deduct = 0.0
                slip.health_insurance_deduct = 0.0
                slip.dependent_health_insurance_deduct = 0.0
                slip.income_tax_deduct = 0.0
                slip.late_deduction = 0.0
                continue

            # PR-043：勞健保費（從合約讀取已計算的費率）
            slip.labor_insurance_deduct = contract.labor_insurance_premium_employee
            slip.health_insurance_deduct = contract.health_insurance_premium_employee
            slip.dependent_health_insurance_deduct = (
                contract.dependent_health_insurance_total
            )

            # PR-044：所得稅計算
            slip.income_tax_deduct = slip._compute_income_tax()

            # 遲到扣款：從月度結算讀取
            if slip.date_from:
                month_rec = self.env["hr.attendance.month"].search([
                    ("employee_id", "=", slip.employee_id.id),
                    ("year", "=", slip.date_from.year),
                    ("month", "=", slip.date_from.month),
                ], limit=1)
                slip.late_deduction = month_rec.deduction_total if month_rec else 0.0
            else:
                slip.late_deduction = 0.0

    def _compute_income_tax(self):
        """PR-044：所得稅計算（居住者稅額表查詢 / 非居住者固定稅率）。"""
        self.ensure_one()
        contract = self.contract_id
        if not contract:
            return 0.0

        gross = self.gross_income + self.overtime_tax_free

        if self.employee_id.no_resident:
            # 非居住者：依全民健保法設定費率
            settings = self.env["res.config.settings"].search([], limit=1)
            rate = (
                settings.non_resident_tax_rate
                if settings and hasattr(settings, "non_resident_tax_rate")
                else 0.18
            )
            return round(gross * rate, 0)

        # 居住者：查扣繳稅額表
        dependents = self.employee_id.active_dependent_count
        tax_record = self.env["hr.income.tax.pivot"].get_tax(
            salary=gross, dependents=dependents
        )
        return tax_record if isinstance(tax_record, (int, float)) else 0.0

    @api.depends(
        "labor_insurance_deduct", "health_insurance_deduct",
        "dependent_health_insurance_deduct", "pension_self_contribute",
        "income_tax_deduct", "late_deduction",
    )
    def _compute_total_deduction(self):
        for slip in self:
            slip.total_deduction = (
                slip.labor_insurance_deduct
                + slip.health_insurance_deduct
                + slip.dependent_health_insurance_deduct
                + slip.pension_self_contribute
                + slip.income_tax_deduct
                + slip.late_deduction
            )

    @api.depends("gross_income", "overtime_tax_free", "total_deduction")
    def _compute_net_salary(self):
        for slip in self:
            slip.net_salary = round(
                slip.gross_income + slip.overtime_tax_free - slip.total_deduction, 0
            )
            slip.transfer_amount = slip.net_salary

    def action_payslip_done(self):
        """PR-045：薪資單完成流程 → 鎖定後不可修改。"""
        for slip in self:
            if slip.state == "done":
                raise ValidationError("薪資單已完成，不可重複確認！")
        return super().action_payslip_done()


class HrPayslipUnfrequented(models.Model):
    """PR-042：非固定薪資記錄（年終/績效獎金）"""
    _name = "hr.payslip.unfrequented"
    _description = "非固定薪資項目"

    payslip_id = fields.Many2one(
        "hr.payslip",
        string="薪資單",
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        related="payslip_id.employee_id",
        store=True,
    )
    name = fields.Char(string="項目名稱", required=True)
    amount = fields.Float(string="金額", digits=(10, 2))
    is_taxable = fields.Boolean(
        string="應稅",
        default=True,
    )
    withholding_code = fields.Char(
        string="扣繳代號",
        help="例如：薪資所得 50、執行業務所得 9A",
    )
    pay_date = fields.Date(string="發放日期")
    note = fields.Text(string="備註")


class HrPayrollTransfers(models.Model):
    """PR-046：銀行薪資轉帳明細"""
    _name = "hr.payroll.transfers"
    _description = "銀行薪資轉帳"
    _order = "payslip_run_id, employee_id"

    payslip_run_id = fields.Many2one(
        "hr.payslip.run",
        string="薪資批次",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
    )
    employee_number = fields.Char(
        string="員工編號",
        related="employee_id.employee_number",
        store=True,
    )
    bank_code = fields.Char(
        string="銀行代號",
        compute="_compute_bank_info",
        store=True,
    )
    account_number = fields.Char(
        string="帳號",
        compute="_compute_bank_info",
        store=True,
    )
    transfer_amount = fields.Float(
        string="轉帳金額",
        digits=(10, 2),
    )
    payslip_id = fields.Many2one(
        "hr.payslip",
        string="薪資單",
    )

    @api.depends("employee_id.bank_account_id")
    def _compute_bank_info(self):
        for rec in self:
            bank = rec.employee_id.bank_account_id
            if bank:
                rec.bank_code = bank.bank_id.bic or ""
                rec.account_number = bank.acc_number or ""
            else:
                rec.bank_code = ""
                rec.account_number = ""


class HrPayslipRun(models.Model):
    """PR-045：薪資批次作業擴充"""
    _inherit = "hr.payslip.run"

    transfer_ids = fields.One2many(
        "hr.payroll.transfers",
        "payslip_run_id",
        string="薪轉明細",
    )
    transfer_count = fields.Integer(
        string="薪轉筆數",
        compute="_compute_transfer_count",
    )

    @api.depends("transfer_ids")
    def _compute_transfer_count(self):
        for run in self:
            run.transfer_count = len(run.transfer_ids)

    def action_generate_transfers(self):
        """PR-046：產生薪轉明細。"""
        for run in self:
            run.transfer_ids.unlink()
            for slip in run.slip_ids.filtered(lambda s: s.state == "done"):
                self.env["hr.payroll.transfers"].create({
                    "payslip_run_id": run.id,
                    "employee_id": slip.employee_id.id,
                    "payslip_id": slip.id,
                    "transfer_amount": slip.transfer_amount,
                })
