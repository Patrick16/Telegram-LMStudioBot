"""Live streaming edits, Stop / Regenerate buttons (Stage 4a)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest, RetryAfter

from src.bot.formatting import format_stream_preview
from src.bot.handlers.menu import menu_callback_handler
from src.bot.services import inference
from src.bot.services.generation import get_generations
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
def message():
    msg = MagicMock()
    msg.chat_id = 42
    msg.chat.send_action = AsyncMock()
    placeholder = AsyncMock()
    msg.reply_text = AsyncMock(return_value=placeholder)
    msg.placeholder = placeholder
    return msg


def _slow_stream(chunks, delay=0.03):
    async def gen(*args, **kwargs):
        for c in chunks:
            await asyncio.sleep(delay)
            yield c

    return gen


# --- preview formatting --------------------------------------------------------

def test_preview_hides_reasoning():
    assert format_stream_preview("<think>hmm") == "💭 Thinking…"
    assert format_stream_preview("") == "⏳ Thinking..."
    assert format_stream_preview("<think>x</think>Hel") == "Hel ▌"


def test_preview_shows_tail_of_long_text():
    preview = format_stream_preview("a" * 10000 + "END")
    assert len(preview) < 4096
    assert preview.endswith("END ▌")


# --- live edits ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_reply_is_edited_live_and_final_has_regenerate_button(store, context, message):
    store.create_session("S")
    with patch("src.bot.services.inference.STREAM_EDIT_INTERVAL", 0.0), \
         patch("src.lms.sdk.chat_stream", _slow_stream(["Hel", "lo ", "world"])):
        await inference.run_text_turn(message, context, "Hi")

    edits = message.placeholder.edit_text.await_args_list
    previews = [c.args[0] for c in edits[:-1]]
    assert previews[:2] == ["Hel ▌", "Hello ▌"]  # live, with cursor
    for call in edits[:-1]:
        assert call.kwargs["parse_mode"] == "HTML"
        assert call.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == inference.CB_STOP

    final = edits[-1]
    assert final.args[0] == "Hello world"
    assert final.kwargs["parse_mode"] == "HTML"
    assert final.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        inference.CB_REGENERATE
    )


@pytest.mark.asyncio
async def test_placeholder_has_stop_button_and_typing_is_shown(store, context, message):
    store.create_session("S")
    with patch("src.lms.sdk.chat_stream", _slow_stream(["ok"], delay=0.05)):
        await inference.run_text_turn(message, context, "Hi")
    markup = message.reply_text.await_args_list[0].kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == inference.CB_STOP
    message.chat.send_action.assert_awaited()


@pytest.mark.asyncio
async def test_live_edits_are_throttled(store, context, message):
    store.create_session("S")
    # default interval (1.5 s) is far longer than the stream -> only the final edit
    with patch("src.lms.sdk.chat_stream", _slow_stream(["a", "b", "c"], delay=0.01)):
        await inference.run_text_turn(message, context, "Hi")
    assert len(message.placeholder.edit_text.await_args_list) == 1


@pytest.mark.asyncio
async def test_live_edit_errors_do_not_break_generation(store, context, message):
    session = store.create_session("S")
    message.placeholder.edit_text.side_effect = [
        BadRequest("Message is not modified"),
        RetryAfter(1),
        None,
    ]
    with patch("src.bot.services.inference.STREAM_EDIT_INTERVAL", 0.0), \
         patch("src.lms.sdk.chat_stream", _slow_stream(["a", "b", "c"])):
        await inference.run_text_turn(message, context, "Hi")
    assert [m.content for m in store.load_history(session.id)] == ["Hi", "abc"]


# --- buttons -------------------------------------------------------------------

def _callback_update(data, chat_id=42):
    update = MagicMock()
    update.effective_user.id = 1
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.message.chat_id = chat_id
    query.message.reply_text = AsyncMock()
    update.callback_query = query
    return update, query


@pytest.mark.asyncio
async def test_stop_button_cancels_generation(store, context, message):
    session = store.create_session("S")
    started = asyncio.Event()

    async def slow(*args, **kwargs):
        yield "partial"
        started.set()
        await asyncio.sleep(10)
        yield "never"

    with patch("src.lms.sdk.chat_stream", slow):
        task = asyncio.create_task(inference.run_text_turn(message, context, "Hi"))
        await started.wait()
        update, _ = _callback_update(inference.CB_STOP)
        await menu_callback_handler(update, context)
        await asyncio.wait_for(task, 2)

    assert message.placeholder.edit_text.await_args.args[0] == inference.MSG_STOPPED
    assert store.load_history(session.id) == []
    assert not get_generations(context).is_active(42)


@pytest.mark.asyncio
async def test_regenerate_button_runs_regeneration(context):
    update, query = _callback_update(inference.CB_REGENERATE)
    with patch(
        "src.bot.handlers.menu.router.inference.run_regenerate", AsyncMock()
    ) as run:
        await menu_callback_handler(update, context)
    run.assert_awaited_once_with(query.message, context)
