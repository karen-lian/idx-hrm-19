from datetime import date, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase


class TestCronUpdateContractState(TransactionCase):
    """測試合約狀態自動更新 cron。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "測試員工 Cron"})

    def test_draft_to_open_when_start_date_reached(self):
        """生效日到達 → draft 合約自動進入 open。"""
        contract = self.env["hr.contract"].create(
            {
                "name": "測試合約",
                "employee_id": self.employee.id,
                "date_start": date.today() - timedelta(days=1),
                "wage": 30000,
                "state": "draft",
            }
        )
        self.env["hr.contract"]._cron_update_contract_state()
        self.assertEqual(contract.state, "open")

    def test_draft_stays_draft_when_not_started(self):
        """生效日未到 → draft 合約不變動。"""
        contract = self.env["hr.contract"].create(
            {
                "name": "測試合約未來",
                "employee_id": self.employee.id,
                "date_start": date.today() + timedelta(days=5),
                "wage": 30000,
                "state": "draft",
            }
        )
        self.env["hr.contract"]._cron_update_contract_state()
        self.assertEqual(contract.state, "draft")

    def test_open_to_close_when_end_date_passed(self):
        """到期日已過 → open 合約自動進入 close。"""
        contract = self.env["hr.contract"].create(
            {
                "name": "測試合約到期",
                "employee_id": self.employee.id,
                "date_start": date.today() - timedelta(days=30),
                "date_end": date.today() - timedelta(days=1),
                "wage": 30000,
                "state": "open",
            }
        )
        self.env["hr.contract"]._cron_update_contract_state()
        self.assertEqual(contract.state, "close")

    def test_open_stays_open_when_not_expired(self):
        """到期日未到 → open 合約不變動。"""
        contract = self.env["hr.contract"].create(
            {
                "name": "測試合約未到期",
                "employee_id": self.employee.id,
                "date_start": date.today() - timedelta(days=30),
                "date_end": date.today() + timedelta(days=30),
                "wage": 30000,
                "state": "open",
            }
        )
        self.env["hr.contract"]._cron_update_contract_state()
        self.assertEqual(contract.state, "open")


class TestCronForgotPunch(TransactionCase):
    """測試忘刷打卡通知 cron。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_normal = cls.env["hr.employee"].create(
            {"name": "一般員工", "is_no_punch": False}
        )
        cls.employee_no_punch = cls.env["hr.employee"].create(
            {"name": "免打卡員工", "is_no_punch": True}
        )

    def test_no_punch_employee_excluded(self):
        """is_no_punch=True 的員工不在忘刷名單中。"""
        # is_no_punch 員工不應被偵測，activity 不應建立
        before_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee_no_punch.id)]
        )
        self.env["hr.attendance"]._cron_send_forgot_punch_notification()
        after_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee_no_punch.id)]
        )
        self.assertEqual(before_count, after_count)

    def test_employee_with_attendance_excluded(self):
        """當日已打卡的員工不在忘刷名單中。"""
        today = fields.Date.today()
        self.env["hr.attendance"].create(
            {
                "employee_id": self.employee_normal.id,
                "check_in": fields.Datetime.now(),
                "check_date": today,
            }
        )
        before_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee_normal.id)]
        )
        self.env["hr.attendance"]._cron_send_forgot_punch_notification()
        after_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.employee_normal.id)]
        )
        self.assertEqual(before_count, after_count)


class TestCronPermitExpiry(TransactionCase):
    """測試外籍員工居留效期警示 cron。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.foreign_emp = cls.env["hr.employee"].create(
            {
                "name": "外籍員工測試",
                "active": True,
            }
        )

    def test_alert_created_for_expiring_permit(self):
        """距效期 30 天 → 應建立 activity 警示。"""
        self.foreign_emp.write(
            {"permit_expiry": date.today() + timedelta(days=30)}
        )
        before_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        self.env["hr.employee"]._cron_check_permit_expiry()
        after_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        self.assertGreater(after_count, before_count)

    def test_no_alert_for_far_expiry(self):
        """效期超過 60 天 → 不建立 activity。"""
        self.foreign_emp.write(
            {"permit_expiry": date.today() + timedelta(days=90)}
        )
        before_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        self.env["hr.employee"]._cron_check_permit_expiry()
        after_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        self.assertEqual(before_count, after_count)

    def test_no_duplicate_alert(self):
        """同一到期日不重複建立 activity。"""
        expiry = date.today() + timedelta(days=30)
        self.foreign_emp.write({"permit_expiry": expiry})
        self.env["hr.employee"]._cron_check_permit_expiry()
        self.env["hr.employee"]._cron_check_permit_expiry()
        activities = self.env["mail.activity"].search(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        # 應只有一筆（第二次執行防重複）
        self.assertEqual(len(activities), 1)

    def test_no_alert_for_already_expired(self):
        """已過期的效期 → 不建立 activity（today <= permit_expiry 條件）。"""
        self.foreign_emp.write(
            {"permit_expiry": date.today() - timedelta(days=1)}
        )
        before_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        self.env["hr.employee"]._cron_check_permit_expiry()
        after_count = self.env["mail.activity"].search_count(
            [("res_model", "=", "hr.employee"), ("res_id", "=", self.foreign_emp.id)]
        )
        self.assertEqual(before_count, after_count)
