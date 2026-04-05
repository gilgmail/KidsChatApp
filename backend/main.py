"""
KidsChatApp — FastAPI Backend
支援平台：macOS (dev/prod) | Raspberry Pi 5 (prod)
Gemini 1.5 Flash + 幼兒對話最佳化
"""

import os
import time
import logging
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import google.generativeai as genai

from config import AppConfig
from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE

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
# Session store
# 結構：{ user_id: { "chat": ChatSession, "created_at": float, "last_active": float } }
# ──────────────────────────────────────────────
sessions: Dict[str, dict] = {}

config = AppConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動時初始化 Gemini SDK"""
    log.info("🚀 KidsChatApp starting up …")
    genai.configure(api_key=config.gemini_api_key)
    log.info("✅ Gemini SDK configured")
    yield
    log.info("🛑 KidsChatApp shutting down")


app = FastAPI(
    title="KidsChatApp",
    description="幼兒 AI 對話後端，支援 macOS / Raspberry Pi 5",
    version="1.0.0",
    lifespan=lifespan,
)

# 允許 iPhone Shortcut / HomePod Proxy 跨域請求
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
    user_id: str = Field(..., description="裝置或使用者 ID", json_schema_extra={"example": "kid_01"})
    message: str = Field(..., min_length=1, max_length=500, json_schema_extra={"example": "我是小公主"})
    mode: Optional[str] = Field(
        default="chat",
        description="互動模式：chat | sing | story | roleplay",
    )


class ChatResponse(BaseModel):
    reply: str
    session_turns: int
    mode: str


class SessionInfo(BaseModel):
    user_id: str
    turns: int
    created_at: float
    last_active: float


# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────
def _get_or_create_session(user_id: str, mode: str) -> dict:
    """取得或建立對話 session，超過 TTL 自動重置"""
    now = time.time()
    session = sessions.get(user_id)

    # Session 不存在 or 超過閒置 TTL (預設 30 分鐘)
    if session is None or (now - session["last_active"]) > config.session_ttl_seconds:
        if session:
            log.info(f"[{user_id}] Session expired, resetting")
        else:
            log.info(f"[{user_id}] New session created (mode={mode})")

        model = genai.GenerativeModel(
            model_name=config.model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        chat = model.start_chat(history=[])
        sessions[user_id] = {
            "chat": chat,
            "created_at": now,
            "last_active": now,
            "mode": mode,
        }
    else:
        sessions[user_id]["last_active"] = now

    return sessions[user_id]


def _trim_history(chat_session) -> None:
    """滑動視窗：保留最近 N 輪，防止 token 爆炸"""
    max_messages = config.history_window * 2  # 每輪含 user + model
    if len(chat_session.history) > max_messages:
        chat_session.history = chat_session.history[-max_messages:]
        log.debug("History trimmed to last %d messages", max_messages)


def _build_prompt(message: str, mode: str) -> str:
    """根據 mode 在訊息前加入引導 prefix"""
    prefixes = {
        "sing":     "【唱歌模式】請帶著我唱一首簡單的兒歌，主題是：",
        "story":    "【故事模式】請講一個超短的睡前故事，主角是：",
        "roleplay": "【角色扮演】我想玩扮演遊戲，我要扮演：",
        "chat":     "",
    }
    prefix = prefixes.get(mode, "")
    return f"{prefix}{message}" if prefix else message


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────
@app.get("/", summary="健康檢查")
async def root():
    return {"status": "ok", "app": "KidsChatApp", "version": "1.0.0"}


@app.get("/health", summary="詳細健康狀態")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "model": config.model_name,
        "platform": config.platform,
    }


@app.post("/chat", response_model=ChatResponse, summary="對話主端點")
async def chat(request: ChatRequest, req: Request):
    client_ip = req.client.host
    log.info(f"[{request.user_id}] {client_ip} → mode={request.mode} msg={request.message[:30]!r}")

    try:
        session = _get_or_create_session(request.user_id, request.mode)
        chat_session = session["chat"]

        prompt = _build_prompt(request.message, request.mode)
        response = chat_session.send_message(prompt)

        _trim_history(chat_session)

        turns = len(chat_session.history) // 2
        log.info(f"[{request.user_id}] reply={response.text[:40]!r} turns={turns}")

        return ChatResponse(
            reply=response.text,
            session_turns=turns,
            mode=request.mode,
        )

    except genai.types.BlockedPromptException:
        log.warning(f"[{request.user_id}] Prompt blocked by Gemini safety filter")
        raise HTTPException(status_code=422, detail="訊息被安全過濾器擋下，請換個說法")
    except Exception as e:
        log.error(f"[{request.user_id}] Gemini error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="AI 服務暫時無法回應，請稍後再試")


@app.get("/session/{user_id}", response_model=SessionInfo, summary="查詢 session 狀態")
async def get_session(user_id: str):
    session = sessions.get(user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session 不存在")
    return SessionInfo(
        user_id=user_id,
        turns=len(session["chat"].history) // 2,
        created_at=session["created_at"],
        last_active=session["last_active"],
    )


@app.delete("/session/{user_id}", summary="重置對話（清除歷史）")
async def reset_session(user_id: str):
    if user_id in sessions:
        del sessions[user_id]
        log.info(f"[{user_id}] Session reset by client")
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
