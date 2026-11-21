"""Stage 4c: error action buttons, retry, /status, onboarding, auto-created first chat."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import lmstudio
import pytest

from src.bot.ephemeral import DEFAULT_DELAY, ERROR_DELAY, reply_ephemeral
from src.bot.handlers.help import start_command
from src.bot.handlers.menu import menu_callback_handler
from src.bot.handlers.status import status_command
from src.bot.services import inference
from src.bot.services.status import build_status_text
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "sessions.json"), histories_dir=str(tmp_path / "histories")
    )


@pytest.fixture
def context(store):
    ctx = MagicMock()
    ctx.bot_data = {
        "config": MagicMock(TELEGRAM_OWNER_ID=1, LMS_HOST="localhost", LMS_PORT=1234),
        "store": store,
    }
    ctx.chat_data = {}
    return ctx


@pytest.fixture
def message():
    msg = MagicMock()
    msg.chat_id = 42
    msg.chat.send_action = AsyncMock()
    placeholder = AsyncMock()
    msg.reply_text = AsyncMock(return_value=placeholder)
    msg.placeholder = placeholder
    return msg


def _failing(exc):
    async def gen(*args, **kwargs):
        raise exc
        yield  # pragma: no cover

    return gen


def _buttons(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# --- error actions ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_model_error_offers_load_and_retry(store, context, message):
    store.create_session("S")
    err = lmstudio.LMStudioModelNotFoundError("none")
    with patch("src.lms.sdk.chat_stream", _failing(err)):
        await inference.run_text_turn(message, context, "question")

    call = message.placeholder.edit_text.await_args
    assert "No model is loaded" in call.args[0]
    assert _buttons(call.kwargs["reply_markup"]) == ["models:load", inference.CB_RETRY]
    assert context.chat_data["retry_text"] == "question"


@pytest.mark.asyncio
async def test_retry_button_resends_the_failed_text(store, context, message):
    store.create_session("S")
    context.chat_data["retry_text"] = "question"
    run = AsyncMock()
    with patch("src.bot.services.inference.run_text_turn", run):
        await inference.run_retry(message, context)
    run.assert_awaited_once_with(message, context, "question")
    assert "retry_text" not in context.chat_data


@pytest.mark.asyncio
async def test_retry_with_nothing_stored(context, message):
    await inference.run_retry(message, context)
    assert "Nothing to retry" in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_retry_callback_is_routed(context):
    update = MagicMock()
    update.effective_user.id = 1
    query = MagicMock(data=inference.CB_RETRY, answer=AsyncMock())
    update.callback_query = query
    with patch("src.bot.handlers.menu.router.inference.run_retry", AsyncMock()) as run:
        await menu_callback_handler(update, context)
    run.assert_awaited_once_with(query.message, context)


@pytest.mark.asyncio
async def test_regenerate_failure_retry_is_regenerate(store, context, message):
    session = store.create_session("S")
    from src.storage.models import ChatMessage

    store.append_messages(session.id, [ChatMessage(role="user", content="q")])
    with patch("src.lms.sdk.chat_stream", _failing(RuntimeError("x"))):
        await inference.run_regenerate(message, context)
    markup = message.placeholder.edit_text.await_args.kwargs["reply_markup"]
    assert _buttons(markup) == [inference.CB_REGENERATE]


@pytest.mark.asyncio
async def test_error_messages_stay_longer_than_confirmations():
    source = MagicMock()
    source.reply_text = AsyncMock(return_value=MagicMock())
    with patch("src.bot.ephemeral.schedule_delete") as sched:
        await reply_ephemeral(source, "✅ done")
        await reply_ephemeral(source, "❌ failed")
    assert sched.call_args_list[0].args[1] == DEFAULT_DELAY
    assert sched.call_args_list[1].args[1] == ERROR_DELAY > DEFAULT_DELAY


# --- first chat is created automatically ---------------------------------------

@pytest.mark.asyncio
async def test_first_message_creates_a_chat(store, context, message):
    async def ok(*args, **kwargs):
        yield "hi"

    with patch("src.lms.sdk.chat_stream", ok):
        await inference.run_text_turn(message, context, "hello")
    assert store.get_active_session().name == "Chat 1"
    assert len(store.list_sessions()) == 1


# --- /status ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_when_lm_studio_is_down(store, context):
    store.create_session("Notes <x>")
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(side_effect=ConnectionError)):
        text = await build_status_text(context)
    assert "unreachable" in text and "localhost:1234" in text
    assert "Notes &lt;x&gt;" in text


@pytest.mark.asyncio
async def test_status_when_online_shows_models_and_context(store, context):
    store.create_session("S")
    handles = [SimpleNamespace(identifier="qwen/qwen3-4b")]
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(return_value=handles)), \
         patch("src.lms.sdk.get_context_length", AsyncMock(return_value=8192)):
        text = await build_status_text(context)
    assert "online" in text
    assert "<code>qwen/qwen3-4b</code>" in text
    assert "<code>8192</code>" in text


@pytest.mark.asyncio
async def test_status_command_replies_html(context):
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.reply_text = AsyncMock()
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(side_effect=ConnectionError)):
        await status_command(update, context)
    assert update.effective_message.reply_text.await_args.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_status_menu_callback(context):
    update = MagicMock()
    update.effective_user.id = 1
    query = MagicMock(data="menu:status", answer=AsyncMock(), edit_message_text=AsyncMock())
    update.callback_query = query
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(side_effect=ConnectionError)):
        await menu_callback_handler(update, context)
    assert "Status" in query.edit_message_text.await_args.kwargs["text"]


# --- onboarding -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_creates_chat_and_welcomes_with_status(store, context):
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_chat.id = 7
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock(message_id=1))
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(side_effect=ConnectionError)):
        await start_command(update, context)

    assert store.get_active_session() is not None
    welcome = update.effective_message.reply_text.await_args_list[0]
    assert "Welcome" in welcome.args[0] and "unreachable" in welcome.args[0]
    assert welcome.kwargs["parse_mode"] == "HTML"
    assert welcome.kwargs["reply_markup"] is not None  # persistent /menu keyboard
