# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

KidsChatApp is a minimal FastAPI backend for a children's AI voice chat app. It takes text input (from an iPhone Siri Shortcut), calls Google Gemini, and returns text that Siri reads aloud. There is no frontend — the "UI" is entirely an iPhone Shortcut.

## Running the Server

Requires `GEMINI_API_KEY` to be set before starting.

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

The server runs on port `8000` by default (configurable via `PORT` env var).

## Test the API

```bash
# Health check
curl http://127.0.0.1:8000/health

# Send a chat message
curl -X POST http://127.0.0.1:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"user_id": "kid_01", "message": "我是小公主", "mode": "chat"}'

# Reset a session
curl -X DELETE http://127.0.0.1:8000/session/kid_01
```

## Architecture

All backend logic lives in three files:

- **`backend/main.py`** — FastAPI app, all route handlers, session store (in-memory dict), history trimming
- **`backend/config.py`** — `AppConfig` dataclass reads all settings from env vars; auto-detects platform (macOS vs Raspberry Pi)
- **`backend/prompts.py`** — `SYSTEM_PROMPT` and `WELCOME_MESSAGE` constants (the child-facing persona and language rules)

**Session model**: Sessions are stored as `{ user_id: { chat, created_at, last_active, mode } }` in a module-level dict. No database. Sessions expire after `SESSION_TTL` seconds of inactivity (default 30 min) and are recreated on next request. History is trimmed to a sliding window of `HISTORY_WINDOW` turns (default 10).

**Mode system**: The `mode` field on `POST /chat` maps to a text prefix injected before the user message in `_build_prompt()`. Modes: `chat` (no prefix), `sing`, `story`, `roleplay`.

**Gemini integration**: Uses `google-generativeai` SDK. The `genai.GenerativeModel` is instantiated per-session (not shared), with `SYSTEM_PROMPT` as `system_instruction`. Conversation history is managed by the SDK's `ChatSession` object.

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | required | |
| `GEMINI_MODEL` | `gemini-1.5-flash` | |
| `PORT` | `8000` | |
| `SESSION_TTL` | `1800` | seconds |
| `HISTORY_WINDOW` | `10` | turns |
| `DEV_MODE` | `false` | enables hot reload + config print |

## Deployment

- **macOS**: `deploy/mac_start.sh` runs uvicorn via `nohup`, writes PID to `kidschat.pid`. For autostart: `deploy/com.kidschat.server.plist` (LaunchAgent).
- **Raspberry Pi 5**: `deploy/pi5_setup.sh` does full setup; `deploy/kidschat.service` is the systemd unit.
- **`python-dotenv` is not installed** — env vars must be exported before running, or set in the plist/service file. The `requirements.txt` has it commented out.

## Modifying the AI Persona

All persona changes go in `backend/prompts.py`. Key constraints defined there: max 35 Chinese characters per reply, simplified vocabulary, mandatory ending question, mode-specific behavior triggers.
