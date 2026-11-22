"""Menu navigation: ``/menu`` command, callback routing and per-section action handlers."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral
from src.bot.handlers.menu.keyboards import (
    build_delete_confirmation_keyboard,
    build_help_models,
    build_help_sessions,
    build_help_settings,
    build_sessions_list_keyboard,
    render_delete_confirmation,
)
from src.bot.handlers.menu.pending import CB_INPUT_CANCEL, request_input
from src.bot.handlers.menu.screens import (
    SCREEN_CURRENT_SETTINGS,
    SCREEN_HELP,
    SCREEN_HISTORY_POLICY,
    SCREEN_MAIN,
    SCREEN_MODEL_SETTINGS,
    SCREEN_MODELS,
    SCREEN_SESSION_SETTINGS,
    SCREEN_SESSIONS,
    SCREEN_SETTINGS,
    SCREEN_STATUS,
    render_screen,
    show_screen,
)
from src.bot.pagination import NOOP
from src.bot.handlers.models import (
    _format_downloaded_list,
    _build_load_keyboard,
    _format_loaded_list,
    _load_prompt,
    _send_load_keyboard,
    _send_unload_keyboard,
    perform_load,
    perform_unload,
)
from src.bot.services import inference
from src.storage.models import HistoryReusePolicy, SessionGenerationSettings
from src.bot.services.generation import get_generations
from src.lms import sdk
from src.lms.cli import LmsCliError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

@require_owner
async def menu_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/menu`` and ``/start`` — show or refresh the persistent menu."""
    context.chat_data["pending_input"] = None
    context.chat_data.pop("pending_return", None)
    logger.info("Menu opened (pending_input cleared)")

    screen = await render_screen(context, SCREEN_MAIN)
    menu_msg_id = context.chat_data.get("menu_message_id")
    if menu_msg_id is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=menu_msg_id,
                text=screen.text,
                reply_markup=screen.markup,
                parse_mode=screen.parse_mode,
            )
            context.chat_data["menu_screen"] = SCREEN_MAIN
            return
        except BadRequest:
            logger.info("Previous menu message stale, sending new one")

    msg = await update.effective_message.reply_text(
        screen.text, reply_markup=screen.markup, parse_mode=screen.parse_mode
    )
    context.chat_data["menu_message_id"] = msg.message_id
    context.chat_data["menu_screen"] = SCREEN_MAIN


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------

# Top-level ``menu:*`` keys that are plain screens (no side effects, no guards).
_NAV_SCREENS = frozenset({
    SCREEN_MAIN, SCREEN_MODELS, SCREEN_SESSIONS, SCREEN_SETTINGS, SCREEN_HELP, SCREEN_STATUS,
})


@require_owner
async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Single callback query handler for all inline menu buttons."""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        logger.debug("Could not answer callback query (likely expired): %s", e)
    data = query.data
    logger.debug("Callback received: %s", data)

    if data == NOOP:
        return

    if data in _NAV_SCREENS:
        await show_screen(query, context, data)
        return

    if data == CB_INPUT_CANCEL:
        context.chat_data["pending_input"] = None
        context.chat_data.pop("pending_return", None)
        try:
            await query.edit_message_text("❌ Cancelled.")
        except BadRequest:
            pass
        return

    # Buttons under a reply / the "thinking" placeholder
    if data == inference.CB_STOP:
        if not get_generations(context).stop(query.message.chat_id):
            await reply_ephemeral(query.message, "Nothing is being generated right now.")
        return

    if data == inference.CB_RETRY:
        await inference.run_retry(query.message, context)
        return

    if data in (inference.CB_REGENERATE, "menu:regenerate"):
        await inference.run_regenerate(query.message, context)
        return

    for prefix, handler in _PREFIX_HANDLERS:
        if data.startswith(prefix):
            await handler(query, context, data)
            return

    logger.warning("Unrecognised callback key: %s", data)


# ---------------------------------------------------------------------------
# Help section handler
# ---------------------------------------------------------------------------

HELP_TOPIC_BUILDERS = {
    "menu:help:models": build_help_models,
    "menu:help:sessions": build_help_sessions,
    "menu:help:settings": build_help_settings,
}


async def _handle_help_section(query, context, data: str) -> None:
    builder = HELP_TOPIC_BUILDERS.get(data)
    if builder is None:
        logger.warning("Unknown help topic: %s", data)
        return
    text, keyboard = builder()
    try:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.error("Failed to show help topic %s: %s", data, e)


# ---------------------------------------------------------------------------
# Model actions handler
# ---------------------------------------------------------------------------

async def _handle_models_action(query, context, data: str) -> None:
    if data == "models:list":
        config = context.bot_data["config"]
        try:
            models = await sdk.list_downloaded_models(config.LMS_HOST, config.LMS_PORT)
            await query.message.reply_text(
                _format_downloaded_list(models),
                parse_mode="HTML",
            )
        except Exception as e:
            await reply_ephemeral(query.message, f"❌ Could not list models: {e}")
        logger.info("Model list requested via menu")
        return

    if data == "models:loaded":
        config = context.bot_data["config"]
        try:
            handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
            await query.message.reply_text(
                _format_loaded_list(handles),
                parse_mode="HTML",
            )
        except Exception as e:
            await reply_ephemeral(query.message, f"❌ Could not list loaded models: {e}")
        logger.info("Loaded models requested via menu")
        return

    if data.startswith("models:loadpage:"):
        await _show_load_page(query, context, int(data[len("models:loadpage:"):]))
        return

    if data == "models:load":
        await _send_load_keyboard(query.message, context)
        logger.info("Load keyboard opened via menu")
        return

    if data == "models:unload":
        await _send_unload_keyboard(query.message, context)
        logger.info("Unload keyboard opened via menu")
        return


async def _show_load_page(query, context, page: int) -> None:
    config = context.bot_data["config"]
    try:
        models, handles = await asyncio.gather(
            sdk.list_downloaded_models(config.LMS_HOST, config.LMS_PORT),
            sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT),
        )
    except Exception:
        await reply_ephemeral(query.message, "❌ Could not connect to LM Studio. Is it running?")
        return
    loaded = {getattr(h, "identifier", None) for h in handles}
    try:
        await query.edit_message_text(
            _load_prompt(len(models), page),
            reply_markup=_build_load_keyboard(models, loaded, page),
        )
    except BadRequest:
        pass


async def _handle_load_model_callback(query, context, data: str) -> None:
    model_key = data[len("models:loadmodel:"):]
    try:
        await query.edit_message_text(f"⏳ Loading {model_key}…")
        await perform_load(context, model_key)
        await query.edit_message_text(f"✅ Loaded {model_key}.")
    except LmsCliError as e:
        await query.edit_message_text(f"❌ Failed to load {model_key}: {e}")


async def _handle_unload_model_callback(query, context, data: str) -> None:
    identifier = data[len("models:unloadmodel:"):]
    try:
        await query.edit_message_text(f"⏳ Unloading {identifier}…")
        await perform_unload(context, identifier)
        await query.edit_message_text(f"✅ Unloaded {identifier}.")
    except LmsCliError as e:
        await query.edit_message_text(f"❌ Failed to unload {identifier}: {e}")


# ---------------------------------------------------------------------------
# Sessions actions handler
# ---------------------------------------------------------------------------

# "Reset" restores sampling parameters; the system prompt, history policy and the
# reasoning toggle are deliberate choices and are kept.
_RESETTABLE_SETTINGS = (
    "temperature", "max_tokens", "top_p", "top_k", "repeat_penalty", "stop_strings", "seed",
)

_SESSIONS_PAGE_TITLES = {
    "switch": "🗂 Select a chat:",
    "remove_ask": "🗑 Select a chat to remove:",
}


async def _show_sessions_page(query, context, action: str, page: int) -> None:
    store = context.bot_data["store"]
    keyboard = build_sessions_list_keyboard(
        store.list_sessions(), action, page=page, active_id=store.store.active_session_id
    )
    context.chat_data["menu_screen"] = None  # dynamic screen: not in the registry
    try:
        await query.edit_message_text(
            text=_SESSIONS_PAGE_TITLES.get(action, "🗂 Select a chat:"), reply_markup=keyboard
        )
    except BadRequest:
        pass


async def _handle_sessions_action(query, context, data: str) -> None:
    store = context.bot_data["store"]

    if data == "sessions:new":
        await request_input(
            query.message, context, "sessions:new",
            "Enter a name for the new chat (or send empty for auto-name):",
        )
        return

    if data == "sessions:list":
        if not store.list_sessions():
            await show_screen(
                query, context, SCREEN_SESSIONS, banner="No chats yet — use ➕ New Chat"
            )
            return
        await _show_sessions_page(query, context, "switch", 0)
        return

    if data == "sessions:remove":
        if not store.list_sessions():
            await show_screen(query, context, SCREEN_SESSIONS, banner="No chats to remove.")
            return
        await _show_sessions_page(query, context, "remove_ask", 0)
        return

    if data.startswith("sessions:page:"):
        _, _, action, page = data.split(":")
        await _show_sessions_page(query, context, action, int(page))
        return

    if data == "sessions:rename":
        if store.get_active_session() is None:
            await show_screen(
                query, context, SCREEN_SESSIONS, banner="❌ No active chat. Create one first."
            )
            return
        await request_input(
            query.message, context, "sessions:rename", "Enter a new name for the current chat:"
        )
        return

    if data.startswith("sessions:switch:"):
        session_id = data[len("sessions:switch:"):]
        result = store.switch_session(session_id)
        banner = f"✅ Switched to chat: {result.name}" if result else "❌ Chat not found."
        logger.info("Session switch via menu: %s", session_id)
        await show_screen(query, context, SCREEN_MAIN, banner=banner)
        return

    if data.startswith("sessions:remove_ask:"):
        session_id = data[len("sessions:remove_ask:"):]
        session = store.store.sessions.get(session_id)
        if session is None:
            await show_screen(query, context, SCREEN_SESSIONS, banner="❌ Chat not found.")
            return
        count = len(store.load_history(session_id))
        context.chat_data["menu_screen"] = None
        try:
            await query.edit_message_text(
                text=render_delete_confirmation(session, count),
                reply_markup=build_delete_confirmation_keyboard(session_id),
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return

    if data.startswith("sessions:confirm_remove:"):
        session_id = data[len("sessions:confirm_remove:"):]
        banner = "✅ Chat removed." if store.delete_session(session_id) else "❌ Chat not found."
        logger.info("Session removed via menu: %s", session_id)
        await show_screen(query, context, SCREEN_SESSIONS, banner=banner)
        return


# ---------------------------------------------------------------------------
# Settings actions handler (split scope + presets + history policy)
# ---------------------------------------------------------------------------

_SETTINGS_SCREENS = frozenset({
    SCREEN_CURRENT_SETTINGS, SCREEN_MODEL_SETTINGS, SCREEN_SESSION_SETTINGS, SCREEN_HISTORY_POLICY,
})

_MODEL_SETTING_PROMPTS = {
    "settings:model:gpu": "Enter GPU setting (auto, max, or 0.0–1.0):",
    "settings:model:context_length": "Enter context length (integer ≥ 512):",
    "settings:model:identifier": "Enter model identifier:",
}

_SESSION_SETTING_PROMPTS = {
    "settings:session:prompt": "Enter the system prompt (or send empty to clear):",
    "settings:session:temperature": "Enter temperature (0.0–2.0):",
    "settings:session:max_tokens": "Enter max tokens (integer ≥ -1, use -1 for unlimited):",
    "settings:session:top_p": "Enter top-p (0.0–1.0):",
    "settings:session:top_k": "Enter top-k (integer ≥ 1, or 'none' to clear):",
    "settings:session:repeat_penalty": "Enter repeat penalty (> 0, or 'none' to clear):",
    "settings:session:stop_strings": "Enter stop strings (comma-separated, or 'none' to clear):",
    "settings:session:seed": "Enter seed (integer ≥ 0, or 'none' for random):",
}


async def _show_presets(query, context, kind: str, title: str, presets) -> None:
    """List presets of *kind* ("model" / "session") as buttons."""
    rows = []
    for i, p in enumerate(presets.presets):
        label = f"{p.name} — {p.description[:30]}" if p.description else p.name
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"settings:apply_{kind}_preset:{i}")]
        )
    rows.append([InlineKeyboardButton("⬅ Back", callback_data=SCREEN_SETTINGS)])
    context.chat_data["menu_screen"] = None
    try:
        await query.edit_message_text(text=title, reply_markup=InlineKeyboardMarkup(rows))
    except BadRequest:
        pass


async def _handle_settings_action(query, context, data: str) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()

    if session is None:
        await show_screen(
            query, context, SCREEN_SETTINGS,
            banner="❌ No active chat. Create one in Chats first.",
        )
        return

    # --- Plain screens ---
    if data in _SETTINGS_SCREENS:
        await show_screen(query, context, data)
        return

    # --- History Policy ---
    if data.startswith("settings:history_policy:"):
        mode = data[len("settings:history_policy:"):]
        if mode == "last_n_pairs":
            await request_input(
                query.message, context, "settings:history_policy:last_n_pairs",
                "Enter the number of message pairs to keep:",
            )
            return
        session.settings.history_policy = HistoryReusePolicy(mode=mode)
        store.update_session(session)
        await show_screen(
            query, context, SCREEN_HISTORY_POLICY, banner=f"✅ History policy set to {mode}"
        )
        return

    # --- Model Presets ---
    if data == "settings:model_presets":
        presets = store.load_model_presets()
        if not presets.presets:
            await show_screen(query, context, SCREEN_SETTINGS, banner="No model presets found.")
            return
        await _show_presets(query, context, "model", "📦 Model Presets", presets)
        return

    if data.startswith("settings:apply_model_preset:"):
        idx = int(data[len("settings:apply_model_preset:"):])
        presets = store.load_model_presets()
        if idx < 0 or idx >= len(presets.presets):
            await show_screen(query, context, SCREEN_SETTINGS, banner="❌ Invalid preset.")
            return
        preset = presets.presets[idx]
        # Model presets are informational — store the values for the next /load
        context.chat_data["staged_model_settings"] = preset.settings.model_dump()
        await show_screen(
            query, context, SCREEN_SETTINGS,
            banner=f"✅ Model preset '{preset.name}' staged. Applies on the next model load.",
        )
        return

    # --- Session Presets ---
    if data == "settings:session_presets":
        presets = store.load_session_presets()
        if not presets.presets:
            await show_screen(
                query, context, SCREEN_SETTINGS, banner="No session presets found."
            )
            return
        await _show_presets(query, context, "session", "💾 Session Presets", presets)
        return

    if data.startswith("settings:apply_session_preset:"):
        idx = int(data[len("settings:apply_session_preset:"):])
        presets = store.load_session_presets()
        if idx < 0 or idx >= len(presets.presets):
            await show_screen(query, context, SCREEN_SETTINGS, banner="❌ Invalid preset.")
            return
        preset = presets.presets[idx]
        for key, value in preset.settings.model_dump().items():
            setattr(session.settings, key, value)
        store.update_session(session)
        await show_screen(
            query, context, SCREEN_SESSION_SETTINGS,
            banner=f"✅ Session preset '{preset.name}' applied.",
        )
        return

    # --- Value prompts ---
    if data in _MODEL_SETTING_PROMPTS:
        await request_input(query.message, context, data, _MODEL_SETTING_PROMPTS[data])
        return

    if data in _SESSION_SETTING_PROMPTS:
        await request_input(query.message, context, data, _SESSION_SETTING_PROMPTS[data])
        return

    # --- Session toggles / reset ---
    if data == "settings:session:toggle_reasoning":
        session.settings.show_reasoning = not session.settings.show_reasoning
        store.update_session(session)
        await show_screen(query, context, SCREEN_SESSION_SETTINGS)
        return

    if data == "settings:session:reset":
        defaults = SessionGenerationSettings()
        for attr in _RESETTABLE_SETTINGS:
            setattr(session.settings, attr, getattr(defaults, attr))
        store.update_session(session)
        await show_screen(
            query, context, SCREEN_SESSION_SETTINGS,
            banner="✅ Generation settings reset to defaults.",
        )
        return

    logger.warning("Unrecognised settings callback: %s", data)


# Longest/most specific prefixes first.
_PREFIX_HANDLERS = (
    ("menu:help:", _handle_help_section),
    ("models:loadmodel:", _handle_load_model_callback),
    ("models:unloadmodel:", _handle_unload_model_callback),
    ("models:", _handle_models_action),
    ("sessions:", _handle_sessions_action),
    ("settings:", _handle_settings_action),
)
