from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrIncomeTaxPivot(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["hr.income.tax.pivot"].create(
            [
                {"year": 2026, "salary_from": 0, "salary_to": 40000,
                 "dependents": 0, "tax_amount": 1500},
                {"year": 2026, "salary_from": 0, "salary_to": 40000,
                 "dependents": 1, "tax_amount": 800},
                {"year": 2026, "salary_from": 40001, "salary_to": 50000,
                 "dependents": 0, "tax_amount": 3000},
                {"year": 2026, "salary_from": 40001, "salary_to": 50000,
                 "dependents": 1, "tax_amount": 2000},
            ]
        )

    def test_lookup_by_salary_and_dependents(self):
        """PR-007: 依薪資與撫養人數查詢稅額。"""
        model = self.env["hr.income.tax.pivot"]
        self.assertEqual(model.get_tax(35000, 0, 2026), 1500)
        self.assertEqual(model.get_tax(35000, 1, 2026), 800)
        self.assertEqual(model.get_tax(50000, 1, 2026), 2000)

    def test_boundary_values(self):
        """PR-007: 邊界值查詢（薪資剛好在區間起迄）。"""
        model = self.env["hr.income.tax.pivot"]
        self.assertEqual(model.get_tax(40000, 0, 2026), 1500)
        self.assertEqual(model.get_tax(40001, 0, 2026), 3000)

    def test_no_match_returns_zero(self):
        """PR-007: 無符合記錄時回傳 0。"""
        model = self.env["hr.income.tax.pivot"]
        self.assertEqual(model.get_tax(100000, 5, 2026), 0.0)

    def test_negative_salary_rejected(self):
        """PR-007: 負薪資起應被拒絕。"""
        with self.assertRaises(ValidationError):
            self.env["hr.income.tax.pivot"].create(
                {"year": 2026, "salary_from": -1, "salary_to": 10000,
                 "dependents": 0, "tax_amount": 0}
            )

    def test_reverse_salary_range_rejected(self):
        """PR-007: salary_from > salary_to 應被拒絕。"""
        with self.assertRaises(ValidationError):
            self.env["hr.income.tax.pivot"].create(
                {"year": 2026, "salary_from": 50000, "salary_to": 10000,
                 "dependents": 0, "tax_amount": 0}
            )

    def test_year_constraint(self):
        """PR-007: 年度 <= 1900 應被拒絕。"""
        with self.assertRaises(ValidationError):
            self.env["hr.income.tax.pivot"].create(
                {"year": 1800, "salary_from": 0, "salary_to": 10000,
                 "dependents": 0, "tax_amount": 0}
            )

    def test_tax_amount_greater_than_zero(self):
        """PR-007: 稅額應大於 0（對有薪資的區間）。"""
        model = self.env["hr.income.tax.pivot"]
        tax = model.get_tax(50000, 1, 2026)
        self.assertGreater(tax, 0)
