#!/bin/bash
set -e

# Định nghĩa tên cho 2 session
BE_SESSION="backend_app"
FE_SESSION="frontend_app"

DASHBOARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DASHBOARD_DIR/.." && pwd)"
FRONTEND="$DASHBOARD_DIR/frontend"
IP_ADDR=$(hostname -I | awk '{print $1}')
API_BASE_URL="http://$IP_ADDR:8000"

echo "--- Đang cài đặt dependencies ---"
cd "$ROOT" && poetry install --no-root
cd "$FRONTEND" && npm install

# 1. Xử lý Backend Session
echo "--- Khởi động Backend Session: $BE_SESSION ---"
tmux kill-session -t $BE_SESSION 2>/dev/null || true
cd "$ROOT"
tmux new-session -d -s $BE_SESSION
tmux send-keys -t $BE_SESSION "PYTHONIOENCODING=utf-8 poetry run uvicorn csv_dashboard.backend.main:app --host 0.0.0.0 --port 8000" C-m

# 2. Xử lý Frontend Session
echo "--- Khởi động Frontend Session: $FE_SESSION ---"
tmux kill-session -t $FE_SESSION 2>/dev/null || true
cd "$FRONTEND"
tmux new-session -d -s $FE_SESSION
tmux send-keys -t $FE_SESSION "VITE_API_BASE_URL=$API_BASE_URL npm run dev -- --host 0.0.0.0" C-m

echo "-----------------------------------------------"
echo "Hệ thống đã khởi động trong 2 sessions riêng biệt!"
echo "Truy cập từ mạng ngoài: http://$IP_ADDR:5173"
echo "-----------------------------------------------"
echo "LỆNH QUẢN LÝ:"
echo ""
echo "1. Xem Backend:  tmux attach -t $BE_SESSION"
echo "2. Xem Frontend: tmux attach -t $FE_SESSION"
echo "3. Thoát ra:     Nhấn Ctrl+B rồi nhấn D"
echo ""
echo "TẮT HỆ THỐNG:"
echo "- Tắt cả hai:    tmux kill-server"
echo "- Tắt riêng lẻ:  tmux kill-session -t $BE_SESSION (hoặc $FE_SESSION)"
echo "-----------------------------------------------"