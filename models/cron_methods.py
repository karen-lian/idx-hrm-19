from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrContractCron(models.Model):
    _inherit = "hr.contract"

    def _cron_update_contract_state(self):
        """每日 00:05 UTC：自動更新合約狀態。
        draft → open：生效日 <= 今日
        open → close：到期日 < 今日
        """
        today = fields.Date.today()

        drafts = self.search([("state", "=", "draft"), ("date_start", "<=", today)])
        if drafts:
            drafts.write({"state": "open"})

        opens = self.search(
            [("state", "=", "open"), ("date_end", "!=", False), ("date_end", "<", today)]
        )
        if opens:
            opens.write({"state": "close"})


class HrAttendanceCron(models.Model):
    _inherit = "hr.attendance"

    def _cron_send_forgot_punch_notification(self):
        """每日 10:30 UTC（台灣 18:30）：偵測忘刷打卡員工並發送通知。
        排除條件：is_no_punch=True 或當日有核准全天假。
        """
        today = fields.Date.today()

        employees = self.env["hr.employee"].search(
            [("active", "=", True), ("is_no_punch", "=", False)]
        )

        # 一次性載入當日假單（避免 N+1）
        all_day_leaves = self.env["hr.leave"].search(
            [
                ("employee_id", "in", employees.ids),
                ("date_from", "<=", fields.Datetime.now()),
                ("date_to", ">=", fields.Datetime.now()),
                ("state", "=", "validate"),
                ("holiday_status_id.request_unit", "in", ["day", "half_day"]),
            ]
        )
        employees_on_leave = all_day_leaves.mapped("employee_id")

        # 當日已有打卡的員工
        attendances = self.search(
            [("employee_id", "in", employees.ids), ("check_date", "=", today)]
        )
        employees_punched = attendances.mapped("employee_id")

        # 忘刷 = 在職 & 非免打卡 & 無假 & 無打卡
        forgot_employees = employees - employees_on_leave - employees_punched

        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for emp in forgot_employees:
            emp.activity_schedule(
                activity_type_id=activity_type.id if activity_type else False,
                summary=f"{today} 未偵測到打卡記錄，請確認或補登",
                date_deadline=today,
                user_id=emp.user_id.id or self.env.user.id,
            )


class HrLeaveAllocationCron(models.Model):
    _inherit = "hr.leave.allocation"

    def _cron_allocate_annual_leave(self):
        """每日 00:10 UTC：掃描到達特休週年日的員工，自動建立配額。
        週年制：到職日當月當日 = 週年日。
        防重複：同一週年不重複分配。
        """
        today = fields.Date.today()
        annual_leave_type = self.env.ref("idx_hrm_19.leave_type_annual", raise_if_not_found=False)
        if not annual_leave_type:
            return

        active_employees = self.env["hr.employee"].search(
            [("active", "=", True), ("contract_id", "!=", False)]
        )

        annual_leave_table = self.env["hr.annual.leave"].search([])

        for emp in active_employees:
            contract = emp.contract_id
            if not contract or not contract.date_start:
                continue

            start = contract.date_start
            # 計算服務滿整月數後的週年日是否是今日
            if start.month != today.month or start.day != today.day:
                continue

            tenure_years = (today - start).days / 365.25
            if tenure_years < 0.5:
                continue

            # 取得應給天數
            leave_days = annual_leave_table.get_leave_days(tenure_years)
            if not leave_days:
                continue

            # 防重複：檢查同一年度是否已分配
            already = self.search(
                [
                    ("employee_id", "=", emp.id),
                    ("holiday_status_id", "=", annual_leave_type.id),
                    ("date_from", ">=", today.replace(month=1, day=1)),
                    ("date_to", "<=", today.replace(month=12, day=31)),
                    ("state", "!=", "refuse"),
                ],
                limit=1,
            )
            if already:
                continue

            self.create(
                {
                    "employee_id": emp.id,
                    "holiday_status_id": annual_leave_type.id,
                    "number_of_days": leave_days,
                    "allocation_type": "regular",
                    "date_from": today,
                    "date_to": today.replace(year=today.year + 1) - timedelta(days=1),
                    "state": "validate",
                    "notes": f"系統自動分配：服務年資 {tenure_years:.2f} 年，週年日 {today}",
                }
            )

    def _cron_expire_compensatory_to_cash(self):
        """每月 1 日 00:20 UTC：將上個月底過期的補休配額轉換為現金補償記錄。
        轉換條件：allocation 的 date_to < 今日 且 remaining_days > 0。
        """
        today = fields.Date.today()
        compensatory_type = self.env.ref(
            "idx_hrm_19.leave_type_compensatory", raise_if_not_found=False
        )
        if not compensatory_type:
            return

        expired_allocs = self.search(
            [
                ("holiday_status_id", "=", compensatory_type.id),
                ("date_to", "<", today),
                ("state", "=", "validate"),
            ]
        )

        for alloc in expired_allocs:
            remaining = alloc.number_of_days_display
            if remaining <= 0:
                continue

            emp = alloc.employee_id
            hourly_rate = emp.contract_id.hour_salary if emp.contract_id else 0.0
            # 補休 1 天 = 8 小時
            cash_amount = remaining * 8 * hourly_rate

            # 建立現金補償記錄（hr.compensatory.cash，Phase 5 PR-036 實裝）
            cash_model = self.env.get("hr.compensatory.cash")
            if cash_model is not None:
                cash_model.create(
                    {
                        "employee_id": emp.id,
                        "allocation_id": alloc.id,
                        "expired_days": remaining,
                        "cash_amount": cash_amount,
                        "source_date": alloc.date_to,
                        "note": f"補休配額到期（{alloc.date_to}），自動轉現金 {cash_amount:.0f} 元",
                    }
                )

            # 標記配額為已處理（refusal 或歸零），避免重複轉換
            alloc.write({"state": "refuse"})


class HrEmployeeCron(models.Model):
    _inherit = "hr.employee"

    def _cron_check_permit_expiry(self):
        """每日 00:15 UTC：掃描外籍員工居留證效期，距到期 60 天內發送 activity 警示。
        條件：permit_expiry 存在 且 today <= permit_expiry <= today+60。
        防重複：同一員工同一到期日不重複建立 activity。
        """
        today = fields.Date.today()
        alert_threshold = today + timedelta(days=60)

        expiring_employees = self.search(
            [
                ("active", "=", True),
                ("permit_expiry", "!=", False),
                ("permit_expiry", ">=", today),
                ("permit_expiry", "<=", alert_threshold),
            ]
        )

        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)

        for emp in expiring_employees:
            days_left = (emp.permit_expiry - today).days
            summary = f"居留證效期即將到期（剩餘 {days_left} 天，到期日：{emp.permit_expiry}）"

            # 防重複：檢查是否已有相同摘要的 activity
            existing = self.env["mail.activity"].search(
                [
                    ("res_model", "=", "hr.employee"),
                    ("res_id", "=", emp.id),
                    ("summary", "=", summary),
                ],
                limit=1,
            )
            if existing:
                continue

            emp.activity_schedule(
                activity_type_id=activity_type.id if activity_type else False,
                summary=summary,
                date_deadline=emp.permit_expiry,
                user_id=emp.user_id.id or self.env.user.id,
            )
