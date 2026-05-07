"""加班費計算引擎（hr.overtime 申請模型 + 免稅/應稅分拆邏輯）。

法規依據：
- 平日加班費：勞基法第 24 條（4/3 + 5/3）
- 休假日加班費：勞基法第 24 條第 2 項（4/3 + 5/3 + 8/3）
- 例假日加班費：勞基法第 36、40 條（第 1~8h 免稅 ×1；第 9h+ 應稅 ×2）
- 國定假日加班費：勞基法第 39 條（第 1~8h 免稅 ×1；第 9~10h 應稅 ×4/3；第 11h+ 應稅 ×5/3）
"""
from decimal import ROUND_HALF_UP, Decimal

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# 加班費分段費率常數（精確小數，避免浮點累計誤差）
_RATE_4_3 = Decimal("4") / Decimal("3")
_RATE_5_3 = Decimal("5") / Decimal("3")
_RATE_8_3 = Decimal("8") / Decimal("3")
_RATE_1 = Decimal("1")
_RATE_2 = Decimal("2")

OT_DAY_TYPE = [
    ("weekday", "平日加班"),
    ("rest_day", "休假日加班"),
    ("mandatory_rest", "例假日加班"),
    ("public_holiday", "國定假日加班"),
]

COMPENSATION_TYPE = [
    ("cash", "加班費（現金）"),
    ("leave", "補休"),
]

OT_STATE = [
    ("draft", "草稿"),
    ("pending", "待審核"),
    ("approved", "核准"),
    ("refused", "退回"),
]


def _dec(value) -> Decimal:
    """將 float/int 轉為 Decimal，統一精度運算。"""
    return Decimal(str(value))


def _round_currency(amount: Decimal) -> float:
    """加班費四捨五入至整數（新台幣不含小數）。"""
    return float(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# 純函式：各類型加班費分段計算
# ---------------------------------------------------------------------------


def calc_weekday_overtime(hours: float, hourly_rate: float) -> dict:
    """平日加班費分段計算（勞基法 §24）。

    第 1~2 小時：×4/3；第 3 小時以上：×5/3。
    全部為應稅。
    """
    h = _dec(hours)
    r = _dec(hourly_rate)
    taxable = Decimal("0")

    seg1 = min(h, _dec(2))
    taxable += seg1 * r * _RATE_4_3

    if h > _dec(2):
        seg2 = h - _dec(2)
        taxable += seg2 * r * _RATE_5_3

    return {
        "tax_free_amount": 0.0,
        "taxable_amount": _round_currency(taxable),
        "total_amount": _round_currency(taxable),
    }


def calc_rest_day_overtime(hours: float, hourly_rate: float) -> dict:
    """休假日加班費分段計算（勞基法 §24-2）。

    第 1~2 小時：×4/3；第 3~8 小時：×5/3；第 9 小時以上：×8/3。
    全部為應稅。
    """
    h = _dec(hours)
    r = _dec(hourly_rate)
    taxable = Decimal("0")

    seg1 = min(h, _dec(2))
    taxable += seg1 * r * _RATE_4_3

    if h > _dec(2):
        seg2 = min(h - _dec(2), _dec(6))
        taxable += seg2 * r * _RATE_5_3

    if h > _dec(8):
        seg3 = h - _dec(8)
        taxable += seg3 * r * _RATE_8_3

    return {
        "tax_free_amount": 0.0,
        "taxable_amount": _round_currency(taxable),
        "total_amount": _round_currency(taxable),
    }


def calc_mandatory_rest_overtime(hours: float, hourly_rate: float) -> dict:
    """例假日加班費分段計算（勞基法 §36、§40）。

    第 1~8 小時：×1（免稅，最低保障）；第 9 小時以上：×2（應稅）。
    """
    h = _dec(hours)
    r = _dec(hourly_rate)

    tax_free_h = min(h, _dec(8))
    tax_free = tax_free_h * r * _RATE_1

    taxable = Decimal("0")
    if h > _dec(8):
        taxable = (h - _dec(8)) * r * _RATE_2

    return {
        "tax_free_amount": _round_currency(tax_free),
        "taxable_amount": _round_currency(taxable),
        "total_amount": _round_currency(tax_free + taxable),
    }


def calc_public_holiday_overtime(hours: float, hourly_rate: float) -> dict:
    """國定假日加班費分段計算（勞基法 §39）。

    第 1~8 小時：×1（免稅）；第 9~10 小時：×4/3（應稅）；第 11 小時以上：×5/3（應稅）。
    """
    h = _dec(hours)
    r = _dec(hourly_rate)

    tax_free_h = min(h, _dec(8))
    tax_free = tax_free_h * r * _RATE_1

    taxable = Decimal("0")
    if h > _dec(8):
        seg2_h = min(h - _dec(8), _dec(2))
        taxable += seg2_h * r * _RATE_4_3

    if h > _dec(10):
        seg3_h = h - _dec(10)
        taxable += seg3_h * r * _RATE_5_3

    return {
        "tax_free_amount": _round_currency(tax_free),
        "taxable_amount": _round_currency(taxable),
        "total_amount": _round_currency(tax_free + taxable),
    }


_CALC_MAP = {
    "weekday": calc_weekday_overtime,
    "rest_day": calc_rest_day_overtime,
    "mandatory_rest": calc_mandatory_rest_overtime,
    "public_holiday": calc_public_holiday_overtime,
}


# ---------------------------------------------------------------------------
# Odoo 模型：hr.overtime 加班申請
# ---------------------------------------------------------------------------


class HrOvertime(models.Model):
    _name = "hr.overtime"
    _description = "加班申請"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="加班編號",
        readonly=True,
        default="新增",
        copy=False,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        index=True,
        tracking=True,
    )
    contract_id = fields.Many2one(
        "hr.version",
        string="薪資版本",
        compute="_compute_contract_id",
        store=True,
    )
    department_id = fields.Many2one(
        related="employee_id.department_id",
        string="部門",
        store=True,
    )
    date = fields.Date(string="加班日期", required=True, tracking=True)
    time_start = fields.Float(string="開始時間", digits=(4, 2))
    time_end = fields.Float(string="結束時間", digits=(4, 2))
    hours = fields.Float(
        string="加班時數",
        compute="_compute_hours",
        store=True,
        digits=(5, 2),
    )
    day_type = fields.Selection(
        selection=OT_DAY_TYPE,
        string="加班日類型",
        required=True,
        tracking=True,
    )
    compensation_type = fields.Selection(
        selection=COMPENSATION_TYPE,
        string="補償方式",
        default="cash",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=OT_STATE,
        string="狀態",
        default="draft",
        tracking=True,
    )
    hour_salary = fields.Float(
        string="加班時薪",
        compute="_compute_hour_salary",
        store=True,
        digits=(10, 2),
        help="取自合約 hour_salary，月薪÷30÷8",
    )

    # --- 加班費計算結果 ---
    tax_free_amount = fields.Float(
        string="免稅加班費",
        compute="_compute_overtime_pay",
        store=True,
        digits=(12, 0),
    )
    taxable_amount = fields.Float(
        string="應稅加班費",
        compute="_compute_overtime_pay",
        store=True,
        digits=(12, 0),
    )
    total_amount = fields.Float(
        string="加班費合計",
        compute="_compute_overtime_pay",
        store=True,
        digits=(12, 0),
    )

    # --- 月加班時數警示 ---
    monthly_hours = fields.Float(
        string="當月累計加班時數",
        compute="_compute_monthly_hours",
        digits=(5, 2),
    )
    over_monthly_limit = fields.Boolean(
        string="超過月加班上限",
        compute="_compute_monthly_hours",
    )

    # --- 補休相關 ---
    leave_compensatory_id = fields.Many2one(
        "hr.leave.allocation",
        string="補休配額",
        readonly=True,
    )

    _sql_constraints = [
        (
            "hours_positive",
            "CHECK(hours > 0 OR time_start = 0)",
            "加班時數必須大於 0",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"].next_by_code("hr.overtime")
        for vals in vals_list:
            if vals.get("name", "新增") == "新增":
                vals["name"] = seq or "OT-0001"
        return super().create(vals_list)

    @api.depends("employee_id", "date")
    def _compute_contract_id(self):
        for rec in self:
            if not rec.employee_id or not rec.date:
                rec.contract_id = False
                continue
            # 找加班日期當天有效的版本（contract_date_start <= date <= contract_date_end 或無結束日）
            version = self.env["hr.version"].search(
                [
                    ("employee_id", "=", rec.employee_id.id),
                    ("contract_date_start", "<=", rec.date),
                    "|",
                    ("contract_date_end", "=", False),
                    ("contract_date_end", ">=", rec.date),
                ],
                limit=1,
                order="contract_date_start desc",
            )
            rec.contract_id = version

    @api.depends("time_start", "time_end")
    def _compute_hours(self):
        for rec in self:
            if rec.time_end > rec.time_start:
                rec.hours = round(rec.time_end - rec.time_start, 2)
            else:
                rec.hours = 0.0

    @api.depends("contract_id")
    def _compute_hour_salary(self):
        for rec in self:
            if rec.contract_id and rec.contract_id.hour_salary:
                rec.hour_salary = rec.contract_id.hour_salary
            else:
                rec.hour_salary = 0.0

    @api.depends("hours", "day_type", "hour_salary")
    def _compute_overtime_pay(self):
        for rec in self:
            if not rec.hours or not rec.day_type or not rec.hour_salary:
                rec.tax_free_amount = 0.0
                rec.taxable_amount = 0.0
                rec.total_amount = 0.0
                continue
            result = rec._calculate_overtime_pay(rec.hours, rec.day_type, rec.hour_salary)
            rec.tax_free_amount = result["tax_free_amount"]
            rec.taxable_amount = result["taxable_amount"]
            rec.total_amount = result["total_amount"]

    @api.depends("employee_id", "date", "hours")
    def _compute_monthly_hours(self):
        for rec in self:
            if not rec.employee_id or not rec.date:
                rec.monthly_hours = 0.0
                rec.over_monthly_limit = False
                continue
            month_start = rec.date.replace(day=1)
            if rec.date.month == 12:
                month_end = rec.date.replace(year=rec.date.year + 1, month=1, day=1)
            else:
                month_end = rec.date.replace(month=rec.date.month + 1, day=1)

            domain = [
                ("employee_id", "=", rec.employee_id.id),
                ("date", ">=", month_start),
                ("date", "<", month_end),
                ("state", "in", ["pending", "approved"]),
                ("id", "!=", rec.id or 0),
            ]
            others = self.search(domain)
            total = sum(others.mapped("hours")) + (rec.hours or 0.0)
            rec.monthly_hours = round(total, 2)

            setting = self.env["hr.overtime.setting"].search(
                [("active", "=", True)], limit=1
            )
            limit = setting.monthly_limit_hours if setting else 46.0
            rec.over_monthly_limit = total > limit

    @api.constrains("hours", "day_type")
    def _check_hours(self):
        for rec in self:
            if rec.hours <= 0:
                raise ValidationError("加班時數必須大於 0")
            if rec.day_type in ("mandatory_rest", "public_holiday") and rec.hours > 12:
                raise ValidationError(
                    f"例假日／國定假日加班時數不得超過 12 小時（目前：{rec.hours} 小時）"
                )
            setting = self.env["hr.overtime.setting"].search(
                [("active", "=", True)], limit=1
            )
            daily_limit = setting.daily_limit_hours if setting else 4.0
            if rec.day_type == "weekday" and rec.hours > daily_limit:
                raise ValidationError(
                    f"平日加班時數不得超過 {daily_limit} 小時（勞基法 §32）"
                )

    # ---------------------------------------------------------------------------
    # 公開計算方法（供薪資單 salary rule 呼叫）
    # ---------------------------------------------------------------------------

    @api.model
    def _calculate_overtime_pay(self, hours: float, day_type: str, hourly_rate: float) -> dict:
        """計算加班費，回傳 tax_free_amount / taxable_amount / total_amount。

        此方法為純計算，不依賴 self 紀錄，可由薪資 rule 直接呼叫。
        """
        calc_fn = _CALC_MAP.get(day_type)
        if not calc_fn:
            return {"tax_free_amount": 0.0, "taxable_amount": 0.0, "total_amount": 0.0}
        return calc_fn(hours, hourly_rate)

    # ---------------------------------------------------------------------------
    # 狀態動作
    # ---------------------------------------------------------------------------

    def action_submit(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "pending"})

    def action_approve(self):
        self.filtered(lambda r: r.state == "pending").write({"state": "approved"})

    def action_refuse(self):
        self.filtered(lambda r: r.state in ("draft", "pending")).write({"state": "refused"})

    def action_reset_draft(self):
        self.filtered(lambda r: r.state == "refused").write({"state": "draft"})
