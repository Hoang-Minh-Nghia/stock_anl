# Deploy dashboard

Xem hướng dẫn đầy đủ tại `../README.md`.

```sh
npm install -g firebase-tools
firebase login
cd anal_stock
firebase deploy --only hosting     # giao diện
firebase deploy --only database    # Security Rules (chỉ sau khi đã đặt FIREBASE_AUTH_TOKEN cho pipeline)
```

Dữ liệu do `python updat_stock.py` (thư mục gốc) ghi vào Firebase:
`stocks/{ngày}`, `flows/{ngày}`, `meta/latest`.
