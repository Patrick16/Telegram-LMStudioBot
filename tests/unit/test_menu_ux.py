"""Stage 4b: cancellable input prompts, delete confirmation, informative menu header."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.menu import (
    _handle_sessions_action,
    _handle_settings_action,
    menu_callback_handler,
)
from src.bot.handlers.menu import pending
from src.bot.handlers.menu.keyboards import render_main_menu_text
from src.bot.handlers.messages import text_message_handler
from src.storage.models import ChatMessage
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
        "config": MagicMock(TELEGRAM_OWNER_ID=1, LMS_HOST="h", LMS_PORT=1),
        "store": store,
    }
    ctx.chat_data = {}
    return ctx


@pytest.fixture
def query():
    q = MagicMock()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    q.message.chat_id = 42
    return q


# --- cancel / timeout ----------------------------------------------------------

@pytest.mark.asyncio
async def test_value_prompt_offers_cancel_and_cancel_clears_pending(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:session:temperature")
    await _handle_settings_action(query, context, "settings:param:input")

    assert context.chat_data["pending_input"] == "settings:session:temperature"
    markup = query.message.reply_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == pending.CB_INPUT_CANCEL

    update = MagicMock()
    update.effective_user.id = 1
    query.data = pending.CB_INPUT_CANCEL
    update.callback_query = query
    await menu_callback_handler(update, context)

    assert context.chat_data["pending_input"] is None
    assert "Cancelled" in query.edit_message_text.await_args.args[0]


@pytest.mark.asyncio
async def test_stale_prompt_expires_and_message_goes_to_model(store, context):
    store.create_session("S")
    context.chat_data["pending_input"] = "settings:session:temperature"
    context.chat_data["pending_input_at"] = 0.0  # long ago

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.text = "hello model"
    update.effective_message.reply_text = AsyncMock()
    run = AsyncMock()
    with patch("src.bot.handlers.messages.inference.run_text_turn", run), \
         patch("src.bot.handlers.messages.reply_ephemeral", AsyncMock()) as notice:
        await text_message_handler(update, context)

    assert context.chat_data["pending_input"] is None
    run.assert_awaited_once()
    assert "expired" in notice.await_args.args[1]


@pytest.mark.asyncio
async def test_fresh_prompt_is_not_expired(context):
    context.chat_data["pending_input"] = "x"
    context.chat_data["pending_input_at"] = pending.time.monotonic()
    assert pending.expire_pending_if_stale(context) is False
    assert context.chat_data["pending_input"] == "x"


# --- delete confirmation -------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_asks_for_confirmation_before_deleting(store, context, query):
    session = store.create_session("Work <chat>")
    store.append_messages(session.id, [ChatMessage(role="user", content="hi")])

    await _handle_sessions_action(query, context, "sessions:remove")
    buttons = query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
    assert buttons[0][0].callback_data == f"sessions:remove_ask:{session.id}"

    await _handle_sessions_action(query, context, f"sessions:remove_ask:{session.id}")
    call = query.edit_message_text.await_args
    assert "Work &lt;chat&gt;" in call.kwargs["text"] and "1 message" in call.kwargs["text"]
    assert call.kwargs["parse_mode"] == "HTML"
    assert session.id in store.store.sessions  # nothing deleted yet
    confirm = call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    assert confirm == f"sessions:confirm_remove:{session.id}"

    await _handle_sessions_action(query, context, confirm)
    assert session.id not in store.store.sessions


# --- menu header ---------------------------------------------------------------

def test_main_menu_header_without_chat(store):
    assert "No chat yet" in render_main_menu_text(store)


def test_main_menu_header_shows_chat_model_and_count(store):
    session = store.create_session("Notes & <ideas>")
    store.append_messages(
        session.id,
        [ChatMessage(role="user", content="a"), ChatMessage(role="assistant", content="b")],
    )
    text = render_main_menu_text(store)
    assert "Notes &amp; &lt;ideas&gt;" in text and "2 message(s)" in text
    assert "not loaded" in text

    session.model_identifier = "qwen/qwen3-4b"
    store.update_session(session)
    assert "<code>qwen/qwen3-4b</code>" in render_main_menu_text(store)
