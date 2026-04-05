"""
KidsChatApp — 設定管理
優先順序：環境變數 > .env 檔 > 預設值
"""

import os
import platform
from dataclasses import dataclass, field


def _detect_platform() -> str:
    """自動偵測執行平台"""
    system = platform.system()
    machine = platform.machine()
    if system == "Linux" and machine in ("aarch64", "armv7l"):
        return "raspberry_pi"
    elif system == "Darwin":
        return "macos"
    return "linux"


@dataclass
class AppConfig:
    # ── Gemini ──────────────────────────────────
    gemini_api_key: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY", "")
    )
    model_name: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    )

    # ── Server ──────────────────────────────────
    port: int = field(
        default_factory=lambda: int(os.environ.get("PORT", "8000"))
    )
    dev_mode: bool = field(
        default_factory=lambda: os.environ.get("DEV_MODE", "false").lower() == "true"
    )

    # ── Session ──────────────────────────────────
    # 閒置超過此秒數自動重置 session（預設 30 分鐘）
    session_ttl_seconds: int = field(
        default_factory=lambda: int(os.environ.get("SESSION_TTL", "1800"))
    )
    # 滑動視窗保留最近 N 輪對話
    history_window: int = field(
        default_factory=lambda: int(os.environ.get("HISTORY_WINDOW", "10"))
    )

    # ── Platform ──────────────────────────────────
    platform: str = field(default_factory=_detect_platform)

    def __post_init__(self):
        if not self.gemini_api_key:
            raise ValueError(
                "❌ GEMINI_API_KEY 未設定！\n"
                "請執行：export GEMINI_API_KEY='AIzaSy...'"
            )
        if self.dev_mode:
            # 開發模式印出設定摘要（隱藏 key）
            masked_key = self.gemini_api_key[:8] + "..." + self.gemini_api_key[-4:]
            print(f"[Config] platform={self.platform}")
            print(f"[Config] model={self.model_name}")
            print(f"[Config] port={self.port}")
            print(f"[Config] api_key={masked_key}")
            print(f"[Config] session_ttl={self.session_ttl_seconds}s")
            print(f"[Config] history_window={self.history_window} turns")
