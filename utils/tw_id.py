"""台灣身分證字號驗證工具（PR-011）

演算法：MOD10 驗算
- 首碼英文字母轉數字：A=10, B=11, ... Z=33（跳過 O/I）
- 第一碼數字拆成十位數×1 + 個位數×9
- 第 2-8 碼分別乘以 8, 7, 6, 5, 4, 3, 2
- 末碼乘以 1
- 總和 % 10 == 0 → 合法
"""
from odoo.exceptions import ValidationError

_LETTER_MAP = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14,
    "F": 15, "G": 16, "H": 17, "I": 34, "J": 18,
    "K": 19, "L": 20, "M": 21, "N": 22, "O": 35,
    "P": 23, "Q": 24, "R": 25, "S": 26, "T": 27,
    "U": 28, "V": 29, "W": 32, "X": 30, "Y": 31,
    "Z": 33,
}

_COUNTY_MAP = {
    "A": "臺北市", "B": "臺中市", "C": "基隆市", "D": "臺南市",
    "E": "高雄市", "F": "新北市", "G": "宜蘭縣", "H": "桃園市",
    "I": "嘉義市", "J": "新竹縣", "K": "苗栗縣", "L": "臺中市",
    "M": "南投縣", "N": "彰化縣", "O": "新竹市", "P": "雲林縣",
    "Q": "嘉義縣", "R": "臺南市", "S": "高雄市", "T": "屏東縣",
    "U": "花蓮縣", "V": "臺東縣", "W": "金門縣", "X": "澎湖縣",
    "Y": "陽明山", "Z": "連江縣",
}


def validate_tw_id(id_number: str) -> bool:
    """驗證台灣身分證字號，合法回傳 True，非法拋出 ValidationError。"""
    if not id_number or len(id_number) != 10:
        raise ValidationError(f"身分證字號格式錯誤：{id_number}")

    id_upper = id_number.upper()
    first = id_upper[0]
    if first not in _LETTER_MAP:
        raise ValidationError(f"身分證首碼錯誤：{first}")

    digits = id_upper[1:]
    if not digits.isdigit():
        raise ValidationError(f"身分證字號第 2-10 碼必須為數字：{id_number}")

    second = int(digits[0])
    if second not in (1, 2):
        raise ValidationError(f"身分證第 2 碼必須為 1（男）或 2（女）：{id_number}")

    letter_val = _LETTER_MAP[first]
    n = [letter_val // 10, letter_val % 10] + [int(c) for c in digits]

    weights = [1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1]
    total = sum(n[i] * weights[i] for i in range(11))

    if total % 10 != 0:
        raise ValidationError(f"身分證字號驗碼錯誤：{id_number}")

    return True


def get_gender_from_tw_id(id_number: str) -> str:
    """從身分證字號推算性別，回傳 'male' 或 'female'。"""
    if not id_number or len(id_number) < 2:
        raise ValidationError(f"身分證字號格式錯誤：{id_number}")
    second = id_number[1]
    if second == "1":
        return "male"
    elif second == "2":
        return "female"
    raise ValidationError(f"無法判斷性別，第 2 碼為：{second}")


def get_county_from_tw_id(id_number: str) -> str:
    """從身分證字號首碼推算戶籍縣市。"""
    if not id_number:
        raise ValidationError("身分證字號不可空白")
    first = id_number[0].upper()
    county = _COUNTY_MAP.get(first)
    if not county:
        raise ValidationError(f"無效的身分證首碼：{first}")
    return county
