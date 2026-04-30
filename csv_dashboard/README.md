# CSV Dashboard

Web app quản lý dữ liệu bài toán tiểu học từ file CSV ở root repo.

## Vị trí trong repo

Dashboard này nằm trong thư mục riêng:

```text
csv_dashboard/
  backend/        FastAPI API đọc/ghi CSV
  frontend/       React/Vite UI
  run_web.ps1     Script Windows mở backend + frontend
```

Dữ liệu vẫn nằm ở root repo để các phần khác của dự án có thể dùng chung:

```text
data_warehouse.csv
data_images/
```

## Tính năng

- Quản lý dữ liệu dạng bảng với phân trang, tìm kiếm và lọc nhanh.
- CRUD dữ liệu trực tiếp trên `../data_warehouse.csv`.
- Xem chi tiết từng record, bao gồm câu hỏi, lời giải, choices và ảnh minh họa.
- Preview ảnh từ `../data_images/`.
- Dashboard tổng quan dataset.
- Dashboard chất lượng dữ liệu.

## Chạy nhanh trên Windows

Mở PowerShell ở root repo `K:\GithubRepo\elementary-math-chatbot`, rồi chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\csv_dashboard\run_web.ps1
```

Script sẽ:

1. chạy `poetry install --no-root` ở root repo,
2. chạy `npm install` trong `csv_dashboard/frontend`,
3. mở backend ở `http://127.0.0.1:8000`,
4. mở frontend ở `http://127.0.0.1:5173`,
5. tự mở trình duyệt vào frontend.

## Chạy thủ công

Terminal 1, tại root repo:

```powershell
poetry install --no-root
poetry run uvicorn csv_dashboard.backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd csv_dashboard/frontend
npm install
npm run dev -- --host 127.0.0.1
```

Mở:

```text
http://127.0.0.1:5173
```

## API chính

```text
GET    /api/health
GET    /api/records
GET    /api/records/{id}
POST   /api/records
PUT    /api/records/{id}
DELETE /api/records/{id}
GET    /api/stats/overview
GET    /api/stats/quality
GET    /images/{filename}
```

## Lưu ý về CRUD

CRUD ghi trực tiếp vào `data_warehouse.csv`:

- `POST` tự cấp `id = max(id) + 1`.
- `PUT` không cho sửa `id`, chỉ sửa các cột dữ liệu.
- `DELETE` xóa record khỏi CSV.
- Xóa record không xóa file trong `data_images/` để tránh mất ảnh đang được record khác tham chiếu.

Nên backup `data_warehouse.csv` trước khi thao tác nhiều dữ liệu quan trọng.

## Lưu ý về script build dữ liệu

Backend dashboard không gọi `scripts/build_data_warehouse.py`.

Script đó dùng để build lại toàn bộ warehouse từ nguồn gốc và có thể xóa/tạo lại `data_images/`, nên không nên chạy trong lúc đang CRUD dữ liệu từ web.
