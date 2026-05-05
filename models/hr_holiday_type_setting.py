from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrHolidayTypeSetting(models.Model):
    _name = "hr.holiday.type.setting"
    _description = "假別政策設定"
    _order = "sequence asc, name asc"

    name = fields.Char(string="假別名稱", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # 對應 Odoo 原生假別（hr.leave.type）
    holiday_type_id = fields.Many2one(
        "hr.leave.type",
        string="假別（系統）",
        ondelete="set null",
    )
    # 薪資規則代號（payslip rule code，用於薪資計算連動）
    payslip_rule_code = fields.Char(
        string="薪資規則代號",
    )
    # 給薪比例（0.0~1.0，1.0=全薪，0.5=半薪，0=無薪）
    pay_ratio = fields.Float(
        string="給薪比例",
        digits=(3, 2),
        default=1.0,
    )
    # 扣繳稅代號（財政部假別扣繳代碼）
    withholding_code = fields.Char(
        string="扣繳代號",
    )
    # 每年度額度（天數，0=無上限）
    annual_quota_days = fields.Float(
        string="年度額度（天）",
        digits=(5, 1),
        default=0.0,
    )
    # 是否可遞延至下年度
    allow_carry_over = fields.Boolean(
        string="可遞延至下年度",
        default=False,
    )
    # 遞延上限（天，0=全數可遞延）
    carry_over_limit_days = fields.Float(
        string="遞延上限（天）",
        digits=(5, 1),
        default=0.0,
    )
    # 備註
    note = fields.Text(string="說明")

    _sql_constraints = [
        (
            "pay_ratio_range",
            "CHECK(pay_ratio >= 0 AND pay_ratio <= 1)",
            "給薪比例必須介於 0 到 1 之間",
        ),
        (
            "annual_quota_non_negative",
            "CHECK(annual_quota_days >= 0)",
            "年度額度不得為負數",
        ),
        (
            "carry_over_non_negative",
            "CHECK(carry_over_limit_days >= 0)",
            "遞延上限不得為負數",
        ),
    ]

    @api.constrains("payslip_rule_code")
    def _check_payslip_rule_code(self):
        for rec in self:
            if rec.payslip_rule_code and len(rec.payslip_rule_code.strip()) == 0:
                raise ValidationError("薪資規則代號不得為空字串")
