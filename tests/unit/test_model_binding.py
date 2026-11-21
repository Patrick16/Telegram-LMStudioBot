"""B14 (bind model to session), B15 (staged settings applied) and lms CLI hardening."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.models import perform_load, perform_unload
from src.lms import cli
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "s.json"), histories_dir=str(tmp_path / "h")
    )


@pytest.fixture
def context(store):
    ctx = MagicMock()
    ctx.bot_data = {"store": store}
    ctx.chat_data = {}
    return ctx


@pytest.mark.asyncio
async def test_load_binds_model_to_active_session(store, context):
    session = store.create_session("S")
    with patch("src.lms.cli.load_model", AsyncMock(return_value="ok")):
        await perform_load(context, "qwen/qwen3-4b")
    assert store.get_active_session().model_identifier == "qwen/qwen3-4b"
    assert store.get_active_session().id == session.id


@pytest.mark.asyncio
async def test_staged_settings_are_applied_then_cleared(store, context):
    store.create_session("S")
    context.chat_data["staged_model_settings"] = {
        "gpu": "max", "context_length": 8192, "identifier": "mine",
    }
    mock_load = AsyncMock(return_value="ok")
    with patch("src.lms.cli.load_model", mock_load):
        await perform_load(context, "m", context_length=4096)

    config = mock_load.await_args.args[1]
    assert (config.gpu, config.context_length, config.identifier) == ("max", 4096, "mine")
    assert "staged_model_settings" not in context.chat_data
    assert store.get_active_session().model_identifier == "mine"


@pytest.mark.asyncio
async def test_failed_load_keeps_staged_and_session(store, context):
    store.create_session("S")
    context.chat_data["staged_model_settings"] = {"gpu": "max"}
    with patch("src.lms.cli.load_model", AsyncMock(side_effect=cli.LmsCliError("nope"))):
        with pytest.raises(cli.LmsCliError):
            await perform_load(context, "m")
    assert context.chat_data["staged_model_settings"] == {"gpu": "max"}
    assert store.get_active_session().model_identifier is None


@pytest.mark.asyncio
async def test_unload_clears_binding(store, context):
    store.create_session("S")
    with patch("src.lms.cli.load_model", AsyncMock()):
        await perform_load(context, "m")
    with patch("src.lms.cli.unload_model", AsyncMock()):
        await perform_unload(context, "m")
    assert store.get_active_session().model_identifier is None


@pytest.mark.asyncio
async def test_missing_lms_binary_is_a_cli_error():
    with patch("src.lms.cli.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with pytest.raises(cli.LmsCliError, match="not found"):
            await cli.list_models()


@pytest.mark.asyncio
async def test_lms_timeout_kills_process():
    proc = MagicMock()
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    proc.wait = AsyncMock()
    with patch("src.lms.cli.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)), \
         patch("src.lms.cli.asyncio.wait_for", side_effect=asyncio.TimeoutError):
        with pytest.raises(cli.LmsCliError, match="timed out"):
            await cli.list_models()
    proc.kill.assert_called_once()
