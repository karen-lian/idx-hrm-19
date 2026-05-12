"""resource.calendar.leaves 擴充欄位（假日類型、民國年）"""
from odoo import fields, models

# 假別類型選項（公眾假日用，不含平日——平日為預設，不需標記）
CALENDAR_LEAVE_TYPE = [
    ("day_off", "休息日"),
    ("regular_holiday", "例假日"),
    ("regular_holiday_national_holiday", "國定假日"),
]


class ResourceCalendarLeaves(models.Model):
    """擴充 resource.calendar.leaves，加入台灣假日類型與民國年欄位。

    leave_type 記錄假日對應的加班日期類型，讓加班申請單可自動帶入加班時段。
    以台灣公眾假日而言，假日日期一定代表整天（00:00 ~ 23:59:59 UTC）。
    """
    _inherit = "resource.calendar.leaves"

    leave_type = fields.Selection(
        selection=CALENDAR_LEAVE_TYPE,
        string="假日類型",
        help="對應加班申請的日期類型（休息日、例假日、國定假日）。\n"
             "台灣公眾假日一定代表整天（全天假期）。\n"
             "未標記的日期預設為平日。",
    )
    roc_year = fields.Integer(string="民國年")
