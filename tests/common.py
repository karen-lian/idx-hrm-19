from odoo.tests.common import TransactionCase


class IdxHrmCase(TransactionCase):
    """Phase 0 測試共用基礎類別。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 建立測試用加班設定
        cls.overtime_setting = cls.env["hr.overtime.setting"].create(
            {"name": "測試加班設定", "monthly_limit_hours": 46.0, "daily_limit_hours": 4.0}
        )
        # 建立平日加班類型與費率規則（勞基法 §24）
        cls.ot_type_weekday = cls.env["hr.overtime.type"].create(
            {
                "setting_id": cls.overtime_setting.id,
                "name": "平日加班",
                "day_type": "weekday",
            }
        )
        cls.env["hr.overtime.type.rule"].create(
            [
                {
                    "overtime_type_id": cls.ot_type_weekday.id,
                    "hour_from": 0,
                    "hour_to": 2,
                    "rate": round(4 / 3, 4),
                    "is_tax_free": False,
                },
                {
                    "overtime_type_id": cls.ot_type_weekday.id,
                    "hour_from": 2,
                    "hour_to": 4,
                    "rate": round(5 / 3, 4),
                    "is_tax_free": False,
                },
            ]
        )
