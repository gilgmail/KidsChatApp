# KidsChatApp — 系統架構與開發計畫

## 系統架構

```
iPhone (iOS App)
    │  按住說話 → STT (SFSpeechRecognizer, zh-TW)
    │  POST /talk  →  http://10.1.1.85:8706
    │
    ▼
Raspberry Pi 5 (~/kidschat/)
    │  FastAPI + google-genai SDK
    │  kidschat-poc.service (systemd, 開機自啟)
    │
    ▼
Google Gemini API (gemini-2.5-flash)
    │
    ▼
iPhone  ← JSON {"reply": "..."}
    TTS (AVSpeechSynthesizer)  → 喇叭播放
```

**Port 統一：8706**（Mac dev 與 Pi5 PoC 相同）

---

## 資料夾結構

```
KidsChatApp/
├── plan.md                    # 本文件
├── CLAUDE.md                  # Claude Code 使用說明
├── README.md                  # 快速啟動指南
├── .env                       # 本機環境變數（gitignored）
│
├── backend/                   # Python FastAPI 後端
│   ├── main.py                # 完整版伺服器（8 遊戲模式 + session）
│   ├── config.py              # 環境變數設定管理
│   ├── prompts.py             # AI persona + 遊戲模式定義
│   ├── requirements.txt       # Python 依賴
│   └── daily_summary.py       # 每日/週報產生器（讀 logs/ 目錄）
│
├── ios/                       # iOS Swift App
│   ├── KidsChatApp.xcodeproj  # Xcode 專案檔
│   ├── project.yml            # xcodegen 設定
│   ├── Info.plist.md          # 必填 plist 說明文件
│   └── Sources/
│       ├── KidsChatAppApp.swift   # @main 入口
│       ├── ContentView.swift      # 極簡 UI（按住說話按鈕）
│       ├── VoiceManager.swift     # STT + API call + TTS 核心引擎
│       └── Info.plist             # 權限設定（已含麥克風 + 語音辨識）
│
├── deploy/                    # 部署腳本
│   ├── mac_start.sh           # macOS 啟動（nohup uvicorn）
│   ├── mac_stop.sh            # macOS 停止
│   ├── pi5_setup.sh           # Pi5 完整部署腳本（含 systemd）
│   ├── kidschat.service       # systemd unit（完整版後端用）
│   └── com.kidschat.server.plist  # macOS LaunchAgent（可選自動啟動）
│
├── logs/                      # 每日 JSONL 對話記錄（自動產生，gitignored）
├── summaries/                 # AI 每日摘要 Markdown（自動產生，gitignored）
└── tests/
    └── test_main.py           # API endpoint 單元測試
```

---

## Milestone 進度

### M1 — Pi5 極薄代理後端 ✅
- FastAPI `/talk` endpoint
- `kid` profile：Sparky 幼兒機器人（中英混合，2 句 + 問題）
- `papa` profile：英文會話教練（糾錯 + 改良版）
- 無歷史上下文（PoC 一問一答）
- 部署：`~/kidschat/` on Pi5，`kidschat-poc.service` (systemd)
- Port：8706，防火牆已開放

### M2 — iOS 語音核心 (Swift) ✅
- [x] `ios/Sources/VoiceManager.swift`：SFSpeechRecognizer + URLSession + AVSpeechSynthesizer
- [x] `ios/Sources/ContentView.swift`：按住說話 UI，ProgressView loading 狀態
- [x] `ios/Sources/Info.plist`：NSMicrophoneUsageDescription + NSSpeechRecognitionUsageDescription + NSAllowsArbitraryLoads
- [x] `ios/KidsChatApp.xcodeproj` 已由 xcodegen 產生

### M3 — Xcode 真機測試 🔧
- [x] Xcode 專案已建立（`ios/KidsChatApp.xcodeproj`）
- [ ] Signing & Capabilities → 選 Apple ID Development Team
- [ ] 接 iPhone → 確認裝置已解鎖再 Run（DDI mount 需要解鎖）
- [ ] 首次啟動 → 允許麥克風 + 語音辨識權限
- [ ] 確認 Pi5 IP 仍為 10.1.1.85（`ssh pi5 "hostname -I"`）
- [ ] 說「你好」→ 確認 Sparky 有語音回覆

### M4 — UAT 驗收 ⏳
**Kid Test（小孩測試）**
- [ ] 她能理解「按住藍色按鈕說話」嗎？
- [ ] Sparky 的中文 TTS 她能聽懂嗎？
- [ ] 互動是否超過 3 分鐘不中斷？
- [ ] Gemini rate limit 不影響日常使用？

**Papa Test（爸爸測試）**
- [ ] STT 能辨識架構類英文專有名詞（microservice, API, latency）？
- [ ] Coach 的糾錯回饋對練習有幫助嗎？
- [ ] 來回 5 輪對話後體驗如何？

---

## Pi5 常用指令

```bash
# 確認服務狀態
ssh pi5 "sudo systemctl status kidschat-poc"

# 即時查看 log
ssh pi5 "journalctl -u kidschat-poc -f"

# 重啟服務
ssh pi5 "sudo systemctl restart kidschat-poc"

# 健康檢查
curl http://10.1.1.85:8706/health

# 測試 kid profile
curl -X POST http://10.1.1.85:8706/talk \
  -H "Content-Type: application/json" \
  -d '{"profile_id":"kid","message":"你好！我叫小花"}'

# 測試 papa profile
curl -X POST http://10.1.1.85:8706/talk \
  -H "Content-Type: application/json" \
  -d '{"profile_id":"papa","message":"I want to improve my English skill"}'
```

---

## Mac 後端（完整版）常用指令

```bash
# 啟動
export GEMINI_API_KEY="..."
bash deploy/mac_start.sh

# 停止
bash deploy/mac_stop.sh

# 開發模式（hot reload）
DEV_MODE=true GEMINI_API_KEY="..." python backend/main.py

# 產生今日摘要
GEMINI_API_KEY="..." python backend/daily_summary.py

# 產生週報
GEMINI_API_KEY="..." python backend/daily_summary.py --week
```

---

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `GEMINI_API_KEY` | 必填 | Google AI Studio API Key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | 模型選擇 |
| `PORT` | `8000` | 伺服器 port（.env 設為 8706） |
| `SESSION_TTL` | `1800` | Session 閒置逾時（秒） |
| `HISTORY_WINDOW` | `10` | 保留對話輪數 |
| `DEV_MODE` | `false` | 開發模式（hot reload + 設定列印） |

---

## 已知問題

- **Gemini free tier quota**：`gemini-2.0-flash` / `gemini-2.0-flash-lite` 在此 project 的免費配額為 0，使用 `gemini-2.5-flash` 可正常運作。如需大量測試，考慮在 Google AI Studio 啟用 billing。
- **Pi5 IP 變動**：Pi5 使用 DHCP 時 IP 可能改變。建議在路由器設定靜態 IP 給 Pi5，或改用 mDNS hostname。
- **iOS STT 需網路**：`SFSpeechRecognizer` 預設走 Apple 伺服器辨識，需要 WiFi。
