# Hướng dẫn triển khai hệ thống thu thập dữ liệu tự động

Kiến trúc: **GitHub Actions (cron) + Database free + Web online**

---

## Mục tiêu

- Chạy một script Python **mỗi ngày** để thu thập dữ liệu từ internet.
- Lưu dữ liệu vào **database online** (miễn phí).
- Hiển thị dữ liệu trên **web online** – bạn chỉ cần mở trình duyệt là xem được.
- Toàn bộ hệ thống chạy trên cloud, **không cần mở máy cá nhân**.

---

## Tổng quan kiến trúc

```text
[GitHub Actions] --(chạy mỗi ngày)--> [main.py]
                                           |
                                           v
                                    [Database online]
                                           ^
                                           |
                                    [Web của bạn]
                                           |
                                    [Trình duyệt của bạn]
```

**Luồng hoạt động:**

1. GitHub Actions kích hoạt workflow theo lịch (cron).
2. `main.py` chạy trên server của GitHub:
   - Thu thập dữ liệu từ API / web.
   - Lưu vào database online.
3. Web của bạn (deploy online) đọc dữ liệu từ database và hiển thị.
4. Bạn mở trình duyệt, truy cập URL web → xem dữ liệu mới nhất.

---

## Bước 1: Chuẩn bị tài khoản và công cụ

### 1.1. Tài khoản cần có

- **GitHub**: để chứa repo và chạy GitHub Actions.
- **Nhà cung cấp database free** (chọn 1 trong các option sau):
  - [Supabase](https://supabase.com) (PostgreSQL, khuyến nghị)
  - [Neon](https://neon.tech) (PostgreSQL serverless)
  - [MongoDB Atlas](https://www.mongodb.com/atlas) (NoSQL)
- **Nền tảng deploy web** (tùy stack của bạn):
  - Frontend tĩnh: Vercel, Netlify, Cloudflare Pages.
  - Backend + frontend: Render, Railway, Fly.io, VPS…

### 1.2. Công cụ trên máy

- Git (đã cài và cấu hình).
- Trình soạn thảo code (VS Code, v.v.).
- Python 3.10+ (để test local, không bắt buộc).

---

## Bước 2: Tạo database free (ví dụ với Supabase)

> Bạn có thể thay Supabase bằng Neon / MongoDB Atlas với ý tưởng tương tự.

### 2.1. Tạo project Supabase

1. Truy cập: https://supabase.com
2. Đăng nhập / đăng ký tài khoản.
3. Nhấn **New Project**:
   - Đặt tên project (ví dụ: `data-collector`).
   - Chọn region gần bạn (ví dụ: Singapore).
   - Đặt password cho database.
4. Đợi project được tạo xong.

### 2.2. Tạo bảng trong database

1. Vào project → **Table Editor**.
2. Nhấn **New Table**:
   - Tên bảng: `daily_data` (hoặc tên phù hợp với dữ liệu của bạn).
   - Thêm các cột, ví dụ:
     - `id` (int8, primary key, auto increment)
     - `created_at` (timestamptz, default: now())
     - `date` (date)
     - `value` (numeric / text / jsonb tùy dữ liệu)
     - Các cột khác tùy nhu cầu.
3. Lưu bảng.

### 2.3. Lấy thông tin kết nối

1. Vào **Settings** → **Database**.
2. Tìm mục **Connection string** (URI).
   - Dạng:  
     `postgresql://postgres:[PASSWORD]@db.xxx.supabase.co:5432/postgres`
3. Copy connection string này, tạm lưu ở nơi an toàn.

> Với Supabase, bạn cũng có thể dùng REST API (Supabase URL + anon/public key). Cách dùng DB qua SQL/ORM thường đơn giản hơn cho backend.

---

## Bước 3: Tạo GitHub repo và cấu trúc project

### 3.1. Tạo repo trên GitHub

1. Đăng nhập GitHub.
2. Nhấn **New repository**.
3. Đặt tên, ví dụ: `auto-data-collector`.
4. Chọn **Public** hoặc **Private** (Private vẫn có 2.000 phút Actions/tháng miễn phí).
5. Tạo repo.

### 3.2. Clone repo về máy

```bash
git clone https://github.com/your-username/auto-data-collector.git
cd auto-data-collector
```

### 3.3. Tạo cấu trúc file

Trong thư mục repo, tạo các file sau:

```text
auto-data-collector/
├─ main.py
├─ requirements.txt
└─ .github/
   └─ workflows/
      └─ daily_job.yml
```

---

## Bước 4: Viết script thu thập dữ liệu (`main.py`)

Dưới đây là mẫu `main.py` dùng Supabase (PostgreSQL). Bạn chỉnh lại logic thu thập dữ liệu cho phù hợp.

### 4.1. Nội dung `main.py`

```python
import os
import datetime
from supabase import create_client, Client

# ========================
# Cấu hình từ biến môi trường
# ========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "daily_data"  # Tên bảng bạn đã tạo

# ========================
# Hàm thu thập dữ liệu
# ========================
def fetch_data():
    """
    Thay logic này bằng cách bạn lấy dữ liệu thực tế:
    - Gọi API
    - Cào web
    - Đọc file, v.v.
    """
    # Ví dụ: trả về một dict đơn giản
    today = datetime.date.today()
    value = 123.45  # Thay bằng dữ liệu thực tế
    return {
        "date": today.isoformat(),
        "value": value,
    }

# ========================
# Hàm lưu dữ liệu vào Supabase
# ========================
def save_to_supabase(data: dict):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Insert vào bảng
    response = supabase.table(TABLE_NAME).insert(data).execute()
    print("Inserted data:", response.data)

# ========================
# Main
# ========================
def main():
    print("Starting data collection...")

    # 1. Thu thập dữ liệu
    data = fetch_data()
    print("Fetched data:", data)

    # 2. Lưu vào database
    save_to_supabase(data)

    print("Data collection finished.")

if __name__ == "__main__":
    main()
```

> Nếu bạn dùng Neon / MongoDB / PostgreSQL thuần, có thể thay phần kết nối bằng `psycopg2`, `sqlalchemy`, `pymongo`, v.v.

---

## Bước 5: Khai báo thư viện (`requirements.txt`)

Tạo file `requirements.txt` với nội dung:

```txt
supabase
requests
python-dotenv
```

Thêm các thư viện khác nếu `main.py` của bạn cần.

---

## Bước 6: Cấu hình GitHub Actions (`daily_job.yml`)

### 6.1. Tạo file workflow

Tạo file: `.github/workflows/daily_job.yml`

### 6.2. Nội dung file

```yaml
name: Daily Data Collection

on:
  schedule:
    # Chạy mỗi ngày lúc 00:00 giờ Việt Nam (UTC+7)
    # Cron dùng UTC, nên 00:00 VN = 17:00 UTC ngày trước
    - cron: "0 17 * * *"
  workflow_dispatch:  # Cho phép chạy thủ công khi test

jobs:
  collect:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then
            pip install -r requirements.txt
          fi

      - name: Run data collection script
        run: python main.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
```

> Nếu bạn dùng database khác, thay `SUPABASE_URL`, `SUPABASE_KEY` bằng `DATABASE_URL`, `MONGODB_URI`, v.v. và điều chỉnh `main.py` cho phù hợp.

---

## Bước 7: Cấu hình Secrets trên GitHub

### 7.1. Lấy Supabase URL và Key

1. Vào project Supabase → **Settings** → **API**.
2. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon/public key** → `SUPABASE_KEY`  
     (với việc insert dữ liệu từ client/public, anon key là đủ nếu bạn đã cấu hình RLS cho phép insert).

> Nếu muốn an toàn hơn, có thể tạo **service role key** và dùng key đó trong server-side (GitHub Actions coi như server).

### 7.2. Thêm Secrets vào GitHub repo

1. Vào repo GitHub → **Settings**.
2. Chọn **Secrets and variables** → **Actions**.
3. Nhấn **New repository secret**:
   - Name: `SUPABASE_URL`
   - Value: dán URL project Supabase.
4. Nhấn **Add secret**.
5. Lặp lại với:
   - Name: `SUPABASE_KEY`
   - Value: dán key bạn copy ở trên.

---

## Bước 8: Đẩy code lên GitHub

Từ thư mục repo:

```bash
git add .
git commit -m "Add data collection script and GitHub Actions workflow"
git push origin main
```

Kiểm tra:

- Vào repo → tab **Actions**.
- Bạn sẽ thấy workflow `Daily Data Collection`.
- Có thể nhấn vào và bấm **Run workflow** để chạy thử ngay (không cần đợi đến giờ cron).
- Xem log để đảm bảo:
  - Cài đặt thư viện thành công.
  - `main.py` chạy không lỗi.
  - Dữ liệu được insert vào Supabase.

---

## Bước 9: Kiểm tra dữ liệu trong database

1. Vào Supabase → **Table Editor**.
2. Chọn bảng `daily_data`.
3. Kiểm tra xem có bản ghi mới được thêm sau khi chạy workflow chưa.

Nếu có dữ liệu → phần thu thập và lưu trữ đã hoạt động.

---

## Bước 10: Xây dựng và deploy web hiển thị dữ liệu

Phần này phụ thuộc vào stack bạn dùng. Dưới đây là một ví dụ đơn giản với **Python + FastAPI + Vercel/Render**.

### 10.1. Tạo backend API đơn giản (FastAPI)

Tạo thêm các file trong repo:

```text
auto-data-collector/
├─ main.py              (script thu thập)
├─ api.py               (backend API cho web)
├─ requirements.txt
└─ .github/workflows/
   └─ daily_job.yml
```

#### `api.py`

```python
import os
from fastapi import FastAPI
from supabase import create_client, Client
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Cho phép CORS nếu frontend ở domain khác
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "daily_data"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.get("/api/data")
def get_data(limit: int = 30):
    """
    Lấy limit bản ghi mới nhất từ bảng daily_data.
    """
    response = (
        supabase
        .table(TABLE_NAME)
        .select("*")
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data
```

Cập nhật `requirements.txt`:

```txt
supabase
requests
python-dotenv
fastapi
uvicorn
```

### 10.2. Deploy backend lên Render / Railway

#### Ví dụ với Render

1. Tạo tài khoản: https://render.com
2. Tạo **New Web Service**:
   - Connect với repo GitHub của bạn.
   - Root directory: `/` (hoặc thư mục chứa `api.py` nếu bạn tách ra).
   - Build Command:
     ```bash
     pip install -r requirements.txt
     ```
   - Start Command:
     ```bash
     uvicorn api:app --host 0.0.0.0 --port $PORT
     ```
3. Trong phần **Environment Variables**, thêm:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
4. Deploy.

Render sẽ cấp cho bạn một URL, ví dụ:

`https://your-api.onrender.com`

Test API:

- Mở trình duyệt, truy cập:
  `https://your-api.onrender.com/api/data`
- Nếu thấy JSON trả về danh sách dữ liệu → backend hoạt động.

### 10.3. Tạo frontend đơn giản

Bạn có thể tạo một trang HTML + JS đơn giản, deploy lên Vercel/Netlify.

Ví dụ `index.html`:

```html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <title>Dữ liệu thu thập tự động</title>
  <style>
    body { font-family: sans-serif; padding: 20px; }
    table { border-collapse: collapse; width: 100%; max-width: 800px; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
    th { background: #f5f5f5; }
  </style>
</head>
<body>
  <h1>Dữ liệu thu thập tự động</h1>
  <table id="data-table">
    <thead>
      <tr>
        <th>Ngày</th>
        <th>Giá trị</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <script>
    const API_URL = "https://your-api.onrender.com/api/data"; // Thay URL của bạn

    fetch(API_URL)
      .then(res => res.json())
      .then(data => {
        const tbody = document.querySelector("#data-table tbody");
        data.forEach(row => {
          const tr = document.createElement("tr");
          const tdDate = document.createElement("td");
          const tdValue = document.createElement("td");
          tdDate.textContent = row.date;
          tdValue.textContent = row.value;
          tr.appendChild(tdDate);
          tr.appendChild(tdValue);
          tbody.appendChild(tr);
        });
      })
      .catch(err => {
        console.error("Lỗi khi lấy dữ liệu:", err);
      });
  </script>
</body>
</html>
```

Deploy lên Vercel/Netlify:

- Tạo repo mới hoặc dùng repo hiện tại (tách folder `frontend/` nếu muốn).
- Connect với Vercel/Netlify.
- Trỏ tới file `index.html`.
- Lấy URL, ví dụ: `https://your-app.vercel.app`.

Mở URL này trên trình duyệt → bạn sẽ thấy bảng dữ liệu lấy từ API, mà API đọc từ database đã được script ghi vào.

---

## Bước 11: Vận hành và theo dõi

### 11.1. Kiểm tra lịch chạy

- Vào repo GitHub → **Actions** → chọn workflow `Daily Data Collection`.
- Xem các lần chạy tự động theo cron.
- Nếu có lỗi, xem log để debug.

### 11.2. Điều chỉnh giờ chạy

Trong `daily_job.yml`:

```yaml
- cron: "0 17 * * *"
```

- Đổi phút/giờ/ngày theo cron syntax.
- Nhớ rằng cron dùng **UTC**.  
  Ví dụ:
  - 00:00 VN (UTC+7) → `0 17 * * *`
  - 07:00 VN → `0 0 * * *`

### 11.3. Mở rộng

- Thêm nhiều script khác (nhiều file `.py`, nhiều workflow).
- Thêm xử lý lỗi, gửi thông báo (Telegram, email) khi script lỗi.
- Thêm biểu đồ, dashboard trên frontend.

---

## Xử lý sự cố thường gặp

### 1. Workflow không chạy

- Kiểm tra:
  - File `.github/workflows/daily_job.yml` có đúng đường dẫn và cú pháp không.
  - Repo có đang enable Actions không (Settings → Actions).
- Thử nhấn **Run workflow** để test thủ công.

### 2. Lỗi kết nối database

- Kiểm tra:
  - Secrets (`SUPABASE_URL`, `SUPABASE_KEY`) có đúng không.
  - Supabase có cho phép kết nối từ IP lạ không (thường mặc định là có).
  - Tên bảng (`TABLE_NAME`) có đúng với bảng đã tạo không.

### 3. Frontend không hiển thị dữ liệu

- Kiểm tra:
  - URL API trong `index.html` có đúng không.
  - Backend có đang chạy và trả JSON hợp lệ không (test trực tiếp trên trình duyệt).
  - Console của trình duyệt có lỗi CORS hay network không.

---

## Tài liệu tham khảo

- GitHub Actions – Scheduled events:  
  https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
- Supabase Python client:  
  https://supabase.com/docs/reference/python
- FastAPI documentation:  
  https://fastapi.tiangolo.com/
- Render documentation:  
  https://render.com/docs

---

## Ghi chú

- Toàn bộ hệ thống chạy online: bạn chỉ cần mở trình duyệt và truy cập URL frontend là xem được dữ liệu.
- Bạn có thể thay đổi:
  - Nhà cung cấp database (Neon, MongoDB Atlas, v.v.).
  - Nền tảng deploy (Railway, Fly.io, VPS, v.v.).
  - Ngôn ngữ/backend (Node.js + Express, v.v.).
- Nếu cần, mình có thể điều chỉnh file này cho đúng với stack cụ thể của bạn (ví dụ: dùng Neon + Node.js + Vercel).