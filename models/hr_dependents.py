from odoo import api, fields, models
from odoo.exceptions import ValidationError
from ..utils.tw_id import validate_tw_id


class HrDependentsInformation(models.Model):
    """PR-017/018：健保眷屬資料與保費計算"""
    _name = "hr.dependents.information"
    _description = "員工健保眷屬資料"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "employee_id, sequence"

    employee_id = fields.Many2one(
        "hr.employee",
        string="員工",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="序號", default=10)
    name = fields.Char(string="眷屬姓名", required=True)
    relationship = fields.Selection(
        selection=[
            ("spouse", "配偶"),
            ("child", "子女"),
            ("parent", "父母"),
            ("parent_in_law", "配偶父母"),
            ("sibling", "兄弟姊妹"),
            ("other", "其他"),
        ],
        string="關係",
        required=True,
    )
    identification_card = fields.Char(
        string="身分證字號",
        copy=False,
    )
    birthday = fields.Date(string="出生日期")
    gender = fields.Selection(
        selection=[("male", "男"), ("female", "女")],
        string="性別",
    )

    # 健保投退保日期
    enroll_date = fields.Date(
        string="健保投保日期",
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    withdraw_date = fields.Date(
        string="健保退保日期",
        tracking=True,
    )
    is_active_insured = fields.Boolean(
        string="在保中",
        compute="_compute_is_active_insured",
        store=True,
    )

    # PR-018：保費計算
    health_insurance_premium = fields.Float(
        string="眷屬健保費（員工負擔）",
        digits=(10, 2),
        compute="_compute_health_insurance_premium",
        store=True,
    )

    _sql_constraints = [
        (
            "identification_card_uniq",
            "UNIQUE(identification_card)",
            "此身分證字號已有眷屬記錄！",
        ),
    ]

    @api.constrains("identification_card")
    def _check_identification_card(self):
        for dep in self:
            if dep.identification_card:
                validate_tw_id(dep.identification_card)

    @api.constrains("enroll_date", "withdraw_date")
    def _check_dates(self):
        for dep in self:
            if dep.enroll_date and dep.withdraw_date:
                if dep.withdraw_date < dep.enroll_date:
                    raise ValidationError(
                        f"眷屬 {dep.name} 的退保日期不能早於投保日期！"
                    )

    @api.depends("enroll_date", "withdraw_date")
    def _compute_is_active_insured(self):
        today = fields.Date.today()
        for dep in self:
            if not dep.enroll_date:
                dep.is_active_insured = False
            elif dep.withdraw_date and dep.withdraw_date < today:
                dep.is_active_insured = False
            else:
                dep.is_active_insured = True

    @api.depends(
        "is_active_insured",
        "employee_id.contract_ids.health_insurance_premium_employee",
        "employee_id.contract_ids.state",
    )
    def _compute_health_insurance_premium(self):
        """PR-018：眷屬健保費 = 員工本人健保費（在職合約）× 眷屬費率倍數。

        依全民健保法：每位眷屬費率與員工本人相同（×1），
        由員工自行負擔，上限 3 口（第 4 口以上由健保署補貼）。
        """
        for dep in self:
            if not dep.is_active_insured:
                dep.health_insurance_premium = 0.0
                continue
            active_contract = dep.employee_id.contract_ids.filtered(
                lambda c: c.state == "open"
            )
            if not active_contract:
                dep.health_insurance_premium = 0.0
                continue
            contract = active_contract[0]
            dep.health_insurance_premium = round(
                contract.health_insurance_premium_employee, 2
            )


class HrContract(models.Model):
    """PR-018：合約加入眷屬保費彙總計算"""
    _inherit = "hr.contract"

    dependent_ids = fields.One2many(
        "hr.dependents.information",
        "employee_id",
        related="employee_id.dependents_information_ids",
        string="健保眷屬",
        readonly=True,
    )
    dependent_count = fields.Integer(
        string="在保眷屬人數",
        compute="_compute_dependent_count",
        store=True,
    )
    dependent_health_insurance_total = fields.Float(
        string="眷屬健保費合計",
        digits=(10, 2),
        compute="_compute_dependent_premium",
        store=True,
    )

    @api.depends("employee_id.dependents_information_ids.is_active_insured")
    def _compute_dependent_count(self):
        for contract in self:
            contract.dependent_count = len(
                contract.employee_id.dependents_information_ids.filtered(
                    "is_active_insured"
                )
            )

    @api.depends(
        "health_insurance_premium_employee",
        "employee_id.dependents_information_ids.is_active_insured",
        "employee_id.dependents_information_ids.health_insurance_premium",
    )
    def _compute_dependent_premium(self):
        for contract in self:
            active_deps = contract.employee_id.dependents_information_ids.filtered(
                "is_active_insured"
            )
            contract.dependent_health_insurance_total = sum(
                dep.health_insurance_premium for dep in active_deps
            )


class HrEmployee(models.Model):
    """PR-017：員工加入眷屬 One2many"""
    _inherit = "hr.employee"

    dependents_information_ids = fields.One2many(
        "hr.dependents.information",
        "employee_id",
        string="健保眷屬",
    )
    active_dependent_count = fields.Integer(
        string="在保眷屬人數",
        compute="_compute_active_dependent_count",
        store=True,
    )

    @api.depends("dependents_information_ids.is_active_insured")
    def _compute_active_dependent_count(self):
        for emp in self:
            emp.active_dependent_count = len(
                emp.dependents_information_ids.filtered("is_active_insured")
            )
