"""Cấu hình tập trung cho pipeline Smart Money. Mọi ngưỡng/trọng số có thể chỉnh tại đây."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT_DIR / "data" / "smart_money_snapshots"
OUTPUT_DIR = ROOT_DIR / "data" / "smart_money_output"
PUBLIC_DATA_DIR = ROOT_DIR / "anal_stock" / "public" / "data"

VN_TZ = "Asia/Ho_Chi_Minh"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fmarket.vn/",
}

# --- Nguồn dữ liệu ---
FMARKET_FILTER_URL = "https://api.fmarket.vn/res/products/filter"
FMARKET_PRODUCT_URL = "https://api.fmarket.vn/res/products/{fund_id}"
# Loại quỹ được quét (quỹ trái phiếu đôi khi cũng nắm cổ phiếu; quỹ không có cổ phiếu tự bị bỏ qua)
FMARKET_FUND_ASSET_TYPES = {"STOCK", "BALANCED", "BOND"}
FMARKET_PRODUCT_TYPES = ["NEW_FUND", "TRADING_FUND"]

SIMPLIZE_HOME_URL = "https://simplize.vn/"
SIMPLIZE_REPORT_URL = "https://simplize.vn/_next/data/{build_id}/co-phieu/{ticker}/bao-cao.json?ticker={ticker}"

SSI_TIME_URL = "https://iboard-query.ssi.com.vn/system/time"

BENCHMARK_SYMBOL = "VNINDEX"
PRICE_HISTORY_LOOKBACK_DAYS = 400   # cửa sổ tính chỉ số giá/rủi ro
PRICE_STORE_YEARS = 3               # độ sâu lịch sử cần tải khi gặp mã mới (đủ cho mọi chỉ số ở trên)
PRICE_WORKERS = 3                   # ít luồng để không bị nguồn giá chặn theo tần suất
HTTP_WORKERS = 6

# --- Dòng tiền quỹ ---
TOP_HOLDING_LIST_SIZE = 10          # FMarket chỉ công bố top 10 mã mỗi quỹ
MIN_FLOW_ABS_VND = 1_000_000_000    # |dòng tiền| < 1 tỷ coi là nhiễu
FLOW_NOISE_REL = 0.01               # hoặc < 1% giá trị nắm giữ kỳ trước
SPLIT_PRICE_DROP = 0.92             # giá/CP thấp hơn >8% so với giá thị trường mà giá trị giữ nguyên → nghi chia tách/thưởng CP
SPLIT_VALUE_TOLERANCE = 0.1

# --- Lọc & chấm điểm ---
ETF_PREFIXES = ("FUE", "E1V")
MIN_ADV_VND = 3_000_000_000         # giá trị giao dịch TB 20 phiên tối thiểu
ANALYST_TARGET_MAX_AGE_DAYS = 180
MIN_SECTOR_SIZE = 4                 # ngành ít hơn N mã → xếp hạng toàn thị trường
WINSOR_QUANTILES = (0.05, 0.95)
MIN_DATA_COVERAGE = 0.6

# Trọng số nhân tố — kiểm chứng bằng `python -m tools.evaluate_scores --price-factors [--from-master --years 14]` (09/2026):
#                         3 năm (57 mã quỹ nắm)          14 năm (VN100)
#   Biến động thấp 60D    IC +0.11 (t=3.3)                IC +0.01 (t=0.3)
#   Momentum 6-1          IC ≈ 0                          IC +0.04 (t=2.1)
#   Sụt giảm thấp 6T      IC +0.02 (20 phiên)             IC +0.09 (60 phiên, t=3.2)
#   Điểm cũ v3            IC +0.04 (t=0.9) → không có ý nghĩa thống kê
# Hiệu quả thay đổi theo giai đoạn → phân bổ cân bằng thay vì dồn vào nhân tố mạnh nhất gần đây.
# Lưu ý survivorship bias: danh sách mã hiện tại thiên về mã "sống sót". Nhân tố cơ bản chưa kiểm chứng được
# (không có lịch sử BCTC) → trọng số theo nghiên cứu phổ biến.
FACTOR_WEIGHTS = {
    "Score_Value": 0.20,
    "Score_Quality": 0.25,
    "Score_Growth": 0.10,
    "Score_Momentum": 0.10,
    "Score_LowRisk": 0.15,
    "Score_SmartMoney": 0.15,
    "Score_Upside": 0.05,
}

# --- Phân nhóm chiến lược (so khớp từ khoá trên tên ngành FMarket + Simplize) ---
GROUP_GROWTH = "Tăng trưởng (Phi chu kỳ)"
GROUP_CYCLICAL = "Tấn công (Chu kỳ)"
GROUP_DEFENSIVE = "Phòng thủ (Cổ tức)"
GROUP_NEUTRAL = "Theo dõi thêm / Trung lập"

CYCLICAL_KEYWORDS = [
    "ngân hàng", "chứng khoán", "môi giới", "thị trường vốn", "bất động sản",
    "xây dựng", "vật liệu", "kim loại", "khai khoáng", "thép", "hóa chất",
    "dầu khí", "dầu và khí", "năng lượng", "cao su",
]
DEFENSIVE_KEYWORDS = [
    "tiện ích", "sản xuất điện", "nước", "dược", "chăm sóc sức khỏe", "y tế",
    "hàng hóa thiết yếu", "thực phẩm", "đồ uống", "bảo hiểm",
]
