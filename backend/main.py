"""
KidsChatApp — FastAPI Backend
支援平台：macOS (dev/prod) | Raspberry Pi 5 (prod)
Gemini 2.5 Flash + 幼兒對話最佳化
"""

import os
import json
import time
import random
import logging
from datetime import datetime
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
import google.generativeai as genai

from config import AppConfig
from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE, MODE_PREFIXES, GAME_OPENERS, GAME_MODES

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# JSONL conversation log (for daily_summary.py)
# ──────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _log_turn(user_id: str, message: str, reply: str, mode: str) -> None:
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, f"{date_str}.jsonl")
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "user_id": user_id,
        "message": message,
        "reply": reply,
        "mode": mode,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────
# Session store
# 結構：{ user_id: { "chat": ChatSession, "created_at": float,
#                    "last_active": float, "mode": str } }
# ──────────────────────────────────────────────
sessions: Dict[str, dict] = {}

config = AppConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 KidsChatApp starting up …")
    genai.configure(api_key=config.gemini_api_key)
    log.info("✅ Gemini SDK configured (model=%s)", config.model_name)
    yield
    log.info("🛑 KidsChatApp shutting down")


app = FastAPI(
    title="KidsChatApp",
    description="幼兒 AI 對話後端，支援 macOS / Raspberry Pi 5",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_id: str = Field(default="kid_01", description="裝置或使用者 ID")
    message: str = Field(..., min_length=1, max_length=500)
    mode: Optional[str] = Field(
        default=None,
        description="可選，傳入時覆蓋 session 目前模式",
    )


class ChatResponse(BaseModel):
    reply: str
    session_turns: int
    mode: str


class ModeRequest(BaseModel):
    user_id: str = Field(default="kid_01")
    mode: str = Field(..., description="模式 ID，例如 animal_quiz")


class SessionInfo(BaseModel):
    user_id: str
    turns: int
    mode: str
    created_at: float
    last_active: float


# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────
def _get_or_create_session(user_id: str, mode: str) -> dict:
    """取得或建立對話 session，超過 TTL 自動重置"""
    now = time.time()
    session = sessions.get(user_id)

    if session is None or (now - session["last_active"]) > config.session_ttl_seconds:
        if session:
            log.info("[%s] Session expired, resetting", user_id)
        else:
            log.info("[%s] New session (mode=%s)", user_id, mode)

        model = genai.GenerativeModel(
            model_name=config.model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        sessions[user_id] = {
            "chat": model.start_chat(history=[]),
            "created_at": now,
            "last_active": now,
            "mode": mode,
        }
    else:
        sessions[user_id]["last_active"] = now

    return sessions[user_id]


def _trim_history(chat_session) -> None:
    """滑動視窗：保留最近 N 輪，防止 token 爆炸"""
    max_messages = config.history_window * 2
    if len(chat_session.history) > max_messages:
        chat_session.history = chat_session.history[-max_messages:]


def _build_prompt(message: str, mode: str) -> str:
    """在訊息前加入模式 prefix"""
    prefix = MODE_PREFIXES.get(mode, MODE_PREFIXES["free"])
    return f"{prefix}{message}"


def _resolve_mode(session: dict, request_mode: Optional[str]) -> str:
    """決定本次使用的 mode：request > session > free"""
    if request_mode and request_mode in MODE_PREFIXES:
        session["mode"] = request_mode
    return session.get("mode", "free")


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────
@app.get("/", summary="健康檢查")
async def root():
    return {"status": "ok", "app": "KidsChatApp", "version": "2.0.0"}


@app.get("/health", summary="詳細健康狀態")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "model": config.model_name,
        "platform": config.platform,
        "game_modes": list(GAME_MODES.keys()),
    }


@app.get("/modes", summary="列出所有遊戲模式")
async def list_modes():
    return {"modes": GAME_MODES}


@app.post("/mode", summary="切換遊戲模式，回傳開場白")
async def set_mode(request: ModeRequest):
    if request.mode not in GAME_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"未知模式 '{request.mode}'，可用：{list(GAME_MODES.keys())}",
        )
    session = _get_or_create_session(request.user_id, request.mode)
    session["mode"] = request.mode
    opener = GAME_OPENERS[request.mode]
    log.info("[%s] Mode switched → %s", request.user_id, request.mode)
    _log_turn(request.user_id, f"[MODE_SWITCH:{request.mode}]", opener, request.mode)
    return {
        "mode": request.mode,
        "mode_name": GAME_MODES[request.mode],
        "opener": opener,
    }


@app.post("/random_game", summary="隨機選一個遊戲，回傳開場白")
async def random_game(user_id: str = "kid_01"):
    mode = random.choice(list(GAME_MODES.keys()))
    session = _get_or_create_session(user_id, mode)
    session["mode"] = mode
    opener = GAME_OPENERS[mode]
    log.info("[%s] Random game → %s", user_id, mode)
    _log_turn(user_id, f"[RANDOM_GAME:{mode}]", opener, mode)
    return {
        "mode": mode,
        "mode_name": GAME_MODES[mode],
        "opener": opener,
    }


@app.post("/chat", response_model=ChatResponse, summary="對話主端點")
async def chat(request: ChatRequest, req: Request):
    client_ip = req.client.host
    session = _get_or_create_session(request.user_id, request.mode or "free")
    mode = _resolve_mode(session, request.mode)

    log.info("[%s] %s → mode=%s msg=%r", request.user_id, client_ip, mode, request.message[:30])

    try:
        chat_session = session["chat"]
        prompt = _build_prompt(request.message, mode)
        response = chat_session.send_message(prompt)
        _trim_history(chat_session)

        turns = len(chat_session.history) // 2
        _log_turn(request.user_id, request.message, response.text, mode)
        log.info("[%s] reply=%r turns=%d", request.user_id, response.text[:40], turns)

        return ChatResponse(reply=response.text, session_turns=turns, mode=mode)

    except genai.types.BlockedPromptException:
        log.warning("[%s] Prompt blocked by safety filter", request.user_id)
        raise HTTPException(status_code=422, detail="訊息被安全過濾器擋下，請換個說法")
    except Exception as e:
        log.error("[%s] Gemini error: %s", request.user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="AI 服務暫時無法回應，請稍後再試")


@app.post("/chat-text", summary="純文字對話（iPhone 捷徑專用，不需解析 JSON）")
async def chat_text(request: ChatRequest, req: Request):
    """回傳純文字，iPhone 捷徑可直接朗讀，不需要「從字典取得值」步驟"""
    result = await chat(request, req)
    return PlainTextResponse(result.reply)


@app.get("/session/{user_id}", response_model=SessionInfo, summary="查詢 session 狀態")
async def get_session(user_id: str):
    session = sessions.get(user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    return SessionInfo(
        user_id=user_id,
        turns=len(session["chat"].history) // 2,
        mode=session.get("mode", "free"),
        created_at=session["created_at"],
        last_active=session["last_active"],
    )


@app.delete("/session/{user_id}", summary="重置對話（清除歷史）")
async def reset_session(user_id: str):
    if user_id in sessions:
        del sessions[user_id]
        log.info("[%s] Session reset by client", user_id)
        return {"message": f"Session '{user_id}' 已重置"}
    raise HTTPException(status_code=404, detail="Session 不存在")


@app.get("/welcome/{user_id}", summary="取得開場白（第一次連線用）")
async def welcome(user_id: str):
    return {"reply": WELCOME_MESSAGE, "user_id": user_id}


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.port,
        reload=config.dev_mode,
        log_level="info",
    )
