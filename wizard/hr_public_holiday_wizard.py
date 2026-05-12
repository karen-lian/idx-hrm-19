"""國定假日匯入 Wizard（Odoo 19）
參考 odoo14 hr_public_holiday.py 邏輯，調整為 Odoo 19 相容版本。

主要差異：
- Odoo 19 的 resource.calendar.leaves 使用 UTC datetime，
  匯入時依工作日曆的 tz 轉換。
- leave_type 選項與 CALENDAR_LEAVE_TYPE 對齊：
    day_off / regular_holiday / regular_holiday_national_holiday
- 去除已廢棄的 'year' 欄位（Odoo 19 resource.calendar.leaves 無此欄位），
  改以 roc_year（本模組自訂欄位）儲存民國年。
"""
import json
import logging
import pytz
import requests
from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

# 政府開放資料 API（新北市人事行政總處行事曆，含全年假日清單）
API_CALENDAR_TAIWAN = (
    "https://data.ntpc.gov.tw/api/datasets/"
    "308DCD75-6434-45BC-A95F-584DA4FED251/json"
)

WEEKDAY_MAP = {
    "SUN": "0",
    "MON": "1",
    "TUE": "2",
    "WED": "3",
    "THU": "4",
    "FRI": "5",
    "SAT": "6",
}


class HrPublicHolidayWizard(models.TransientModel):
    _name = "hr.public.holiday.wizard"
    _description = "國定假日匯入精靈"

    calendar_id = fields.Many2one(
        "resource.calendar",
        string="工作時間表",
        required=True,
        readonly=True,
    )
    specify_year = fields.Char(
        string="西元年度",
        required=True,
        default=lambda self: str(fields.Date.today().year),
        help="要匯入的西元年份，例如 2025",
    )
    day_off = fields.Selection(
        [
            ("SUN", "日"), ("MON", "一"), ("TUE", "二"),
            ("WED", "三"), ("THU", "四"), ("FRI", "五"), ("SAT", "六"),
        ],
        string="休假日（休息日）預設星期",
        default="SAT",
        required=True,
        help="政府公告假日中，落在此星期的記為「休息日」",
    )
    regular_holiday = fields.Selection(
        [
            ("SUN", "日"), ("MON", "一"), ("TUE", "二"),
            ("WED", "三"), ("THU", "四"), ("FRI", "五"), ("SAT", "六"),
        ],
        string="例假日預設星期",
        default="SUN",
        required=True,
        help="政府公告假日中，落在此星期的記為「例假日」",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        calendar_id = self._context.get("active_id")
        if calendar_id:
            res["calendar_id"] = calendar_id
        return res

    # ── 主要匯入方法 ─────────────────────────────────────────────

    def action_import(self):
        """按下「確認匯入」後執行。"""
        self.ensure_one()
        calendar = self.calendar_id
        if not calendar:
            raise UserError(_("找不到工作時間表，請重新開啟視窗。"))

        specify_year = self.specify_year.strip()
        if not specify_year.isdigit() or len(specify_year) != 4:
            raise UserError(_("年度格式錯誤，請輸入 4 位西元年，例如 2025。"))
        year = int(specify_year)
        roc_year = year - 1911

        # 確認該年度是否已匯入（以 roc_year 判斷）
        already = self.env["resource.calendar.leaves"].search_count([
            ("calendar_id", "=", calendar.id),
            ("roc_year", "=", roc_year),
        ])
        if already > 0:
            raise UserError(_(f"民國 {roc_year} 年（西元 {year} 年）假日已匯入，請勿重複匯入。"))

        # 取得工作日曆時區，用於 UTC 轉換
        tz_name = calendar.tz or "Asia/Taipei"
        calendar_tz = pytz.timezone(tz_name)

        dates = self._get_days_from_api()
        created = 0
        skipped = 0
        Leaves = self.env["resource.calendar.leaves"]

        for item in dates:
            date_str = item.get("date", "")
            # API 欄位：isHoliday（新版）或 isholiday（舊版），值為 "1"/"是"
            is_holiday = (
                item.get("isHoliday") == "1"
                or item.get("isholiday") == "是"
            )
            if not date_str or not is_holiday:
                continue
            # 只處理指定年份
            if not date_str.startswith(str(year)):
                continue

            try:
                date_local = datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                _logger.warning("假日日期格式異常，跳過：%s", date_str)
                continue

            # 轉 UTC（工作日曆時區 → UTC）
            dt_start_local = calendar_tz.localize(
                datetime.combine(date_local, time.min), is_dst=None
            )
            dt_end_local = calendar_tz.localize(
                datetime.combine(date_local, time.max), is_dst=None
            )
            dt_start_utc = dt_start_local.astimezone(pytz.utc).replace(tzinfo=None)
            dt_end_utc = dt_end_local.astimezone(pytz.utc).replace(tzinfo=None)

            # 取假日名稱
            name = (
                item.get("name") or item.get("description") or
                item.get("holidaycategory") or "國定假日"
            )
            if not name.strip():
                name = "國定假日"

            # 重複判斷
            existing = Leaves.search([
                ("calendar_id", "=", calendar.id),
                ("date_from", "=", fields.Datetime.to_string(dt_start_utc)),
                ("date_to", "=", fields.Datetime.to_string(dt_end_utc)),
            ])
            if existing:
                skipped += 1
                continue

            # 判斷假日類型（依星期）
            week_of_day = date_local.strftime("%w")  # "0"=Sun … "6"=Sat
            if WEEKDAY_MAP[self.day_off] == week_of_day:
                leave_type = "day_off"
            elif WEEKDAY_MAP[self.regular_holiday] == week_of_day:
                leave_type = "regular_holiday"
            else:
                leave_type = "regular_holiday_national_holiday"

            Leaves.create({
                "name": name,
                "calendar_id": calendar.id,
                "resource_id": False,
                "date_from": fields.Datetime.to_string(dt_start_utc),
                "date_to": fields.Datetime.to_string(dt_end_utc),
                "leave_type": leave_type,
                "roc_year": roc_year,
            })
            created += 1

        _logger.info("國定假日匯入完成：新建 %d 筆，跳過 %d 筆", created, skipped)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("匯入完成"),
                "message": _(
                    f"西元 {year} 年（民國 {roc_year} 年）假日匯入完成！\n"
                    f"新建 {created} 筆，跳過 {skipped} 筆。"
                ),
                "type": "success",
                "sticky": False,
            },
        }

    # ── 呼叫政府 API ─────────────────────────────────────────────

    def _get_days_from_api(self):
        """分頁取得政府開放資料全部假日清單。"""
        date_array = []
        page = 0
        while True:
            url = f"{API_CALENDAR_TAIWAN}?page={page}&size=1000"
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                batch = resp.json()
            except requests.exceptions.Timeout:
                raise UserError(_("連線政府假日 API 逾時，請稍後再試。"))
            except Exception as e:
                raise UserError(_(f"無法取得政府假日資料：{e}"))
            if not batch:
                break
            date_array.extend(batch)
            page += 1
        return date_array
