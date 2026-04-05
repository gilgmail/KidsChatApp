#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────
# KidsChatApp — macOS 停止腳本
# ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/kidschat.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✅ KidsChatApp (PID=$PID) 已停止"
    else
        echo "⚠️  PID=$PID 的 process 不存在，清除 pid 檔"
        rm -f "$PID_FILE"
    fi
else
    echo "⚠️  找不到 PID 檔，嘗試透過 port 8000 停止 …"
    PID=$(lsof -ti:8000 2>/dev/null || true)
    if [ -n "$PID" ]; then
        kill "$PID"
        echo "✅ 已停止 port 8000 上的 process (PID=$PID)"
    else
        echo "ℹ️  沒有 process 在 port 8000 上執行"
    fi
fi
