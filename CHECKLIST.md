# Checklist dự án phân tích chứng khoán (chạy cục bộ)

`[x]` đã làm và kiểm tra · `[ ]` bạn cần tự làm / tự quyết

## A. Dòng tiền quỹ (Smart Money)
- [x] A1. Lấy danh sách quỹ qua API `products/filter` (68 quỹ, quét cả quỹ trái phiếu/cân bằng có nắm CP) — trước bỏ sót quỹ ID > 80
- [x] A2. Tải song song + retry; quỹ lỗi mạng giữ danh mục kỳ trước; quỹ ngừng công bố không tính là đang nắm
- [x] A3. Lưu số cổ phiếu, ngày báo cáo; tính dòng tiền theo **kỳ báo cáo** bằng thay đổi số CP × giá
- [x] A4. Xử lý chia tách/thưởng CP, giới hạn top 10, kỳ chuyển tiếp 1 ngày, lần chạy đầu không có tín hiệu giả
- [x] A5. Mỗi ngày 1 snapshot; cảnh báo khi hai lần chạy cách nhau > 35 ngày (có thể lỡ kỳ báo cáo)

## B. Chấm điểm
- [x] B1. Giá mục tiêu ≤ 180 ngày (trung vị), thiếu → trung lập; lọc thanh khoản theo GTGD, thiếu → loại
- [x] B2. Mô hình đa nhân tố v4, xếp hạng trong ngành, `Data_Coverage`, loại ETF
- [x] B3. Phân nhóm theo từ khoá ngành FMarket + Simplize
- [x] B4. Công cụ IC `tools/evaluate_scores.py` (điểm cũ v3: IC 0.04, t=0.9 — không có ý nghĩa); trọng số v4 theo IC 3 & 14 năm

## C. Chạy cục bộ & online
- [x] C1. Kho giá dùng chung `data/prices/`: chỉ tải ngày thiếu, tự tải lại khi giá quá khứ bị điều chỉnh, không lưu nến chưa đóng cửa
- [x] C2. Bỏ toàn bộ code cloud cũ; kết quả lưu `anal_stock/public/data/runs/{ngày}.json` + CSV
- [x] C3. Nhập 177 ngày điểm số lịch sử về máy (đã kiểm tra IC khớp số liệu cũ)
- [x] C4. `run.py` chạy tất cả + mở dashboard; `Chay_phan_tich.bat` bấm đúp là chạy
- [x] C5. Lần chạy lặp lại trong ngày không tải lại giá (100/100 mã "đã đủ")
- [x] C6. Đã xoá toàn bộ Firebase và toàn bộ phần AI (LSTM) khỏi dự án
- [ ] C7. **Bạn làm nốt**: database Firebase trên cloud vẫn còn (project `stock-trading-ad193`, đang đọc được công khai) — vào Firebase Console xoá Realtime Database / Hosting hoặc xoá cả project

## C2. Chạy online (GitHub Actions + Pages)
- [x] Workflow chạy 16:00 giờ VN các ngày trong tuần (+ lượt chạy lại 18:00 phòng lỗi tạm thời), commit dữ liệu vào repo, deploy GitHub Pages
- [x] Dashboard tự hiện nút "Run workflow" khi dữ liệu quá 3 ngày; README có huy hiệu trạng thái
- [x] Kho giá 2 nguồn: SSI (chạy ở VN) ↔ Vietcap (chạy được từ máy chủ nước ngoài), tự chuyển khi bị chặn
- [x] Lấy giá theo lô 30 mã/request (Vietcap chặn theo số lượt gọi): 79 mã + lịch sử từ 2000 trong ~9 giây
- [x] Chốt chặn: dưới 50% mã có giá → pipeline dừng; dưới 10 mã được chấm điểm → không deploy
- [x] Workflow `kiem-tra-nguon.yml` để dò nguồn nào gọi được từ GitHub (kết quả ghi ra `ket-qua-do-nguon.txt`)

## D. Dashboard
- [x] D1. Đọc file cục bộ (tải ~0,1 giây), ô chọn ngày xem lại lịch sử, giữ ngày khi chuyển trang
- [x] D2. Chống XSS, CSS/JS dùng chung, bảng sort riêng, tìm kiếm/lọc, bảng chi tiết từng mã
- [x] D3. Trang dòng tiền: kỳ so sánh, quỹ ↔ mã, trạng thái quỹ; trang nhóm chiến lược tiếng Việt có dấu
- [x] D4. Cảnh báo dữ liệu cũ / mô hình cũ; kiểm tra hiển thị mobile

## F. Kiểm thử & tài liệu
- [x] F1. 41 unit test (kho giá, dòng tiền, chấm điểm, phân nhóm, feature AI không look-ahead)
- [x] F2. `README.md` hướng dẫn chạy cục bộ
- [x] F3. Sao lưu mã nguồn gốc `_backup/2026-09-15_truoc_nang_cap/`
