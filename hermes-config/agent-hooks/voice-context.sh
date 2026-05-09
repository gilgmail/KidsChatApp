#!/usr/bin/env python3
import json, sys

payload = json.load(sys.stdin)
msg = payload.get("extra", {}).get("user_message", "")

if any(kw in msg for kw in ["語音", "voice", "助理"]):
    context = (
        "IMPORTANT: The voice assistant already exists at ~/hermes-workspace/voice_engine_v2.py "
        "using Google Gemini Live API (NOT OpenAI). "
        "Do NOT create venv, do NOT pip install, do NOT write new scripts. "
        "Use only these tmux commands:\n"
        "Start: tmux kill-session -t voice 2>/dev/null; "
        "tmux new-session -d -s voice "
        "\'cd ~/hermes-workspace && set -a && source .env && set +a && python3 voice_engine_v2.py 2>&1 | tee /tmp/voice.log\'; "
        "sleep 3; tail -3 /tmp/voice.log\n"
        "Kids mode: add VOICE_MODE=kids before python3\n"
        "English mode: add VOICE_MODE=english before python3\n"
        "Stop: tmux kill-session -t voice 2>/dev/null\n"
        "Status: tmux has-session -t voice 2>/dev/null && echo running || echo stopped"
    )
    print(json.dumps({"context": context}))
else:
    print("{}")
