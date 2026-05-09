---
name: voice-assistant
description: Start, stop, restart, and check status of the Chinese voice assistant on pi5. Supports chat/kids/english modes. Requires Bluetooth audio device.
---

# 語音助理技能

## 重要規則

- **你只負責執行以下指定的 bash 指令**
- **不要建立新腳本、不要安裝套件、不要修改任何現有檔案**
- **不要問使用者要 API key**
- **指令已經包含所有需要的環境設定**
- 執行完後回覆使用者結果，不要給操作說明

## 開啟語音助理（純聊天，預設）

```bash
tmux kill-session -t voice 2>/dev/null
tmux new-session -d -s voice 'cd ~/hermes-workspace && set -a && source .env && set +a && python3 voice_engine_v2.py 2>&1 | tee /tmp/voice.log'
sleep 3
tmux has-session -t voice 2>/dev/null && tail -3 /tmp/voice.log || echo 啟動失敗
```

成功：log 出現「Gemini 連線成功」。回覆「語音助理已啟動（純聊天）」。

## 開啟兒童模式

使用者說「兒童模式」「給女兒」「kids」：

```bash
tmux kill-session -t voice 2>/dev/null
tmux new-session -d -s voice 'cd ~/hermes-workspace && set -a && source .env && set +a && VOICE_MODE=kids python3 voice_engine_v2.py 2>&1 | tee /tmp/voice.log'
sleep 3
tmux has-session -t voice 2>/dev/null && tail -3 /tmp/voice.log || echo 啟動失敗
```

## 開啟英文練習模式

使用者說「英文模式」「練英文」「english」：

```bash
tmux kill-session -t voice 2>/dev/null
tmux new-session -d -s voice 'cd ~/hermes-workspace && set -a && source .env && set +a && VOICE_MODE=english python3 voice_engine_v2.py 2>&1 | tee /tmp/voice.log'
sleep 3
tmux has-session -t voice 2>/dev/null && tail -3 /tmp/voice.log || echo 啟動失敗
```

## 關閉語音助理

```bash
tmux kill-session -t voice 2>/dev/null && echo 已關閉 || echo 未在執行
```

## 查詢狀態

```bash
if tmux has-session -t voice 2>/dev/null; then echo 執行中; tail -3 /tmp/voice.log; else echo 未執行; fi
```

## 重啟

```bash
tmux kill-session -t voice 2>/dev/null
sleep 1
tmux new-session -d -s voice 'cd ~/hermes-workspace && set -a && source .env && set +a && python3 voice_engine_v2.py 2>&1 | tee /tmp/voice.log'
sleep 3
tail -3 /tmp/voice.log
```
