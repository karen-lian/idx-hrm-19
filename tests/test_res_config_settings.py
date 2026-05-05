from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestResConfigSettings(TransactionCase):

    def _create_settings(self, vals=None):
        return self.env["res.config.settings"].create(vals or {})

    def test_save_and_load_labor_min_salary(self):
        """PR-002: 寫入後讀取薪資設定值一致。"""
        settings = self._create_settings({"labor_min_salary": 27470})
        settings.execute()
        new_settings = self._create_settings()
        self.assertEqual(new_settings.labor_min_salary, 27470)

    def test_pension_employer_rate_default(self):
        """PR-002: 勞退雇主提撥率預設值 6%。"""
        settings = self._create_settings()
        self.assertAlmostEqual(settings.pension_employer_rate, 6.0)

    def test_rate_boundary_zero(self):
        """PR-002: 費率 0% 合法。"""
        settings = self._create_settings({"labor_accident_rate": 0.0})
        settings._check_rates()  # 不應拋出

    def test_rate_boundary_hundred(self):
        """PR-002: 費率 100% 合法。"""
        settings = self._create_settings({"labor_accident_rate": 100.0})
        settings._check_rates()

    def test_rate_negative_rejected(self):
        """PR-002: 負費率應被拒絕。"""
        settings = self._create_settings({"labor_accident_rate": -1.0})
        with self.assertRaises(ValidationError):
            settings._check_rates()

    def test_rate_over_hundred_rejected(self):
        """PR-002: 費率 > 100% 應被拒絕。"""
        settings = self._create_settings({"health_insurance_rate": 101.0})
        with self.assertRaises(ValidationError):
            settings._check_rates()

    def test_min_salary_negative_rejected(self):
        """PR-002: 負最低投保薪資應被拒絕。"""
        settings = self._create_settings({"labor_min_salary": -1.0})
        with self.assertRaises(ValidationError):
            settings._check_min_salary()

    def test_resident_tax_method_default(self):
        """PR-002: 居住者扣繳方式預設為稅額表。"""
        settings = self._create_settings()
        self.assertEqual(settings.resident_tax_method, "table")
