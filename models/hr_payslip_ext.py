"""PR-038/042/046：薪資單輔助欄位、非固定薪資、銀行薪轉

設計原則：
hr.payslip 不擴充任何台灣薪資計算欄位（base_wage、勞健保、所得稅等）。
所有薪資計算邏輯都在 hr.salary.rule 的 amount_python_compute 中執行，
產生 hr.payslip.line 明細時即時計算。
這樣不同公司可以選擇不同薪資結構（含/不含勞健保），保持彈性。
"""
from odoo import api, fields, models


class HrPayslip(models.Model):
    """PR-042/046：薪資單輔助欄位（非固定薪資、銀行薪轉）"""
    _inherit = "hr.payslip"

    # PR-042：非固定薪資（年終/績效/分紅獎金等）
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
    """PR-045/046：薪資批次作業擴充（薪轉明細）"""
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
        """PR-046：產生薪轉明細。
        薪轉金額 = 薪資單明細中 net_amount 規則的金額。
        """
        for run in self:
            run.transfer_ids.unlink()
            for slip in run.slip_ids.filtered(lambda s: s.state == "done"):
                # 從薪資單明細讀取「實發金額」
                net_line = slip.line_ids.filtered(
                    lambda l: l.code == "net_amount"
                )
                amount = net_line[:1].total if net_line else 0.0
                self.env["hr.payroll.transfers"].create({
                    "payslip_run_id": run.id,
                    "employee_id": slip.employee_id.id,
                    "payslip_id": slip.id,
                    "transfer_amount": amount,
                })
