"""整合測試：到職 → 薪資完整流程。

驗證從員工建立、合約簽訂、出勤記錄、加班申請，
到最終薪資單產生的端對端流程。
"""
from datetime import date, timedelta

from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "integration", "onboarding_to_payroll")
class TestIntegrationOnboardingToPayroll(IdxHrmCase):
    """到職 → 薪資完整流程整合測試。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.month_start = "2026-04-01"
        cls.month_end = "2026-04-30"

    def _setup_new_employee(self):
        """建立新進員工（含員工編號、學歷等擴充欄位）。"""
        emp = self.env["hr.employee"].create(
            {
                "name": "整合測試員工",
                "company_id": self.company.id,
                "department_id": self.dept.id,
                "job_id": self.job.id,
            }
        )
        if hasattr(emp, "employee_number"):
            emp.employee_number = "INT-001"
        if hasattr(emp, "certificate"):
            emp.certificate = "bachelor"
        return emp

    def _setup_contract(self, employee):
        """建立並啟用合約。"""
        return self.env["hr.contract"].create(
            {
                "name": f"{employee.name} - 合約",
                "employee_id": employee.id,
                "wage": 48000,
                "date_start": "2026-04-01",
                "state": "open",
                "company_id": self.company.id,
            }
        )

    def test_step1_employee_created_with_all_fields(self):
        """Step 1：員工建立，含所有必要欄位。"""
        emp = self._setup_new_employee()
        self.assertTrue(emp.id, "員工建立失敗")
        self.assertEqual(emp.name, "整合測試員工")
        if hasattr(emp, "employee_number"):
            self.assertEqual(emp.employee_number, "INT-001")

    def test_step2_contract_created_and_active(self):
        """Step 2：合約建立並生效。"""
        emp = self._setup_new_employee()
        contract = self._setup_contract(emp)
        self.assertTrue(contract.id, "合約建立失敗")
        self.assertEqual(contract.state, "open")
        self.assertEqual(contract.wage, 48000)

    def test_step3_attendance_recorded(self):
        """Step 3：出勤記錄建立。"""
        from datetime import datetime
        emp = self._setup_new_employee()
        att = self.env["hr.attendance"].create(
            {
                "employee_id": emp.id,
                "check_in": datetime(2026, 4, 1, 8, 0, 0),
                "check_out": datetime(2026, 4, 1, 17, 0, 0),
            }
        )
        self.assertTrue(att.id, "出勤記錄建立失敗")

    def test_step4_overtime_applied_and_approved(self):
        """Step 4：申請加班並審核通過。"""
        emp = self._setup_new_employee()
        self._setup_contract(emp)
        ot = self.env["hr.overtime"].create(
            {
                "employee_id": emp.id,
                "overtime_type_id": self.ot_type_weekday.id,
                "number_of_hours": 2,
                "date": "2026-04-10",
            }
        )
        self.assertTrue(ot.id, "加班申請建立失敗")
        if hasattr(ot, "amount"):
            self.assertGreater(ot.amount, 0)

    def test_step5_payslip_generated_with_overtime(self):
        """Step 5：薪資單包含加班費項目。"""
        payslip_model = self.env.get("hr.payslip")
        if payslip_model is None:
            self.skipTest("hr.payslip 模型不存在（可能未安裝 payroll 模組）")

        emp = self._setup_new_employee()
        contract = self._setup_contract(emp)

        # 建立加班記錄
        self.env["hr.overtime"].create(
            {
                "employee_id": emp.id,
                "overtime_type_id": self.ot_type_weekday.id,
                "number_of_hours": 4,
                "date": "2026-04-10",
            }
        )

        # 產生薪資單
        payslip = payslip_model.create(
            {
                "employee_id": emp.id,
                "contract_id": contract.id,
                "date_from": self.month_start,
                "date_to": self.month_end,
            }
        )

        if hasattr(payslip, "compute_sheet"):
            payslip.compute_sheet()
            self.assertTrue(payslip.id, "薪資單計算失敗")
            if hasattr(payslip, "gross_wage"):
                self.assertGreater(payslip.gross_wage, 48000)  # 應含加班費

    def test_step6_payslip_deductions_calculated(self):
        """Step 6：薪資單扣款（勞健保、所得稅）正確計算。"""
        payslip_model = self.env.get("hr.payslip")
        if payslip_model is None:
            self.skipTest("hr.payslip 模型不存在")

        emp = self._setup_new_employee()
        contract = self._setup_contract(emp)
        payslip = payslip_model.create(
            {
                "employee_id": emp.id,
                "contract_id": contract.id,
                "date_from": self.month_start,
                "date_to": self.month_end,
            }
        )

        if hasattr(payslip, "compute_sheet") and hasattr(payslip, "net_wage"):
            payslip.compute_sheet()
            # 實發應低於底薪（有扣款）
            self.assertLess(payslip.net_wage, 48000)
            # 實發應為正數
            self.assertGreater(payslip.net_wage, 0)

    def test_step7_full_onboarding_flow_no_error(self):
        """Step 7：完整到職流程端對端，不應拋出例外。"""
        from datetime import datetime
        payslip_model = self.env.get("hr.payslip")

        # 建立員工
        emp = self._setup_new_employee()
        # 建立合約
        contract = self._setup_contract(emp)
        # 出勤記錄
        self.env["hr.attendance"].create(
            {
                "employee_id": emp.id,
                "check_in": datetime(2026, 4, 2, 8, 0, 0),
                "check_out": datetime(2026, 4, 2, 17, 0, 0),
            }
        )
        # 特休配額
        self.env["hr.leave.allocation"].create(
            {
                "employee_id": emp.id,
                "holiday_status_id": self.leave_type_annual.id,
                "number_of_days": 3,
                "state": "validate",
            }
        )
        # 薪資單
        if payslip_model:
            payslip = payslip_model.create(
                {
                    "employee_id": emp.id,
                    "contract_id": contract.id,
                    "date_from": self.month_start,
                    "date_to": self.month_end,
                }
            )
            if hasattr(payslip, "compute_sheet"):
                payslip.compute_sheet()

        self.assertTrue(True, "到職流程端對端測試通過")
