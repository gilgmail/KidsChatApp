"""
KidsChatApp — Backend Unit Tests
"""
import time
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key-fake")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ──────────────────────────────────────────────
# _build_prompt
# ──────────────────────────────────────────────
class TestBuildPrompt:
    def setup_method(self):
        import importlib
        import main as m
        importlib.reload(m)
        self.build = m._build_prompt

    def test_free_mode_prefix(self):
        result = self.build("你好", "free")
        assert result == "【自由聊天】你好"

    def test_chat_alias(self):
        # "chat" is backward-compat alias for "free"
        result = self.build("你好", "chat")
        assert result == "【自由聊天】你好"

    def test_animal_quiz_prefix(self):
        result = self.build("是狗狗嗎", "animal_quiz")
        assert result.startswith("【猜動物】")
        assert "是狗狗嗎" in result

    def test_sing_mode_prefix(self):
        result = self.build("小星星", "sing")
        assert result.startswith("【唱兒歌】")

    def test_story_mode_prefix(self):
        result = self.build("小熊", "story")
        assert result.startswith("【互動故事】")

    def test_daily_english_prefix(self):
        result = self.build("apple", "daily_english")
        assert result.startswith("【英文小教室】")

    def test_emotion_prefix(self):
        result = self.build("我很開心", "emotion")
        assert result.startswith("【情緒小學堂】")

    def test_unknown_mode_falls_back_to_free(self):
        result = self.build("測試", "unknown_mode")
        assert result.startswith("【自由聊天】")


# ──────────────────────────────────────────────
# _trim_history
# ──────────────────────────────────────────────
class TestTrimHistory:
    def setup_method(self):
        import importlib
        import main as m
        importlib.reload(m)
        self.trim = m._trim_history
        self.config = m.config

    def test_no_trim_when_under_limit(self):
        mock_chat = MagicMock()
        mock_chat.history = list(range(10))
        self.trim(mock_chat)
        assert len(mock_chat.history) == 10

    def test_trims_when_over_limit(self):
        mock_chat = MagicMock()
        max_msgs = self.config.history_window * 2
        mock_chat.history = list(range(max_msgs + 6))
        self.trim(mock_chat)
        assert len(mock_chat.history) == max_msgs

    def test_trim_keeps_recent_messages(self):
        mock_chat = MagicMock()
        max_msgs = self.config.history_window * 2
        all_msgs = list(range(max_msgs + 4))
        mock_chat.history = all_msgs
        self.trim(mock_chat)
        assert mock_chat.history == all_msgs[-max_msgs:]


# ──────────────────────────────────────────────
# _get_or_create_session
# ──────────────────────────────────────────────
class TestGetOrCreateSession:
    def setup_method(self):
        import importlib
        import main as m
        importlib.reload(m)
        self.main = m
        self.get_or_create = m._get_or_create_session
        m.sessions.clear()

    def _mock_model(self):
        mock_chat = MagicMock()
        mock_chat.history = []
        mock_model = MagicMock()
        mock_model.start_chat.return_value = mock_chat
        return mock_model

    @patch("main.genai")
    def test_creates_new_session(self, mock_genai):
        mock_genai.GenerativeModel.return_value = self._mock_model()
        session = self.get_or_create("user_1", "free")
        assert "user_1" in self.main.sessions
        assert "chat" in session
        assert session["mode"] == "free"

    @patch("main.genai")
    def test_reuses_existing_session(self, mock_genai):
        mock_genai.GenerativeModel.return_value = self._mock_model()
        s1 = self.get_or_create("user_2", "free")
        created = s1["created_at"]
        s2 = self.get_or_create("user_2", "free")
        assert s2["created_at"] == created

    @patch("main.genai")
    def test_session_expires_after_ttl(self, mock_genai):
        mock_genai.GenerativeModel.return_value = self._mock_model()
        s1 = self.get_or_create("user_3", "free")
        old_created = s1["created_at"]
        self.main.sessions["user_3"]["last_active"] = (
            time.time() - self.main.config.session_ttl_seconds - 1
        )
        s2 = self.get_or_create("user_3", "free")
        assert s2["created_at"] != old_created


# ──────────────────────────────────────────────
# _resolve_mode
# ──────────────────────────────────────────────
class TestResolveMode:
    def setup_method(self):
        import importlib
        import main as m
        importlib.reload(m)
        self.resolve = m._resolve_mode

    def test_request_mode_overrides_session(self):
        session = {"mode": "free"}
        result = self.resolve(session, "animal_quiz")
        assert result == "animal_quiz"
        assert session["mode"] == "animal_quiz"

    def test_session_mode_used_when_no_request_mode(self):
        session = {"mode": "counting"}
        result = self.resolve(session, None)
        assert result == "counting"

    def test_unknown_request_mode_ignored(self):
        session = {"mode": "sing"}
        result = self.resolve(session, "nonexistent")
        assert result == "sing"


# ──────────────────────────────────────────────
# GAME_MODES & GAME_OPENERS completeness
# ──────────────────────────────────────────────
class TestPrompts:
    def test_all_modes_have_openers(self):
        from prompts import GAME_MODES, GAME_OPENERS
        for mode in GAME_MODES:
            assert mode in GAME_OPENERS, f"Missing opener for mode: {mode}"

    def test_all_modes_have_prefixes(self):
        from prompts import GAME_MODES, MODE_PREFIXES
        for mode in GAME_MODES:
            assert mode in MODE_PREFIXES, f"Missing prefix for mode: {mode}"

    def test_openers_not_empty(self):
        from prompts import GAME_OPENERS
        for mode, opener in GAME_OPENERS.items():
            assert opener.strip(), f"Empty opener for mode: {mode}"


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
class TestAppConfig:
    def test_missing_api_key_raises(self):
        from config import AppConfig
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            AppConfig(gemini_api_key="")

    def test_defaults(self):
        from config import AppConfig
        cfg = AppConfig(gemini_api_key="fake-key")
        assert cfg.model_name == "gemini-2.0-flash"
        assert cfg.port == 8000
        assert cfg.session_ttl_seconds == 1800
        assert cfg.history_window == 10
        assert cfg.dev_mode is False

    def test_platform_detected(self):
        from config import AppConfig
        cfg = AppConfig(gemini_api_key="fake-key")
        assert cfg.platform in ("macos", "raspberry_pi", "linux")
