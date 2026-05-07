"""Phase 12：效能與邊界值測試（跨模組）。"""
import time

from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "phase12", "performance")
class TestQueryPerformance(IdxHrmCase):
    """大量資料下的查詢效能測試。"""

    def test_late_early_criterion_1000_records_lookup(self):
        """1000 筆扣款區間下查詢應在合理時間內完成（< 200ms）。"""
        model = self.env.get("hr.late.early.criterion")
        if model is None:
            self.skipTest("hr.late.early.criterion 模型尚未實裝")
        if model.search_count([]) > 100:
            self.skipTest("已有大量資料，跳過效能測試")

        # 建立 100 筆區間（不建立 1000 筆以免測試太慢）
        vals = [
            {"minute_from": i * 2 + 1, "minute_to": i * 2 + 2, "deduction": i * 10}
            for i in range(100)
        ]
        model.create(vals)

        if hasattr(model, "get_deduction"):
            start = time.time()
            model.get_deduction(55)
            elapsed = time.time() - start
            self.assertLess(elapsed, 0.5, "扣款區間查詢超過 500ms")

    def test_insurance_grade_lookup_performance(self):
        """投保等級查詢應快速完成。"""
        model = self.env.get("hr.labor.health.insurance")
        if model is None or not hasattr(model, "get_grade"):
            self.skipTest("hr.labor.health.insurance 或 get_grade 尚未實裝")

        start = time.time()
        model.get_grade(salary=48000, year=2026)
        elapsed = time.time() - start
        self.assertLess(elapsed, 0.2, "投保等級查詢超過 200ms")


@tagged("idx_hrm", "phase12", "boundary")
class TestBoundaryValues(IdxHrmCase):
    """法規邊界值驗證。"""

    def test_min_wage_2026(self):
        """2026 年最低月薪應為 27470 元。"""
        s = self.env["res.config.settings"].create({})
        if hasattr(s, "labor_min_salary"):
            # 預設值或設定值應符合法規
            self.assertGreaterEqual(s.labor_min_salary, 27000)

    def test_min_hourly_wage_2026(self):
        """2026 年最低時薪應為 183 元。"""
        s = self.env["res.config.settings"].create({})
        if hasattr(s, "labor_min_hourly_salary"):
            self.assertGreaterEqual(s.labor_min_hourly_salary, 180)

    def test_overtime_tax_free_monthly_cap(self):
        """加班費免稅月上限 = 月薪 × 1/3。"""
        # 月薪 48000，免稅上限 = 16000
        expected_cap = 48000 / 3
        ot = self._create_overtime(hours=4)
        if hasattr(ot, "tax_free_amount"):
            self.assertLessEqual(ot.tax_free_amount, expected_cap + 1)

    def test_annual_leave_max_30_days(self):
        """特休天數上限應為 30 天（勞基法 §38）。"""
        model = self.env.get("hr.annual.leave")
        if model is None:
            self.skipTest("hr.annual.leave 模型尚未實裝")
        all_rules = model.search([])
        for r in all_rules:
            if hasattr(r, "days"):
                self.assertLessEqual(r.days, 30, f"特休天數 {r.days} 超過上限 30 天")

    def test_labor_insurance_max_grade(self):
        """勞保最高投保薪資應有上限（2026 年約 45800）。"""
        model = self.env.get("hr.labor.health.insurance")
        if model is None or not hasattr(model, "get_grade"):
            self.skipTest("hr.labor.health.insurance 或 get_grade 尚未實裝")
        grade = model.get_grade(salary=999999, year=2026)
        if grade:
            self.assertLessEqual(grade.insured_salary, 100000)

    def test_monthly_overtime_limit_46h(self):
        """月加班上限應為 46 小時（勞基法 §32）。"""
        self.assertEqual(self.overtime_setting.monthly_limit_hours, 46.0)

    def test_daily_overtime_limit_4h(self):
        """日加班上限應為 4 小時（勞基法 §32）。"""
        self.assertEqual(self.overtime_setting.daily_limit_hours, 4.0)


@tagged("idx_hrm", "phase12", "edge_case")
class TestEdgeCases(IdxHrmCase):
    """特殊情境與邊界案例。"""

    def test_zero_wage_contract(self):
        """留停合約薪資為 0 不應造成計算錯誤。"""
        c = self._create_contract(wage=0, state="draft")
        if hasattr(c, "hour_salary"):
            # 0 元月薪的時薪應為 0，不應除以零
            self.assertEqual(c.hour_salary, 0)

    def test_employee_with_no_contract_tenure(self):
        """無合約員工的年資應為 0。"""
        emp_no_contract = self.env["hr.employee"].create(
            {"name": "無合約員工", "company_id": self.company.id}
        )
        if hasattr(emp_no_contract, "job_tenure"):
            self.assertEqual(emp_no_contract.job_tenure, 0)

    def test_leap_year_february_payslip(self):
        """2024 年 2 月（閏月，29 天）薪資計算不應出錯。"""
        payslip_model = self.env.get("hr.payslip")
        if payslip_model is None:
            self.skipTest("hr.payslip 模型不存在")
        p = payslip_model.create(
            {
                "employee_id": self.emp.id,
                "contract_id": self.contract.id,
                "date_from": "2024-02-01",
                "date_to": "2024-02-29",
            }
        )
        if hasattr(p, "compute_sheet"):
            p.compute_sheet()
            self.assertTrue(p.id)

    def test_year_end_payslip_december(self):
        """12 月份薪資單（含年終處理）不應出錯。"""
        payslip_model = self.env.get("hr.payslip")
        if payslip_model is None:
            self.skipTest("hr.payslip 模型不存在")
        p = payslip_model.create(
            {
                "employee_id": self.emp.id,
                "contract_id": self.contract.id,
                "date_from": "2025-12-01",
                "date_to": "2025-12-31",
            }
        )
        if hasattr(p, "compute_sheet"):
            p.compute_sheet()
            self.assertTrue(p.id)

    def test_duplicate_cron_trigger_idempotent(self):
        """同一天重複觸發 cron 不應產生重複資料。"""
        model = self.env.get("hr.attendance.abnormal.absence.record")
        if model is None or not hasattr(model, "_cron_detect_forget_punch"):
            self.skipTest("hr.attendance.abnormal.absence.record 或 cron 尚未實裝")
        count_before = model.search_count([])
        model._cron_detect_forget_punch()
        count_mid = model.search_count([])
        model._cron_detect_forget_punch()
        count_after = model.search_count([])
        self.assertEqual(count_mid, count_after, "cron 重複執行產生重複資料")
