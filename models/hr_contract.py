from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrContract(models.Model):
    """PR-014/015/016/016b：合約擴充欄位、狀態流程與審核工作流"""
    _inherit = "hr.contract"

    # PR-014：合約基本擴充欄位

    change_reason = fields.Selection(
        selection=[
            ("new_hire", "新進"),
            ("promotion", "晉升"),
            ("transfer", "調職"),
            ("salary_adjust", "薪資調整"),
            ("furlough", "留職停薪"),
            ("reinstate", "復職"),
            ("resign", "離職"),
            ("retire", "退休"),
        ],
        string="異動原因",
        tracking=True,
    )
    job_level = fields.Char(
        string="職等",
        help="例如：P1, P2, M1",
    )
    job_class = fields.Char(
        string="職級",
        help="例如：工程師、資深工程師",
    )
    is_part_time = fields.Boolean(
        string="部分工時",
        default=False,
    )
    hour_salary = fields.Float(
        string="時薪",
        digits=(10, 2),
        compute="_compute_hour_salary",
        store=True,
        help="月薪 ÷ 30 ÷ 8",
    )
    hour_leave_salary = fields.Float(
        string="事假時薪",
        digits=(10, 2),
        compute="_compute_hour_salary",
        store=True,
        help="用於事假扣薪計算",
    )
    labor_insurance_premium_employee = fields.Float(
        string="員工勞保費",
        digits=(10, 2),
        default=0.0,
    )
    labor_insurance_premium_employer = fields.Float(
        string="雇主勞保費",
        digits=(10, 2),
        default=0.0,
    )
    health_insurance_premium_employee = fields.Float(
        string="員工健保費",
        digits=(10, 2),
        default=0.0,
    )
    health_insurance_premium_employer = fields.Float(
        string="雇主健保費",
        digits=(10, 2),
        default=0.0,
    )
    pension_employer = fields.Float(
        string="雇主勞退提撥",
        digits=(10, 2),
        default=0.0,
    )
    is_no_pr = fields.Boolean(
        string="無永久居留權",
        default=False,
        help="外籍員工無永久居留權，影響加班申請",
    )
    no_resident = fields.Boolean(
        string="非居住者",
        default=False,
        related="employee_id.no_resident",
        store=True,
    )

    # PR-015：合約狀態流程欄位
    approval_state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("pending", "待審核"),
            ("approved", "已核准"),
            ("rejected", "已駁回"),
        ],
        string="審核狀態",
        default="draft",
        tracking=True,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="核准人",
        readonly=True,
    )
    approval_date = fields.Datetime(
        string="核准日期",
        readonly=True,
    )
    rejection_reason = fields.Text(
        string="駁回原因",
        readonly=True,
    )
    no_seniority = fields.Boolean(
        string="不計年資",
        default=False,
        help="勾選表示此合約期間不計入服務年資（如留停合約）",
    )

    @api.depends("wage")
    def _compute_hour_salary(self):
        for contract in self:
            if contract.wage and contract.wage > 0:
                contract.hour_salary = round(contract.wage / 30 / 8, 2)
                contract.hour_leave_salary = round(contract.wage / 30 / 8, 2)
            else:
                contract.hour_salary = 0.0
                contract.hour_leave_salary = 0.0

    @api.constrains("date_start", "date_end", "employee_id", "state")
    def _check_no_overlapping_contracts(self):
        for contract in self:
            if contract.state in ("cancel",):
                continue
            domain = [
                ("employee_id", "=", contract.employee_id.id),
                ("state", "not in", ("cancel",)),
                ("id", "!=", contract.id),
            ]
            if contract.date_end:
                domain += [
                    ("date_start", "<=", contract.date_end),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", contract.date_start),
                ]
            else:
                domain += [
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", contract.date_start),
                ]
            overlapping = self.search(domain)
            if overlapping:
                raise ValidationError(
                    f"員工 {contract.employee_id.name} 的合約期間與既有合約重疊！\n"
                    f"重疊合約：{overlapping.mapped('name')}"
                )

    # PR-015：狀態轉換方法

    def action_submit_for_approval(self):
        """提交合約審核"""
        for contract in self:
            if contract.state != "draft":
                raise ValidationError("只有草稿合約才能提交審核！")
            contract.write({"approval_state": "pending"})
            contract.message_post(
                body="合約已提交審核，等待主管核准。",
                subtype_xmlid="mail.mt_note",
            )

    def _cron_update_contract_state(self):
        """每日 cron：到期合約自動 close、生效日到達自動 open"""
        today = fields.Date.today()

        # 生效日到達且已核准 → open
        to_open = self.search([
            ("state", "=", "draft"),
            ("approval_state", "=", "approved"),
            ("date_start", "<=", today),
        ])
        to_open.write({"state": "open"})

        # 到期合約自動 close
        to_close = self.search([
            ("state", "=", "open"),
            ("date_end", "!=", False),
            ("date_end", "<", today),
        ])
        to_close.write({"state": "close"})

    # PR-016/016b：合約審核工作流

    def action_approve(self):
        """主管核准合約"""
        for contract in self:
            if contract.approval_state != "pending":
                raise ValidationError("只有待審核的合約才能核准！")
            contract.write({
                "approval_state": "approved",
                "approver_id": self.env.uid,
                "approval_date": fields.Datetime.now(),
                "rejection_reason": False,
            })
            # 生效日已到達則立即 open
            today = fields.Date.today()
            if contract.date_start and contract.date_start <= today:
                contract.write({"state": "open"})
            contract.message_post(
                body=f"合約已由 {self.env.user.name} 核准。",
                subtype_xmlid="mail.mt_note",
            )

    def action_reject(self, reason=""):
        """主管駁回合約"""
        for contract in self:
            if contract.approval_state != "pending":
                raise ValidationError("只有待審核的合約才能駁回！")
            contract.write({
                "approval_state": "rejected",
                "rejection_reason": reason,
                "state": "draft",
            })
            body = f"合約已駁回。"
            if reason:
                body += f"<br/>駁回原因：{reason}"
            contract.message_post(
                body=body,
                subtype_xmlid="mail.mt_note",
            )

    def write(self, vals):
        # PR-016：未核准合約不能手動切換至 open
        if "state" in vals and vals["state"] == "open":
            for contract in self:
                if contract.approval_state not in ("approved",):
                    raise ValidationError(
                        f"合約 {contract.name} 尚未核准，無法設定為生效狀態！"
                        "請先提交審核並等待核准。"
                    )
        return super().write(vals)
