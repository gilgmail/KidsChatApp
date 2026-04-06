# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

KidsChatApp is an iOS native app (`ios/`) — Swift SwiftUI with press-to-talk, STT, and TTS — backed by a FastAPI server (`backend/`) that runs on macOS (dev) or Raspberry Pi 5 (prod) and calls Google Gemini.

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

## Running Tests

```bash
source venv/bin/activate
pytest tests/ -v

# Run a single test class
pytest tests/test_main.py::TestBuildPrompt -v
```

Tests use `unittest.mock` to patch `genai` — no real API key needed (test-key-fake is set automatically).

## Test the API

```bash
# Health check (also returns active_sessions, model, platform, game_modes)
curl http://127.0.0.1:8706/health

# List available game modes
curl http://127.0.0.1:8706/modes

# Chat (full backend, returns JSON with reply + session_turns + mode)
curl -X POST http://127.0.0.1:8706/chat \
     -H "Content-Type: application/json" \
     -d '{"user_id": "kid_01", "message": "我是小公主", "mode": "animal_quiz"}'

# Chat (plain text — for Siri Shortcut, no JSON parsing needed)
curl -X POST http://127.0.0.1:8706/chat-text \
     -H "Content-Type: application/json" \
     -d '{"user_id": "kid_01", "message": "你好"}'

# Switch mode, receive opener line
curl -X POST http://127.0.0.1:8706/mode \
     -H "Content-Type: application/json" \
     -d '{"user_id": "kid_01", "mode": "story"}'

# Random game
curl -X POST "http://127.0.0.1:8706/random_game?user_id=kid_01"

# Welcome message (first connection)
curl http://127.0.0.1:8706/welcome/kid_01

# Inspect session state
curl http://127.0.0.1:8706/session/kid_01

# Reset a session
curl -X DELETE http://127.0.0.1:8706/session/kid_01

# Talk (Pi5 PoC — returns {"reply": "...", "audio_b64": "..."})
curl -X POST http://10.1.1.85:8706/talk \
     -H "Content-Type: application/json" \
     -d '{"profile_id": "kid", "message": "你好"}'
```

## Daily Summary

```bash
# Generate today's summary from logs/*.jsonl
GEMINI_API_KEY="..." python backend/daily_summary.py

# Generate weekly report
GEMINI_API_KEY="..." python backend/daily_summary.py --week
```

## iOS Build

The Xcode project is generated from `ios/project.yml` using [xcodegen](https://github.com/yonaskolb/XcodeGen):

```bash
cd ios && xcodegen generate
```

Bundle ID: `com.gilko.kidschatapp`, deployment target iOS 16.0, display name "Sparky".

## Architecture

### Backend (`backend/`)

- **`main.py`** — FastAPI app, all route handlers, in-memory session store, history trimming, JSONL logging
- **`config.py`** — `AppConfig` dataclass; reads env vars; auto-detects platform (macOS vs Raspberry Pi)
- **`prompts.py`** — `SYSTEM_PROMPT`, `WELCOME_MESSAGE`, 8 game modes with prefixes and openers
- **`daily_summary.py`** — Reads `logs/*.jsonl`, generates daily/weekly AI reports via Gemini

**Session model**: `{ user_id: { chat, created_at, last_active, mode } }` in-memory dict. TTL = 30 min. History window = 10 turns.

**Mode system**: `POST /chat` accepts `mode` field. `_build_prompt()` injects a text prefix from `MODE_PREFIXES` dict. Available modes: `free`, `animal_quiz`, `color_shape`, `counting`, `story`, `sing`, `daily_english`, `emotion`. `"chat"` is a backward-compat alias for `"free"`.

**Gemini integration**: `google-generativeai` SDK. `GenerativeModel` instantiated per-session with `SYSTEM_PROMPT` as `system_instruction`. History managed by SDK's `ChatSession`.

### Pi5 PoC (`~/kidschat/` on Pi5)

Simpler stateless backend for rapid validation:
- **Endpoint**: `POST /talk` — takes `profile_id` + `message`, returns `{ reply, audio_b64 }` (audio_b64 may be null)
- **Profiles**: `kid` (Sparky — zh-TW, 2 sentences + question) | `papa` (English coach — grammar correction)
- **No history** — pure one-shot responses
- **SDK**: `google.genai` (new SDK), model: `gemini-2.5-flash`
- **Port**: 8706, systemd service: `kidschat-poc`
- **IP**: 10.1.1.85 (set static in router if DHCP)

### iOS App (`ios/Sources/`)

- **`KidsChatAppApp.swift`** — `@main` SwiftUI entry point
- **`ContentView.swift`** — Segmented picker (kid/papa), press-to-hold circle button, shows STT text + AI reply
- **`VoiceManager.swift`** — `SFSpeechRecognizer` (zh-TW), `AVAudioEngine`, `URLSession` POST to Pi5, plays `audio_b64` WAV if present, falls back to `AVSpeechSynthesizer` TTS
- **`Info.plist`** — microphone + speech recognition permissions, `NSAllowsArbitraryLoads` (Pi5 is HTTP not HTTPS)

API endpoint in `VoiceManager.swift`: `http://10.1.1.85:8706/talk` (hardcoded — update if Pi5 IP changes)

## Pi5 Monitoring

```bash
ssh pi5 "sudo systemctl status kidschat-poc"
ssh pi5 "journalctl -u kidschat-poc -f"
ssh pi5 "sudo systemctl restart kidschat-poc"
```

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

Edit **`backend/system_prompt.txt`** directly — no Python changes needed. Restart the server to pick up changes.

If `system_prompt.txt` is missing, the server falls back to the hardcoded minimal prompt in `prompts.py`.

For Pi5 PoC persona changes, edit `~/kidschat/main.py` `PROMPTS` dict directly, then `sudo systemctl restart kidschat-poc`.

## Known Issues

- **Gemini free tier quota**: `gemini-2.0-flash` and `gemini-2.0-flash-lite` have 0 free quota in this project. Use `gemini-2.5-flash` (set in `.env`). Enable billing in Google AI Studio for heavy testing.
- **Pi5 IP drift**: Pi5 uses DHCP; if IP changes from 10.1.1.85, update `VoiceManager.swift` and test curl commands. Set a static DHCP lease in the router to prevent this.
- **iOS STT requires internet**: `SFSpeechRecognizer` routes to Apple servers by default — needs WiFi.
