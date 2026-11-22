"""Stage 3: unified models screen + model card, chats list + chat card, reply buttons."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.menu import (
    _handle_models_action,
    _handle_sessions_action,
    handle_pending_input,
    menu_callback_handler,
)
from src.bot.handlers.menu.cards import ModelEntry, build_models_keyboard, format_ago
from src.bot.handlers.menu.screens import (
    SCREEN_CHATS,
    SCREEN_MODEL_CARD,
    SCREEN_MODELS,
    render_screen,
    show_screen,
)
from src.bot.services import inference
from src.lms.cli import LmsCliError
from src.storage.models import ChatMessage
from src.storage.session_store import SessionStoreManager

GB = 1024 ** 3


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(str(tmp_path / "s.json"), histories_dir=str(tmp_path / "h"))


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
    q.message.reply_text = AsyncMock(return_value=MagicMock(message_id=3))
    q.message.chat_id = 5
    q.message.message_id = 77
    return q


def _downloaded(*keys):
    return [SimpleNamespace(model_key=k, info=SimpleNamespace(size_bytes=2 * GB)) for k in keys]


def _loaded(*ids):
    return [SimpleNamespace(identifier=i) for i in ids]


def lms(downloaded, loaded):
    """Patch LM Studio to report these downloaded / loaded models."""
    return (
        patch("src.lms.sdk.list_downloaded_models", AsyncMock(return_value=downloaded)),
        patch("src.lms.sdk.list_loaded_models", AsyncMock(return_value=loaded)),
    )


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


# --- format_ago --------------------------------------------------------------------

def test_format_ago():
    now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)

    def ago(**delta):
        return format_ago((now - timedelta(**delta)).isoformat(), now)

    assert ago(seconds=5) == "just now"
    assert ago(minutes=5) == "5 min ago"
    assert ago(hours=3) == "3 h ago"
    assert ago(days=2) == "2 d ago"
    assert ago(days=30) == "2025-12-11"
    assert format_ago("garbage") == ""


# --- models screen -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_models_screen_marks_loaded_and_bound(store, context):
    session = store.create_session("S")
    session.model_identifier = "a"
    store.update_session(session)
    d, ld = lms(_downloaded("a", "b", "c"), _loaded("a", "b"))
    with d, ld:
        screen = await render_screen(context, SCREEN_MODELS)
    labels = [t for t, _ in buttons(screen.markup)]
    assert labels[0].startswith("▶ a") and labels[1].startswith("🟢 b")
    assert labels[2].startswith("⚪ c")
    assert "2 loaded of 3" in screen.text
    assert buttons(screen.markup)[0][1] == "models:card:0"


@pytest.mark.asyncio
async def test_models_screen_when_lms_down_offers_retry(store, context):
    screen = await render_screen(context, SCREEN_MODELS)  # conftest: offline
    assert "unreachable" in screen.text
    assert ("🔄 Retry", "menu:models") in buttons(screen.markup)


def test_models_keyboard_paginates():
    entries = [ModelEntry(f"m{i}", GB) for i in range(20)]
    markup, page, pages = build_models_keyboard(entries, 1, None)
    assert (page, pages) == (1, 3)
    data = [d for _, d in buttons(markup)]
    assert "models:card:8" in data and "models:card:0" not in data
    assert "models:page:0" in data and "models:page:2" in data


@pytest.mark.asyncio
async def test_models_page_callback(store, context, query):
    d, ld = lms(_downloaded(*[f"m{i}" for i in range(20)]), [])
    with d, ld:
        await _handle_models_action(query, context, "models:page:2")
    assert "Page 3/3" in query.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", ["models:list", "models:loaded", "models:load", "models:unload"])
async def test_legacy_model_entry_points_open_models_screen(store, context, query, legacy):
    d, ld = lms(_downloaded("a"), [])
    with d, ld:
        await _handle_models_action(query, context, legacy)
    assert "Models" in query.edit_message_text.await_args.kwargs["text"]


# --- model card ---------------------------------------------------------------------

async def _open_card(context, query, key_index=0, downloaded=("a", "b"), loaded=()):
    d, ld = lms(_downloaded(*downloaded), _loaded(*loaded))
    with d, ld:
        await show_screen(query, context, SCREEN_MODELS)  # fills the cache
        await _handle_models_action(query, context, f"models:card:{key_index}")
    return query.edit_message_text.await_args.kwargs


@pytest.mark.asyncio
async def test_card_for_unloaded_model_offers_load(store, context, query):
    call = await _open_card(context, query)
    assert "<b>a</b>" in call["text"] and "Not loaded" in call["text"]
    assert ("⬆ Load", "models:do:load") in buttons(call["reply_markup"])


@pytest.mark.asyncio
async def test_card_for_loaded_model_offers_unload_and_use(store, context, query):
    store.create_session("S")
    call = await _open_card(context, query, loaded=("a",))
    data = [d for _, d in buttons(call["reply_markup"])]
    assert "models:do:unload" in data and "models:do:bind" in data


@pytest.mark.asyncio
async def test_card_with_stale_index_returns_to_list(store, context, query):
    context.chat_data["models_cache"] = []
    await _handle_models_action(query, context, "models:card:5")
    assert "changed" in query.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_load_from_card_binds_and_shows_banner(store, context, query):
    store.create_session("S")
    await _open_card(context, query)
    with patch("src.bot.handlers.menu.router.perform_load", AsyncMock()) as load:
        d, ld = lms(_downloaded("a", "b"), _loaded("a"))
        with d, ld:
            await _handle_models_action(query, context, "models:do:load")
    load.assert_awaited_once_with(context, "a")
    final = query.edit_message_text.await_args.kwargs["text"]
    assert "✅ Loaded a" in final and "Loaded" in final


@pytest.mark.asyncio
async def test_load_failure_is_a_banner_on_the_card(store, context, query):
    await _open_card(context, query)
    failing = AsyncMock(side_effect=LmsCliError("out of memory"))
    with patch("src.bot.handlers.menu.router.perform_load", failing):
        d, ld = lms(_downloaded("a", "b"), [])
        with d, ld:
            await _handle_models_action(query, context, "models:do:load")
    assert "❌ Loading failed: out of memory" in query.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_unload_from_card(store, context, query):
    await _open_card(context, query, loaded=("a",))
    with patch("src.bot.handlers.menu.router.perform_unload", AsyncMock()) as unload:
        d, ld = lms(_downloaded("a", "b"), [])
        with d, ld:
            await _handle_models_action(query, context, "models:do:unload")
    unload.assert_awaited_once_with(context, "a")
    assert "✅ Unloaded a" in query.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_use_in_chat_binds_model(store, context, query):
    session = store.create_session("S")
    await _open_card(context, query, loaded=("a",))
    d, ld = lms(_downloaded("a", "b"), _loaded("a"))
    with d, ld:
        await _handle_models_action(query, context, "models:do:bind")
    assert store.get_active_session().model_identifier == "a"
    assert session.id == store.get_active_session().id
    assert "This chat now uses a" in query.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_use_in_chat_without_chat_explains(store, context, query):
    await _open_card(context, query, loaded=("a",))
    d, ld = lms(_downloaded("a", "b"), _loaded("a"))
    with d, ld:
        await _handle_models_action(query, context, "models:do:bind")
    assert "No active chat" in query.edit_message_text.await_args.kwargs["text"]


# --- chats list + card --------------------------------------------------------------

@pytest.mark.asyncio
async def test_chats_list_shows_count_activity_and_active_mark(store, context):
    first = store.create_session("Alpha")
    store.append_messages(first.id, [ChatMessage(role="user", content="a"),
                                     ChatMessage(role="assistant", content="b")])
    store.create_session("Beta")  # becomes active
    screen = await render_screen(context, SCREEN_CHATS)
    rows = buttons(screen.markup)
    assert rows[0][0].startswith("Alpha · 2 msg · ")
    assert rows[1][0].startswith("▶ Beta · 0 msg")
    assert rows[0][1] == f"sessions:card:{first.id}"
    assert ("➕ New Chat", "sessions:new") in rows and ("⬅ Back", "menu:main") in rows


@pytest.mark.asyncio
async def test_chats_list_empty(store, context):
    screen = await render_screen(context, SCREEN_CHATS)
    assert "No chats yet" in screen.text


def test_appending_messages_updates_last_activity(store):
    session = store.create_session("S")
    before = session.updated_at
    store.append_messages(session.id, [ChatMessage(role="user", content="hi")])
    assert store.store.sessions[session.id].updated_at > before


@pytest.mark.asyncio
async def test_chat_card_actions(store, context, query):
    a = store.create_session("Alpha")
    store.create_session("Beta")
    await _handle_sessions_action(query, context, f"sessions:card:{a.id}")
    call = query.edit_message_text.await_args.kwargs
    assert "<b>Alpha</b>" in call["text"] and "0 message" in call["text"]
    data = [d for _, d in buttons(call["reply_markup"])]
    assert f"sessions:switch:{a.id}" in data       # not active → can be opened
    assert f"sessions:rename:{a.id}" in data and f"sessions:del_card:{a.id}" in data


@pytest.mark.asyncio
async def test_active_chat_card_has_no_open_button(store, context, query):
    a = store.create_session("Alpha")
    await _handle_sessions_action(query, context, f"sessions:card:{a.id}")
    data = [d for _, d in buttons(query.edit_message_text.await_args.kwargs["reply_markup"])]
    assert not any(d.startswith("sessions:switch:") for d in data)


@pytest.mark.asyncio
async def test_rename_chat_from_card_renames_that_chat_and_refreshes_card(store, context, query):
    a = store.create_session("Alpha")
    store.create_session("Beta")  # active is Beta
    await _handle_sessions_action(query, context, f"sessions:card:{a.id}")
    await _handle_sessions_action(query, context, f"sessions:rename:{a.id}")
    assert context.chat_data["pending_input"] == f"sessions:rename:{a.id}"

    update = MagicMock()
    update.effective_message.text = "Renamed"
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    await handle_pending_input(update, context)

    assert store.store.sessions[a.id].name == "Renamed"
    assert store.get_active_session().name == "Beta"
    assert "Renamed" in context.bot.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_delete_from_card_cancel_returns_to_card_and_confirm_to_list(store, context, query):
    a = store.create_session("Alpha")
    await _handle_sessions_action(query, context, f"sessions:card:{a.id}")
    await _handle_sessions_action(query, context, f"sessions:del_card:{a.id}")
    markup = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[1][0].callback_data == f"sessions:card:{a.id}"

    confirm = markup.inline_keyboard[0][0].callback_data
    await _handle_sessions_action(query, context, confirm)
    text = query.edit_message_text.await_args.kwargs["text"]
    assert "✅ Chat removed." in text and "No chats yet" in text
    assert store.list_sessions() == []


@pytest.mark.asyncio
async def test_chats_page_callback(store, context, query):
    for i in range(10):
        store.create_session(f"C{i}")
    await _handle_sessions_action(query, context, "sessions:page:card:1")
    labels = [t for t, _ in buttons(query.edit_message_text.await_args.kwargs["reply_markup"])]
    assert any(t.startswith("▶ C9") for t in labels) and not any(t.startswith("C0") for t in labels)


# --- buttons under a finished reply -------------------------------------------------

def test_reply_keyboard_has_four_actions():
    data = [d for _, d in buttons(inference.reply_keyboard())]
    assert data == [inference.CB_REGENERATE, inference.CB_CONTINUE,
                    inference.CB_NEW_CHAT, inference.CB_MENU]


async def _press(context, data):
    update = MagicMock()
    update.effective_user.id = 1
    query = MagicMock(data=data, answer=AsyncMock())
    query.message.reply_text = AsyncMock(return_value=MagicMock(message_id=11))
    update.callback_query = query
    await menu_callback_handler(update, context)
    return query


@pytest.mark.asyncio
async def test_continue_button_runs_a_turn(store, context):
    with patch("src.bot.handlers.menu.router.inference.run_text_turn", AsyncMock()) as turn:
        query = await _press(context, inference.CB_CONTINUE)
    turn.assert_awaited_once_with(query.message, context, inference.CONTINUE_PROMPT)


@pytest.mark.asyncio
async def test_new_chat_button_creates_and_activates_a_chat(store, context):
    store.create_session("Old")
    with patch("src.bot.handlers.menu.router.reply_ephemeral", AsyncMock()) as notice:
        await _press(context, inference.CB_NEW_CHAT)
    assert len(store.list_sessions()) == 2 and store.get_active_session().name == "Chat 2"
    assert "Chat 2" in notice.await_args.args[1]


@pytest.mark.asyncio
async def test_menu_button_sends_a_fresh_menu(store, context):
    query = await _press(context, inference.CB_MENU)
    assert "Main Menu" in query.message.reply_text.await_args.args[0]
    assert context.chat_data["menu_message_id"] == 11
