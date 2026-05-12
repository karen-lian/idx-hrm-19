from odoo import api, fields, models
from odoo.exceptions import ValidationError

OVERTIME_DAY_TYPE = [
    ("weekday", "平日加班"),
    ("day_off", "休息日加班"),
    ("regular_holiday", "例假日加班"),
    ("regular_holiday_national_holiday", "國定假日加班"),
]

COMPENSATION_TYPE = [
    ("cash", "加班費（現金）"),
    ("leave", "補休"),
]


class HrOvertimeType(models.Model):
    _name = "hr.overtime.type"
    _description = "加班時段"

    name = fields.Char(string="加班時段", required=True)
    type = fields.Selection(
        selection=[("cash", "加班費"), ("leave", "補休")],
        string="加班類型",
        required=True,
    )
    leave_type_id = fields.Many2one("hr.leave.type", string="請假類型")
    rule_line_ids = fields.One2many(
        "hr.overtime.type.rule", "type_line_id", string="費率規則"
    )
    leave_line_ids = fields.One2many(
        "hr.overtime.type.leave", "type_line_id", string="休息時間"
    )
    overtime_type_date_rule = fields.Selection(
        selection=OVERTIME_DAY_TYPE,
        string="加班日期類型",
    )
    request_unit = fields.Selection(
        selection=[("hour", "小時"), ("half_an_hour", "半小時")],
        default="half_an_hour",
        string="加班最短時長",
        required=True,
    )
    minimum_overtime = fields.Boolean(string="時數最小以八小時計算", default=False)

    @api.constrains("request_unit")
    def check_request_unit(self):
        for rec in self:
            if rec.request_unit == "hour":
                leave_lines = self.env["hr.overtime.type.leave"].search(
                    [("type_line_id", "=", rec.id)]
                )
                for line in leave_lines:
                    if line.hrs % 1 != 0:
                        raise ValidationError(
                            "休息時間中有總時數最小單位不為「小時」的資料！"
                        )


class HrOvertimeTypeRule(models.Model):
    _name = "hr.overtime.type.rule"
    _description = "加班類型規則"

    type_line_id = fields.Many2one(
        "hr.overtime.type", string="加班時段", ondelete="cascade"
    )
    name = fields.Char(string="名稱", required=True)
    from_hrs = fields.Integer(string="區間（開始）")
    to_hrs = fields.Integer(string="區間（結束）")
    hrs_amount = fields.Float(string="費率", digits=(2, 8))
    no_taxable = fields.Boolean(string="不計入加班免稅總時數上限", default=False)

    @api.constrains("from_hrs", "to_hrs")
    def _check_hour_range(self):
        for rec in self:
            if rec.from_hrs >= rec.to_hrs:
                raise ValidationError(
                    f"區間開始（{rec.from_hrs}）必須小於區間結束（{rec.to_hrs}）"
                )
            domain = [
                ("id", "!=", rec.id),
                ("type_line_id", "=", rec.type_line_id.id),
                ("from_hrs", "<", rec.to_hrs),
                ("to_hrs", ">", rec.from_hrs),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    f"時段 {rec.from_hrs}～{rec.to_hrs} 與現有規則重疊"
                )

    def get_rate(self, hours, day_type):
        """依加班時數與日類型查詢對應費率與免稅標記。"""
        ot_type = self.env["hr.overtime.type"].search(
            [("overtime_type_date_rule", "=", day_type)],
            limit=1,
        )
        if not ot_type:
            return []
        result = []
        remaining = hours
        for rule in ot_type.rule_line_ids.sorted("from_hrs"):
            if remaining <= 0:
                break
            seg_start = rule.from_hrs
            seg_end = rule.to_hrs
            seg_hours = min(remaining, seg_end - seg_start)
            if seg_hours > 0:
                result.append(
                    {
                        "hour_from": seg_start,
                        "hour_to": seg_end,
                        "rate": rule.hrs_amount,
                        "is_tax_free": rule.no_taxable,
                        "hours_in_segment": seg_hours,
                    }
                )
                remaining -= seg_hours
        return result


class HrOvertimeTypeLeave(models.Model):
    _name = "hr.overtime.type.leave"
    _description = "加班類型休息時間"
    _order = "hour_from"

    type_line_id = fields.Many2one(
        "hr.overtime.type", string="加班時段", ondelete="cascade"
    )
    name = fields.Char(string="名稱", required=True)
    hour_from = fields.Float(string="開始時間", required=True)
    hour_to = fields.Float(string="結束時間", required=True)
    hrs = fields.Float(string="總時數", compute="_compute_total_hrs", store=True)

    @api.depends("hour_from", "hour_to")
    def _compute_total_hrs(self):
        for rec in self:
            rec.hrs = rec.hour_to - rec.hour_from

    @api.constrains("hour_from", "hour_to")
    def check_typetime(self):
        for rec in self:
            if rec.hour_from >= rec.hour_to:
                raise ValidationError("結束時間不可小於等於開始時間")
            if rec.hour_to % 0.5 != 0 or rec.hour_from % 0.5 != 0:
                raise ValidationError("開始或結束時間須為整點或 30 分")
            time_diff = rec.hour_to - rec.hour_from
            if rec.type_line_id.request_unit == "half_an_hour" and time_diff % 0.5 != 0:
                raise ValidationError(
                    "加班最短時長設為「半小時」時，休息時間最小單位也須設為半小時"
                )
            if rec.type_line_id.request_unit == "hour" and time_diff % 1 != 0:
                raise ValidationError(
                    "加班最短時長設為「小時」時，休息時間最小單位也須設為一小時"
                )

    @api.onchange("hour_from", "hour_to")
    def _onchange_hours(self):
        self.hour_from = max(0.0, min(self.hour_from, 23.99))
        self.hour_to = max(0.0, min(self.hour_to, 23.99))
        self.hour_to = max(self.hour_to, self.hour_from)
