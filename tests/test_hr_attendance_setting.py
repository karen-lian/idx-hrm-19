from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHrAttendanceSetting(TransactionCase):

    def test_defaults(self):
        """PR-003: 新建出勤設定預設值正確。"""
        setting = self.env["hr.attendance.setting"].create({"name": "測試"})
        self.assertFalse(setting.enable_perfect_attendance)
        self.assertEqual(setting.grace_minutes, 0)
        self.assertFalse(setting.enable_late_deduction)

    def test_crud(self):
        """PR-003: CRUD 操作正常。"""
        setting = self.env["hr.attendance.setting"].create(
            {
                "name": "全勤測試",
                "enable_perfect_attendance": True,
                "perfect_attendance_amount": 1000.0,
                "grace_minutes": 5,
            }
        )
        self.assertEqual(setting.perfect_attendance_amount, 1000.0)
        setting.write({"grace_minutes": 10})
        self.assertEqual(setting.grace_minutes, 10)
        setting.unlink()
        self.assertFalse(self.env["hr.attendance.setting"].search([("name", "=", "全勤測試")]))

    def test_negative_amount_rejected(self):
        """PR-003: 負金額由 SQL constraint 拒絕（TransactionCase 需繞過 ORM 測試）。"""
        with self.assertRaises(Exception):
            self.env.cr.execute(
                "INSERT INTO hr_attendance_setting(name, perfect_attendance_amount, active) "
                "VALUES ('壞資料', -100, true)"
            )

    def test_leave_limit_negative_rejected(self):
        """PR-003: 負請假時數上限由 constrains 拒絕。"""
        setting = self.env["hr.attendance.setting"].create({"name": "測試"})
        with self.assertRaises(ValidationError):
            setting.write({"perfect_attendance_leave_limit": -1.0})
            setting._check_leave_limit()
