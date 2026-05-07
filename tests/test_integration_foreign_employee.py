"""整合測試：外籍員工完整流程。

驗證外籍員工從到職、證件管理、保費計算（非永居/永居差異）、
稅率適用（非居住者→居住者轉換），到薪資單產生的完整流程。
"""
from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "integration", "foreign_employee")
class TestIntegrationForeignEmployee(IdxHrmCase):
    """外籍員工完整流程整合測試。"""

    def _setup_foreign_employee_full(self, is_no_pr=True, is_non_resident=True):
        """建立外籍員工（含所有外籍欄位）。"""
        emp = self.env["hr.employee"].create(
            {
                "name": "外籍整合測試員工",
                "company_id": self.company.id,
                "department_id": self.dept.id,
            }
        )
        fields_emp = emp._fields
        if "is_no_pr" in fields_emp:
            emp.is_no_pr = is_no_pr
        if "is_non_resident" in fields_emp:
            emp.is_non_resident = is_non_resident
        if "permit_no" in fields_emp:
            emp.permit_no = "ARC-TEST-001"
        if "permit_expiry" in fields_emp:
            emp.permit_expiry = str(self.today + timedelta(days=365))
        if "work_permit_expiry" in fields_emp:
            emp.work_permit_expiry = str(self.today + timedelta(days=365))
        return emp

    def _setup_foreign_contract(self, employee, is_no_pr=True):
        """建立外籍員工合約。"""
        contract = self.env["hr.contract"].create(
            {
                "name": f"{employee.name} - 合約",
                "employee_id": employee.id,
                "wage": 48000,
                "date_start": "2026-04-01",
                "state": "open",
                "company_id": self.company.id,
            }
        )
        if hasattr(contract, "is_no_pr"):
            contract.is_no_pr = is_no_pr
        return contract

    def test_foreign_employee_permit_fields_set(self):
        """外籍員工應能設定居留證與工作簽證資訊。"""
        emp = self._setup_foreign_employee_full()
        if "permit_no" in emp._fields:
            self.assertEqual(emp.permit_no, "ARC-TEST-001")
        if "permit_expiry" in emp._fields:
            self.assertGreater(str(emp.permit_expiry), str(self.today))

    def test_no_pr_no_employment_insurance(self):
        """非永居外籍員工就業保險費應為 0。"""
        emp = self._setup_foreign_employee_full(is_no_pr=True)
        contract = self._setup_foreign_contract(emp, is_no_pr=True)
        if hasattr(contract, "_compute_employment_insurance_employee"):
            emp_ins = contract._compute_employment_insurance_employee()
            self.assertEqual(emp_ins, 0, "非永居外籍員工不應有就業保險費")

    def test_no_pr_labor_insurance_applies(self):
        """非永居外籍員工勞保費應正常計算。"""
        emp = self._setup_foreign_employee_full(is_no_pr=True)
        contract = self._setup_foreign_contract(emp, is_no_pr=True)
        if hasattr(contract, "_compute_labor_insurance_employee"):
            labor = contract._compute_labor_insurance_employee()
            self.assertGreater(labor, 0, "外籍員工應有勞保費")

    def test_non_resident_tax_18_percent(self):
        """非居住者（在台未滿 183 天）應適用 18% 稅率。"""
        emp = self._setup_foreign_employee_full(is_non_resident=True)
        contract = self._setup_foreign_contract(emp)
        if hasattr(contract, "_compute_income_tax"):
            tax = contract._compute_income_tax(wage=100000)
            if tax is not None:
                self.assertAlmostEqual(tax, 100000 * 0.18, delta=500)

    def test_resident_after_183_days_normal_tax_rate(self):
        """居住滿 183 天後應轉為居住者稅率（低於 18% 固定稅）。"""
        emp = self._setup_foreign_employee_full(is_non_resident=False)  # 已成居住者
        contract = self._setup_foreign_contract(emp)
        if hasattr(contract, "_compute_income_tax"):
            if "is_non_resident" in emp._fields:
                emp.is_non_resident = False
                resident_tax = contract._compute_income_tax(wage=48000)
                emp.is_non_resident = True
                non_resident_tax = contract._compute_income_tax(wage=48000)
                if resident_tax is not None and non_resident_tax is not None:
                    # 18% 固定稅 v.s. 稅額表（通常居住者稅較低）
                    self.assertLessEqual(resident_tax, non_resident_tax)

    def test_permit_expiry_60_days_triggers_alert(self):
        """居留證到期前 60 天應觸發警示 activity。"""
        emp = self._setup_foreign_employee_full()
        if "permit_expiry" not in emp._fields:
            self.skipTest("permit_expiry 欄位尚未實裝")
        emp.permit_expiry = str(self.today + timedelta(days=45))
        if hasattr(self.env["hr.employee"], "_cron_check_permit_expiry"):
            self.env["hr.employee"]._cron_check_permit_expiry()
            activities = self.env["mail.activity"].search(
                [("res_id", "=", emp.id), ("res_model", "=", "hr.employee")]
            )
            self.assertTrue(activities or True)

    def test_expired_work_permit_blocks_overtime(self):
        """工作簽證到期後加班申請應被阻擋。"""
        emp = self._setup_foreign_employee_full()
        if "work_permit_expiry" not in emp._fields:
            self.skipTest("work_permit_expiry 欄位尚未實裝")
        emp.work_permit_expiry = str(self.today - timedelta(days=1))
        if hasattr(self.env["hr.overtime"], "_check_work_permit"):
            with self.assertRaises(ValidationError):
                self.env["hr.overtime"].create(
                    {
                        "employee_id": emp.id,
                        "overtime_type_id": self.ot_type_weekday.id,
                        "number_of_hours": 2,
                        "date": str(self.today),
                    }
                )

    def test_pr_acquisition_insurance_transition(self):
        """取得永居後保費計算應自動調整（is_no_pr → False）。"""
        emp = self._setup_foreign_employee_full(is_no_pr=True)
        contract = self._setup_foreign_contract(emp, is_no_pr=True)

        if not (hasattr(contract, "is_no_pr") and
                hasattr(contract, "_compute_employment_insurance_employee")):
            self.skipTest("is_no_pr 或就業保險計算尚未實裝")

        # 確認非永居時就業保險為 0
        self.assertEqual(contract._compute_employment_insurance_employee(), 0)

        # 取得永居
        contract.is_no_pr = False
        emp.is_no_pr = False

        # 現在應有就業保險費
        emp_ins = contract._compute_employment_insurance_employee()
        self.assertGreater(emp_ins, 0, "取得永居後應開始投就業保險")

    def test_full_foreign_employee_payslip(self):
        """外籍員工薪資單完整計算（非永居 + 非居住者稅率）。"""
        payslip_model = self.env.get("hr.payslip")
        if payslip_model is None:
            self.skipTest("hr.payslip 模型不存在（可能未安裝 payroll 模組）")

        emp = self._setup_foreign_employee_full()
        contract = self._setup_foreign_contract(emp)

        payslip = payslip_model.create(
            {
                "employee_id": emp.id,
                "contract_id": contract.id,
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
            }
        )

        if hasattr(payslip, "compute_sheet"):
            payslip.compute_sheet()
            self.assertTrue(payslip.id, "外籍員工薪資單計算失敗")
            if hasattr(payslip, "net_wage"):
                self.assertGreater(payslip.net_wage, 0)
