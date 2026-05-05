from odoo import api, fields, models
from odoo.exceptions import ValidationError

# 加班類型代號：對應勞基法各條款加班情境
OVERTIME_DAY_TYPE = [
    ("weekday", "平日加班"),
    ("rest_day", "休假日加班"),
    ("mandatory_rest", "例假日加班"),
    ("public_holiday", "國定假日加班"),
]

COMPENSATION_TYPE = [
    ("cash", "加班費（現金）"),
    ("leave", "補休"),
]


class HrOvertimeSetting(models.Model):
    _name = "hr.overtime.setting"
    _description = "加班全域設定"

    name = fields.Char(string="設定名稱", required=True, default="加班設定")
    active = fields.Boolean(default=True)
    # 每月加班上限（勞基法 §32：每月不得超過 46 小時）
    monthly_limit_hours = fields.Float(
        string="每月加班上限（小時）", digits=(5, 1), default=46.0
    )
    # 單日加班上限（勞基法 §32：每日不得超過 4 小時）
    daily_limit_hours = fields.Float(
        string="單日加班上限（小時）", digits=(4, 1), default=4.0
    )
    overtime_type_ids = fields.One2many(
        "hr.overtime.type", "setting_id", string="加班類型費率表"
    )

    _sql_constraints = [
        (
            "monthly_limit_positive",
            "CHECK(monthly_limit_hours > 0)",
            "每月加班上限必須大於 0",
        ),
        (
            "daily_limit_positive",
            "CHECK(daily_limit_hours > 0)",
            "單日加班上限必須大於 0",
        ),
    ]


class HrOvertimeType(models.Model):
    _name = "hr.overtime.type"
    _description = "加班類型"
    _order = "day_type, sequence"

    setting_id = fields.Many2one(
        "hr.overtime.setting", string="加班設定", required=True, ondelete="cascade"
    )
    name = fields.Char(string="類型名稱", required=True)
    sequence = fields.Integer(default=10)
    day_type = fields.Selection(
        selection=OVERTIME_DAY_TYPE,
        string="加班日類型",
        required=True,
    )
    compensation_type = fields.Selection(
        selection=COMPENSATION_TYPE,
        string="預設補償方式",
        default="cash",
    )
    # 補休換算比例（1 小時加班 = N 小時補休）
    leave_conversion_ratio = fields.Float(
        string="補休換算比例", digits=(4, 2), default=1.0
    )
    rule_ids = fields.One2many(
        "hr.overtime.type.rule", "overtime_type_id", string="費率規則"
    )

    _sql_constraints = [
        (
            "leave_conversion_ratio_positive",
            "CHECK(leave_conversion_ratio > 0)",
            "補休換算比例必須大於 0",
        ),
    ]


class HrOvertimeTypeRule(models.Model):
    _name = "hr.overtime.type.rule"
    _description = "加班費率規則"
    _order = "hour_from asc"

    overtime_type_id = fields.Many2one(
        "hr.overtime.type", string="加班類型", required=True, ondelete="cascade"
    )
    name = fields.Char(
        string="規則名稱",
        compute="_compute_name",
        store=True,
    )
    # 時段起迄（小時，含）
    hour_from = fields.Float(string="小時起（含）", digits=(4, 1), required=True)
    hour_to = fields.Float(string="小時迄（含）", digits=(4, 1), required=True)
    # 費率倍數（例：4/3 ≈ 1.3333）
    rate = fields.Float(string="費率倍數", digits=(6, 4), required=True)
    # 是否為免稅加班費（例假日/國定假日之基本保障部分）
    is_tax_free = fields.Boolean(string="免稅", default=False)

    _sql_constraints = [
        (
            "rate_positive",
            "CHECK(rate > 0)",
            "費率倍數必須大於 0",
        ),
        (
            "hour_from_positive",
            "CHECK(hour_from >= 0)",
            "小時起不得為負數",
        ),
    ]

    @api.depends("hour_from", "hour_to", "rate", "is_tax_free")
    def _compute_name(self):
        for rec in self:
            tax_label = "（免稅）" if rec.is_tax_free else ""
            rec.name = (
                f"第 {rec.hour_from:.0f}~{rec.hour_to:.0f} 小時：×{rec.rate:.4f}{tax_label}"
            )

    @api.constrains("hour_from", "hour_to")
    def _check_hour_range(self):
        for rec in self:
            if rec.hour_from >= rec.hour_to:
                raise ValidationError(
                    f"小時起（{rec.hour_from}）必須小於小時迄（{rec.hour_to}）"
                )
            # 同一 overtime_type 內的時段不得重疊
            domain = [
                ("id", "!=", rec.id),
                ("overtime_type_id", "=", rec.overtime_type_id.id),
                ("hour_from", "<", rec.hour_to),
                ("hour_to", ">", rec.hour_from),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    f"時段 {rec.hour_from}~{rec.hour_to} 小時與現有規則重疊"
                )

    def get_rate(self, hours, day_type, setting=None):
        """依加班時數與日類型查詢對應費率與免稅標記。
        回傳 list of dict: [{hour_from, hour_to, rate, is_tax_free, hours_in_segment}]
        """
        if not setting:
            setting = self.env["hr.overtime.setting"].search(
                [("active", "=", True)], limit=1
            )
        ot_type = self.env["hr.overtime.type"].search(
            [
                ("setting_id", "=", setting.id),
                ("day_type", "=", day_type),
            ],
            limit=1,
        )
        if not ot_type:
            return []
        result = []
        remaining = hours
        for rule in ot_type.rule_ids.sorted("hour_from"):
            if remaining <= 0:
                break
            seg_start = rule.hour_from
            seg_end = rule.hour_to
            seg_hours = min(remaining, seg_end - seg_start)
            if seg_hours > 0:
                result.append(
                    {
                        "hour_from": seg_start,
                        "hour_to": seg_end,
                        "rate": rule.rate,
                        "is_tax_free": rule.is_tax_free,
                        "hours_in_segment": seg_hours,
                    }
                )
                remaining -= seg_hours
        return result
