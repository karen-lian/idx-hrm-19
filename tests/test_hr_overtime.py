from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrOvertimeSetting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setting = cls.env["hr.overtime.setting"].create(
            {"name": "測試設定", "monthly_limit_hours": 46.0, "daily_limit_hours": 4.0}
        )
        cls.ot_weekday = cls.env["hr.overtime.type"].create(
            {"setting_id": cls.setting.id, "name": "平日加班", "day_type": "weekday"}
        )
        cls.env["hr.overtime.type.rule"].create(
            [
                {"overtime_type_id": cls.ot_weekday.id, "hour_from": 0, "hour_to": 2,
                 "rate": round(4 / 3, 4), "is_tax_free": False},
                {"overtime_type_id": cls.ot_weekday.id, "hour_from": 2, "hour_to": 4,
                 "rate": round(5 / 3, 4), "is_tax_free": False},
            ]
        )
        # 例假日加班（勞基法 §36：前 8 小時免稅，第 9-10 小時 2 倍應稅）
        cls.ot_mandatory = cls.env["hr.overtime.type"].create(
            {"setting_id": cls.setting.id, "name": "例假日加班", "day_type": "mandatory_rest"}
        )
        cls.env["hr.overtime.type.rule"].create(
            [
                {"overtime_type_id": cls.ot_mandatory.id, "hour_from": 0, "hour_to": 8,
                 "rate": 1.0, "is_tax_free": True},
                {"overtime_type_id": cls.ot_mandatory.id, "hour_from": 8, "hour_to": 10,
                 "rate": 2.0, "is_tax_free": False},
            ]
        )

    def test_weekday_overtime_rate_first_2h(self):
        """PR-005: 平日前 2 小時費率 4/3。"""
        rules = self.ot_weekday.rule_ids.filtered(lambda r: r.hour_from == 0)
        self.assertAlmostEqual(rules.rate, 4 / 3, places=4)

    def test_weekday_overtime_rate_next_2h(self):
        """PR-005: 平日第 3-4 小時費率 5/3。"""
        rules = self.ot_weekday.rule_ids.filtered(lambda r: r.hour_from == 2)
        self.assertAlmostEqual(rules.rate, 5 / 3, places=4)

    def test_mandatory_rest_tax_free(self):
        """PR-005: 例假日前 8 小時免稅。"""
        rules = self.ot_mandatory.rule_ids.filtered(lambda r: r.is_tax_free)
        self.assertTrue(rules)
        self.assertEqual(rules.hour_to, 8)

    def test_mandatory_rest_taxable(self):
        """PR-005: 例假日第 9-10 小時應稅 2 倍。"""
        rules = self.ot_mandatory.rule_ids.filtered(lambda r: not r.is_tax_free)
        self.assertAlmostEqual(rules.rate, 2.0)

    def test_hour_range_reverse_rejected(self):
        """PR-005: hour_from >= hour_to 應被拒絕。"""
        with self.assertRaises(ValidationError):
            self.env["hr.overtime.type.rule"].create(
                {"overtime_type_id": self.ot_weekday.id,
                 "hour_from": 5, "hour_to": 3, "rate": 1.5}
            )

    def test_rate_precision(self):
        """PR-005: 費率計算精度至小數第 4 位。"""
        rule = self.ot_weekday.rule_ids.filtered(lambda r: r.hour_from == 0)
        self.assertAlmostEqual(rule.rate, 1.3333, places=4)

    def test_leave_conversion_ratio_default(self):
        """PR-005: 補休換算比例預設值 1.0。"""
        self.assertAlmostEqual(self.ot_weekday.leave_conversion_ratio, 1.0)

    def test_monthly_limit_default(self):
        """PR-005: 每月加班上限預設 46 小時（勞基法 §32）。"""
        self.assertAlmostEqual(self.setting.monthly_limit_hours, 46.0)
