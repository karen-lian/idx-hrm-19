from datetime import date, timedelta

from odoo.tests.common import TransactionCase


class IdxHrmCase(TransactionCase):
    """idx_hrm_19 測試共用基礎類別，提供完整的 fixtures。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── 公司 ──────────────────────────────────────────────────
        cls.company = cls.env.ref("base.main_company")

        # ── 職務 ──────────────────────────────────────────────────
        cls.job = cls.env["hr.job"].create({"name": "工程師", "company_id": cls.company.id})

        # ── 部門 ──────────────────────────────────────────────────
        cls.dept = cls.env["hr.department"].create(
            {"name": "研發部", "company_id": cls.company.id}
        )

        # ── 員工（本國籍） ─────────────────────────────────────────
        cls.emp = cls.env["hr.employee"].create(
            {
                "name": "測試員工甲",
                "company_id": cls.company.id,
                "department_id": cls.dept.id,
                "job_id": cls.job.id,
            }
        )

        # ── 員工（外籍） ───────────────────────────────────────────
        cls.emp_foreign = cls.env["hr.employee"].create(
            {
                "name": "Foreign Worker",
                "company_id": cls.company.id,
                "department_id": cls.dept.id,
            }
        )

        # ── 第二位員工（用於多人測試） ───────────────────────────────
        cls.emp2 = cls.env["hr.employee"].create(
            {
                "name": "測試員工乙",
                "company_id": cls.company.id,
                "department_id": cls.dept.id,
            }
        )

        # ── 合約 ──────────────────────────────────────────────────
        cls.today = date.today()
        cls.contract = cls.env["hr.contract"].create(
            {
                "name": "測試合約甲",
                "employee_id": cls.emp.id,
                "wage": 48000,
                "date_start": cls.today - timedelta(days=365),
                "state": "open",
                "company_id": cls.company.id,
            }
        )

        # ── 加班設定 ───────────────────────────────────────────────
        cls.overtime_setting = cls.env["hr.overtime.setting"].create(
            {
                "name": "測試加班設定",
                "monthly_limit_hours": 46.0,
                "daily_limit_hours": 4.0,
            }
        )

        # 平日加班類型（勞基法 §24）
        cls.ot_type_weekday = cls.env["hr.overtime.type"].create(
            {
                "setting_id": cls.overtime_setting.id,
                "name": "平日加班",
                "day_type": "weekday",
            }
        )
        cls.env["hr.overtime.type.rule"].create(
            [
                {
                    "overtime_type_id": cls.ot_type_weekday.id,
                    "hour_from": 0,
                    "hour_to": 2,
                    "rate": round(4 / 3, 4),
                    "is_tax_free": False,
                },
                {
                    "overtime_type_id": cls.ot_type_weekday.id,
                    "hour_from": 2,
                    "hour_to": 4,
                    "rate": round(5 / 3, 4),
                    "is_tax_free": False,
                },
            ]
        )

        # 例假日加班類型（勞基法 §36）
        cls.ot_type_holiday = cls.env["hr.overtime.type"].create(
            {
                "setting_id": cls.overtime_setting.id,
                "name": "例假日加班",
                "day_type": "holiday",
            }
        )
        cls.env["hr.overtime.type.rule"].create(
            {
                "overtime_type_id": cls.ot_type_holiday.id,
                "hour_from": 0,
                "hour_to": 12,
                "rate": 2.0,
                "is_tax_free": False,
            }
        )

        # 國定假日加班類型（勞基法 §39）
        cls.ot_type_statutory = cls.env["hr.overtime.type"].create(
            {
                "setting_id": cls.overtime_setting.id,
                "name": "國定假日加班",
                "day_type": "statutory_holiday",
            }
        )
        cls.env["hr.overtime.type.rule"].create(
            {
                "overtime_type_id": cls.ot_type_statutory.id,
                "hour_from": 0,
                "hour_to": 12,
                "rate": 2.0,
                "is_tax_free": False,
            }
        )

        # ── 假別（特休） ───────────────────────────────────────────
        cls.leave_type_annual = cls.env["hr.leave.type"].search(
            [("time_type", "=", "leave")], limit=1
        )
        if not cls.leave_type_annual:
            cls.leave_type_annual = cls.env["hr.leave.type"].create(
                {
                    "name": "特休假",
                    "time_type": "leave",
                    "requires_allocation": "yes",
                    "company_id": cls.company.id,
                }
            )

        # ── 假別（病假） ───────────────────────────────────────────
        cls.leave_type_sick = cls.env["hr.leave.type"].create(
            {
                "name": "病假",
                "time_type": "leave",
                "requires_allocation": "no",
                "company_id": cls.company.id,
            }
        )

    # ── 工具方法 ───────────────────────────────────────────────────

    def _create_overtime(self, employee=None, ot_type=None, hours=2, date_val=None):
        """建立加班記錄的快捷方法。"""
        return self.env["hr.overtime"].create(
            {
                "employee_id": (employee or self.emp).id,
                "overtime_type_id": (ot_type or self.ot_type_weekday).id,
                "number_of_hours": hours,
                "date": date_val or self.today,
            }
        )

    def _create_leave(self, employee=None, leave_type=None, date_from=None, date_to=None):
        """建立請假記錄的快捷方法。"""
        date_from = date_from or self.today
        date_to = date_to or self.today
        return self.env["hr.leave"].create(
            {
                "employee_id": (employee or self.emp).id,
                "holiday_status_id": (leave_type or self.leave_type_annual).id,
                "request_date_from": str(date_from),
                "request_date_to": str(date_to),
            }
        )

    def _create_contract(self, employee=None, wage=48000, date_start=None, state="open"):
        """建立合約的快捷方法。"""
        return self.env["hr.contract"].create(
            {
                "name": f"測試合約_{employee.name if employee else ''}",
                "employee_id": (employee or self.emp).id,
                "wage": wage,
                "date_start": date_start or str(self.today - timedelta(days=30)),
                "state": state,
                "company_id": self.company.id,
            }
        )
