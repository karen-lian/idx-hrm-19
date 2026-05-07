"""加班費計算引擎（純函式 + service model）。

法規依據：
- 平日加班費：勞基法第 24 條（4/3 + 5/3）
- 休假日加班費：勞基法第 24 條第 2 項（4/3 + 5/3 + 8/3）
- 例假日加班費：勞基法第 36、40 條（第 1~8h 免稅 ×1；第 9h+ 應稅 ×2）
- 國定假日加班費：勞基法第 39 條（第 1~8h 免稅 ×1；第 9~10h 應稅 ×4/3；第 11h+ 應稅 ×5/3）
"""
from decimal import ROUND_HALF_UP, Decimal

from odoo import api, models

_RATE_4_3 = Decimal("4") / Decimal("3")
_RATE_5_3 = Decimal("5") / Decimal("3")
_RATE_8_3 = Decimal("8") / Decimal("3")
_RATE_1 = Decimal("1")
_RATE_2 = Decimal("2")


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _round_currency(amount: Decimal) -> float:
    return float(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calc_weekday_overtime(hours: float, hourly_rate: float) -> dict:
    """平日加班費（勞基法 §24）：第 1~2h ×4/3，第 3h+ ×5/3，全部應稅。"""
    h, r = _dec(hours), _dec(hourly_rate)
    taxable = min(h, _dec(2)) * r * _RATE_4_3
    if h > _dec(2):
        taxable += (h - _dec(2)) * r * _RATE_5_3
    return {"tax_free_amount": 0.0, "taxable_amount": _round_currency(taxable), "total_amount": _round_currency(taxable)}


def calc_rest_day_overtime(hours: float, hourly_rate: float) -> dict:
    """休假日加班費（勞基法 §24-2）：第 1~2h ×4/3，第 3~8h ×5/3，第 9h+ ×8/3，全部應稅。"""
    h, r = _dec(hours), _dec(hourly_rate)
    taxable = min(h, _dec(2)) * r * _RATE_4_3
    if h > _dec(2):
        taxable += min(h - _dec(2), _dec(6)) * r * _RATE_5_3
    if h > _dec(8):
        taxable += (h - _dec(8)) * r * _RATE_8_3
    return {"tax_free_amount": 0.0, "taxable_amount": _round_currency(taxable), "total_amount": _round_currency(taxable)}


def calc_mandatory_rest_overtime(hours: float, hourly_rate: float) -> dict:
    """例假日加班費（勞基法 §36、§40）：第 1~8h 免稅 ×1，第 9h+ 應稅 ×2。"""
    h, r = _dec(hours), _dec(hourly_rate)
    tax_free = min(h, _dec(8)) * r * _RATE_1
    taxable = (h - _dec(8)) * r * _RATE_2 if h > _dec(8) else Decimal("0")
    return {"tax_free_amount": _round_currency(tax_free), "taxable_amount": _round_currency(taxable), "total_amount": _round_currency(tax_free + taxable)}


def calc_public_holiday_overtime(hours: float, hourly_rate: float) -> dict:
    """國定假日加班費（勞基法 §39）：第 1~8h 免稅 ×1，第 9~10h 應稅 ×4/3，第 11h+ 應稅 ×5/3。"""
    h, r = _dec(hours), _dec(hourly_rate)
    tax_free = min(h, _dec(8)) * r * _RATE_1
    taxable = Decimal("0")
    if h > _dec(8):
        taxable += min(h - _dec(8), _dec(2)) * r * _RATE_4_3
    if h > _dec(10):
        taxable += (h - _dec(10)) * r * _RATE_5_3
    return {"tax_free_amount": _round_currency(tax_free), "taxable_amount": _round_currency(taxable), "total_amount": _round_currency(tax_free + taxable)}


_CALC_MAP = {
    "weekday": calc_weekday_overtime,
    "rest_day": calc_rest_day_overtime,
    "mandatory_rest": calc_mandatory_rest_overtime,
    "public_holiday": calc_public_holiday_overtime,
}


class HrOvertimeCalculation(models.AbstractModel):
    """薪資 rule 可呼叫的加班費計算 service（無資料表）。"""
    _name = "hr.overtime.calculation"
    _description = "加班費計算引擎"

    @api.model
    def calculate(self, hours: float, day_type: str, hourly_rate: float) -> dict:
        """回傳 {tax_free_amount, taxable_amount, total_amount}。"""
        fn = _CALC_MAP.get(day_type)
        if not fn:
            return {"tax_free_amount": 0.0, "taxable_amount": 0.0, "total_amount": 0.0}
        return fn(hours, hourly_rate)
