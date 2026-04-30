#!/bin/bash

# Dừng script ngay lập tức nếu có lệnh nào bị lỗi
set -e

# Lấy đường dẫn thư mục hiện tại (nơi đặt script)
ROOT=$(pwd)
FRONTEND="$ROOT/frontend"

echo "--- Đang cài đặt dependencies cho Backend ---"
cd "$ROOT"
poetry install --no-root

echo "--- Đang cài đặt dependencies cho Frontend ---"
cd "$FRONTEND"
npm install

echo "--- Đang khởi động Backend trong nền ---"
cd "$ROOT"
# Chạy uvicorn trong nền (background) và lưu log vào file backend.log
PYTHONIOENCODING=utf-8 poetry run uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &

echo "--- Đang khởi động Frontend trong nền ---"
cd "$FRONTEND"
# Chạy npm dev trong nền và lưu log vào file frontend.log
npm run dev -- --host 127.0.0.1 > frontend.log 2>&1 &

# Chờ một lát để server khởi động
sleep 4

echo ""
echo "Backend:  http://127.0.0.1:8000"
echo "Frontend: http://127.0.0.1:5173"
echo ""
echo "Logs được lưu tại backend.log và frontend.log"
echo "Để tắt các server, hãy dùng lệnh: killall python3 node"
echo ""

# Mở trình duyệt mặc định trên Ubuntu (tương đương Start-Process)
xdg-open "http://127.0.0.1:5173" 2>/dev/null || echo "Vui lòng mở trình duyệt và truy cập http://127.0.0.1:5173"