"""
KidsChatApp — Backend Unit Tests
"""
import time
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Set required env var before importing app modules
os.environ.setdefault("GEMINI_API_KEY", "test-key-fake")

# Add backend to path
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

    def test_chat_mode_no_prefix(self):
        assert self.build("你好", "chat") == "你好"

    def test_sing_mode_prefix(self):
        result = self.build("小星星", "sing")
        assert result.startswith("【唱歌模式】")
        assert "小星星" in result

    def test_story_mode_prefix(self):
        result = self.build("小熊", "story")
        assert result.startswith("【故事模式】")
        assert "小熊" in result

    def test_roleplay_mode_prefix(self):
        result = self.build("公主", "roleplay")
        assert result.startswith("【角色扮演】")
        assert "公主" in result

    def test_unknown_mode_no_prefix(self):
        # Unknown mode falls back to no prefix
        assert self.build("測試", "unknown") == "測試"


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
        mock_chat.history = list(range(10))  # 5 turns, window=10
        self.trim(mock_chat)
        assert len(mock_chat.history) == 10

    def test_trims_when_over_limit(self):
        mock_chat = MagicMock()
        window = self.config.history_window  # default 10
        max_msgs = window * 2
        # Create history longer than max
        mock_chat.history = list(range(max_msgs + 6))
        self.trim(mock_chat)
        assert len(mock_chat.history) == max_msgs

    def test_trim_keeps_recent_messages(self):
        mock_chat = MagicMock()
        window = self.config.history_window
        max_msgs = window * 2
        all_msgs = list(range(max_msgs + 4))
        mock_chat.history = all_msgs
        self.trim(mock_chat)
        # Should keep the LAST max_msgs messages
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

    def _mock_generative_model(self):
        mock_chat = MagicMock()
        mock_chat.history = []
        mock_model = MagicMock()
        mock_model.start_chat.return_value = mock_chat
        return mock_model

    @patch("main.genai")
    def test_creates_new_session(self, mock_genai):
        mock_genai.GenerativeModel.return_value = self._mock_generative_model()
        session = self.get_or_create("user_1", "chat")
        assert "user_1" in self.main.sessions
        assert "chat" in session
        assert "created_at" in session
        assert "last_active" in session

    @patch("main.genai")
    def test_reuses_existing_session(self, mock_genai):
        mock_genai.GenerativeModel.return_value = self._mock_generative_model()
        s1 = self.get_or_create("user_2", "chat")
        created = s1["created_at"]
        s2 = self.get_or_create("user_2", "chat")
        # Should be the same session object
        assert s2["created_at"] == created

    @patch("main.genai")
    def test_session_expires_after_ttl(self, mock_genai):
        mock_genai.GenerativeModel.return_value = self._mock_generative_model()
        s1 = self.get_or_create("user_3", "chat")
        old_created = s1["created_at"]

        # Manually expire the session
        self.main.sessions["user_3"]["last_active"] = time.time() - self.main.config.session_ttl_seconds - 1

        s2 = self.get_or_create("user_3", "chat")
        assert s2["created_at"] != old_created


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
        assert cfg.model_name == "gemini-1.5-flash"
        assert cfg.port == 8000
        assert cfg.session_ttl_seconds == 1800
        assert cfg.history_window == 10
        assert cfg.dev_mode is False

    def test_platform_detected(self):
        from config import AppConfig
        cfg = AppConfig(gemini_api_key="fake-key")
        assert cfg.platform in ("macos", "raspberry_pi", "linux")
