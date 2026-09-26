# Smart Money VN — công cụ phân tích cổ phiếu cá nhân (chạy trên máy)

Không cần server, không cần tài khoản cloud. Mọi dữ liệu nằm trong thư mục dự án.

> Công cụ phân tích cá nhân. Điểm số và dự báo **không phải khuyến nghị đầu tư**.

## Cài đặt (1 lần)

```bash
pip install pandas numpy requests scikit-learn joblib tqdm tensorflow matplotlib pytest
python ai_stock/get_stock_name.py   # (tuỳ chọn) khởi tạo phần AI: danh sách VN100 + lịch sử giá
```

## Chạy hằng ngày

Bấm đúp **`Chay_phan_tich.bat`**, hoặc:

```bash
python run.py --serve       # cập nhật dữ liệu còn thiếu → phân tích → mở dashboard
python run.py               # chỉ cập nhật & phân tích
python run.py --serve-only  # chỉ mở dashboard với dữ liệu đã có
python run.py --no-ai       # bỏ qua phần AI (nhanh hơn, ~30 giây)
```

Mỗi lần chạy:
1. **Giá** (SSI hoặc Vietcap) — chỉ tải những ngày còn thiếu vào `data/prices/`. Hai nguồn tự chuyển cho nhau:
   SSI chạy được từ Việt Nam nhưng **chặn IP nước ngoài (403)**, Vietcap thì ngược lại — nhờ vậy cùng một code
   chạy được cả trên máy lẫn trên GitHub Actions. Giá hai nguồn lệch trung bình 0,1% và các phiên gần đây trùng khớp. Nếu SSI điều chỉnh giá quá khứ (cổ tức, thưởng CP), mã đó được tải lại toàn bộ để không có bước nhảy giá giả. Nến của phiên chưa đóng cửa (trước 15:05) không được lưu.
2. **Danh mục quỹ** (FMarket) — lưu snapshot của ngày. FMarket **chỉ có danh mục hiện tại**, không lấy lại được ngày đã qua; nhưng danh mục chỉ đổi theo kỳ báo cáo (~hàng tháng), nên **chạy ít nhất mỗi tuần 1 lần** là không bỏ lỡ kỳ nào. Dashboard sẽ cảnh báo nếu hai lần chạy cách nhau quá 35 ngày.
3. **Dữ liệu cơ bản** (Simplize) → chấm điểm → lưu kết quả của ngày.
4. **AI** — cập nhật chỉ báo và dự báo nếu đã huấn luyện mô hình.

Dashboard có ô **chọn ngày** để xem lại kết quả các ngày trước.

## Dữ liệu trên máy

| Thư mục | Nội dung |
|---|---|
| `data/prices/` | Giá ngày từng mã (dùng chung Smart Money + AI) |
| `data/smart_money_snapshots/` | Danh mục quỹ theo ngày — **nguồn lịch sử dòng tiền, đừng xoá** |
| `data/smart_money_output/` | `scores_{ngày}.csv`, `fund_flows_{ngày}.csv` (mở bằng Excel) |
| `anal_stock/public/data/` | Dữ liệu dashboard: `runs/{ngày}.json`, `index.json`, `score_history.json` |
| `ai_stock/data/`, `ai_stock/models/` | Dữ liệu & mô hình AI, `predictions_latest.csv` |

Lịch sử 177 ngày điểm số (03–09/2026) chạy bằng mô hình cũ v3, đã được nhập sẵn vào `anal_stock/public/data/runs/`.

## Smart Money

Cấu hình (ngưỡng thanh khoản, trọng số, từ khoá ngành...) trong `smart_money/config.py`.

**Dòng tiền quỹ**: so sánh kỳ báo cáo hiện tại với kỳ trước của từng quỹ; dòng tiền = thay đổi **số cổ phiếu** × giá (loại bỏ ảnh hưởng giá); FMarket chỉ công bố top 10 mã/quỹ nên mã rời danh sách được ước lượng thận trọng; quỹ lỗi mạng giữ danh mục kỳ trước.

**Chấm điểm (v4)**: Định giá 20% · Chất lượng 25% · Tăng trưởng 10% · Xu hướng giá 10% · Rủi ro thấp 15% · Dòng tiền quỹ 15% · Giá mục tiêu 5%. Định giá/chất lượng xếp hạng trong ngành; loại ETF và mã có GTGD TB 20 phiên < 3 tỷ. Căn cứ trọng số ghi trong `config.py`.

Kiểm chứng sức dự báo (IC):
```bash
python -m tools.evaluate_scores                             # điểm đã lưu các ngày
python -m tools.evaluate_scores --price-factors --years 14  # nhân tố giá trên VN100
```

## AI (LSTM)

```bash
python ai_stock/run_daily_update.py        # (run.py tự gọi) giá ngày thiếu + chỉ báo + bối cảnh thị trường
python ai_stock/process_data_for_lstm.py   # tạo dataset (mục tiêu: lợi nhuận log 5 phiên)
python ai_stock/train_lstm_model.py        # huấn luyện + đánh giá so với baseline (~2 phút CPU)
python ai_stock/predict_future.py          # (run.py tự gọi) dự báo & xếp hạng → models/predictions_latest.csv
```

Mô hình hiện tại **chưa vượt baseline** trên tập test (IC 0.019) nên kết quả được đánh dấu "chỉ tham khảo". Nên huấn luyện lại vài tháng một lần khi có thêm dữ liệu.

## Kiểm thử

```bash
python -m pytest
```

## Lưu trữ
- `_backup/2026-09-15_truoc_nang_cap/` — mã nguồn + giá gốc trước khi nâng cấp
- `_archive/dnse/` — client DNSE LightSpeed API (dùng khi có API key)

## Chạy online (không cần mở máy)

Kiến trúc: **GitHub Actions (cron) → chạy pipeline → commit dữ liệu vào repo → GitHub Pages hiển thị**.
Không cần database, không cần backend, không cần secret nào.

| Thành phần | Nơi chạy | Chi phí |
|---|---|---|
| Thu thập + chấm điểm (`updat_stock.py`) | GitHub Actions, 16:00 giờ VN các ngày trong tuần | Miễn phí (~2 phút/lần) |
| Lưu trữ lịch sử | Chính repo (`data/`, `anal_stock/public/data/`) | Miễn phí |
| Dashboard | GitHub Pages | Miễn phí |

Kho giá `data/prices/` **không** nằm trong repo; GitHub Actions dùng cache, mất cache thì tải lại (~1 phút).
Trên GitHub chỉ tải 3 năm gần nhất (đủ cho mọi chỉ số của Smart Money) vì Vietcap giới hạn tần suất gọi.

### Các bước đưa lên online

1. Tạo repo rỗng trên GitHub (Public để dùng Pages miễn phí).
2. Đẩy code lên:
   ```bash
   git remote add origin https://github.com/<tên-của-bạn>/<tên-repo>.git
   git push -u origin main
   ```
3. Repo → **Settings** → **Pages** → Source: **GitHub Actions**.
4. Repo → **Settings** → **Actions** → **General** → Workflow permissions: **Read and write permissions**.
5. Repo → **Actions** → workflow *Cập nhật dữ liệu & dashboard* → **Run workflow** để chạy thử.
6. Xem log. Chạy xong, dashboard ở `https://<tên-của-bạn>.github.io/<tên-repo>/`.

Sau đó hệ thống tự chạy hằng ngày. Khi workflow lỗi, GitHub gửi email báo.

### Vẫn chạy được trên máy
`python run.py --serve` vẫn hoạt động song song. Nhớ `git pull` trước để lấy dữ liệu mà Actions đã tạo,
và `git push` nếu bạn chạy trên máy và muốn đẩy kết quả lên.
