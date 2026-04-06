#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────
# KidsChatApp — Raspberry Pi 5 完整部署腳本
# 執行前提：Pi5 已安裝 Raspberry Pi OS (Bookworm 64-bit)
#
# 用法：
#   1. 登入 Pi5（SSH 或直接）
#   2. git clone 或 scp 整個專案到 Pi
#   3. bash deploy/pi5_setup.sh YOUR_GEMINI_API_KEY
#
# 完成後服務會：
#   - 在 port 8000 提供 API
#   - 開機自動啟動（systemd）
#   - 崩潰自動重啟
# ────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "\n${CYAN}══ $* ══${NC}"; }

# ── 參數檢查 ───────────────────────────────────────────────
GEMINI_KEY="${1:-${GEMINI_API_KEY:-}}"
if [ -z "$GEMINI_KEY" ]; then
    error "請提供 Gemini API Key\n用法：bash pi5_setup.sh YOUR_API_KEY"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="kidschat"
SERVICE_USER="$(whoami)"

# ── 步驟 1：系統套件 ───────────────────────────────────────
step "安裝系統依賴"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    git curl

info "Python 版本：$(python3 --version)"

# ── 步驟 2：Python 虛擬環境 ────────────────────────────────
step "建立 Python 虛擬環境"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    info "虛擬環境建立完成：$VENV_DIR"
else
    info "虛擬環境已存在，跳過"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
info "依賴安裝完成"

# ── 步驟 3：環境變數設定檔 ─────────────────────────────────
step "設定環境變數"
ENV_FILE="$PROJECT_DIR/.env"
cat > "$ENV_FILE" << EOF
GEMINI_API_KEY=${GEMINI_KEY}
PORT=8706
SESSION_TTL=1800
HISTORY_WINDOW=10
GEMINI_MODEL=gemini-1.5-flash
EOF
chmod 600 "$ENV_FILE"   # 只有擁有者可讀
info "環境變數寫入：$ENV_FILE（權限 600）"

# ── 步驟 4：建立 systemd service ──────────────────────────
step "設定 systemd service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=KidsChatApp — 幼兒 AI 對話後端
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${BACKEND_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kidschat

# 安全限制（可選）
# NoNewPrivileges=true
# PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

info "systemd service 已啟動"

# ── 步驟 5：確認服務狀態 ───────────────────────────────────
step "確認服務狀態"
sleep 3
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    LAN_IP=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅  KidsChatApp 部署成功！            ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  區網 API：http://${LAN_IP}:8000   ║${NC}"
    echo -e "${GREEN}║  健康檢查：http://${LAN_IP}:8000/health ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  常用指令：                            ║${NC}"
    echo -e "${GREEN}║  systemctl status kidschat             ║${NC}"
    echo -e "${GREEN}║  journalctl -u kidschat -f             ║${NC}"
    echo -e "${GREEN}║  systemctl restart kidschat            ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
else
    error "服務啟動失敗！查看 log：\n  journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
fi
