"""Screen registry: every menu screen is rendered from current state in one place.

A screen is ``(text, keyboard, parse_mode)``. Navigation always edits the single
menu message, and one-off feedback ("✅ Chat removed") is shown as a *banner* on
top of the screen instead of a separate chat message.
"""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from src.bot.handlers.menu.cards import (
    ModelEntry,
    build_chat_card_keyboard,
    build_model_card_keyboard,
    build_models_keyboard,
    build_models_unreachable,
    chat_row_label,
    render_chat_card,
    render_model_card,
    render_models_text,
)
from src.bot.handlers.menu.keyboards import (
    LmsState,
    build_back_button,
    build_help_menu,
    build_history_policy_menu,
    build_main_menu,
    build_model_settings_menu,
    build_session_settings_menu,
    build_sessions_menu,
    build_settings_menu,
    render_current_settings,
    render_main_menu_text,
)
from src.bot.pagination import nav_row, paginate
from src.bot.services.status import build_status_text
from src.lms import sdk

logger = logging.getLogger(__name__)

LMS_PROBE_TIMEOUT = 2.0  # seconds; the menu must stay snappy when LM Studio is down

SCREEN_MAIN = "menu:main"
SCREEN_MODELS = "menu:models"
SCREEN_SESSIONS = "menu:sessions"
SCREEN_SETTINGS = "menu:settings"
SCREEN_HELP = "menu:help"
SCREEN_STATUS = "menu:status"
SCREEN_MODEL_SETTINGS = "settings:model_menu"
SCREEN_SESSION_SETTINGS = "settings:session_menu"
SCREEN_HISTORY_POLICY = "settings:history_policy"
SCREEN_CURRENT_SETTINGS = "settings:current"
SCREEN_MODEL_CARD = "models:card"
SCREEN_CHATS = "sessions:list"
SCREEN_CHAT_CARD = "sessions:card"


@dataclass(frozen=True)
class Screen:
    text: str
    markup: InlineKeyboardMarkup
    parse_mode: str = "HTML"


def with_banner(text: str, banner: str | None) -> str:
    """Prefix *text* with a one-line feedback banner (plain text, escaped for HTML)."""
    if not banner:
        return text
    return f"{html.escape(banner, quote=False)}\n\n{text}"


async def probe_lms(context) -> LmsState:
    """Ask LM Studio what is loaded; never raises, never blocks for long."""
    config = context.bot_data["config"]
    try:
        handles = await asyncio.wait_for(
            sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT), LMS_PROBE_TIMEOUT
        )
    except Exception:
        return LmsState(online=False)
    return LmsState(online=True, loaded=tuple(getattr(h, "identifier", "?") for h in handles))


def _active_session(context):
    return context.bot_data["store"].get_active_session()


def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


async def _main(context) -> Screen:
    text = render_main_menu_text(context.bot_data["store"], await probe_lms(context))
    return Screen(text, build_main_menu())


async def fetch_models(context) -> list[ModelEntry] | None:
    """Downloaded models flagged with their loaded state; ``None`` when LM Studio is down."""
    config = context.bot_data["config"]
    try:
        models, handles = await asyncio.wait_for(
            asyncio.gather(
                sdk.list_downloaded_models(config.LMS_HOST, config.LMS_PORT),
                sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT),
            ),
            LMS_PROBE_TIMEOUT * 2,
        )
    except Exception:
        context.chat_data["models_cache"] = None
        return None
    loaded = {getattr(h, "identifier", None) for h in handles}
    entries = []
    for model in models:
        key = str(getattr(model, "model_key", "unknown"))
        size = getattr(getattr(model, "info", None), "size_bytes", 0) or 0
        entries.append(ModelEntry(key=key, size_bytes=int(size), loaded=key in loaded))
    context.chat_data["models_cache"] = entries
    return entries


def _bound_model(context) -> str | None:
    session = _active_session(context)
    return session.model_identifier if session is not None else None


async def _models(context) -> Screen:
    entries = await fetch_models(context)
    if entries is None:
        text, markup = build_models_unreachable()
        return Screen(text, markup)
    if not entries:
        return Screen(
            "📦 <b>Models</b>\n<i>No models found in LM Studio.</i>",
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data=SCREEN_MAIN)]]),
        )
    bound = _bound_model(context)
    markup, page, pages = build_models_keyboard(
        entries, context.chat_data.get("models_page", 0), bound
    )
    context.chat_data["models_page"] = page
    return Screen(render_models_text(entries, bound, page, pages), markup)


async def _model_card(context) -> Screen:
    key = context.chat_data.get("model_card_key")
    entries = await fetch_models(context)
    entry = next((e for e in entries or [] if e.key == key), None)
    if entry is None:
        return await _models(context)
    bound = _bound_model(context)
    text = render_model_card(entry, bound, context.chat_data.get("staged_model_settings"))
    markup = build_model_card_keyboard(entry, bound, _active_session(context) is not None)
    return Screen(text, markup)


async def _sessions(context) -> Screen:
    store = context.bot_data["store"]
    session = store.get_active_session()
    lines = ["🧠 <b>Chat Sessions</b>", f"🗂 {len(store.list_sessions())} chat(s)"]
    if session is not None:
        lines.append(f"💬 Active: <b>{html.escape(session.name, quote=False)}</b>")
    return Screen("\n".join(lines), build_sessions_menu())


async def _chats(context) -> Screen:
    store = context.bot_data["store"]
    sessions = store.list_sessions()
    footer = [
        InlineKeyboardButton("➕ New Chat", callback_data="sessions:new"),
        InlineKeyboardButton("⬅ Back", callback_data=SCREEN_MAIN),
    ]
    if not sessions:
        text = "🗂 <b>Chats</b>\nNo chats yet — use ➕ New Chat"
        return Screen(text, InlineKeyboardMarkup([footer]))
    shown, page, pages = paginate(sessions, context.chat_data.get("chats_page", 0))
    context.chat_data["chats_page"] = page
    active_id = store.store.active_session_id
    rows = [
        [InlineKeyboardButton(
            chat_row_label(s, len(store.load_history(s.id)), s.id == active_id),
            callback_data=f"sessions:card:{s.id}",
        )]
        for s in shown
    ]
    navigation = nav_row("sessions:page:card:", page, pages)
    if navigation:
        rows.append(navigation)
    rows.append(footer)
    return Screen("🗂 <b>Select a chat:</b>", InlineKeyboardMarkup(rows))


async def _chat_card(context) -> Screen:
    store = context.bot_data["store"]
    session = store.store.sessions.get(context.chat_data.get("chat_card_id"))
    if session is None:
        return await _chats(context)
    active = session.id == store.store.active_session_id
    text = render_chat_card(session, len(store.load_history(session.id)), active)
    return Screen(text, build_chat_card_keyboard(session.id, active))


async def _settings(context) -> Screen:
    return Screen("⚙️ <b>Settings</b>", build_settings_menu())


async def _help(context) -> Screen:
    return Screen("❓ <b>Help</b>", build_help_menu())


async def _status(context) -> Screen:
    return Screen(await build_status_text(context), build_back_button(SCREEN_MAIN))


async def _model_settings(context) -> Screen:
    return Screen("🖥 <b>Model Settings</b>", build_model_settings_menu())


async def _session_settings(context) -> Screen:
    session = _active_session(context)
    settings = session.settings if session is not None else None
    return Screen("💬 <b>Session Settings</b>", build_session_settings_menu(settings))


async def _history_policy(context) -> Screen:
    session = _active_session(context)
    current = session.settings.history_policy.mode if session is not None else "—"
    text = f"📜 <b>History Reuse Policy</b>\nCurrent: {_code(current)}"
    return Screen(text, build_history_policy_menu())


async def _current_settings(context) -> Screen:
    session = _active_session(context)
    if session is None:
        empty = "📋 <b>Current Settings</b>\n<i>No active chat.</i>"
        return Screen(empty, build_back_button(SCREEN_SETTINGS))
    text = render_current_settings(session, session.model_identifier)
    return Screen(text, build_back_button(SCREEN_SETTINGS))


SCREENS: dict[str, Callable[..., Awaitable[Screen]]] = {
    SCREEN_MAIN: _main,
    SCREEN_MODELS: _models,
    SCREEN_MODEL_CARD: _model_card,
    SCREEN_SESSIONS: _sessions,
    SCREEN_CHATS: _chats,
    SCREEN_CHAT_CARD: _chat_card,
    SCREEN_SETTINGS: _settings,
    SCREEN_HELP: _help,
    SCREEN_STATUS: _status,
    SCREEN_MODEL_SETTINGS: _model_settings,
    SCREEN_SESSION_SETTINGS: _session_settings,
    SCREEN_HISTORY_POLICY: _history_policy,
    SCREEN_CURRENT_SETTINGS: _current_settings,
}


async def render_screen(context, key: str, banner: str | None = None) -> Screen | None:
    """Render screen *key* from current state, or ``None`` for an unknown key."""
    renderer = SCREENS.get(key)
    if renderer is None:
        return None
    screen = await renderer(context)
    if banner:
        screen = Screen(with_banner(screen.text, banner), screen.markup, screen.parse_mode)
    return screen


async def show_screen(query, context, key: str, banner: str | None = None) -> None:
    """Edit the menu message to show screen *key*, recovering from a stale message."""
    screen = await render_screen(context, key, banner)
    if screen is None:
        logger.warning("Unknown screen: %s", key)
        return
    context.chat_data["menu_screen"] = key
    try:
        await query.edit_message_text(
            text=screen.text, reply_markup=screen.markup, parse_mode=screen.parse_mode
        )
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.info("Stale menu detected, sending fresh menu: %s", e)
        await query.answer("Menu expired — opening a fresh menu.")
        context.chat_data["menu_message_id"] = None
        main = await render_screen(context, SCREEN_MAIN, banner)
        msg = await query.message.chat.send_message(
            text=main.text, reply_markup=main.markup, parse_mode=main.parse_mode
        )
        context.chat_data["menu_message_id"] = msg.message_id
        context.chat_data["menu_screen"] = SCREEN_MAIN


async def refresh_screen(context, chat_id, message_id, key: str, banner: str | None = None) -> None:
    """Re-render screen *key* into an existing menu message (best effort)."""
    screen = await render_screen(context, key, banner)
    if screen is None:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=screen.text,
            reply_markup=screen.markup,
            parse_mode=screen.parse_mode,
        )
        context.chat_data["menu_screen"] = key
    except BadRequest as e:
        logger.debug("Could not refresh menu screen %s: %s", key, e)
