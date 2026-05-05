from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrAnnualLeave(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["hr.annual.leave"].search([]).unlink()
        # 勞基法 §38 標準特休天數
        cls.env["hr.annual.leave"].create(
            [
                {"tenure_from": 0.5, "tenure_to": 1.0, "leave_days": 3},
                {"tenure_from": 1.0, "tenure_to": 2.0, "leave_days": 7},
                {"tenure_from": 2.0, "tenure_to": 3.0, "leave_days": 10},
                {"tenure_from": 3.0, "tenure_to": 5.0, "leave_days": 14},
                {"tenure_from": 5.0, "tenure_to": 10.0, "leave_days": 15},
            ]
        )
        # 10 年以上遞增規則（每年 +1，上限 30 天，基準 15 天）
        cls.env["hr.annual.leave"].create(
            {
                "tenure_from": 10.0,
                "tenure_to": 999.0,
                "leave_days": 16,
                "is_incremental": True,
                "incremental_base_tenure": 10.0,
                "incremental_base_days": 15.0,
                "incremental_days_per_year": 1.0,
                "incremental_max_days": 30.0,
            }
        )

    def test_6_months_to_1_year(self):
        """PR-008: 6 個月~1 年 → 3 天。"""
        model = self.env["hr.annual.leave"]
        self.assertEqual(model.get_leave_days(0.6), 3)

    def test_1_to_2_years(self):
        """PR-008: 1~2 年 → 7 天。"""
        model = self.env["hr.annual.leave"]
        self.assertEqual(model.get_leave_days(1), 7)

    def test_5_to_10_years(self):
        """PR-008: 5~10 年 → 15 天。"""
        model = self.env["hr.annual.leave"]
        self.assertEqual(model.get_leave_days(7), 15)

    def test_10_years_incremental(self):
        """PR-008: 10 年以上遞增規則（每年 +1）。"""
        model = self.env["hr.annual.leave"]
        self.assertEqual(model.get_leave_days(10), 15)   # 基準 15
        self.assertEqual(model.get_leave_days(11), 16)
        self.assertEqual(model.get_leave_days(12), 17)

    def test_max_30_days(self):
        """PR-008: 遞增上限 30 天（15 年 = 15+5=20，25 年 = 30 封頂）。"""
        model = self.env["hr.annual.leave"]
        self.assertEqual(model.get_leave_days(25), 30)
        self.assertEqual(model.get_leave_days(50), 30)

    def test_tenure_before_6_months(self):
        """PR-008: 未滿 6 個月無特休。"""
        model = self.env["hr.annual.leave"]
        self.assertEqual(model.get_leave_days(0.3), 0.0)

    def test_overlap_rejected(self):
        """PR-008: 年資區間重疊應被拒絕。"""
        with self.assertRaises(ValidationError):
            self.env["hr.annual.leave"].create(
                {"tenure_from": 0.8, "tenure_to": 1.5, "leave_days": 5}
            )
