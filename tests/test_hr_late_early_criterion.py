from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrLateEarlyCriterion(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env["hr.late.early.criterion"].search([]).unlink()

    def _create(self, minute_from, minute_to, deduction):
        return self.env["hr.late.early.criterion"].create(
            {"minute_from": minute_from, "minute_to": minute_to, "deduction": deduction}
        )

    def test_lookup(self):
        """PR-004: 依分鐘數查詢正確扣款金額。"""
        self._create(1, 10, 50)
        self._create(11, 30, 100)
        model = self.env["hr.late.early.criterion"]
        self.assertEqual(model.get_deduction(5), 50)
        self.assertEqual(model.get_deduction(15), 100)
        self.assertEqual(model.get_deduction(0), 0)   # 無符合區間

    def test_overlap_rejected(self):
        """PR-004: 區間重疊應被拒絕。"""
        self._create(1, 10, 50)
        with self.assertRaises(ValidationError):
            self._create(5, 15, 80)

    def test_reverse_range_rejected(self):
        """PR-004: minute_from > minute_to 應被拒絕。"""
        with self.assertRaises(ValidationError):
            self._create(10, 5, 50)

    def test_compute_name(self):
        """PR-004: compute 欄位 name 正確產生。"""
        rec = self._create(1, 10, 50)
        self.assertIn("50", rec.name)
        self.assertIn("1", rec.name)
