"""PR-056/057a/057b/057c/058：員工到職/離職/留停復職流程"""
from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrVersion(models.Model):
    """PR-056/058：到職觸發假別分配、留停/復職流程（基於 hr.version）"""
    _inherit = "hr.version"

    def write(self, vals):
        result = super().write(vals)
        # PR-056：當 approval_state 首次變為 approved 且版本是當前版本時，觸發到職流程
        if "approval_state" in vals and vals["approval_state"] == "approved":
            for version in self:
                if version.is_current:
                    version._on_version_approved()
        return result

    def _on_version_approved(self):
        """PR-056：版本核准且為當前版本 → 自動建立法定假別配額。"""
        self.ensure_one()
        emp = self.employee_id
        if not emp:
            return
        STATUTORY_LEAVE_DAYS = {
            "PERSONAL": 14,
            "SICK": 30,
            "OFFICIAL": 0,
        }
        for code, days in STATUTORY_LEAVE_DAYS.items():
            lt = self.env["hr.leave.type"].search([("code", "=", code)], limit=1)
            if not lt or days == 0:
                continue
            existing = self.env["hr.leave.allocation"].search([
                ("employee_id", "=", emp.id),
                ("holiday_status_id", "=", lt.id),
                ("state", "=", "validate"),
            ], limit=1)
            if not existing:
                self.env["hr.leave.allocation"].create({
                    "name": f"{lt.name}（到職初始分配）",
                    "employee_id": emp.id,
                    "holiday_status_id": lt.id,
                    "number_of_days": days,
                    "allocation_type": "fixed",
                    "state": "validate",
                    "is_auto_allocated": True,
                })
        # 特休自動分配
        self.env["hr.leave.allocation"]._auto_allocate_annual(emp)

    def action_furlough(self):
        """PR-058：建立留停新版本（將合約結束日設為今日、下一版本為留停）。"""
        self.ensure_one()
        if not self.is_current:
            raise ValidationError("只有當前生效版本才能轉為留停！")
        today = fields.Date.today()
        # 建立留停版本（date_version = 今日，change_reason = furlough，no_seniority = True）
        furlough_version = self.copy({
            "name": f"{self.name}（留停）",
            "date_version": today,
            "change_reason": "furlough",
            "no_seniority": True,
            "approval_state": "approved",
            "labor_insurance_premium_employee": 0.0,
            "health_insurance_premium_employee": 0.0,
            "pension_employer": 0.0,
            "contract_date_start": today,
            "contract_date_end": False,
        })
        return furlough_version

    def action_reinstate(self, reinstate_date=None):
        """PR-058：復職 → 結束留停版本、計算留停天數延順特休結轉日。"""
        self.ensure_one()
        if self.change_reason != "furlough":
            raise ValidationError("此版本不是留停版本！")
        today = reinstate_date or fields.Date.today()
        furlough_days = (today - self.contract_date_start).days if self.contract_date_start else 0

        # 設定留停結束日
        self.write({"contract_date_end": today})

        # 延順特休結轉日期
        annual_allocs = self.env["hr.leave.allocation"].search([
            ("employee_id", "=", self.employee_id.id),
            ("holiday_status_id.code", "=", "ANNUAL"),
            ("state", "=", "validate"),
        ])
        annual_allocs.freeze_for_furlough(furlough_days)

        # 建立復職新版本
        self.copy({
            "name": f"{self.employee_id.name} 復職合約",
            "date_version": today,
            "change_reason": "reinstate",
            "no_seniority": False,
            "approval_state": "approved",
            "contract_date_start": today,
            "contract_date_end": False,
        })


class HrResignationWizard(models.TransientModel):
    """PR-057a：離職流程 Wizard UI"""
    _name = "hr.resignation.wizard"
    _description = "員工離職流程"

    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
    )
    resignation_date = fields.Date(
        string="離職日期",
        required=True,
        default=fields.Date.today,
    )
    resignation_type = fields.Selection(
        selection=[
            ("voluntary", "自願離職"),
            ("involuntary", "非自願離職"),
            ("mutual", "合意終止"),
            ("retire", "退休"),
        ],
        string="離職原因",
        required=True,
    )
    note = fields.Text(string="備註")

    # PR-057b：清算欄位
    unused_annual_days = fields.Float(
        string="未休特休天數",
        compute="_compute_settlement",
        digits=(6, 1),
    )
    unused_leave_amount = fields.Float(
        string="未休特休折現",
        compute="_compute_settlement",
        digits=(10, 2),
    )
    comp_leave_hours = fields.Float(
        string="未使用補休時數",
        compute="_compute_settlement",
        digits=(6, 2),
    )
    comp_leave_amount = fields.Float(
        string="補休轉現金",
        compute="_compute_settlement",
        digits=(10, 2),
    )
    pro_rata_bonus = fields.Float(
        string="比例年終獎金",
        compute="_compute_settlement",
        digits=(10, 2),
    )
    severance_pay = fields.Float(
        string="遣散費",
        compute="_compute_settlement",
        digits=(10, 2),
    )
    settlement_total = fields.Float(
        string="清算合計",
        compute="_compute_settlement",
        digits=(10, 2),
    )

    @api.depends("employee_id", "resignation_date")
    def _compute_settlement(self):
        """PR-057b：計算離職清算金額。"""
        for wizard in self:
            emp = wizard.employee_id
            if not emp:
                wizard.unused_annual_days = 0.0
                wizard.unused_leave_amount = 0.0
                wizard.comp_leave_hours = 0.0
                wizard.comp_leave_amount = 0.0
                wizard.pro_rata_bonus = 0.0
                wizard.severance_pay = 0.0
                wizard.settlement_total = 0.0
                continue

            current_version = emp.current_version_id
            if not current_version:
                wizard.unused_annual_days = 0.0
                wizard.unused_leave_amount = 0.0
                wizard.comp_leave_hours = 0.0
                wizard.comp_leave_amount = 0.0
                wizard.pro_rata_bonus = 0.0
                wizard.severance_pay = 0.0
                wizard.settlement_total = 0.0
                continue

            daily_wage = round(current_version.wage / 30, 2)
            hour_wage = current_version.hour_salary

            # 未休特休
            annual_lt = self.env["hr.leave.type"].search([("code", "=", "ANNUAL")], limit=1)
            remaining_annual = 0.0
            if annual_lt:
                remaining_annual = self.env["hr.leave.allocation"].get_remaining_days(
                    emp.id, annual_lt.id
                )
            wizard.unused_annual_days = remaining_annual
            wizard.unused_leave_amount = round(remaining_annual * daily_wage, 2)

            # 補休轉現金
            comp_lt = self.env["hr.leave.type"].search([("code", "=", "COMP")], limit=1)
            remaining_comp_days = 0.0
            if comp_lt:
                remaining_comp_days = self.env["hr.leave.allocation"].get_remaining_days(
                    emp.id, comp_lt.id
                )
            comp_hours = remaining_comp_days * 8
            wizard.comp_leave_hours = comp_hours
            wizard.comp_leave_amount = round(comp_hours * hour_wage, 2)

            # 比例年終：任職月數 / 12
            months_worked = max(int(emp.job_tenure * 12), 1)
            annual_bonus_base = current_version.wage
            wizard.pro_rata_bonus = round(annual_bonus_base * min(months_worked, 12) / 12, 2)

            # 遣散費：依勞基法年資分級（每年 0.5 個月薪）
            tenure_years = emp.job_tenure
            wizard.severance_pay = round(current_version.wage * tenure_years * 0.5, 2)

            total = (
                wizard.unused_leave_amount
                + wizard.comp_leave_amount
                + wizard.pro_rata_bonus
                + wizard.severance_pay
            )
            wizard.settlement_total = round(total, 2)

    def action_confirm_resignation(self):
        """PR-057a：確認離職 → 設定離職日期、封存員工。"""
        self.ensure_one()
        emp = self.employee_id
        # 在當前版本設定離職日期與原因
        current_version = emp.current_version_id
        if current_version:
            current_version.write({
                "contract_date_end": self.resignation_date,
                "change_reason": "resign",
            })
        emp.write({"active": False})

        # PR-057c：建立最終薪資單草稿
        self._generate_final_payslip()

        return {"type": "ir.actions.act_window_close"}

    def _generate_final_payslip(self):
        """PR-057c：產生最終薪資單（含清算明細）。"""
        self.ensure_one()
        emp = self.employee_id
        # 找最近一個 change_reason == 'resign' 的版本（含 contract_date_end）
        resigned_version = emp.version_ids.filtered(
            lambda v: v.change_reason == "resign" and v.contract_date_end
        ).sorted("contract_date_end", reverse=True)
        if not resigned_version:
            return

        version = resigned_version[0]
        date_from = self.resignation_date.replace(day=1)
        date_to = self.resignation_date

        payslip = self.env["hr.payslip"].create({
            "name": f"最終薪資單 - {emp.name}（{date_to}）",
            "employee_id": emp.id,
            "version_id": version.id,
            "date_from": date_from,
            "date_to": date_to,
            "state": "draft",
        })

        # 加入清算項目（非固定薪資）
        settlement_items = [
            ("未休特休折現", self.unused_leave_amount, "50"),
            ("補休轉現金", self.comp_leave_amount, "50"),
            ("比例年終獎金", self.pro_rata_bonus, "50"),
            ("遣散費", self.severance_pay, "50"),
        ]
        for name, amount, code in settlement_items:
            if amount > 0:
                self.env["hr.payslip.unfrequented"].create({
                    "payslip_id": payslip.id,
                    "name": name,
                    "amount": amount,
                    "withholding_code": code,
                    "is_taxable": name not in ("遣散費",),
                })
        return payslip
