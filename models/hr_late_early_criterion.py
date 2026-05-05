from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrLateEarlyCriterion(models.Model):
    _name = "hr.late.early.criterion"
    _description = "遲到早退扣款標準"
    _order = "minute_from asc"

    name = fields.Char(
        string="名稱",
        compute="_compute_name",
        store=True,
    )
    minute_from = fields.Integer(string="分鐘起（含）", required=True)
    minute_to = fields.Integer(string="分鐘迄（含）", required=True)
    deduction = fields.Float(string="扣款金額", digits=(12, 0), required=True)

    _sql_constraints = [
        (
            "deduction_positive",
            "CHECK(deduction >= 0)",
            "扣款金額不得為負數",
        ),
        (
            "minute_from_positive",
            "CHECK(minute_from >= 0)",
            "分鐘起不得為負數",
        ),
    ]

    @api.depends("minute_from", "minute_to", "deduction")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.minute_from}–{rec.minute_to} 分鐘：扣 {rec.deduction:.0f} 元"

    @api.constrains("minute_from", "minute_to")
    def _check_minute_range(self):
        for rec in self:
            if rec.minute_from > rec.minute_to:
                raise ValidationError(
                    f"分鐘起（{rec.minute_from}）不得大於分鐘迄（{rec.minute_to}）"
                )
            # 區間重疊檢查（排除自身）
            domain = [
                ("id", "!=", rec.id),
                ("minute_from", "<=", rec.minute_to),
                ("minute_to", ">=", rec.minute_from),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    f"分鐘區間 {rec.minute_from}–{rec.minute_to} 與現有記錄重疊"
                )

    def get_deduction(self, minutes):
        """依遲到/早退分鐘數查詢對應扣款金額。"""
        criterion = self.search(
            [("minute_from", "<=", minutes), ("minute_to", ">=", minutes)],
            limit=1,
        )
        return criterion.deduction if criterion else 0.0
