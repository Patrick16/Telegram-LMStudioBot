"""Menu navigation: ``/menu`` command, callback routing and per-section action handlers."""

import asyncio
import logging

from telegram import Update
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
from src.bot.handlers.menu.params import CREATIVITY_MODES, history_policy_title
from src.bot.handlers.menu.pending import CB_INPUT_CANCEL, request_input
from src.bot.handlers.menu.screens import (
    SCREEN_CURRENT_SETTINGS,
    SCREEN_HELP,
    SCREEN_HISTORY_POLICY,
    SCREEN_CHAT_CARD,
    SCREEN_CHATS,
    SCREEN_MAIN,
    SCREEN_MODEL_CARD,
    SCREEN_MODEL_PRESETS,
    SCREEN_PARAM,
    SCREEN_PRESET_CARD,
    SCREEN_MODEL_SETTINGS,
    SCREEN_MODELS,
    SCREEN_SESSION_PRESETS,
    SCREEN_SESSION_SETTINGS,
    SCREEN_SESSIONS,
    SCREEN_SETTINGS,
    SCREEN_STATUS,
    render_screen,
    show_screen,
)
from src.bot.pagination import NOOP
from src.bot.handlers.models import (
    _build_load_keyboard,
    _load_prompt,
    perform_load,
    perform_unload,
)
from src.bot.services import inference
from src.bot.handlers.settings_spec import SETTING_SPECS, confirmation_for, step_value
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

    if data == inference.CB_CONTINUE:
        await inference.run_text_turn(query.message, context, inference.CONTINUE_PROMPT)
        return

    if data == inference.CB_NEW_CHAT:
        store = context.bot_data["store"]
        session = store.create_session(f"Chat {len(store.list_sessions()) + 1}")
        await reply_ephemeral(query.message, f"✅ New chat started: {session.name}")
        return

    if data == inference.CB_MENU:
        screen = await render_screen(context, SCREEN_MAIN)
        msg = await query.message.reply_text(
            screen.text, reply_markup=screen.markup, parse_mode=screen.parse_mode
        )
        context.chat_data["menu_message_id"] = msg.message_id
        context.chat_data["menu_screen"] = SCREEN_MAIN
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
    # Legacy entry points (error buttons, old menus) all lead to the unified screen.
    if data in ("models:list", "models:loaded", "models:load", "models:unload"):
        context.chat_data["models_page"] = 0
        await show_screen(query, context, SCREEN_MODELS)
        return

    if data.startswith("models:page:"):
        context.chat_data["models_page"] = int(data[len("models:page:"):])
        await show_screen(query, context, SCREEN_MODELS)
        return

    if data.startswith("models:loadpage:"):  # paginated /load keyboard
        await _show_load_page(query, context, int(data[len("models:loadpage:"):]))
        return

    if data.startswith("models:card:"):
        cache = context.chat_data.get("models_cache") or []
        index = int(data[len("models:card:"):])
        if not 0 <= index < len(cache):
            await show_screen(
                query, context, SCREEN_MODELS, banner="⚠️ The model list changed — pick again."
            )
            return
        context.chat_data["model_card_key"] = cache[index].key
        await show_screen(query, context, SCREEN_MODEL_CARD)
        return

    if data.startswith("models:do:"):
        await _model_card_action(query, context, data[len("models:do:"):])
        return

    logger.warning("Unrecognised models callback: %s", data)


async def _model_card_action(query, context, action: str) -> None:
    """Load / unload / bind the model shown on the model card."""
    key = context.chat_data.get("model_card_key")
    if not key:
        await show_screen(query, context, SCREEN_MODELS)
        return

    if action == "bind":
        store = context.bot_data["store"]
        session = store.get_active_session()
        if session is None:
            banner = "❌ No active chat. Create one first."
        else:
            session.model_identifier = key
            store.update_session(session)
            banner = f"✅ This chat now uses {key}"
        await show_screen(query, context, SCREEN_MODEL_CARD, banner=banner)
        return

    if action not in ("load", "unload"):
        logger.warning("Unknown model card action: %s", action)
        return

    verb = "Loading" if action == "load" else "Unloading"
    try:
        await query.edit_message_text(f"⏳ {verb} {key}…")
    except BadRequest:
        pass
    try:
        if action == "load":
            await perform_load(context, key)
            banner = f"✅ Loaded {key} — this chat now uses it."
        else:
            await perform_unload(context, key)
            banner = f"✅ Unloaded {key}."
    except LmsCliError as e:
        banner = f"❌ {verb} failed: {e}"
    await show_screen(query, context, SCREEN_MODEL_CARD, banner=banner)


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
        context.chat_data["chats_page"] = 0
        await show_screen(query, context, SCREEN_CHATS)
        return

    if data.startswith("sessions:card:"):
        context.chat_data["chat_card_id"] = data[len("sessions:card:"):]
        await show_screen(query, context, SCREEN_CHAT_CARD)
        return

    if data == "sessions:remove":
        if not store.list_sessions():
            await show_screen(query, context, SCREEN_SESSIONS, banner="No chats to remove.")
            return
        await _show_sessions_page(query, context, "remove_ask", 0)
        return

    if data.startswith("sessions:page:"):
        _, _, action, page = data.split(":")
        if action == "card":
            context.chat_data["chats_page"] = int(page)
            await show_screen(query, context, SCREEN_CHATS)
            return
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

    if data.startswith("sessions:rename:"):
        session_id = data[len("sessions:rename:"):]
        if session_id not in store.store.sessions:
            await show_screen(query, context, SCREEN_CHATS, banner="❌ Chat not found.")
            return
        await request_input(query.message, context, data, "Enter a new name for this chat:")
        return

    if data.startswith("sessions:switch:"):
        session_id = data[len("sessions:switch:"):]
        result = store.switch_session(session_id)
        banner = f"✅ Switched to chat: {result.name}" if result else "❌ Chat not found."
        logger.info("Session switch via menu: %s", session_id)
        await show_screen(query, context, SCREEN_MAIN, banner=banner)
        return

    if data.startswith(("sessions:remove_ask:", "sessions:del_card:")):
        from_card = data.startswith("sessions:del_card:")
        session_id = data.split(":", 2)[2]
        context.chat_data["delete_from_card"] = from_card
        session = store.store.sessions.get(session_id)
        if session is None:
            await show_screen(query, context, SCREEN_SESSIONS, banner="❌ Chat not found.")
            return
        count = len(store.load_history(session_id))
        context.chat_data["menu_screen"] = None
        try:
            await query.edit_message_text(
                text=render_delete_confirmation(session, count),
                reply_markup=build_delete_confirmation_keyboard(
                    session_id, cancel=f"sessions:card:{session_id}" if from_card else None
                ),
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return

    if data.startswith("sessions:confirm_remove:"):
        session_id = data[len("sessions:confirm_remove:"):]
        banner = "✅ Chat removed." if store.delete_session(session_id) else "❌ Chat not found."
        logger.info("Session removed via menu: %s", session_id)
        from_card = context.chat_data.pop("delete_from_card", False)
        target = SCREEN_CHATS if from_card else SCREEN_SESSIONS
        await show_screen(query, context, target, banner=banner)
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


async def _handle_param_action(query, context, session, action: str) -> None:
    """Buttons on a parameter screen: quick pick, +/-, enter a value, back to default."""
    store = context.bot_data["store"]
    spec = SETTING_SPECS.get(context.chat_data.get("param_key"))
    if spec is None:
        await show_screen(query, context, SCREEN_SESSION_SETTINGS)
        return

    if action == "input":
        key = context.chat_data["param_key"]
        await request_input(query.message, context, f"settings:session:{key}", spec.prompt)
        return

    current = getattr(session.settings, spec.attr)
    if action.startswith("pick:"):
        index = int(action[len("pick:"):])
        if not 0 <= index < len(spec.choices):
            await show_screen(query, context, SCREEN_PARAM)
            return
        value = spec.choices[index][1]
        message = confirmation_for(spec, value)
    elif action.startswith("step:"):
        try:
            value = step_value(spec, current, int(action[len("step:"):]))
        except ValueError:
            await show_screen(query, context, SCREEN_PARAM, banner="⚠️ Already at the limit.")
            return
        message = spec.on_set(value)
    elif action == "reset":
        value = getattr(SessionGenerationSettings(), spec.attr)
        message = f"✅ {spec.title} reset to default."
    else:
        logger.warning("Unknown parameter action: %s", action)
        return

    setattr(session.settings, spec.attr, value)
    store.update_session(session)
    await show_screen(query, context, SCREEN_PARAM, banner=message)


async def _handle_preset_action(query, context, session, data: str) -> bool:
    """Preset list / preview / apply / delete / save. Returns False if *data* is not ours."""
    store = context.bot_data["store"]

    if data == "settings:model_presets":
        if not store.load_model_presets().presets:
            await show_screen(query, context, SCREEN_SETTINGS, banner="No model presets found.")
        else:
            await show_screen(query, context, SCREEN_MODEL_PRESETS)
        return True

    if data == "settings:session_presets":
        await show_screen(query, context, SCREEN_SESSION_PRESETS)
        return True

    if data.startswith("settings:preset:"):
        _, _, kind, index = data.split(":")
        context.chat_data["preset_card"] = (kind, int(index))
        await show_screen(query, context, SCREEN_PRESET_CARD)
        return True

    if data.startswith("settings:apply_model_preset:"):
        index = int(data[len("settings:apply_model_preset:"):])
        presets = store.load_model_presets().presets
        if not 0 <= index < len(presets):
            await show_screen(query, context, SCREEN_SETTINGS, banner="❌ Invalid preset.")
            return True
        preset = presets[index]
        # Model presets are informational — stage the values for the next load.
        context.chat_data["staged_model_settings"] = preset.settings.model_dump()
        await show_screen(
            query, context, SCREEN_SETTINGS,
            banner=f"✅ Model preset '{preset.name}' staged. Applies on the next model load.",
        )
        return True

    if data.startswith("settings:apply_session_preset:"):
        index = int(data[len("settings:apply_session_preset:"):])
        presets = store.load_session_presets().presets
        if not 0 <= index < len(presets):
            await show_screen(query, context, SCREEN_SETTINGS, banner="❌ Invalid preset.")
            return True
        preset = presets[index]
        session.settings = preset.settings.model_copy(deep=True)
        store.update_session(session)
        await show_screen(
            query, context, SCREEN_SESSION_SETTINGS,
            banner=f"✅ Session preset '{preset.name}' applied.",
        )
        return True

    if data.startswith("settings:del_session_preset:"):
        index = int(data[len("settings:del_session_preset:"):])
        banner = "✅ Preset deleted." if store.delete_session_preset(index) else "❌ Invalid preset."
        await show_screen(query, context, SCREEN_SESSION_PRESETS, banner=banner)
        return True

    if data == "settings:save_session_preset":
        await request_input(
            query.message, context, "settings:save_preset",
            "Enter a name for the preset (it saves this chat's current settings):",
        )
        return True

    return False


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

    # --- Parameter screens ---
    if data.startswith("settings:param:"):
        await _handle_param_action(query, context, session, data[len("settings:param:"):])
        return

    # --- Creativity modes ---
    if data.startswith("settings:mode:"):
        title, values = CREATIVITY_MODES.get(data[len("settings:mode:"):], (None, None))
        if values is None:
            logger.warning("Unknown creativity mode: %s", data)
            return
        for attr, value in values.items():
            setattr(session.settings, attr, value)
        store.update_session(session)
        await show_screen(query, context, SCREEN_SESSION_SETTINGS, banner=f"✅ Mode: {title}")
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
            query, context, SCREEN_HISTORY_POLICY,
            banner=f"✅ History: {history_policy_title(mode)}",
        )
        return

    # --- Presets ---
    if await _handle_preset_action(query, context, session, data):
        return

    # --- Model-scoped value prompts ---
    if data in _MODEL_SETTING_PROMPTS:
        await request_input(query.message, context, data, _MODEL_SETTING_PROMPTS[data])
        return

    # --- Session toggles / reset / per-setting screens ---
    if data.startswith("settings:session:"):
        key = data[len("settings:session:"):]
        if key == "toggle_reasoning":
            session.settings.show_reasoning = not session.settings.show_reasoning
            store.update_session(session)
            await show_screen(query, context, SCREEN_SESSION_SETTINGS)
            return
        if key == "reset":
            defaults = SessionGenerationSettings()
            for attr in _RESETTABLE_SETTINGS:
                setattr(session.settings, attr, getattr(defaults, attr))
            store.update_session(session)
            await show_screen(
                query, context, SCREEN_SESSION_SETTINGS,
                banner="✅ Generation settings reset to defaults.",
            )
            return
        if key in SETTING_SPECS:
            context.chat_data["param_key"] = key
            await show_screen(query, context, SCREEN_PARAM)
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
