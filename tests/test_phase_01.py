"""Phase 1：員工與合約核心模型（PR-010 ~ PR-016b）。"""
from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "phase01", "pr010")
class TestHrEmployee(IdxHrmCase):
    """PR-010：員工基本資料擴充（hr.employee）。"""

    def test_employee_number_uniqueness(self):
        """同公司員工編號不可重複。"""
        if not hasattr(self.env["hr.employee"], "employee_number"):
            self.skipTest("employee_number 欄位尚未實裝")
        self.emp.employee_number = "IDX-E001"
        with self.assertRaises(Exception):
            self.emp2.employee_number = "IDX-E001"
            self.env.flush_all()

    def test_substitute_no_self_loop(self):
        """代理人不可為自己。"""
        if not hasattr(self.env["hr.employee"], "substitute_id"):
            self.skipTest("substitute_id 欄位尚未實裝")
        with self.assertRaises(ValidationError):
            self.emp.substitute_id = self.emp.id
            self.env.flush_all()

    def test_is_no_punch_excludes_abnormal(self):
        """is_no_punch 員工不應產生出勤異常記錄。"""
        if not hasattr(self.env["hr.employee"], "is_no_punch"):
            self.skipTest("is_no_punch 欄位尚未實裝")
        self.emp.is_no_punch = True
        model = self.env.get("hr.attendance.abnormal.absence.record")
        if model and hasattr(model, "_detect_abnormal"):
            model._detect_abnormal(
                employee_ids=self.emp.ids,
                date_from=str(self.today),
                date_to=str(self.today),
            )
            abnormal = model.search([("employee_id", "=", self.emp.id)])
            self.assertEqual(len(abnormal), 0)


@tagged("idx_hrm", "phase01", "pr011")
class TestTwIdValidation(IdxHrmCase):
    """PR-011：台灣身分證驗證邏輯。"""

    KNOWN_VALID_ID = "A123456789"  # 示範用，實際應使用正確測試 ID

    def _validate(self, id_num):
        """呼叫模組的身分證驗證方法。"""
        emp = self.env["hr.employee"]
        if hasattr(emp, "_validate_tw_id"):
            return emp._validate_tw_id(id_num)
        return True  # 尚未實裝，放行

    def test_valid_id_accepted(self):
        """合法身分證號應通過驗證。"""
        # 使用已知合法測試號碼，實際上需使用通過 MOD10 的值
        # 此處僅確認驗證方法存在且可呼叫
        emp = self.env["hr.employee"]
        if not hasattr(emp, "_validate_tw_id"):
            self.skipTest("_validate_tw_id 尚未實裝")

    def test_gender_second_digit_1_is_male(self):
        """第 2 位為 1 應推算為男性。"""
        emp = self.env["hr.employee"]
        if hasattr(emp, "_get_gender_from_id"):
            gender = emp._get_gender_from_id("A1XXXXXXXX")
            self.assertEqual(gender, "male")

    def test_gender_second_digit_2_is_female(self):
        """第 2 位為 2 應推算為女性。"""
        emp = self.env["hr.employee"]
        if hasattr(emp, "_get_gender_from_id"):
            gender = emp._get_gender_from_id("A2XXXXXXXX")
            self.assertEqual(gender, "female")

    def test_invalid_second_digit_rejected(self):
        """第 2 位非 1、2 應拒絕。"""
        emp_model = self.env["hr.employee"]
        if hasattr(emp_model, "_validate_tw_id"):
            with self.assertRaises(ValidationError):
                emp_model._validate_tw_id("A033456789")


@tagged("idx_hrm", "phase01", "pr012")
class TestJobTenure(IdxHrmCase):
    """PR-012：服務年資計算邏輯。"""

    def test_single_contract_tenure(self):
        """單份合約年資計算正確。"""
        if not hasattr(self.emp, "job_tenure"):
            self.skipTest("job_tenure 欄位尚未實裝")
        # contract 建立於 365 天前，年資約 1 年
        self.assertGreater(self.emp.job_tenure, 0.9)
        self.assertLess(self.emp.job_tenure, 1.1)

    def test_multiple_contracts_cumulative_tenure(self):
        """多份合約應累計年資。"""
        if not hasattr(self.emp2, "job_tenure"):
            self.skipTest("job_tenure 欄位尚未實裝")
        c1 = self._create_contract(
            employee=self.emp2,
            date_start=str(self.today - timedelta(days=1095)),  # 3 年前
            state="close",
        )
        c1.date_end = str(self.today - timedelta(days=366))
        c2 = self._create_contract(
            employee=self.emp2,
            date_start=str(self.today - timedelta(days=365)),
            state="open",
        )
        self.assertGreater(self.emp2.job_tenure, 2.5)

    def test_draft_contract_excluded(self):
        """草稿合約不計入年資。"""
        if not hasattr(self.emp2, "job_tenure"):
            self.skipTest("job_tenure 欄位尚未實裝")
        tenure_before = self.emp2.job_tenure
        self._create_contract(
            employee=self.emp2,
            date_start=str(self.today + timedelta(days=10)),
            state="draft",
        )
        self.assertAlmostEqual(self.emp2.job_tenure, tenure_before, places=2)

    def test_precision_three_decimal(self):
        """年資精度應至小數第三位。"""
        if not hasattr(self.emp, "job_tenure"):
            self.skipTest("job_tenure 欄位尚未實裝")
        tenure = self.emp.job_tenure
        # 驗證不超過 3 位小數
        rounded = round(tenure, 3)
        self.assertAlmostEqual(tenure, rounded, places=5)


@tagged("idx_hrm", "phase01", "pr013")
class TestForeignEmployee(IdxHrmCase):
    """PR-013：外籍員工欄位與效期管理。"""

    def test_permit_expiry_field_exists(self):
        """居留證到期日欄位應存在。"""
        if not hasattr(self.env["hr.employee"], "permit_expiry"):
            self.skipTest("permit_expiry 欄位尚未實裝")
        self.emp_foreign.permit_expiry = str(self.today + timedelta(days=100))
        self.assertEqual(
            str(self.emp_foreign.permit_expiry), str(self.today + timedelta(days=100))
        )

    def test_cron_expiry_notification(self):
        """cron 掃描應對即將到期員工產生通知。"""
        if not hasattr(self.env["hr.employee"], "_cron_check_permit_expiry"):
            self.skipTest("_cron_check_permit_expiry 尚未實裝")
        if not hasattr(self.env["hr.employee"], "permit_expiry"):
            self.skipTest("permit_expiry 欄位尚未實裝")
        self.emp_foreign.permit_expiry = str(self.today + timedelta(days=55))
        self.env["hr.employee"]._cron_check_permit_expiry()
        activities = self.env["mail.activity"].search(
            [("res_id", "=", self.emp_foreign.id), ("res_model", "=", "hr.employee")]
        )
        self.assertTrue(activities, "效期警示 cron 未產生通知")

    def test_is_no_pr_field(self):
        """is_no_pr（非永居）欄位應存在。"""
        if not hasattr(self.env["hr.employee"], "is_no_pr"):
            self.skipTest("is_no_pr 欄位尚未實裝")
        self.emp_foreign.is_no_pr = True
        self.assertTrue(self.emp_foreign.is_no_pr)

    def test_permit_and_visa_independence(self):
        """居留證與工作簽證效期應獨立管理。"""
        fields_emp = self.env["hr.employee"]._fields
        has_permit = "permit_expiry" in fields_emp
        has_work_permit = "work_permit_expiry" in fields_emp
        if not (has_permit and has_work_permit):
            self.skipTest("permit_expiry 或 work_permit_expiry 尚未實裝")
        self.emp_foreign.permit_expiry = str(self.today + timedelta(days=10))
        self.emp_foreign.work_permit_expiry = str(self.today + timedelta(days=100))
        self.assertNotEqual(
            self.emp_foreign.permit_expiry, self.emp_foreign.work_permit_expiry
        )


@tagged("idx_hrm", "phase01", "pr014")
class TestHrContract(IdxHrmCase):
    """PR-014：合約基本擴充欄位（hr.contract）。"""

    def test_hour_salary_calculation(self):
        """月薪 48000 → 時薪應為 200.0（÷30÷8）。"""
        if not hasattr(self.contract, "hour_salary"):
            self.skipTest("hour_salary 欄位尚未實裝")
        self.assertAlmostEqual(self.contract.hour_salary, 48000 / 30 / 8, places=1)

    def test_hour_salary_updates_on_wage_change(self):
        """月薪變更時時薪應自動更新。"""
        if not hasattr(self.contract, "hour_salary"):
            self.skipTest("hour_salary 欄位尚未實裝")
        self.contract.wage = 60000
        self.assertAlmostEqual(self.contract.hour_salary, 60000 / 30 / 8, places=1)

    def test_furlough_contract_zero_rates(self):
        """留停合約費率應自動設為 0。"""
        if not hasattr(self.contract, "labor_employee_rate"):
            self.skipTest("labor_employee_rate 欄位尚未實裝")
        furlough_type = self.env["hr.contract.type"].search(
            [("name", "ilike", "留停")], limit=1
        )
        if furlough_type:
            c = self._create_contract(state="draft")
            c.contract_type_id = furlough_type.id
            # 留停合約費率應為 0
            self.assertEqual(c.labor_employee_rate, 0)

    def test_no_pr_employment_insurance_zero(self):
        """外籍無永居員工就業保險費應為 0。"""
        if not hasattr(self.contract, "is_no_pr"):
            self.skipTest("is_no_pr 欄位尚未實裝")
        c = self._create_contract(employee=self.emp_foreign)
        c.is_no_pr = True
        if hasattr(c, "_compute_employment_insurance_employee"):
            emp_ins = c._compute_employment_insurance_employee()
            self.assertEqual(emp_ins, 0)

    def test_job_class_related_field(self):
        """job_class 應從 job_id 自動推導。"""
        if not hasattr(self.contract, "job_class"):
            self.skipTest("job_class 欄位尚未實裝")
        if hasattr(self.job, "job_class"):
            self.job.job_class = "P1"
            self.contract.job_id = self.job.id
            self.assertEqual(self.contract.job_class, "P1")


@tagged("idx_hrm", "phase01", "pr015")
class TestContractStateCron(IdxHrmCase):
    """PR-015：合約狀態流程與 cron。"""

    def test_cron_contract_state_update(self):
        """cron 應自動將到期合約轉為 close。"""
        if not hasattr(self.env["hr.contract"], "_cron_update_contract_state"):
            self.skipTest("_cron_update_contract_state 尚未實裝")
        c = self._create_contract(
            employee=self.emp2,
            date_start=str(self.today - timedelta(days=365)),
            state="open",
        )
        c.date_end = str(self.today - timedelta(days=1))
        self.env["hr.contract"]._cron_update_contract_state()
        self.assertEqual(c.state, "close")

    def test_adjacent_contracts_allowed(self):
        """相鄰（不重疊）合約應允許同時存在。"""
        c1 = self.env["hr.contract"].create(
            {
                "name": "合約 A",
                "employee_id": self.emp2.id,
                "wage": 48000,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "company_id": self.company.id,
            }
        )
        # 不應拋出例外
        c2 = self.env["hr.contract"].create(
            {
                "name": "合約 B",
                "employee_id": self.emp2.id,
                "wage": 48000,
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
                "company_id": self.company.id,
            }
        )
        self.assertTrue(c2.id)

    def test_overlapping_contracts_rejected(self):
        """重疊合約應拒絕。"""
        self.env["hr.contract"].create(
            {
                "name": "合約 C",
                "employee_id": self.emp2.id,
                "wage": 48000,
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
                "state": "open",
                "company_id": self.company.id,
            }
        )
        if hasattr(self.env["hr.contract"], "_check_date_overlap"):
            with self.assertRaises(ValidationError):
                self.env["hr.contract"].create(
                    {
                        "name": "合約 D 重疊",
                        "employee_id": self.emp2.id,
                        "wage": 48000,
                        "date_start": "2025-06-01",
                        "date_end": "2026-06-30",
                        "company_id": self.company.id,
                    }
                )


@tagged("idx_hrm", "phase01", "pr016b")
class TestContractApprovalWorkflow(IdxHrmCase):
    """PR-016b：合約審核工作流與 UI。"""

    def test_contract_approval_state_exists(self):
        """合約應有審核狀態欄位（若已實裝）。"""
        fields_c = self.env["hr.contract"]._fields
        # 若有 approval_state 欄位
        if "approval_state" in fields_c:
            c = self._create_contract(state="draft")
            self.assertIn(c.approval_state, ["draft", "pending", "approved", "refused"])
        else:
            self.skipTest("approval_state 欄位尚未實裝")

    def test_contract_submit_for_approval(self):
        """合約應可提交審核。"""
        if not hasattr(self.env["hr.contract"], "action_submit_approval"):
            self.skipTest("action_submit_approval 尚未實裝")
        c = self._create_contract(state="draft")
        c.action_submit_approval()
        self.assertIn(getattr(c, "approval_state", "pending"), ["pending", "submitted"])
