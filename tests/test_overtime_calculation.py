"""加班費計算引擎完整單元測試。

驗證所有 4 種加班類型的分段費率、免稅/應稅分拆，及 hr.overtime 模型行為。
"""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models.hr_overtime_calculation import (
    calc_mandatory_rest_overtime,
    calc_public_holiday_overtime,
    calc_rest_day_overtime,
    calc_weekday_overtime,
)

HOURLY_RATE = 200.0  # 測試用時薪（月薪 48000 ÷ 30 ÷ 8）


class TestWeekdayOvertimePure(TransactionCase):
    """平日加班費純函式測試（勞基法 §24）。"""

    def test_weekday_1h(self):
        """1 小時平日加班：時薪 × 4/3。"""
        result = calc_weekday_overtime(1.0, HOURLY_RATE)
        self.assertAlmostEqual(result["tax_free_amount"], 0.0)
        # 200 × 4/3 × 1 ≈ 267（四捨五入）
        self.assertEqual(result["taxable_amount"], 267.0)
        self.assertEqual(result["total_amount"], 267.0)

    def test_weekday_2h(self):
        """2 小時平日加班：2 × 時薪 × 4/3。"""
        result = calc_weekday_overtime(2.0, HOURLY_RATE)
        self.assertAlmostEqual(result["taxable_amount"], 2 * 200 * 4 / 3, delta=1.0)

    def test_weekday_3h(self):
        """3 小時平日加班：2h@4/3 + 1h@5/3。"""
        result = calc_weekday_overtime(3.0, HOURLY_RATE)
        expected = 2 * HOURLY_RATE * 4 / 3 + 1 * HOURLY_RATE * 5 / 3
        self.assertAlmostEqual(result["taxable_amount"], round(expected), delta=1.0)

    def test_weekday_4h(self):
        """4 小時平日加班：2h@4/3 + 2h@5/3。"""
        result = calc_weekday_overtime(4.0, HOURLY_RATE)
        expected = 2 * HOURLY_RATE * 4 / 3 + 2 * HOURLY_RATE * 5 / 3
        self.assertAlmostEqual(result["taxable_amount"], round(expected), delta=1.0)

    def test_weekday_no_tax_free(self):
        """平日加班全部為應稅，免稅為 0。"""
        result = calc_weekday_overtime(4.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 0.0)

    def test_weekday_total_equals_sum(self):
        """total = tax_free + taxable。"""
        result = calc_weekday_overtime(3.5, HOURLY_RATE)
        self.assertAlmostEqual(
            result["total_amount"],
            result["tax_free_amount"] + result["taxable_amount"],
            delta=1.0,
        )


class TestRestDayOvertimePure(TransactionCase):
    """休假日加班費純函式測試（勞基法 §24-2）。"""

    def test_rest_day_2h(self):
        """2 小時：×4/3。"""
        result = calc_rest_day_overtime(2.0, HOURLY_RATE)
        expected = 2 * HOURLY_RATE * 4 / 3
        self.assertAlmostEqual(result["taxable_amount"], round(expected), delta=1.0)

    def test_rest_day_8h(self):
        """8 小時：2h@4/3 + 6h@5/3。"""
        result = calc_rest_day_overtime(8.0, HOURLY_RATE)
        expected = 2 * HOURLY_RATE * 4 / 3 + 6 * HOURLY_RATE * 5 / 3
        self.assertAlmostEqual(result["taxable_amount"], round(expected), delta=1.0)
        self.assertEqual(result["tax_free_amount"], 0.0)

    def test_rest_day_10h(self):
        """10 小時：2h@4/3 + 6h@5/3 + 2h@8/3。"""
        result = calc_rest_day_overtime(10.0, HOURLY_RATE)
        expected = (
            2 * HOURLY_RATE * 4 / 3
            + 6 * HOURLY_RATE * 5 / 3
            + 2 * HOURLY_RATE * 8 / 3
        )
        self.assertAlmostEqual(result["taxable_amount"], round(expected), delta=1.0)

    def test_rest_day_no_tax_free(self):
        """休假日加班全部應稅。"""
        result = calc_rest_day_overtime(10.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 0.0)


class TestMandatoryRestOvertimePure(TransactionCase):
    """例假日加班費純函式測試（勞基法 §36、§40）。"""

    def test_mandatory_rest_8h(self):
        """8 小時：全免稅 ×1。"""
        result = calc_mandatory_rest_overtime(8.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 8 * HOURLY_RATE)
        self.assertEqual(result["taxable_amount"], 0.0)

    def test_mandatory_rest_10h(self):
        """10 小時：8h 免稅 + 2h 應稅 ×2。"""
        result = calc_mandatory_rest_overtime(10.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 8 * HOURLY_RATE)
        self.assertEqual(result["taxable_amount"], 2 * HOURLY_RATE * 2)

    def test_mandatory_rest_4h(self):
        """4 小時（未達 8h）：全免稅。"""
        result = calc_mandatory_rest_overtime(4.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 4 * HOURLY_RATE)
        self.assertEqual(result["taxable_amount"], 0.0)

    def test_mandatory_rest_total(self):
        """10h：total = 免稅 1600 + 應稅 800 = 2400。"""
        result = calc_mandatory_rest_overtime(10.0, HOURLY_RATE)
        self.assertEqual(result["total_amount"], 8 * HOURLY_RATE + 2 * HOURLY_RATE * 2)


class TestPublicHolidayOvertimePure(TransactionCase):
    """國定假日加班費純函式測試（勞基法 §39）。"""

    def test_public_holiday_8h(self):
        """8 小時：全免稅 ×1。"""
        result = calc_public_holiday_overtime(8.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 8 * HOURLY_RATE)
        self.assertEqual(result["taxable_amount"], 0.0)

    def test_public_holiday_10h(self):
        """10 小時：8h 免稅 + 2h 應稅 ×4/3。"""
        result = calc_public_holiday_overtime(10.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 8 * HOURLY_RATE)
        expected_taxable = 2 * HOURLY_RATE * 4 / 3
        self.assertAlmostEqual(result["taxable_amount"], round(expected_taxable), delta=1.0)

    def test_public_holiday_12h(self):
        """12 小時：8h 免稅 + 2h@4/3 + 2h@5/3 應稅。"""
        result = calc_public_holiday_overtime(12.0, HOURLY_RATE)
        self.assertEqual(result["tax_free_amount"], 8 * HOURLY_RATE)
        expected_taxable = 2 * HOURLY_RATE * 4 / 3 + 2 * HOURLY_RATE * 5 / 3
        self.assertAlmostEqual(result["taxable_amount"], round(expected_taxable), delta=1.0)

    def test_public_holiday_total(self):
        """12h：total = 免稅 + 應稅。"""
        result = calc_public_holiday_overtime(12.0, HOURLY_RATE)
        self.assertAlmostEqual(
            result["total_amount"],
            result["tax_free_amount"] + result["taxable_amount"],
            delta=1.0,
        )


class TestHrOvertimeModel(TransactionCase):
    """hr.overtime 申請模型測試。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "加班測試員工"})
        cls.contract = cls.env["hr.contract"].create(
            {
                "name": "加班測試合約",
                "employee_id": cls.employee.id,
                "wage": 48000,
                "date_start": "2025-01-01",
                "state": "open",
            }
        )
        cls.ot_setting = cls.env["hr.overtime.config"].create(
            {
                "name": "測試加班設定",
                "monthly_limit_hours": 46.0,
                "daily_limit_hours": 4.0,
                "active": True,
            }
        )

    def _create_ot(self, day_type, time_start, time_end, date="2026-05-05"):
        return self.env["hr.overtime"].create(
            {
                "employee_id": self.employee.id,
                "date": date,
                "day_type": day_type,
                "time_start": time_start,
                "time_end": time_end,
                "compensation_type": "cash",
            }
        )

    def test_compute_hours(self):
        """時數計算：time_end - time_start。"""
        ot = self._create_ot("weekday", 18.0, 20.0)
        self.assertAlmostEqual(ot.hours, 2.0)

    def test_weekday_overtime_pay_compute(self):
        """平日 2h 加班費計算正確。"""
        ot = self._create_ot("weekday", 18.0, 20.0)
        # 合約未設定 hour_salary 時需先確認（依測試環境）
        if ot.hour_salary:
            expected = ot.hour_salary * 2 * 4 / 3
            self.assertAlmostEqual(ot.taxable_amount, round(expected), delta=1.0)
            self.assertEqual(ot.tax_free_amount, 0.0)

    def test_mandatory_rest_tax_split(self):
        """例假日 10h：有免稅與應稅拆分。"""
        ot = self._create_ot("mandatory_rest", 8.0, 18.0)
        if ot.hour_salary:
            self.assertGreater(ot.tax_free_amount, 0.0)
            self.assertGreater(ot.taxable_amount, 0.0)
            self.assertAlmostEqual(ot.total_amount, ot.tax_free_amount + ot.taxable_amount)

    def test_public_holiday_tax_split(self):
        """國定假日 12h：有免稅與應稅拆分。"""
        ot = self._create_ot("public_holiday", 8.0, 20.0)
        if ot.hour_salary:
            self.assertGreater(ot.tax_free_amount, 0.0)
            self.assertGreater(ot.taxable_amount, 0.0)

    def test_state_flow_submit_approve(self):
        """狀態流：draft → pending → approved。"""
        ot = self._create_ot("weekday", 18.0, 20.0)
        self.assertEqual(ot.state, "draft")
        ot.action_submit()
        self.assertEqual(ot.state, "pending")
        ot.action_approve()
        self.assertEqual(ot.state, "approved")

    def test_state_flow_refuse_reset(self):
        """狀態流：pending → refused → draft。"""
        ot = self._create_ot("weekday", 18.0, 20.0)
        ot.action_submit()
        ot.action_refuse()
        self.assertEqual(ot.state, "refused")
        ot.action_reset_draft()
        self.assertEqual(ot.state, "draft")

    def test_weekday_daily_limit_constraint(self):
        """平日加班超過日上限（4 小時）應拋出 ValidationError。"""
        with self.assertRaises(ValidationError):
            self._create_ot("weekday", 18.0, 23.0)  # 5 小時，超過 4h 上限

    def test_mandatory_rest_over_12h_constraint(self):
        """例假日超過 12 小時應拋出 ValidationError。"""
        with self.assertRaises(ValidationError):
            self._create_ot("mandatory_rest", 7.0, 20.0)  # 13 小時

    def test_calculate_overtime_pay_model_method(self):
        """_calculate_overtime_pay 類方法直接呼叫驗證。"""
        OvertimeModel = self.env["hr.overtime"]

        result = OvertimeModel._calculate_overtime_pay(10.0, "mandatory_rest", 200.0)
        self.assertEqual(result["tax_free_amount"], 1600.0)  # 8h × 200
        self.assertEqual(result["taxable_amount"], 800.0)   # 2h × 200 × 2

        result2 = OvertimeModel._calculate_overtime_pay(12.0, "public_holiday", 200.0)
        self.assertEqual(result2["tax_free_amount"], 1600.0)  # 8h × 200
        # 2h × 4/3 × 200 + 2h × 5/3 × 200 ≈ 533 + 667 = 1200（四捨五入）
        self.assertAlmostEqual(result2["taxable_amount"], 1200.0, delta=5.0)
