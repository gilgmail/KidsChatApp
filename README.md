# KidsChatApp

幼兒 AI 語音對話 App，使用 Google Gemini 1.5 Flash，
支援 macOS 本機運行 與 Raspberry Pi 5 區網部署。

```
iPhone / HomePod
     │  Siri 捷徑（HTTP POST）
     ▼
FastAPI Server (Mac or Pi5)  ──►  Google Gemini API
     │
     ▼
  語音回覆（Siri TTS 播放）
```

---

## 專案結構

```
KidsChatApp/
├── backend/
│   ├── main.py          # FastAPI 主程式（路由、session 管理）
│   ├── config.py        # 設定（環境變數 / 平台偵測）
│   ├── prompts.py       # System prompt（幼兒語氣設計）
│   └── requirements.txt
├── deploy/
│   ├── mac_start.sh               # macOS 一鍵啟動
│   ├── mac_stop.sh                # macOS 停止
│   ├── com.kidschat.server.plist  # macOS LaunchAgent（開機自啟）
│   ├── pi5_setup.sh               # Pi5 完整部署腳本
│   └── kidschat.service           # systemd unit（Pi5 用）
└── shortcuts/
    └── iphone_shortcut_guide.md   # iPhone 捷徑設定圖文指南
```

---

## 快速開始

### A. macOS

**第一次設定：**

```bash
cd ~/KidsChatApp
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
```

**每次啟動：**

```bash
export GEMINI_API_KEY="AIzaSy..."
bash deploy/mac_start.sh
```

啟動後終端機會顯示：

```
✅  KidsChatApp 啟動成功！
本機：  http://127.0.0.1:8000
區網：  http://192.168.1.105:8000   ← iPhone 捷徑要用這個
```

**測試：**

```bash
curl -X POST http://127.0.0.1:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"user_id": "kid_01", "message": "我是小公主", "mode": "chat"}'
```

**開機自動啟動（可選）：**

```bash
# 編輯 plist，換掉 YOUR_USERNAME 和 YOUR_GEMINI_KEY
nano deploy/com.kidschat.server.plist

cp deploy/com.kidschat.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kidschat.server.plist
```

---

### B. Raspberry Pi 5

**一鍵部署：**

```bash
# 在 Pi5 上執行（需 sudo 權限）
git clone <此專案> ~/KidsChatApp
cd ~/KidsChatApp
bash deploy/pi5_setup.sh "AIzaSy..."
```

**服務管理：**

```bash
sudo systemctl status kidschat    # 查看狀態
sudo systemctl restart kidschat   # 重啟
journalctl -u kidschat -f         # 即時 log
```

---

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查，回傳 session 數與模型名稱 |
| POST | `/chat` | 主對話端點 |
| GET | `/welcome/{user_id}` | 取得開場白（第一次連線） |
| GET | `/session/{user_id}` | 查詢 session 狀態 |
| DELETE | `/session/{user_id}` | 重置對話（清除歷史） |

### POST /chat 請求格式

```json
{
  "user_id": "kid_01",
  "message": "我想聽故事",
  "mode": "story"
}
```

### 回應格式

```json
{
  "reply": "好哦！從前有隻小兔兔，牠找到了一顆好大的胡蘿蔔！你猜牠怎麼辦呀？",
  "session_turns": 3,
  "mode": "story"
}
```

### 互動模式（mode）

| 值 | 說明 |
|----|------|
| `chat` | 一般對話（預設） |
| `sing` | 帶唱兒歌，主題由 `message` 提供 |
| `story` | 三句話短故事，主角由 `message` 提供 |
| `roleplay` | 角色扮演，AI 扮配角 |

---

## 設定（環境變數）

| 變數名 | 預設值 | 說明 |
|--------|--------|------|
| `GEMINI_API_KEY` | 必填 | Google AI Studio 取得 |
| `GEMINI_MODEL` | `gemini-1.5-flash` | 可換 `gemini-1.5-pro` |
| `PORT` | `8000` | 伺服器 port |
| `SESSION_TTL` | `1800` | 閒置幾秒後重置 session（秒） |
| `HISTORY_WINDOW` | `10` | 保留最近 N 輪對話 |
| `DEV_MODE` | `false` | 開啟熱重載與設定印出 |

---

## 設計決策

**為何用 session dict 而非資料庫？**
幼兒對話本質上是短期狀態，session 重置反而是功能（避免孩子被前一天的對話卡住）。
若有多 child 支援需求再引入 SQLite。

**為何選 gemini-1.5-flash？**
在 Pi5 等低頻寬環境下，Flash 的回應速度（<1s p50）遠優於 Pro，
對語音互動體驗影響顯著。需要更長回應時換 Pro。

**滑動視窗 vs 摘要壓縮？**
三歲小孩對話主題跳躍頻繁，長期記憶的邊際效益低，
滑動視窗實作簡單且足夠，避免引入額外 LLM 呼叫成本。

---

## iPhone 捷徑

詳見 [`shortcuts/iphone_shortcut_guide.md`](shortcuts/iphone_shortcut_guide.md)

觸發流程：嘿 Siri → 小老師 → 說話 → AI 回覆語音播放

---

## 取得 Gemini API Key

1. 前往 [Google AI Studio](https://aistudio.google.com/)
2. 右上角「Get API Key」→「Create API Key」
3. 複製金鑰，免費額度通常足夠家庭使用
