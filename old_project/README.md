# Hướng Dẫn Chạy Crawler

Tài liệu này hướng dẫn cách chạy script `crawl_math_pipeline.py` để thu thập dữ liệu và hình ảnh.

## Cú pháp chung
```bash
python crawl_math_pipeline.py --links <file_link> --output <file_csv> --images-dir <thư_mục_ảnh> --errors <file_json>
```

**Giải thích các tham số:**
*   `--links`: Tên file chứa danh sách các link cần chạy (có thể đổi thành `sgk_links.txt` hoặc `links.txt`).
*   `--output`: Tên file CSV xuất ra chứa dữ liệu kết quả.
*   `--images-dir`: Tên thư mục sẽ được tạo để tải và lưu ảnh vào.
*   `--errors`: Tên file JSON dùng để thống kê các lỗi xảy ra trong quá trình chạy.

---

## Các lệnh chạy tự động (Copy & Paste)

Dưới đây là 2 lệnh đã được thiết lập sẵn, bạn chỉ cần copy và dán vào terminal để chạy:

### 1. Dành cho dữ liệu SGK
```bash
python crawl_math_pipeline.py --links sgk_links.txt --output sgk/sgk_production_math_with_images.csv --images-dir sgk/sgk_production_images --errors sgk/sgk_production_crawl_errors.json
```

### 2. Dành cho dữ liệu link chung
```bash
python crawl_math_pipeline.py --links links.txt --output prod/production_math_with_images.csv --images-dir prod/production_images --errors prod/production_crawl_errors.json
```