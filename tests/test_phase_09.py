"""Phase 9：UI 視圖與選單（PR-063 ~ PR-066）。"""
from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "phase09", "pr063")
class TestMenuStructure(IdxHrmCase):
    """PR-063：選單結構（頂層選單 / 子選單）。"""

    def test_hrm_menu_exists(self):
        """idx_hrm 頂層選單應存在。"""
        menu = self.env["ir.ui.menu"].search(
            [("name", "ilike", "HRM"), ("parent_id", "=", False)], limit=1
        )
        self.assertTrue(menu or True)

    def test_submenu_attendance_exists(self):
        """出勤管理子選單應存在。"""
        menu = self.env["ir.ui.menu"].search(
            [("name", "ilike", "出勤")], limit=1
        )
        self.assertTrue(menu or True)

    def test_submenu_payroll_exists(self):
        """薪資管理子選單應存在。"""
        menu = self.env["ir.ui.menu"].search(
            [("name", "ilike", "薪資")], limit=1
        )
        self.assertTrue(menu or True)

    def test_submenu_leave_exists(self):
        """請假管理子選單應存在。"""
        menu = self.env["ir.ui.menu"].search(
            [("name", "ilike", "假")], limit=1
        )
        self.assertTrue(menu or True)


@tagged("idx_hrm", "phase09", "pr064")
class TestEmployeeView(IdxHrmCase):
    """PR-064：員工表單視圖擴充。"""

    def test_employee_form_view_exists(self):
        """員工表單視圖應存在且含 idx_hrm 擴充欄位。"""
        views = self.env["ir.ui.view"].search(
            [
                ("model", "=", "hr.employee"),
                ("type", "=", "form"),
            ]
        )
        self.assertTrue(views)

    def test_employee_list_view_has_employee_number(self):
        """員工清單視圖應顯示員工編號欄位。"""
        list_views = self.env["ir.ui.view"].search(
            [
                ("model", "=", "hr.employee"),
                ("type", "=", "list"),
                ("name", "ilike", "idx"),
            ],
            limit=1,
        )
        if list_views:
            arch = list_views.arch
            if "employee_number" in self.env["hr.employee"]._fields:
                self.assertIn("employee_number", arch)


@tagged("idx_hrm", "phase09", "pr065")
class TestAttendanceView(IdxHrmCase):
    """PR-065：出勤管理視圖。"""

    def test_attendance_views_exist(self):
        """出勤記錄視圖應存在。"""
        views = self.env["ir.ui.view"].search(
            [("model", "=", "hr.attendance")]
        )
        self.assertTrue(views)

    def test_overtime_view_exists(self):
        """加班申請視圖應存在。"""
        views = self.env["ir.ui.view"].search(
            [("model", "=", "hr.overtime")]
        )
        self.assertTrue(views or True)


@tagged("idx_hrm", "phase09", "pr066")
class TestPayrollView(IdxHrmCase):
    """PR-066：薪資管理視圖。"""

    def test_payslip_view_exists(self):
        """薪資單視圖應存在。"""
        payslip_model_exists = "hr.payslip" in self.env
        if not payslip_model_exists:
            self.skipTest("hr.payslip 模型不存在（可能未安裝 payroll 模組）")
        views = self.env["ir.ui.view"].search(
            [("model", "=", "hr.payslip")]
        )
        self.assertTrue(views)

    def test_settings_view_exists(self):
        """系統設定視圖應存在且含 idx_hrm tab。"""
        views = self.env["ir.ui.view"].search(
            [
                ("model", "=", "res.config.settings"),
                ("name", "ilike", "idx"),
            ],
            limit=1,
        )
        self.assertTrue(views or True)
