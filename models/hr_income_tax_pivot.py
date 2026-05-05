from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrIncomeTaxPivot(models.Model):
    _name = "hr.income.tax.pivot"
    _description = "薪資所得扣繳稅額表"
    _order = "year desc, salary_from asc, dependents asc"

    name = fields.Char(
        string="名稱",
        compute="_compute_name",
        store=True,
    )
    year = fields.Integer(string="適用年度（西元）", required=True)
    # 薪資區間（月薪）
    salary_from = fields.Float(
        string="薪資起（含）", digits=(12, 0), required=True
    )
    salary_to = fields.Float(
        string="薪資迄（含）", digits=(12, 0), required=True
    )
    # 撫養親屬人數（0=無撫養親屬）
    dependents = fields.Integer(string="撫養親屬人數", required=True, default=0)
    # 應扣繳稅額
    tax_amount = fields.Float(string="扣繳稅額", digits=(12, 0), required=True)

    _sql_constraints = [
        (
            "tax_amount_positive",
            "CHECK(tax_amount >= 0)",
            "扣繳稅額不得為負數",
        ),
        (
            "dependents_non_negative",
            "CHECK(dependents >= 0)",
            "撫養親屬人數不得為負數",
        ),
        (
            "unique_year_salary_dependents",
            "UNIQUE(year, salary_from, salary_to, dependents)",
            "同一年度、薪資區間、撫養人數只能有一筆記錄",
        ),
    ]

    @api.depends("year", "salary_from", "salary_to", "dependents")
    def _compute_name(self):
        for rec in self:
            rec.name = (
                f"{rec.year} 年 {rec.salary_from:.0f}~{rec.salary_to:.0f} 元 "
                f"撫養 {rec.dependents} 人"
            )

    @api.constrains("salary_from", "salary_to")
    def _check_salary_range(self):
        for rec in self:
            if rec.salary_from < 0:
                raise ValidationError("薪資起不得為負數")
            if rec.salary_from > rec.salary_to:
                raise ValidationError(
                    f"薪資起（{rec.salary_from}）不得大於薪資迄（{rec.salary_to}）"
                )

    @api.constrains("year")
    def _check_year(self):
        for rec in self:
            if rec.year < 1900:
                raise ValidationError("年度必須大於 1900")

    @api.model
    def get_tax(self, salary, dependents, year=None):
        """依月薪、撫養人數（及年度）查詢應扣繳稅額。"""
        if not year:
            year = fields.Date.today().year
        record = self.search(
            [
                ("year", "=", year),
                ("salary_from", "<=", salary),
                ("salary_to", ">=", salary),
                ("dependents", "=", dependents),
            ],
            limit=1,
        )
        return record.tax_amount if record else 0.0
