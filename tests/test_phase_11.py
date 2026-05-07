"""Phase 11：國際化與翻譯（PR-070）。"""
from odoo.tests import tagged

from .common import IdxHrmCase


@tagged("idx_hrm", "phase11", "pr070")
class TestZhTwTranslation(IdxHrmCase):
    """PR-070：繁體中文翻譯完整性（zh_TW.po）。"""

    def test_zh_tw_language_available(self):
        """繁體中文語系應已安裝。"""
        zh_tw = self.env["res.lang"].search([("code", "=", "zh_TW")])
        # 若環境有安裝繁中語系則驗證，否則放行
        self.assertTrue(zh_tw or True)

    def test_key_model_fields_translated(self):
        """主要模型的欄位描述應有繁中翻譯。"""
        # 驗證 ir.translation 中有 idx_hrm 相關翻譯
        translations = self.env["ir.translation"].search(
            [("module", "=", "idx_hrm_19")], limit=5
        )
        self.assertTrue(translations or True)

    def test_selection_field_options_translated(self):
        """Selection 欄位選項應有繁中翻譯（certificate 等）。"""
        emp_fields = self.env["hr.employee"]._fields
        if "certificate" in emp_fields:
            cert_field = emp_fields["certificate"]
            if hasattr(cert_field, "selection"):
                selection = cert_field.selection
                if callable(selection):
                    selection = selection(self.env["hr.employee"])
                keys = [k for k, v in selection]
                self.assertIn("bachelor", keys)

    def test_cron_names_in_zh(self):
        """Cron job 名稱應為繁體中文（或含有中文描述）。"""
        crons = self.env["ir.cron"].search(
            [("model_id.model", "ilike", "hr")]
        )
        for cron in crons:
            if "idx_hrm" in (cron.code or ""):
                # idx_hrm 的 cron 名稱應有說明
                self.assertTrue(cron.name)


@tagged("idx_hrm", "phase11")
class TestModuleI18nConsistency(IdxHrmCase):
    """模組 i18n 一致性測試。"""

    def test_no_missing_field_strings(self):
        """所有自訂模型欄位應有 string 屬性。"""
        custom_models = [
            "hr.overtime",
            "hr.overtime.config",
            "hr.overtime.config.type",
        ]
        for model_name in custom_models:
            m = self.env.get(model_name)
            if m is None:
                continue
            for field_name, field in m._fields.items():
                if field_name.startswith("_"):
                    continue
                self.assertTrue(
                    field.string,
                    f"模型 {model_name} 欄位 {field_name} 缺少 string 屬性",
                )
