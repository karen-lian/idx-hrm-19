from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # --- 銀行薪轉參數 ---
    tw_bank_identifier1 = fields.Char(
        string="識別碼 1",
        config_parameter="idx_hrm.bank_identifier1",
    )
    tw_bank_identifier2 = fields.Char(
        string="識別碼 2",
        config_parameter="idx_hrm.bank_identifier2",
    )
    tw_bank_unit_code = fields.Char(
        string="委託單位代號",
        config_parameter="idx_hrm.bank_unit_code",
    )

    # --- 所得稅申報參數 ---
    tw_tax_office_code = fields.Char(
        string="所轄國稅局代號",
        config_parameter="idx_hrm.tax_office_code",
    )
    tw_company_tax_id = fields.Char(
        string="公司統一編號",
        config_parameter="idx_hrm.company_tax_id",
    )
    tw_withholding_agent_name = fields.Char(
        string="扣繳義務人名稱",
        config_parameter="idx_hrm.withholding_agent_name",
    )
    tw_tax_office_address = fields.Char(
        string="國稅局地址",
        config_parameter="idx_hrm.tax_office_address",
    )
    tw_withholding_agent_person = fields.Char(
        string="扣繳義務人姓名",
        config_parameter="idx_hrm.withholding_agent_person",
    )
    tw_tax_seq_number = fields.Char(
        string="邏輯序號",
        config_parameter="idx_hrm.tax_seq_number",
    )

    # --- 勞保費率參數 ---
    labor_min_salary = fields.Float(
        string="勞保最低投保薪資",
        config_parameter="idx_hrm.labor_min_salary",
        digits=(12, 0),
    )
    labor_accident_rate = fields.Float(
        string="普通事故費率 (%)",
        config_parameter="idx_hrm.labor_accident_rate",
        digits=(5, 4),
    )
    labor_employment_insurance_rate = fields.Float(
        string="就業保險費率 (%)",
        config_parameter="idx_hrm.labor_employment_insurance_rate",
        digits=(5, 4),
    )
    labor_wage_guarantee_rate = fields.Float(
        string="工資墊償基金費率（元/萬元）",
        config_parameter="idx_hrm.labor_wage_guarantee_rate",
        digits=(5, 4),
    )
    labor_employee_ratio = fields.Float(
        string="勞保員工負擔比例 (%)",
        config_parameter="idx_hrm.labor_employee_ratio",
        digits=(5, 4),
    )
    labor_employer_ratio = fields.Float(
        string="勞保雇主負擔比例 (%)",
        config_parameter="idx_hrm.labor_employer_ratio",
        digits=(5, 4),
    )

    # --- 勞退費率參數 ---
    pension_employer_rate = fields.Float(
        string="勞退雇主提撥率 (%)",
        config_parameter="idx_hrm.pension_employer_rate",
        digits=(5, 4),
        default=6.0,
    )

    # --- 健保費率參數 ---
    health_min_salary = fields.Float(
        string="健保最低投保薪資",
        config_parameter="idx_hrm.health_min_salary",
        digits=(12, 0),
    )
    health_insurance_rate = fields.Float(
        string="健保費率 (%)",
        config_parameter="idx_hrm.health_insurance_rate",
        digits=(5, 4),
    )
    health_employer_dependent_multiplier = fields.Float(
        string="雇主眷屬負擔倍數",
        config_parameter="idx_hrm.health_employer_dependent_multiplier",
        digits=(5, 2),
    )
    health_employee_ratio = fields.Float(
        string="健保員工負擔比例 (%)",
        config_parameter="idx_hrm.health_employee_ratio",
        digits=(5, 4),
    )
    health_employer_ratio = fields.Float(
        string="健保雇主負擔比例 (%)",
        config_parameter="idx_hrm.health_employer_ratio",
        digits=(5, 4),
    )
    health_supplement_rate = fields.Float(
        string="補充保費費率 (%)",
        config_parameter="idx_hrm.health_supplement_rate",
        digits=(5, 4),
    )

    # --- 居住者所得稅參數 ---
    resident_tax_method = fields.Selection(
        selection=[("fixed", "固定稅率"), ("table", "稅額表")],
        string="扣繳方式",
        config_parameter="idx_hrm.resident_tax_method",
        default="table",
    )
    resident_fixed_rate = fields.Float(
        string="居住者固定稅率 (%)",
        config_parameter="idx_hrm.resident_fixed_rate",
        digits=(5, 4),
    )
    resident_variable_threshold = fields.Float(
        string="非固定薪資門檻",
        config_parameter="idx_hrm.resident_variable_threshold",
        digits=(12, 0),
    )
    resident_variable_rate = fields.Float(
        string="非固定薪資稅率 (%)",
        config_parameter="idx_hrm.resident_variable_rate",
        digits=(5, 4),
    )
    resident_other_threshold = fields.Float(
        string="其他所得門檻",
        config_parameter="idx_hrm.resident_other_threshold",
        digits=(12, 0),
    )
    resident_other_rate = fields.Float(
        string="其他所得稅率 (%)",
        config_parameter="idx_hrm.resident_other_rate",
        digits=(5, 4),
    )

    # --- 非居住者所得稅參數 ---
    non_resident_salary_threshold = fields.Float(
        string="非居住者薪資門檻",
        config_parameter="idx_hrm.non_resident_salary_threshold",
        digits=(12, 0),
    )
    non_resident_high_rate = fields.Float(
        string="非居住者高薪資稅率 (%)",
        config_parameter="idx_hrm.non_resident_high_rate",
        digits=(5, 4),
    )
    non_resident_normal_rate = fields.Float(
        string="非居住者一般薪資稅率 (%)",
        config_parameter="idx_hrm.non_resident_normal_rate",
        digits=(5, 4),
    )
    non_resident_other_rate = fields.Float(
        string="非居住者其他所得稅率 (%)",
        config_parameter="idx_hrm.non_resident_other_rate",
        digits=(5, 4),
    )

    @api.constrains(
        "labor_accident_rate", "labor_employment_insurance_rate",
        "labor_employee_ratio", "labor_employer_ratio",
        "pension_employer_rate",
        "health_insurance_rate", "health_employee_ratio", "health_employer_ratio",
        "health_supplement_rate",
        "resident_fixed_rate", "resident_variable_rate", "resident_other_rate",
        "non_resident_high_rate", "non_resident_normal_rate", "non_resident_other_rate",
    )
    def _check_rates(self):
        rate_fields = [
            "labor_accident_rate", "labor_employment_insurance_rate",
            "labor_employee_ratio", "labor_employer_ratio",
            "pension_employer_rate",
            "health_insurance_rate", "health_employee_ratio", "health_employer_ratio",
            "health_supplement_rate",
            "resident_fixed_rate", "resident_variable_rate", "resident_other_rate",
            "non_resident_high_rate", "non_resident_normal_rate", "non_resident_other_rate",
        ]
        for rec in self:
            for fname in rate_fields:
                val = getattr(rec, fname)
                if val < 0 or val > 100:
                    raise ValidationError(f"費率欄位 {fname} 必須介於 0 到 100 之間，目前值：{val}")

    @api.constrains("labor_min_salary", "health_min_salary")
    def _check_min_salary(self):
        for rec in self:
            if rec.labor_min_salary < 0:
                raise ValidationError("勞保最低投保薪資不得為負數")
            if rec.health_min_salary < 0:
                raise ValidationError("健保最低投保薪資不得為負數")
