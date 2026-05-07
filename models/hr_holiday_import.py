"""PR-059：政府辦公日曆表匯入（國定假日）"""
import logging
import requests
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 政府開放資料 API（人事行政總處行事曆）
TW_HOLIDAY_API = (
    "https://data.ntpc.gov.tw/api/datasets/"
    "308DCD75-6434-45BC-A95F-584DA4FED251/json"
)


class ResourceCalendarLeaves(models.Model):
    """PR-059：擴充 resource.calendar.leaves 加入台灣假日匯入功能"""
    _inherit = "resource.calendar.leaves"

    is_tw_national_holiday = fields.Boolean(
        string="台灣國定假日",
        default=False,
    )
    roc_year = fields.Integer(string="民國年")


class ResourceCalendar(models.Model):
    """PR-059：工作日曆加入國定假日匯入按鈕"""
    _inherit = "resource.calendar"

    def _import_tw_holidays(self, year):
        """PR-059：從政府開放資料 API 匯入國定假日。

        回傳 dict：{'created': N, 'skipped': M, 'error': msg}
        """
        self.ensure_one()
        roc_year = year - 1911
        try:
            resp = requests.get(TW_HOLIDAY_API, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            _logger.error("台灣假日 API 呼叫失敗：%s", e)
            raise UserError(f"無法連線至政府假日 API：{e}")

        created = 0
        skipped = 0
        Leaves = self.env["resource.calendar.leaves"]

        for item in data:
            date_str = item.get("date", "")
            name = item.get("description", "國定假日")
            is_holiday = item.get("isHoliday", "0") == "1"
            if not date_str or not is_holiday:
                continue
            if not date_str.startswith(str(year)):
                continue

            try:
                holiday_date = fields.Date.from_string(
                    f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                )
            except Exception:
                continue

            existing = Leaves.search([
                ("calendar_id", "=", self.id),
                ("date_from", ">=", fields.Datetime.from_string(f"{holiday_date} 00:00:00")),
                ("date_from", "<=", fields.Datetime.from_string(f"{holiday_date} 23:59:59")),
                ("is_tw_national_holiday", "=", True),
            ])
            if existing:
                skipped += 1
                continue

            Leaves.create({
                "name": name,
                "calendar_id": self.id,
                "date_from": fields.Datetime.from_string(f"{holiday_date} 00:00:00"),
                "date_to": fields.Datetime.from_string(f"{holiday_date} 23:59:59"),
                "is_tw_national_holiday": True,
                "roc_year": roc_year,
            })
            created += 1

        _logger.info("台灣假日匯入完成：新建 %d 筆，跳過 %d 筆", created, skipped)
        return {"created": created, "skipped": skipped}

    def action_import_tw_holidays(self):
        """UI 按鈕：匯入今年台灣國定假日。"""
        year = fields.Date.today().year
        result = self._import_tw_holidays(year)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": f"匯入完成！新建 {result['created']} 筆，跳過 {result['skipped']} 筆。",
                "type": "success",
            },
        }
