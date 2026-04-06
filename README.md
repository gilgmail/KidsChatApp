# KidsChatApp

幼兒 AI 語音對話 App，使用 Google Gemini 2.5 Flash，
支援 **iOS 原生 App**（Swift）與 **iPhone Siri 捷徑** 兩種使用方式，
後端可跑在 macOS 或 Raspberry Pi 5 上。

```
iPhone (iOS App 或 Siri 捷徑)
     │  語音 → STT → POST /talk 或 POST /chat
     ▼
FastAPI Server (Mac port 8706 / Pi5 port 8706)
     │
     ▼
Google Gemini API (gemini-2.5-flash)
     │
     ▼
iPhone ← 文字回覆 → TTS 播放
```

---

## 專案結構

```
KidsChatApp/
├── plan.md                    # 系統架構 + Milestone + TODO
├── backend/
│   ├── main.py                # FastAPI 完整版（8 遊戲模式 + session）
│   ├── config.py              # 環境變數設定
│   ├── prompts.py             # AI persona + 遊戲模式定義
│   ├── requirements.txt       # Python 依賴
│   └── daily_summary.py       # 每日/週報產生器
├── ios/
│   ├── KidsChatApp.xcodeproj  # Xcode 專案（直接開啟）
│   ├── project.yml            # xcodegen 設定
│   └── Sources/
│       ├── KidsChatAppApp.swift   # App 入口 (@main)
│       ├── ContentView.swift      # 按住說話 UI
│       ├── VoiceManager.swift     # STT + API + TTS
│       └── Info.plist             # 權限設定
├── deploy/
│   ├── mac_start.sh               # macOS 一鍵啟動
│   ├── mac_stop.sh                # macOS 停止
│   ├── pi5_setup.sh               # Pi5 完整部署（含 systemd）
│   ├── kidschat.service           # systemd unit
│   └── com.kidschat.server.plist  # macOS LaunchAgent（可選）
├── shortcuts/
│   └── iphone_shortcut_guide.md   # Siri 捷徑設定指南
└── tests/
    └── test_main.py               # API 單元測試
```

---

## 快速開始

### A. iOS App（推薦）

1. 開啟 `ios/KidsChatApp.xcodeproj`
2. Signing & Capabilities → 選你的 Apple ID Team
3. 確認 Pi5 已啟動（見下方 Pi5 部署）
4. 接 iPhone → ⌘R Run

### B. macOS 後端

**第一次設定：**

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
```

**啟動（port 8706）：**

```bash
export GEMINI_API_KEY="AIzaSy..."
bash deploy/mac_start.sh
```

**停止：**

```bash
bash deploy/mac_stop.sh
```

**開發模式（hot reload）：**

```bash
DEV_MODE=true GEMINI_API_KEY="..." python backend/main.py
```

### C. Raspberry Pi 5 部署

**一鍵部署（在 Pi5 上執行）：**

```bash
git clone git@github.com:gilgmail/KidsChatApp.git ~/KidsChatApp
cd ~/KidsChatApp
bash deploy/pi5_setup.sh "AIzaSy..."
```

**Pi5 PoC（簡化版，已部署在 ~/kidschat/）：**

```bash
ssh pi5 "sudo systemctl status kidschat-poc"
ssh pi5 "sudo systemctl restart kidschat-poc"
curl http://10.1.1.85:8706/health
```

---

## API 端點

### Pi5 PoC（簡化版）— port 8706

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |
| POST | `/talk` | 單輪對話（kid / papa profile） |

```bash
curl -X POST http://10.1.1.85:8706/talk \
  -H "Content-Type: application/json" \
  -d '{"profile_id": "kid", "message": "你好！"}'
```

### Mac 完整版後端 — port 8706

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查（顯示 session 數、模型、遊戲模式） |
| POST | `/chat` | 主對話端點（含歷史、模式切換） |
| POST | `/chat-text` | 純文字回覆（Siri 捷徑專用） |
| POST | `/mode` | 切換遊戲模式，回傳開場白 |
| POST | `/random_game` | 隨機選一個遊戲 |
| GET | `/modes` | 列出所有遊戲模式 |
| GET | `/welcome/{user_id}` | 第一次連線開場白 |
| GET | `/session/{user_id}` | 查詢 session 狀態 |
| DELETE | `/session/{user_id}` | 重置對話 |

### 遊戲模式（mode）

| 值 | 中文名 | 說明 |
|----|--------|------|
| `free` | 自由聊天 | 一般對話（預設） |
| `animal_quiz` | 猜動物 | AI 出謎，孩子猜 |
| `color_shape` | 顏色形狀 | 認識顏色與形狀 |
| `counting` | 數數字 | 數數與簡單算術 |
| `story` | 互動故事 | 三句話短故事 |
| `sing` | 唱兒歌 | 兒歌歌詞與節奏 |
| `daily_english` | 英文小教室 | 幼兒英文單字 |
| `emotion` | 情緒小學堂 | 認識情緒與表達 |

---

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `GEMINI_API_KEY` | 必填 | Google AI Studio API Key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | 實際使用 gemini-2.5-flash（.env 覆蓋） |
| `PORT` | `8000` | .env 設為 8706 |
| `SESSION_TTL` | `1800` | Session 閒置逾時（秒） |
| `HISTORY_WINDOW` | `10` | 保留最近 N 輪對話 |
| `DEV_MODE` | `false` | 開啟熱重載與設定印出 |

---

## 設計決策

**為何用 session dict 而非資料庫？**
幼兒對話本質上是短期狀態，重置反而是功能。若有多 child 支援再引入 SQLite。

**Pi5 PoC vs 完整版後端？**
Pi5 目前跑 `~/kidschat/` 簡化版（無歷史、兩 profile），驗證 STT/TTS 核心體驗。
驗收通過後再升級為 `backend/main.py` 完整版。

**滑動視窗 vs 摘要壓縮？**
三歲對話主題跳躍頻繁，長期記憶邊際效益低，滑動視窗足夠。

---

## 取得 Gemini API Key

1. 前往 [Google AI Studio](https://aistudio.google.com/)
2. 右上角「Get API Key」→「Create API Key」
3. 複製金鑰，存入 `.env` 或 export 到環境變數
