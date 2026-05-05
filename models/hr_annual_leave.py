from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrAnnualLeave(models.Model):
    _name = "hr.annual.leave"
    _description = "特休年資對照表"
    _order = "tenure_from asc"

    name = fields.Char(
        string="名稱",
        compute="_compute_name",
        store=True,
    )
    # 年資區間（年，可含小數，例：0.5 = 6 個月）
    tenure_from = fields.Float(
        string="年資起（年，含）", digits=(5, 2), required=True
    )
    tenure_to = fields.Float(
        string="年資迄（年，不含）", digits=(5, 2), required=True
    )
    # 基本特休天數
    leave_days = fields.Float(
        string="特休天數", digits=(5, 1), required=True
    )
    # 是否為遞增規則（10 年以上每年 +1 天，上限 30 天）
    is_incremental = fields.Boolean(
        string="年資遞增規則", default=False
    )
    # 遞增基準年資（遞增規則起點，例：10 年）
    incremental_base_tenure = fields.Float(
        string="遞增基準年資（年）", digits=(5, 2), default=0.0
    )
    # 遞增基準天數（遞增規則基礎天數，例：15 天）
    incremental_base_days = fields.Float(
        string="遞增基準天數", digits=(5, 1), default=0.0
    )
    # 每增加 1 年多給 N 天
    incremental_days_per_year = fields.Float(
        string="每年遞增天數", digits=(4, 1), default=1.0
    )
    # 遞增上限天數（勞基法：最高 30 天）
    incremental_max_days = fields.Float(
        string="遞增上限天數", digits=(4, 1), default=30.0
    )

    _sql_constraints = [
        (
            "leave_days_positive",
            "CHECK(leave_days >= 0)",
            "特休天數不得為負數",
        ),
        (
            "tenure_from_non_negative",
            "CHECK(tenure_from >= 0)",
            "年資起不得為負數",
        ),
    ]

    @api.depends("tenure_from", "tenure_to", "leave_days")
    def _compute_name(self):
        for rec in self:
            rec.name = (
                f"年資 {rec.tenure_from}~{rec.tenure_to} 年：{rec.leave_days:.1f} 天"
            )

    @api.constrains("tenure_from", "tenure_to")
    def _check_tenure_range(self):
        for rec in self:
            if rec.tenure_from >= rec.tenure_to and not rec.is_incremental:
                raise ValidationError(
                    f"年資起（{rec.tenure_from}）必須小於年資迄（{rec.tenure_to}）"
                )
            # 區間重疊檢查
            domain = [
                ("id", "!=", rec.id),
                ("is_incremental", "=", False),
                ("tenure_from", "<", rec.tenure_to),
                ("tenure_to", ">", rec.tenure_from),
            ]
            if not rec.is_incremental and self.search_count(domain):
                raise ValidationError(
                    f"年資區間 {rec.tenure_from}~{rec.tenure_to} 與現有記錄重疊"
                )

    @api.model
    def get_leave_days(self, tenure_years):
        """依年資（年）查詢對應特休天數。
        遞增規則：10 年以上每多 1 年加 incremental_days_per_year 天，上限 30 天。
        """
        # 先查固定區間（非遞增）
        record = self.search(
            [
                ("is_incremental", "=", False),
                ("tenure_from", "<=", tenure_years),
                ("tenure_to", ">", tenure_years),
            ],
            limit=1,
        )
        if record:
            return record.leave_days

        # 查遞增規則
        inc_rule = self.search(
            [("is_incremental", "=", True)],
            order="incremental_base_tenure desc",
            limit=1,
        )
        if inc_rule and tenure_years >= inc_rule.incremental_base_tenure:
            extra_years = int(tenure_years - inc_rule.incremental_base_tenure)
            days = (
                inc_rule.incremental_base_days
                + extra_years * inc_rule.incremental_days_per_year
            )
            return min(days, inc_rule.incremental_max_days)

        return 0.0
