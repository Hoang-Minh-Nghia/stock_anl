import numpy as np
import pytest

from smart_money import config
from smart_money.scoring import classify_row


@pytest.mark.parametrize(
    "row, expected",
    [
        ({"Nganh": "Công nghệ và thông tin", "ROE_pct": 28.0, "PE": 18.0}, config.GROUP_GROWTH),
        ({"Nganh": "Ngân hàng", "ROE_pct": 22.0, "PE": 8.0}, config.GROUP_CYCLICAL),
        ({"Nganh": "Vận tải - Kho bãi", "ROE_pct": 12.0, "PE": 8.5}, config.GROUP_DEFENSIVE),
        ({"Nganh": "Hàng không", "ROE_pct": 5.0, "PE": -5.0}, config.GROUP_NEUTRAL),
        ({"Nganh": "Sản xuất", "ROE_pct": np.nan, "PE": np.nan}, config.GROUP_NEUTRAL),
        # HPG: FMarket ghi "Sản xuất" nhưng Simplize ghi Kim loại → chu kỳ (trước đây bị bỏ sót)
        ({"Nganh": "Sản xuất", "Nhom_Nganh": "Nguyên vật liệu", "Nganh_Chi_Tiet": "Kim loại và Khai khoáng", "ROE_pct": 14}, config.GROUP_CYCLICAL),
        ({"Nganh": "Tiện ích", "Nhom_Nganh": "Tiện ích", "ROE_pct": 12, "PE": 15}, config.GROUP_DEFENSIVE),
        ({"Nganh": "Sản xuất", "Nhom_Nganh": "Chăm sóc sức khỏe", "Nganh_Chi_Tiet": "Dược phẩm", "ROE_pct": 16, "PE": 14}, config.GROUP_DEFENSIVE),
        # "Hàng hóa không thiết yếu" không được nhầm thành phòng thủ
        ({"Nganh": "Bán lẻ", "Nhom_Nganh": "Hàng hóa không thiết yếu", "ROE_pct": 12, "PE": 20}, config.GROUP_NEUTRAL),
        # "Thiết bị điện" không phải tiện ích điện
        ({"Nganh": "Thiết bị điện", "ROE_pct": 9, "PE": 20}, config.GROUP_NEUTRAL),
        ({"Nganh": "Sản xuất", "ROE_pct": 16, "Tang_Truong_LNST_pct": 25, "PE": 20}, config.GROUP_GROWTH),
    ],
)
def test_classify_row(row, expected):
    assert classify_row(row) == expected
