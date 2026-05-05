from odoo.tests.common import TransactionCase


class TestHrLaborHealthInsurance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.version = cls.env["hr.labor.health.insurance.type"].create(
            {"year": 2026, "insurance_type": "labor"}
        )
        # 建立幾個投保等級
        cls.env["hr.labor.health.insurance"].create(
            [
                {"version_id": cls.version.id, "grade": 1,
                 "insured_salary": 27470, "employee_labor": 478, "employer_labor": 1005},
                {"version_id": cls.version.id, "grade": 2,
                 "insured_salary": 28000, "employee_labor": 488, "employer_labor": 1026},
                {"version_id": cls.version.id, "grade": 3,
                 "insured_salary": 30300, "employee_labor": 527, "employer_labor": 1109},
                {"version_id": cls.version.id, "grade": 10,
                 "insured_salary": 36300, "employee_labor": 632, "employer_labor": 1330},
            ]
        )

    def test_grade_lookup_exact(self):
        """PR-006: 薪資精確符合投保等級。"""
        model = self.env["hr.labor.health.insurance"]
        grade = model.get_grade(27470, 2026, "labor")
        self.assertEqual(grade.insured_salary, 27470)

    def test_grade_lookup_between(self):
        """PR-006: 薪資介於等級之間，取最接近不低於薪資之等級。"""
        model = self.env["hr.labor.health.insurance"]
        grade = model.get_grade(35000, 2026, "labor")
        self.assertEqual(grade.insured_salary, 36300)

    def test_grade_lookup_above_max(self):
        """PR-006: 薪資超過最高等級，取最高等級。"""
        model = self.env["hr.labor.health.insurance"]
        grade = model.get_grade(999999, 2026, "labor")
        self.assertEqual(grade.insured_salary, 36300)

    def test_version_unique_constraint(self):
        """PR-006: 同年度同類別不可重複建立版本。"""
        with self.assertRaises(Exception):
            self.env["hr.labor.health.insurance.type"].create(
                {"year": 2026, "insurance_type": "labor"}
            )

    def test_version_name_computed(self):
        """PR-006: 版本名稱 compute 欄位正確。"""
        self.assertIn("2026", self.version.name)
        self.assertIn("勞工保險", self.version.name)

    def test_multi_year_switch(self):
        """PR-006: 多年度版本切換正確。"""
        version2 = self.env["hr.labor.health.insurance.type"].create(
            {"year": 2025, "insurance_type": "labor"}
        )
        self.env["hr.labor.health.insurance"].create(
            {"version_id": version2.id, "grade": 1,
             "insured_salary": 26400, "employee_labor": 460}
        )
        model = self.env["hr.labor.health.insurance"]
        grade_2025 = model.get_grade(26000, 2025, "labor")
        self.assertEqual(grade_2025.insured_salary, 26400)
        grade_2026 = model.get_grade(26000, 2026, "labor")
        self.assertEqual(grade_2026.insured_salary, 27470)
