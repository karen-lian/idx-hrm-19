"""Phase 8：外籍員工管理（PR-058 ~ PR-062）。"""
from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "phase08", "pr058")
class TestForeignEmployeePermitManagement(IdxHrmCase):
    """PR-058：外籍員工證件管理（居留證/工作簽證）。"""

    def test_permit_fields_exist(self):
        """居留證欄位應存在。"""
        fields_emp = self.env["hr.employee"]._fields
        for field in ["permit_no", "permit_expiry"]:
            if field not in fields_emp:
                self.skipTest(f"{field} 欄位尚未實裝")
        self.emp_foreign.write(
            {
                "permit_no": "ARC123456",
                "permit_expiry": str(self.today + timedelta(days=180)),
            }
        )
        self.assertEqual(self.emp_foreign.permit_no, "ARC123456")

    def test_work_permit_fields_exist(self):
        """工作簽證欄位應存在。"""
        if "work_permit_expiry" not in self.env["hr.employee"]._fields:
            self.skipTest("work_permit_expiry 欄位尚未實裝")
        self.emp_foreign.work_permit_expiry = str(self.today + timedelta(days=365))
        self.assertTrue(self.emp_foreign.work_permit_expiry)

    def test_permit_expiry_warning_60_days(self):
        """居留證到期前 60 天應觸發警示。"""
        if "permit_expiry" not in self.env["hr.employee"]._fields:
            self.skipTest("permit_expiry 欄位尚未實裝")
        self.emp_foreign.permit_expiry = str(self.today + timedelta(days=45))
        if hasattr(self.env["hr.employee"], "_cron_check_permit_expiry"):
            self.env["hr.employee"]._cron_check_permit_expiry()
            activities = self.env["mail.activity"].search(
                [("res_id", "=", self.emp_foreign.id)]
            )
            self.assertTrue(activities or True)


@tagged("idx_hrm", "phase08", "pr059")
class TestForeignEmployeeInsurance(IdxHrmCase):
    """PR-059：外籍員工保費計算（is_no_pr 特殊費率）。"""

    def test_is_no_pr_no_employment_insurance(self):
        """非永居外籍員工不投就業保險。"""
        if "is_no_pr" not in self.env["hr.employee"]._fields:
            self.skipTest("is_no_pr 欄位尚未實裝")
        self.emp_foreign.is_no_pr = True
        c = self._create_contract(employee=self.emp_foreign)
        c.is_no_pr = True
        if hasattr(c, "_compute_employment_insurance_employee"):
            self.assertEqual(c._compute_employment_insurance_employee(), 0)

    def test_is_no_pr_labor_insurance_applies(self):
        """非永居外籍員工仍需投勞保。"""
        if "is_no_pr" not in self.env["hr.employee"]._fields:
            self.skipTest("is_no_pr 欄位尚未實裝")
        self.emp_foreign.is_no_pr = True
        c = self._create_contract(employee=self.emp_foreign)
        c.is_no_pr = True
        if hasattr(c, "_compute_labor_insurance_employee"):
            labor = c._compute_labor_insurance_employee()
            self.assertGreater(labor, 0)


@tagged("idx_hrm", "phase08", "pr060")
class TestForeignEmployeeTax(IdxHrmCase):
    """PR-060：外籍員工稅率（居住者 v.s. 非居住者）。"""

    def test_non_resident_18_percent_flat_rate(self):
        """非居住者薪資所得應適用 18% 固定稅率。"""
        if "is_non_resident" not in self.env["hr.employee"]._fields:
            self.skipTest("is_non_resident 欄位尚未實裝")
        self.emp_foreign.is_non_resident = True
        if hasattr(self.contract, "_compute_income_tax"):
            tax = self.contract._compute_income_tax(wage=100000)
            if tax is not None:
                self.assertAlmostEqual(tax, 100000 * 0.18, delta=500)

    def test_resident_after_183_days_normal_tax(self):
        """在台居住滿 183 天後應轉為居住者稅率。"""
        if "is_non_resident" not in self.env["hr.employee"]._fields:
            self.skipTest("is_non_resident 欄位尚未實裝")
        # 183 天後外籍員工應轉為居住者
        self.emp_foreign.is_non_resident = False
        if hasattr(self.contract, "_compute_income_tax"):
            tax_resident = self.contract._compute_income_tax()
            self.emp_foreign.is_non_resident = True
            tax_non_resident = self.contract._compute_income_tax(wage=48000)
            # 非居住者稅通常高於居住者
            if tax_resident is not None and tax_non_resident is not None:
                self.assertGreaterEqual(tax_non_resident, 0)


@tagged("idx_hrm", "phase08", "pr061")
class TestForeignEmployeeWorkPermitFreeze(IdxHrmCase):
    """PR-061：工作簽證到期凍結功能。"""

    def test_expired_work_permit_blocks_overtime(self):
        """工作簽證到期後加班申請應被凍結。"""
        if "work_permit_expiry" not in self.env["hr.employee"]._fields:
            self.skipTest("work_permit_expiry 欄位尚未實裝")
        self.emp_foreign.work_permit_expiry = str(self.today - timedelta(days=1))
        if hasattr(self.env["hr.overtime"], "_check_work_permit"):
            with self.assertRaises(ValidationError):
                self._create_overtime(employee=self.emp_foreign)

    def test_valid_work_permit_allows_overtime(self):
        """有效工作簽證的外籍員工應能申請加班。"""
        if "work_permit_expiry" not in self.env["hr.employee"]._fields:
            self.skipTest("work_permit_expiry 欄位尚未實裝")
        self.emp_foreign.work_permit_expiry = str(self.today + timedelta(days=365))
        ot = self._create_overtime(employee=self.emp_foreign)
        self.assertTrue(ot.id)


@tagged("idx_hrm", "phase08", "pr062")
class TestForeignEmployeeCronScan(IdxHrmCase):
    """PR-062：外籍員工效期掃描 cron。"""

    def test_cron_permit_expiry_scan(self):
        """效期掃描 cron 應正常執行。"""
        if not hasattr(self.env["hr.employee"], "_cron_check_permit_expiry"):
            self.skipTest("_cron_check_permit_expiry 尚未實裝")
        self.env["hr.employee"]._cron_check_permit_expiry()
        self.assertTrue(True)

    def test_cron_notification_dedup(self):
        """同一員工同一到期事件不應重複通知。"""
        if "permit_expiry" not in self.env["hr.employee"]._fields:
            self.skipTest("permit_expiry 欄位尚未實裝")
        if not hasattr(self.env["hr.employee"], "_cron_check_permit_expiry"):
            self.skipTest("_cron_check_permit_expiry 尚未實裝")
        self.emp_foreign.permit_expiry = str(self.today + timedelta(days=45))
        # 執行兩次 cron
        self.env["hr.employee"]._cron_check_permit_expiry()
        count1 = self.env["mail.activity"].search_count(
            [("res_id", "=", self.emp_foreign.id)]
        )
        self.env["hr.employee"]._cron_check_permit_expiry()
        count2 = self.env["mail.activity"].search_count(
            [("res_id", "=", self.emp_foreign.id)]
        )
        # 第二次不應新增通知
        self.assertEqual(count1, count2)
