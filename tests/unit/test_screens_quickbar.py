"""Stages 1-2: screen registry, banners, origin-screen refresh, control-panel menu, quickbar."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest

from src.bot.handlers import quickbar
from src.bot.handlers.menu import _handle_sessions_action, handle_pending_input
from src.bot.handlers.menu.keyboards import LmsState, render_main_menu_text
from src.bot.handlers.menu.screens import (
    SCREEN_MAIN,
    SCREEN_SESSIONS,
    SCREEN_PARAM,
    SCREENS,
    render_screen,
    show_screen,
    with_banner,
)
from src.bot.handlers.menu import _handle_settings_action
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "s.json"), histories_dir=str(tmp_path / "h")
    )


@pytest.fixture
def context(store):
    ctx = MagicMock()
    ctx.bot_data = {
        "config": MagicMock(TELEGRAM_OWNER_ID=1, LMS_HOST="h", LMS_PORT=1),
        "store": store,
    }
    ctx.chat_data = {}
    ctx.bot.edit_message_text = AsyncMock()
    return ctx


@pytest.fixture
def query():
    q = MagicMock()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    q.message.chat_id = 5
    q.message.message_id = 77
    return q


@pytest.mark.asyncio
async def test_every_registered_screen_renders(store, context):
    store.create_session("S")
    for key in SCREENS:
        screen = await render_screen(context, key)
        assert screen.text and screen.markup.inline_keyboard, key
        assert screen.parse_mode == "HTML"


@pytest.mark.asyncio
async def test_unknown_screen_is_none(context):
    assert await render_screen(context, "nope") is None


def test_banner_is_escaped_and_prepended():
    assert with_banner("body", "✅ a<b>") == "✅ a&lt;b&gt;\n\nbody"
    assert with_banner("body", None) == "body"


@pytest.mark.asyncio
async def test_show_screen_tracks_current_screen_and_banner(store, context, query):
    store.create_session("S")
    await show_screen(query, context, SCREEN_SESSIONS, banner="✅ done")
    text = query.edit_message_text.await_args.kwargs["text"]
    assert text.startswith("✅ done") and "Chat Sessions" in text
    assert context.chat_data["menu_screen"] == SCREEN_SESSIONS


@pytest.mark.asyncio
async def test_stale_menu_recovery_keeps_banner(store, context, query):
    query.edit_message_text = AsyncMock(side_effect=BadRequest("Message to edit not found"))
    query.message.chat.send_message = AsyncMock(return_value=MagicMock(message_id=9))
    await show_screen(query, context, SCREEN_SESSIONS, banner="✅ done")
    assert "✅ done" in query.message.chat.send_message.await_args.kwargs["text"]
    assert context.chat_data["menu_message_id"] == 9


# --- main menu header -------------------------------------------------------------

def test_main_header_shows_lms_state_and_temperature(store):
    assert "offline" in render_main_menu_text(store, LmsState(online=False))
    assert "2 loaded" in render_main_menu_text(store, LmsState(online=True, loaded=("a", "b")))
    store.create_session("S")
    assert "Temperature" in render_main_menu_text(store)


@pytest.mark.asyncio
async def test_main_screen_probes_lms(store, context):
    handle = SimpleNamespace(identifier="qwen")
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(return_value=[handle])):
        screen = await render_screen(context, SCREEN_MAIN)
    assert "🟢 LM Studio · 1 loaded" in screen.text


@pytest.mark.asyncio
async def test_main_screen_survives_lms_down(store, context):
    screen = await render_screen(context, SCREEN_MAIN)  # conftest: LM Studio offline
    assert "offline" in screen.text


# --- banners replace separate confirmation messages ------------------------------

@pytest.mark.asyncio
async def test_switch_chat_returns_to_main_with_banner(store, context, query):
    s = store.create_session("Alpha")
    store.create_session("Beta")
    await _handle_sessions_action(query, context, f"sessions:switch:{s.id}")
    text = query.edit_message_text.await_args.kwargs["text"]
    assert "Switched to chat: Alpha" in text and "Main Menu" in text
    query.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_reset_shows_banner_on_session_settings(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:session:reset")
    text = query.edit_message_text.await_args.kwargs["text"]
    assert "reset to defaults" in text and "Session Settings" in text


# --- origin screen refresh after a typed value -----------------------------------

@pytest.mark.asyncio
async def test_saved_value_refreshes_originating_screen(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:session:temperature")
    await _handle_settings_action(query, context, "settings:param:input")
    assert context.chat_data["pending_return"]["screen"] == SCREEN_PARAM

    update = MagicMock()
    update.effective_message.text = "1.5"
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    await handle_pending_input(update, context)

    call = context.bot.edit_message_text.await_args.kwargs
    assert call["message_id"] == 77 and call["chat_id"] == 5
    assert "<code>1.5</code>" in call["text"]
    assert any("✅ 1.5" in b.text for row in call["reply_markup"].inline_keyboard for b in row)
    assert context.chat_data.get("pending_return") is None


@pytest.mark.asyncio
async def test_invalid_value_keeps_waiting_without_refresh(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:session:temperature")
    await _handle_settings_action(query, context, "settings:param:input")
    update = MagicMock()
    update.effective_message.text = "banana"
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    await handle_pending_input(update, context)
    context.bot.edit_message_text.assert_not_called()
    assert context.chat_data["pending_input"] == "settings:session:temperature"


# --- bottom keyboard ---------------------------------------------------------------

def test_quickbar_has_four_shortcuts():
    labels = [b.text for row in quickbar.QUICKBAR_KEYBOARD.keyboard for b in row]
    assert labels == [quickbar.BTN_MENU, quickbar.BTN_STOP, quickbar.BTN_NEW_CHAT,
                      quickbar.BTN_STATUS]


@pytest.mark.asyncio
@pytest.mark.parametrize("label,target", [
    (quickbar.BTN_MENU, "menu_command_handler"),
    (quickbar.BTN_STOP, "stop_command"),
    (quickbar.BTN_NEW_CHAT, "newchat_command"),
    (quickbar.BTN_STATUS, "status_command"),
])
async def test_quickbar_dispatches_to_command(label, target):
    update, context = MagicMock(), MagicMock()
    update.effective_message.text = label
    mock = AsyncMock()
    with patch.dict(quickbar._ACTIONS, {label: mock}):
        await quickbar.quickbar_handler(update, context)
    mock.assert_awaited_once_with(update, context)
