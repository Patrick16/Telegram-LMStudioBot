"""Stage 4d (part 1): pagination of long lists and chat renaming."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.chats import renamechat_command
from src.bot.handlers.menu import (
    _handle_sessions_action,
    build_sessions_list_keyboard,
    handle_pending_input,
    menu_callback_handler,
)
from src.bot.pagination import NOOP, nav_row, paginate
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
    ctx.args = []
    return ctx


@pytest.fixture
def query():
    q = MagicMock()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    return q


# --- helpers -----------------------------------------------------------------------

def test_paginate_slices_and_clamps():
    items = list(range(20))
    assert paginate(items, 0) == (list(range(8)), 0, 3)
    assert paginate(items, 2) == (list(range(16, 20)), 2, 3)
    assert paginate(items, 99)[1] == 2
    assert paginate(items, -5)[1] == 0
    assert paginate([], 0) == ([], 0, 1)


def test_nav_row_shapes():
    assert nav_row("p:", 0, 1) == []
    first = [(b.text, b.callback_data) for b in nav_row("p:", 0, 3)]
    assert first == [("1/3", NOOP), ("▶", "p:1")]
    middle = [(b.text, b.callback_data) for b in nav_row("p:", 1, 3)]
    assert middle == [("◀", "p:0"), ("2/3", NOOP), ("▶", "p:2")]
    last = [(b.text, b.callback_data) for b in nav_row("p:", 2, 3)]
    assert last == [("◀", "p:1"), ("3/3", NOOP)]


# --- sessions list -------------------------------------------------------------------

def _sessions(n):
    return [SimpleNamespace(id=f"id{i}", name=f"Chat {i}") for i in range(n)]


def test_sessions_keyboard_marks_active_and_paginates():
    kb = build_sessions_list_keyboard(_sessions(10), "switch", page=0, active_id="id1")
    rows = kb.inline_keyboard
    assert len(rows) == 8 + 1 + 1  # items + navigation + back
    assert rows[1][0].text == "▶ Chat 1"
    assert [b.callback_data for b in rows[8]] == [NOOP, "sessions:page:switch:1"]

    page2 = build_sessions_list_keyboard(_sessions(10), "switch", page=1).inline_keyboard
    assert [r[0].text for r in page2[:2]] == ["Chat 8", "Chat 9"]
    assert page2[2][0].callback_data == "sessions:page:switch:0"


def test_short_lists_have_no_navigation():
    rows = build_sessions_list_keyboard(_sessions(3), "switch").inline_keyboard
    assert len(rows) == 3 + 1


@pytest.mark.asyncio
async def test_page_callback_edits_list(store, context, query):
    for i in range(10):
        store.create_session(f"Chat {i}")
    await _handle_sessions_action(query, context, "sessions:page:remove_ask:1")
    call = query.edit_message_text.await_args
    assert "remove" in call.kwargs["text"]
    first_page_button = call.kwargs["reply_markup"].inline_keyboard[0][0]
    assert first_page_button.text == "Chat 8"
    assert first_page_button.callback_data.startswith("sessions:remove_ask:")


@pytest.mark.asyncio
async def test_noop_callback_does_nothing(context):
    update = MagicMock()
    update.effective_user.id = 1
    q = MagicMock(data=NOOP, answer=AsyncMock(), edit_message_text=AsyncMock())
    update.callback_query = q
    await menu_callback_handler(update, context)
    q.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_load_page_callback_shows_requested_page(context):
    models = [
        SimpleNamespace(model_key=f"m{i}", info=SimpleNamespace(size_bytes=1)) for i in range(20)
    ]
    update = MagicMock()
    update.effective_user.id = 1
    q = MagicMock(data="models:loadpage:2", answer=AsyncMock(), edit_message_text=AsyncMock())
    update.callback_query = q
    with patch("src.lms.sdk.list_downloaded_models", AsyncMock(return_value=models)), \
         patch("src.lms.sdk.list_loaded_models", AsyncMock(return_value=[])):
        await menu_callback_handler(update, context)
    call = q.edit_message_text.await_args
    assert "page 3/3" in call.args[0]
    assert call.kwargs["reply_markup"].inline_keyboard[0][0].text.startswith("m16")


# --- rename ----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rename_button_asks_for_name(store, context, query):
    store.create_session("Old")
    await _handle_sessions_action(query, context, "sessions:rename")
    assert context.chat_data["pending_input"] == "sessions:rename"


@pytest.mark.asyncio
async def test_rename_button_without_chat(context, query):
    await _handle_sessions_action(query, context, "sessions:rename")
    assert "pending_input" not in context.chat_data


@pytest.mark.asyncio
async def test_rename_via_pending_input(store, context):
    store.create_session("Old")
    context.chat_data["pending_input"] = "sessions:rename"
    update = MagicMock()
    update.effective_message.text = "  Shiny new name "
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    await handle_pending_input(update, context)
    assert store.get_active_session().name == "Shiny new name"
    assert context.chat_data["pending_input"] is None


@pytest.mark.asyncio
async def test_rename_rejects_empty_and_too_long_names(store, context):
    store.create_session("Old")
    context.chat_data["pending_input"] = "sessions:rename"
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    for bad in ("", "x" * 65):
        update.effective_message.text = bad
        await handle_pending_input(update, context)
        assert store.get_active_session().name == "Old"
        assert context.chat_data["pending_input"] == "sessions:rename"  # keeps waiting


@pytest.mark.asyncio
async def test_renamechat_command(store, context):
    store.create_session("Old")
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())

    context.args = ["My", "project"]
    await renamechat_command(update, context)
    assert store.get_active_session().name == "My project"

    context.args = []
    await renamechat_command(update, context)
    assert "Usage" in update.effective_message.reply_text.await_args.args[0]
    assert store.get_active_session().name == "My project"
