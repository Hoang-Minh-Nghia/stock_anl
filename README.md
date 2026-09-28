# Smart Money VN — công cụ phân tích cổ phiếu cá nhân

[![Cập nhật dữ liệu](https://github.com/Hoang-Minh-Nghia/stock_anl/actions/workflows/cap-nhat.yml/badge.svg)](https://github.com/Hoang-Minh-Nghia/stock_anl/actions/workflows/cap-nhat.yml)

## 👉 Xem tại: https://hoang-minh-nghia.github.io/stock_anl/

Hệ thống chạy hoàn toàn trên GitHub, **không cần mở máy**. Mỗi ngày thường lúc **16:00 giờ Việt Nam**
(sau khi thị trường đóng cửa) nó tự lấy dữ liệu, chấm điểm và cập nhật trang web.

> Công cụ phân tích cá nhân. Điểm số và dự báo **không phải khuyến nghị đầu tư**.

| Trang | Nội dung |
|---|---|
| Xếp hạng | 3 nhóm cổ phiếu quỹ đang nắm, chấm điểm 7 nhân tố, bấm vào dòng để xem chi tiết |
| Dòng tiền quỹ | Quỹ nào mua/bán mã nào giữa hai kỳ báo cáo |
| Nhóm chiến lược | Phân lớp tấn công / tăng trưởng / phòng thủ / trung lập |

Ô **Ngày** góc trên bên phải để xem lại kết quả những ngày trước (có 179 ngày lịch sử).

## Khi cần chạy lại ngay

Mở [tab Actions](https://github.com/Hoang-Minh-Nghia/stock_anl/actions/workflows/cap-nhat.yml) →
bấm **Run workflow** → đợi khoảng 1 phút → tải lại trang web.

Dashboard cũng tự hiện nút này khi dữ liệu quá 3 ngày chưa cập nhật.

## Khi có sự cố

- Workflow lỗi thì GitHub **gửi email** cho bạn; huy hiệu ở đầu trang này chuyển sang đỏ.
- Trang web **không bị ghi đè bằng dữ liệu hỏng**: nếu dưới 10 mã được chấm điểm, hệ thống dừng và giữ bản cũ.
- Nếu nguồn giá bị chặn, chạy workflow **Dò nguồn dữ liệu** trong tab Actions; kết quả ghi vào `ket-qua-do-nguon.txt`.

## Hệ thống chạy thế nào

```
GitHub Actions (16:00 VN, T2–T6)
   └─ updat_stock.py
        ├─ Giá: Vietcap hoặc SSI → data/prices/ (chỉ tải ngày còn thiếu, 30 mã/request)
        ├─ Danh mục quỹ: FMarket → data/smart_money_snapshots/
        ├─ Cơ bản: Simplize (P/E, ROE, giá mục tiêu)
        └─ Chấm điểm → anal_stock/public/data/runs/{ngày}.json
             └─ commit vào repo → GitHub Pages hiển thị
```

Không database, không backend, không secret. Dữ liệu là file JSON/CSV trong chính repo
(mỗi ngày thêm ~105 KB sau nén, khoảng 26 MB/năm).

**Dòng tiền quỹ**: FMarket chỉ cập nhật danh mục theo kỳ báo cáo (~hàng tháng) nên hệ thống so sánh kỳ hiện tại
với kỳ trước của từng quỹ; dòng tiền tính bằng **thay đổi số cổ phiếu × giá** để loại ảnh hưởng tăng/giảm giá.
FMarket chỉ công bố top 10 mã/quỹ nên mã rời danh sách được ước lượng thận trọng.

**Chấm điểm (v4)**: Định giá 20% · Chất lượng 25% · Tăng trưởng 10% · Xu hướng giá 10% · Rủi ro thấp 15% ·
Dòng tiền quỹ 15% · Giá mục tiêu 5%. Xếp hạng trong ngành; loại ETF và mã có GTGD TB 20 phiên < 3 tỷ.
Căn cứ trọng số ghi trong `smart_money/config.py`.

**Hai nguồn giá**: SSI chạy được từ Việt Nam nhưng chặn IP nước ngoài (403); Vietcap thì ngược lại.
Kho giá tự chọn nguồn đang sống, nhờ vậy cùng một code chạy được cả trên máy lẫn trên GitHub.

## Chạy ở máy (tùy chọn, không bắt buộc)

```bash
pip install -r requirements.txt
git pull                 # lấy dữ liệu GitHub đã tạo
python run.py --serve    # chạy + mở dashboard ở localhost
```

Kiểm chứng thuật toán và chạy test:

```bash
python -m tools.evaluate_scores
python -m pytest
```

## Lưu trữ
- `_backup/` — mã nguồn + dữ liệu trước khi nâng cấp (chỉ trên máy, không đưa lên GitHub)
- `_archive/dnse/` — client DNSE LightSpeed API (dùng khi có API key)
