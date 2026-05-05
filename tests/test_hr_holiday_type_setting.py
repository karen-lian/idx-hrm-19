from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrHolidayTypeSetting(TransactionCase):

    def _create(self, vals=None):
        defaults = {"name": "測試假別", "pay_ratio": 1.0}
        if vals:
            defaults.update(vals)
        return self.env["hr.holiday.type.setting"].create(defaults)

    def test_crud(self):
        """PR-009: CRUD 操作正常。"""
        rec = self._create({"name": "事假", "pay_ratio": 0.0, "annual_quota_days": 14})
        self.assertEqual(rec.pay_ratio, 0.0)
        rec.write({"annual_quota_days": 30})
        self.assertEqual(rec.annual_quota_days, 30)
        rec.unlink()

    def test_default_pay_ratio(self):
        """PR-009: 給薪比例預設值 1.0（全薪）。"""
        rec = self._create()
        self.assertAlmostEqual(rec.pay_ratio, 1.0)

    def test_pay_ratio_out_of_range_rejected(self):
        """PR-009: 給薪比例超過 1 應被拒絕。"""
        with self.assertRaises(Exception):
            self.env.cr.execute(
                "INSERT INTO hr_holiday_type_setting(name, pay_ratio, active, sequence) "
                "VALUES ('壞資料', 1.5, true, 10)"
            )

    def test_pay_ratio_negative_rejected(self):
        """PR-009: 負給薪比例應被拒絕。"""
        with self.assertRaises(Exception):
            self.env.cr.execute(
                "INSERT INTO hr_holiday_type_setting(name, pay_ratio, active, sequence) "
                "VALUES ('壞資料', -0.1, true, 10)"
            )

    def test_annual_quota_non_negative(self):
        """PR-009: 年度額度不得為負數（SQL constraint）。"""
        with self.assertRaises(Exception):
            self.env.cr.execute(
                "INSERT INTO hr_holiday_type_setting"
                "(name, pay_ratio, annual_quota_days, active, sequence) "
                "VALUES ('壞資料', 1.0, -1, true, 10)"
            )

    def test_empty_payslip_code_rejected(self):
        """PR-009: 空薪資規則代號應被拒絕。"""
        rec = self._create({"payslip_rule_code": "  "})
        with self.assertRaises(ValidationError):
            rec._check_payslip_rule_code()

    def test_allow_carry_over_default(self):
        """PR-009: 預設不允許遞延。"""
        rec = self._create()
        self.assertFalse(rec.allow_carry_over)
