# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

KidsChatApp has two interfaces:
1. **iOS Native App** (`ios/`) — Swift SwiftUI app with press-to-talk, STT, and TTS
2. **iPhone Siri Shortcut** (`shortcuts/`) — HTTP POST to the FastAPI backend, Siri reads the reply

The FastAPI backend (`backend/`) runs on macOS (dev) or Raspberry Pi 5 (prod), calls Google Gemini, and returns text.

## Running the Server

Requires `GEMINI_API_KEY` to be set before starting. Default port is **8706** (set in `.env`).

```bash
# First-time setup
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt

# Start (macOS, background process)
export GEMINI_API_KEY="AIzaSy..."
bash deploy/mac_start.sh

# Stop
bash deploy/mac_stop.sh

# Dev mode (hot reload, prints config)
DEV_MODE=true GEMINI_API_KEY="..." python backend/main.py
```

## Test the API

```bash
# Health check
curl http://127.0.0.1:8706/health

# Chat (full backend)
curl -X POST http://127.0.0.1:8706/chat \
     -H "Content-Type: application/json" \
     -d '{"user_id": "kid_01", "message": "我是小公主", "mode": "animal_quiz"}'

# Talk (Pi5 PoC)
curl -X POST http://10.1.1.85:8706/talk \
     -H "Content-Type: application/json" \
     -d '{"profile_id": "kid", "message": "你好"}'

# Reset a session
curl -X DELETE http://127.0.0.1:8706/session/kid_01
```

## Architecture

### Backend (`backend/`)

- **`main.py`** — FastAPI app, all route handlers, in-memory session store, history trimming, JSONL logging
- **`config.py`** — `AppConfig` dataclass; reads env vars; auto-detects platform (macOS vs Raspberry Pi)
- **`prompts.py`** — `SYSTEM_PROMPT`, `WELCOME_MESSAGE`, 8 game modes with prefixes and openers
- **`daily_summary.py`** — Reads `logs/*.jsonl`, generates daily/weekly AI reports via Gemini

**Session model**: `{ user_id: { chat, created_at, last_active, mode } }` in-memory dict. TTL = 30 min. History window = 10 turns.

**Mode system**: `POST /chat` accepts `mode` field. `_build_prompt()` injects a text prefix from `MODE_PREFIXES` dict. Available modes: `free`, `animal_quiz`, `color_shape`, `counting`, `story`, `sing`, `daily_english`, `emotion`.

**Gemini integration**: `google-generativeai` SDK. `GenerativeModel` instantiated per-session with `SYSTEM_PROMPT` as `system_instruction`. History managed by SDK's `ChatSession`.

### Pi5 PoC (`~/kidschat/` on Pi5)

Simpler stateless backend for rapid validation:
- **Endpoint**: `POST /talk` — takes `profile_id` + `message`, returns `reply`
- **Profiles**: `kid` (Sparky — zh-TW, 2 sentences + question) | `papa` (English coach — grammar correction)
- **No history** — pure one-shot responses
- **SDK**: `google.genai` (new SDK), model: `gemini-2.5-flash`
- **Port**: 8706, systemd service: `kidschat-poc`
- **IP**: 10.1.1.85 (set static in router if DHCP)

### iOS App (`ios/Sources/`)

- **`KidsChatAppApp.swift`** — `@main` SwiftUI entry point
- **`ContentView.swift`** — Segmented picker (kid/papa), press-to-hold circle button, shows STT text + AI reply
- **`VoiceManager.swift`** — `SFSpeechRecognizer` (zh-TW), `AVAudioEngine`, `URLSession` POST to Pi5, `AVSpeechSynthesizer` TTS
- **`Info.plist`** — `NSMicrophoneUsageDescription`, `NSSpeechRecognitionUsageDescription`, `NSAllowsArbitraryLoads`

API endpoint in `VoiceManager.swift`: `http://10.1.1.85:8706/talk` (hardcoded — update if Pi5 IP changes)

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | required | |
| `GEMINI_MODEL` | `gemini-2.0-flash` | `.env` overrides to `gemini-2.5-flash` |
| `PORT` | `8000` | `.env` overrides to `8706` |
| `SESSION_TTL` | `1800` | seconds |
| `HISTORY_WINDOW` | `10` | turns |
| `DEV_MODE` | `false` | enables hot reload + config print |

## Deployment

- **macOS**: `deploy/mac_start.sh` runs uvicorn via `nohup`, writes PID to `kidschat.pid`
- **Pi5 full setup**: `bash deploy/pi5_setup.sh YOUR_API_KEY` — installs venv, systemd service
- **Pi5 PoC** (already deployed): `ssh pi5 "sudo systemctl restart kidschat-poc"`
- **`python-dotenv` is installed** on Pi5 PoC; Mac backend reads env vars directly

## Modifying the AI Persona

All persona changes go in `backend/prompts.py`. Key constraints: max 35 Chinese characters per reply, simplified vocabulary, mandatory ending question, mode-specific behavior triggers.

For Pi5 PoC persona changes, edit `~/kidschat/main.py` `PROMPTS` dict directly, then `sudo systemctl restart kidschat-poc`.
