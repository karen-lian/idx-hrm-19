from odoo import api, fields, models
from odoo.exceptions import ValidationError

INSURANCE_TYPE = [
    ("labor", "勞工保險"),
    ("health", "全民健康保險"),
    ("pension", "勞工退休金"),
    ("occupational", "職業災害保險"),
]


class HrLaborHealthInsuranceType(models.Model):
    _name = "hr.labor.health.insurance.type"
    _description = "保費費率版本"
    _order = "year desc, insurance_type"

    name = fields.Char(
        string="版本名稱",
        compute="_compute_name",
        store=True,
    )
    year = fields.Integer(string="適用年度", required=True)
    insurance_type = fields.Selection(
        selection=INSURANCE_TYPE,
        string="保險類別",
        required=True,
    )
    active = fields.Boolean(default=True)
    grade_ids = fields.One2many(
        "hr.labor.health.insurance", "version_id", string="等級表"
    )

    _sql_constraints = [
        (
            "unique_year_type",
            "UNIQUE(year, insurance_type)",
            "同一年度與保險類別只能有一個費率版本",
        ),
        (
            "year_positive",
            "CHECK(year > 1900)",
            "年度必須大於 1900",
        ),
    ]

    @api.depends("year", "insurance_type")
    def _compute_name(self):
        type_label = dict(INSURANCE_TYPE)
        for rec in self:
            rec.name = f"{rec.year} 年 {type_label.get(rec.insurance_type, '')}"


class HrLaborHealthInsurance(models.Model):
    _name = "hr.labor.health.insurance"
    _description = "勞健保費率等級表"
    _order = "version_id, insured_salary asc"

    version_id = fields.Many2one(
        "hr.labor.health.insurance.type",
        string="費率版本",
        required=True,
        ondelete="cascade",
    )
    year = fields.Integer(
        string="適用年度",
        related="version_id.year",
        store=True,
    )
    insurance_type = fields.Selection(
        selection=INSURANCE_TYPE,
        string="保險類別",
        related="version_id.insurance_type",
        store=True,
    )
    grade = fields.Integer(string="等級", required=True)
    # 投保薪資（投保等級對應之月薪上限）
    insured_salary = fields.Float(
        string="投保薪資（月）", digits=(12, 0), required=True
    )
    # 員工自付金額
    employee_labor = fields.Float(string="員工勞保費", digits=(10, 0))
    employee_health = fields.Float(string="員工健保費", digits=(10, 0))
    employee_pension = fields.Float(string="員工勞退費", digits=(10, 0))
    # 雇主負擔金額
    employer_labor = fields.Float(string="雇主勞保費", digits=(10, 0))
    employer_health = fields.Float(string="雇主健保費", digits=(10, 0))
    employer_pension = fields.Float(string="雇主勞退費", digits=(10, 0))
    employer_occupational = fields.Float(string="職災保費（雇主）", digits=(10, 0))
    employer_wage_guarantee = fields.Float(string="工資墊償基金（雇主）", digits=(10, 0))

    _sql_constraints = [
        (
            "insured_salary_positive",
            "CHECK(insured_salary > 0)",
            "投保薪資必須大於 0",
        ),
        (
            "unique_grade_version",
            "UNIQUE(version_id, grade)",
            "同一費率版本中每個等級只能有一筆",
        ),
    ]

    @api.constrains("grade")
    def _check_grade(self):
        for rec in self:
            if rec.grade <= 0:
                raise ValidationError("等級必須大於 0")

    @api.model
    def get_grade(self, salary, year, insurance_type="labor"):
        """依月薪與年度查詢對應投保等級記錄（取最接近且不低於薪資之等級）。"""
        version = self.env["hr.labor.health.insurance.type"].search(
            [("year", "=", year), ("insurance_type", "=", insurance_type)],
            limit=1,
        )
        if not version:
            return self.browse()
        grade = self.search(
            [
                ("version_id", "=", version.id),
                ("insured_salary", ">=", salary),
            ],
            order="insured_salary asc",
            limit=1,
        )
        if not grade:
            # 薪資超過最高等級，取最高等級
            grade = self.search(
                [("version_id", "=", version.id)],
                order="insured_salary desc",
                limit=1,
            )
        return grade
