#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────
# KidsChatApp — macOS 一鍵啟動腳本
# 用法：bash mac_start.sh
# ────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$PROJECT_DIR/venv"
LOG_FILE="$PROJECT_DIR/kidschat.log"
PID_FILE="$PROJECT_DIR/kidschat.pid"

# ── 顏色輸出 ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 檢查 API Key ────────────────────────────────────────────
if [ -z "${GEMINI_API_KEY:-}" ]; then
    error "GEMINI_API_KEY 未設定！\n請先執行：export GEMINI_API_KEY='AIzaSy...'"
fi

# ── 建立虛擬環境（首次）────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    info "建立 Python 虛擬環境 …"
    python3 -m venv "$VENV_DIR"
fi

info "啟用虛擬環境"
source "$VENV_DIR/bin/activate"

# ── 安裝/升級依賴 ────────────────────────────────────────────
info "安裝/確認依賴套件 …"
pip install --quiet --upgrade pip
pip install --quiet -r "$BACKEND_DIR/requirements.txt"

# ── 停止舊的 instance ─────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        warn "偵測到舊 instance (PID=$OLD_PID)，正在停止 …"
        kill "$OLD_PID"
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

# ── 取得區網 IP ───────────────────────────────────────────
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

# ── 讀取實際 PORT ─────────────────────────────────────────
PORT="${PORT:-8000}"

# ── 啟動伺服器 ──────────────────────────────────────────────
info "啟動 KidsChatApp server …"
cd "$BACKEND_DIR"
nohup python main.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# ── 等待啟動確認 ────────────────────────────────────────────
sleep 2
if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅  KidsChatApp 啟動成功！            ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  本機：  http://127.0.0.1:${PORT}         ║${NC}"
    echo -e "${GREEN}║  區網：  http://${LAN_IP}:${PORT}      ║${NC}"
    echo -e "${GREEN}║  PID：   $SERVER_PID                          ║${NC}"
    echo -e "${GREEN}║  Log：   $LOG_FILE  ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  iPhone 捷徑 URL：                     ║${NC}"
    echo -e "${GREEN}║  http://${LAN_IP}:${PORT}/chat       ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    info "停止指令：bash mac_stop.sh  或  kill \$(cat $PID_FILE)"
else
    error "啟動失敗！請查看 log：cat $LOG_FILE"
fi
