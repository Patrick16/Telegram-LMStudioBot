from unittest.mock import AsyncMock, MagicMock

import pytest

from src.storage.session_store import SessionStoreManager


@pytest.fixture
def bot_config():
    cfg = MagicMock()
    cfg.TELEGRAM_OWNER_ID = 12345
    cfg.LMS_HOST = "localhost"
    cfg.LMS_PORT = 1234
    cfg.SESSIONS_FILE = "data/sessions.json"
    cfg.LOG_LEVEL = "DEBUG"
    return cfg


@pytest.fixture
def session_store(tmp_path):
    return SessionStoreManager(str(tmp_path / "sessions.json"))


@pytest.fixture
def mock_context(bot_config, session_store):
    ctx = MagicMock()
    ctx.bot_data = {"config": bot_config, "store": session_store}
    ctx.args = []
    return ctx


@pytest.fixture
def mock_update():
    u = MagicMock()
    u.effective_user.id = 12345
    u.effective_message.reply_text = AsyncMock()
    u.effective_message.text = "test"
    return u


@pytest.fixture(autouse=True)
def _no_real_lm_studio(monkeypatch):
    """Never reach a real LM Studio from tests; context size is 'unknown' by default."""
    monkeypatch.setattr(
        "src.lms.sdk.get_context_length", AsyncMock(side_effect=ConnectionError("offline"))
    )


@pytest.fixture(autouse=True)
def _lms_offline_by_default(monkeypatch):
    """Menu screens probe LM Studio; tests that care patch list_loaded_models themselves."""
    monkeypatch.setattr(
        "src.lms.sdk.list_loaded_models", AsyncMock(side_effect=ConnectionError("offline"))
    )
    monkeypatch.setattr(
        "src.lms.sdk.list_downloaded_models", AsyncMock(side_effect=ConnectionError("offline"))
    )


@pytest.fixture(autouse=True)
def _english_ui():
    """Tests assert English UI text; the language is process-wide, so reset it around each test."""
    from src.bot import i18n

    i18n.set_language("en")
    yield
    i18n.set_language("en")
