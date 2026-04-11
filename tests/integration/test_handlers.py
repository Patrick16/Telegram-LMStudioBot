from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.chats import (
    chats_command,
    newchat_command,
    removechat_command,
    switchchat_command,
)
from src.bot.handlers.messages import regenerate_command, text_message_handler
from src.bot.handlers.models import (
    load_command,
    loaded_command,
    models_command,
    unload_command,
)
from src.bot.handlers.settings import set_command, setprompt_command
from src.lms.cli import LmsCliError
from src.storage.models import ChatMessage
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.TELEGRAM_OWNER_ID = 12345
    cfg.LMS_HOST = "localhost"
    cfg.LMS_PORT = 1234
    return cfg


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(str(tmp_path / "sessions.json"))


@pytest.fixture
def context(config, store):
    ctx = MagicMock()
    ctx.bot_data = {"config": config, "store": store}
    ctx.args = []
    return ctx


@pytest.fixture
def update():
    u = MagicMock()
    u.effective_user.id = 12345
    u.effective_message.reply_text = AsyncMock()
    u.effective_message.text = "Hello"
    return u


# --- US1: /models, /loaded ---

@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.list_models", new_callable=AsyncMock)
async def test_models_success(mock_list, update, context):
    mock_list.return_value = "• qwen/qwen3-4b\n• mistral/mistral-7b"
    await models_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "qwen/qwen3-4b" in reply
    assert "📦" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.list_models", new_callable=AsyncMock)
async def test_models_unreachable(mock_list, update, context):
    mock_list.side_effect = LmsCliError("Connection refused")
    await models_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Could not connect" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.list_loaded", new_callable=AsyncMock)
async def test_loaded_success(mock_loaded, update, context):
    mock_loaded.return_value = "• qwen/qwen3-4b [my-model]"
    await loaded_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "qwen/qwen3-4b" in reply
    assert "🧠" in reply


# --- US2: /load, /unload ---

@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.load_model", new_callable=AsyncMock)
async def test_load_success(mock_load, update, context):
    context.args = ["qwen/qwen3-4b", "gpu=max", "ctx=4096"]
    mock_load.return_value = "OK"
    await load_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "loaded successfully" in reply


@pytest.mark.asyncio
async def test_load_invalid_gpu(update, context):
    context.args = ["qwen/qwen3-4b", "gpu=invalid"]
    await load_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Invalid gpu value" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.load_model", new_callable=AsyncMock)
async def test_load_model_not_found(mock_load, update, context):
    context.args = ["nonexistent/model"]
    mock_load.side_effect = LmsCliError("Model not found")
    await load_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Load failed" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.unload_model", new_callable=AsyncMock)
async def test_unload_success(mock_unload, update, context):
    context.args = ["qwen/qwen3-4b"]
    mock_unload.return_value = "OK"
    await unload_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "unloaded" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.unload_model", new_callable=AsyncMock)
async def test_unload_not_loaded(mock_unload, update, context):
    context.args = ["qwen/qwen3-4b"]
    mock_unload.side_effect = LmsCliError("Model not loaded")
    await unload_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Model not loaded" in reply


# --- US3: /setprompt, /set ---

@pytest.mark.asyncio
async def test_setprompt_no_chat(update, context):
    context.args = ["You", "are", "a", "helper"]
    await setprompt_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


@pytest.mark.asyncio
async def test_setprompt_set(update, context, store):
    store.create_session("Test")
    context.args = ["You", "are", "a", "helper"]
    await setprompt_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "updated" in reply
    session = store.get_active_session()
    assert session.system_prompt == "You are a helper"


@pytest.mark.asyncio
async def test_setprompt_clear(update, context, store):
    s = store.create_session("Test")
    s.system_prompt = "old prompt"
    store.update_session(s)
    context.args = []
    await setprompt_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "cleared" in reply


@pytest.mark.asyncio
async def test_set_temperature(update, context, store):
    store.create_session("Test")
    context.args = ["temperature", "0.5"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "temperature set to 0.5" in reply


@pytest.mark.asyncio
async def test_set_invalid_value(update, context, store):
    store.create_session("Test")
    context.args = ["temperature", "5.0"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Invalid value" in reply or "<=" in reply


@pytest.mark.asyncio
async def test_set_unknown_setting(update, context, store):
    store.create_session("Test")
    context.args = ["unknown_param", "1.0"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Unknown setting" in reply


@pytest.mark.asyncio
async def test_set_no_chat(update, context):
    context.args = ["temperature", "0.5"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


# --- US4: /newchat, /chats, /switchchat ---

@pytest.mark.asyncio
async def test_newchat(update, context, store):
    context.args = ["My", "Chat"]
    await newchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "My Chat" in reply
    assert len(store.list_sessions()) == 1


@pytest.mark.asyncio
async def test_newchat_default_name(update, context, store):
    context.args = []
    await newchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Chat 1" in reply


@pytest.mark.asyncio
async def test_chats_empty(update, context, store):
    await chats_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No chats" in reply


@pytest.mark.asyncio
async def test_chats_list(update, context, store):
    store.create_session("Alpha")
    store.create_session("Beta")
    await chats_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Alpha" in reply
    assert "Beta" in reply
    assert "▶" in reply


@pytest.mark.asyncio
async def test_switchchat_valid(update, context, store):
    s1 = store.create_session("First")
    store.create_session("Second")
    context.args = ["1"]
    await switchchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "First" in reply
    assert store.store.active_session_id == s1.id


@pytest.mark.asyncio
async def test_switchchat_invalid(update, context, store):
    context.args = ["99"]
    await switchchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "not found" in reply


# --- US6: /removechat ---

@pytest.mark.asyncio
async def test_removechat_existing(update, context, store):
    store.create_session("ToRemove")
    store.create_session("Keep")
    context.args = ["1"]
    await removechat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "removed" in reply
    assert len(store.list_sessions()) == 1


@pytest.mark.asyncio
async def test_removechat_last(update, context, store):
    store.create_session("Only")
    context.args = ["1"]
    await removechat_command(update, context)
    assert store.store.active_session_id is None


@pytest.mark.asyncio
async def test_removechat_not_found(update, context):
    context.args = ["99"]
    await removechat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "not found" in reply


# --- US7: text handler, /regenerate ---

class MockStream:
    def __init__(self, fragments):
        self._fragments = list(fragments)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._fragments:
            raise StopAsyncIteration
        return self._fragments.pop(0)


@pytest.mark.asyncio
async def test_text_handler_no_chat(update, context):
    await text_message_handler(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.messages.sdk.chat_stream")
async def test_text_handler_success(mock_stream, update, context, store):
    store.create_session("Test")
    mock_stream.return_value = MockStream(["Hello", " there"])
    sent_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=sent_msg)
    update.effective_message.text = "Hi"
    # Need to mock the auth check
    update.effective_user.id = 12345

    await text_message_handler(update, context)
    session = store.get_active_session()
    assert len(session.history) == 2
    assert session.history[0].role == "user"
    assert session.history[1].role == "assistant"


@pytest.mark.asyncio
async def test_regenerate_no_chat(update, context):
    await regenerate_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


@pytest.mark.asyncio
async def test_regenerate_empty_history(update, context, store):
    store.create_session("Test")
    await regenerate_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Nothing to regenerate" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.messages.sdk.chat_stream")
async def test_regenerate_success(mock_stream, update, context, store):
    s = store.create_session("Test")
    s.history = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Old response"),
    ]
    store.update_session(s)

    mock_stream.return_value = MockStream(["New", " response"])
    sent_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=sent_msg)

    await regenerate_command(update, context)
    session = store.get_active_session()
    assert session.history[-1].content == "New response"
