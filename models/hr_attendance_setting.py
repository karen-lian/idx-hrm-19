from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrAttendanceSetting(models.Model):
    _name = "hr.attendance.setting"
    _description = "出勤設定"
    _order = "id desc"

    name = fields.Char(string="設定名稱", required=True, default="出勤設定")
    active = fields.Boolean(default=True)

    # --- 全勤獎金 ---
    enable_perfect_attendance = fields.Boolean(
        string="啟用全勤獎金", default=False
    )
    perfect_attendance_amount = fields.Float(
        string="全勤獎金金額", digits=(12, 0), default=0.0
    )
    # 取消全勤之請假時數上限（超過則無全勤）
    perfect_attendance_leave_limit = fields.Float(
        string="取消全勤請假時數上限", digits=(5, 1), default=0.0
    )
    # 遲早到寬限分鐘數
    grace_minutes = fields.Integer(
        string="遲早到寬限分鐘", default=0
    )
    # 遲早到次數上限（超過則取消全勤）
    perfect_attendance_late_limit = fields.Integer(
        string="取消全勤遲早到次數上限", default=0
    )
    # 月中到職不扣全勤
    no_deduct_on_join = fields.Boolean(
        string="月中到職不扣全勤", default=False
    )
    # 月中離職不扣全勤
    no_deduct_on_resign = fields.Boolean(
        string="月中離職不扣全勤", default=False
    )

    # --- 遲到/早退扣款 ---
    enable_late_deduction = fields.Boolean(
        string="啟用遲到早退扣款", default=False
    )
    # 需請假分鐘門檻（超過才需補假單）
    leave_required_minutes = fields.Integer(
        string="需請假分鐘門檻", default=0
    )

    _sql_constraints = [
        (
            "perfect_attendance_amount_positive",
            "CHECK(perfect_attendance_amount >= 0)",
            "全勤獎金金額不得為負數",
        ),
        (
            "grace_minutes_positive",
            "CHECK(grace_minutes >= 0)",
            "寬限分鐘數不得為負數",
        ),
        (
            "leave_required_minutes_positive",
            "CHECK(leave_required_minutes >= 0)",
            "需請假分鐘門檻不得為負數",
        ),
    ]

    @api.constrains("perfect_attendance_leave_limit")
    def _check_leave_limit(self):
        for rec in self:
            if rec.perfect_attendance_leave_limit < 0:
                raise ValidationError("取消全勤請假時數上限不得為負數")

    @api.constrains("perfect_attendance_late_limit")
    def _check_late_limit(self):
        for rec in self:
            if rec.perfect_attendance_late_limit < 0:
                raise ValidationError("取消全勤遲早到次數上限不得為負數")
