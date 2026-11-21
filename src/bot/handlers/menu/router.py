"""Menu navigation: ``/menu`` command, callback routing and per-section action handlers."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral
from src.bot.handlers.menu.keyboards import (
    build_back_button,
    build_help_menu,
    build_delete_confirmation_keyboard,
    build_help_models,
    build_help_sessions,
    build_help_settings,
    build_history_policy_menu,
    build_main_menu,
    build_model_settings_menu,
    build_models_menu,
    build_session_settings_menu,
    build_sessions_list_keyboard,
    build_sessions_menu,
    build_settings_menu,
    render_current_settings,
    render_delete_confirmation,
    render_main_menu_text,
)
from src.bot.handlers.menu.pending import CB_INPUT_CANCEL, request_input
from src.bot.handlers.models import (
    _format_downloaded_list,
    _format_loaded_list,
    _send_load_keyboard,
    _send_unload_keyboard,
    perform_load,
    perform_unload,
)
from src.bot.services import inference
from src.bot.services.generation import get_generations
from src.lms import sdk
from src.lms.cli import LmsCliError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section display helper
# ---------------------------------------------------------------------------

SECTION_BUILDERS = {
    "menu:models": ("📦 Model Management", build_models_menu),
    "menu:sessions": ("🧠 Chat Sessions", build_sessions_menu),
    "menu:settings": ("⚙️ Settings", build_settings_menu),
    "menu:help": ("❓ Help", build_help_menu),
}


async def _show_section(query, context: ContextTypes.DEFAULT_TYPE, section: str) -> None:
    """Edit the menu message to show *section*, with stale-message recovery."""
    parse_mode = None
    if section == "menu:main":
        text = render_main_menu_text(context.bot_data["store"])
        keyboard, parse_mode = build_main_menu(), "HTML"
    elif section in SECTION_BUILDERS:
        text, builder = SECTION_BUILDERS[section]
        keyboard = builder()
    else:
        logger.warning("Unknown section: %s", section)
        return

    try:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode=parse_mode)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.info("Stale menu detected, sending fresh menu: %s", e)
        await query.answer("Menu expired — opening a fresh menu.")
        context.chat_data["menu_message_id"] = None
        msg = await query.message.chat.send_message(
            text=render_main_menu_text(context.bot_data["store"]),
            reply_markup=build_main_menu(),
            parse_mode="HTML",
        )
        context.chat_data["menu_message_id"] = msg.message_id


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

@require_owner
async def menu_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/menu`` and ``/start`` — show or refresh the persistent menu."""
    context.chat_data["pending_input"] = None
    logger.info("Menu opened (pending_input cleared)")

    menu_msg_id = context.chat_data.get("menu_message_id")
    if menu_msg_id is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=menu_msg_id,
                text=render_main_menu_text(context.bot_data["store"]),
                reply_markup=build_main_menu(),
                parse_mode="HTML",
            )
            return
        except BadRequest:
            logger.info("Previous menu message stale, sending new one")

    msg = await update.effective_message.reply_text(
        render_main_menu_text(context.bot_data["store"]),
        reply_markup=build_main_menu(),
        parse_mode="HTML",
    )
    context.chat_data["menu_message_id"] = msg.message_id


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------

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

    # Navigation
    if data in ("menu:main", "menu:models", "menu:sessions",
                "menu:settings", "menu:help"):
        await _show_section(query, context, data)
        return

    if data == CB_INPUT_CANCEL:
        context.chat_data["pending_input"] = None
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

    if data == inference.CB_REGENERATE:
        await _execute_inference_regenerate(query, context)
        return

    # Top-level regenerate
    if data == "menu:regenerate":
        await _execute_inference_regenerate(query, context)
        return

    # Help topics
    if data.startswith("menu:help:"):
        await _handle_help_section(query, context, data)
        return

    if data.startswith("models:loadmodel:"):
        await _handle_load_model_callback(query, context, data)
        return

    if data.startswith("models:unloadmodel:"):
        await _handle_unload_model_callback(query, context, data)
        return

    # Model actions
    if data.startswith("models:"):
        await _handle_models_action(query, context, data)
        return

    # Session actions
    if data.startswith("sessions:"):
        await _handle_sessions_action(query, context, data)
        return

    # Settings actions
    if data.startswith("settings:"):
        await _handle_settings_action(query, context, data)
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

    if data == "models:load":
        await _send_load_keyboard(query.message, context)
        logger.info("Load keyboard opened via menu")
        return

    if data == "models:unload":
        await _send_unload_keyboard(query.message, context)
        logger.info("Unload keyboard opened via menu")
        return


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

async def _handle_sessions_action(query, context, data: str) -> None:
    store = context.bot_data["store"]

    if data == "sessions:new":
        await request_input(
            query.message, context, "sessions:new",
            "Enter a name for the new chat (or send empty for auto-name):",
        )
        return

    if data == "sessions:list":
        sessions = store.list_sessions()
        if not sessions:
            try:
                await query.edit_message_text(
                    text="No chats yet — use ➕ New Chat",
                    reply_markup=build_sessions_menu(),
                )
            except BadRequest:
                pass
            return
        keyboard = build_sessions_list_keyboard(sessions, "switch")
        try:
            await query.edit_message_text(text="🗂 Select a chat:", reply_markup=keyboard)
        except BadRequest:
            pass
        return

    if data == "sessions:remove":
        sessions = store.list_sessions()
        if not sessions:
            try:
                await query.edit_message_text(
                    text="No chats to remove.",
                    reply_markup=build_sessions_menu(),
                )
            except BadRequest:
                pass
            return
        keyboard = build_sessions_list_keyboard(sessions, "remove_ask")
        try:
            await query.edit_message_text(
                text="🗑 Select a chat to remove:", reply_markup=keyboard
            )
        except BadRequest:
            pass
        return

    if data.startswith("sessions:switch:"):
        session_id = data[len("sessions:switch:"):]
        result = store.switch_session(session_id)
        if result:
            await reply_ephemeral(query.message, f"✅ Switched to chat: {result.name}")
        else:
            await reply_ephemeral(query.message, "❌ Chat not found.")
        logger.info("Session switch via menu: %s", session_id)
        try:
            await query.edit_message_text(
                text="🧠 Chat Sessions", reply_markup=build_sessions_menu()
            )
        except BadRequest:
            pass
        return

    if data.startswith("sessions:remove_ask:"):
        session_id = data[len("sessions:remove_ask:"):]
        session = store.store.sessions.get(session_id)
        if session is None:
            await reply_ephemeral(query.message, "❌ Chat not found.")
            return
        count = len(store.load_history(session_id))
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
        deleted = store.delete_session(session_id)
        if deleted:
            await reply_ephemeral(query.message, "✅ Chat removed.")
        else:
            await reply_ephemeral(query.message, "❌ Chat not found.")
        logger.info("Session removed via menu: %s", session_id)
        try:
            await query.edit_message_text(
                text="🧠 Chat Sessions", reply_markup=build_sessions_menu()
            )
        except BadRequest:
            pass
        return


# ---------------------------------------------------------------------------
# Settings actions handler (split scope + presets + history policy)
# ---------------------------------------------------------------------------

async def _handle_settings_action(query, context, data: str) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()

    if session is None:
        await reply_ephemeral(
            query.message,
            "❌ No active chat. Create one in Chat Sessions first."
        )
        return

    # --- Current Settings ---
    if data == "settings:current":
        model_id = session.model_identifier
        text = render_current_settings(session, model_id)
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=build_back_button("menu:settings"),
                parse_mode="HTML",
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                logger.error("Could not show current settings: %s", e)
        return

    # --- Scope sub-menus ---
    if data == "settings:model_menu":
        try:
            await query.edit_message_text(
                text="🖥 Model Settings",
                reply_markup=build_model_settings_menu(),
            )
        except BadRequest:
            pass
        return

    if data == "settings:session_menu":
        try:
            await query.edit_message_text(
                text="💬 Session Settings",
                reply_markup=build_session_settings_menu(),
            )
        except BadRequest:
            pass
        return

    # --- History Policy ---
    if data == "settings:history_policy":
        try:
            current = session.settings.history_policy.mode
            await query.edit_message_text(
                text=f"📜 History Reuse Policy\nCurrent: <code>{current}</code>",
                reply_markup=build_history_policy_menu(),
                parse_mode="HTML",
            )
        except BadRequest:
            pass
        return

    if data.startswith("settings:history_policy:"):
        mode = data[len("settings:history_policy:"):]
        if mode == "last_n_pairs":
            await request_input(
                query.message, context, "settings:history_policy:last_n_pairs",
                "Enter the number of message pairs to keep:",
            )
            return
        from src.storage.models import HistoryReusePolicy
        session.settings.history_policy = HistoryReusePolicy(mode=mode)
        store.update_session(session)
        await reply_ephemeral(query.message, f"✅ History policy set to {mode}")
        return

    # --- Model Presets ---
    if data == "settings:model_presets":
        presets = store.load_model_presets()
        if not presets.presets:
            await reply_ephemeral(query.message, "No model presets found.")
            return
        rows = []
        for i, p in enumerate(presets.presets):
            label = p.name
            if p.description:
                label = f"{p.name} — {p.description[:30]}"
            rows.append([InlineKeyboardButton(
                label,
                callback_data=f"settings:apply_model_preset:{i}",
            )])
        rows.append([InlineKeyboardButton(
            "⬅ Back", callback_data="menu:settings",
        )])
        try:
            await query.edit_message_text(
                text="📦 Model Presets",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        except BadRequest:
            pass
        return

    if data.startswith("settings:apply_model_preset:"):
        idx = int(data[len("settings:apply_model_preset:"):])
        presets = store.load_model_presets()
        if idx < 0 or idx >= len(presets.presets):
            await reply_ephemeral(query.message, "❌ Invalid preset.")
            return
        preset = presets.presets[idx]
        # Model presets are informational — store the values for the next /load
        context.chat_data["staged_model_settings"] = preset.settings.model_dump()
        await reply_ephemeral(
            query.message,
            f"✅ Model preset '{preset.name}' staged. Values will apply on the next model load."
        )
        return

    # --- Session Presets ---
    if data == "settings:session_presets":
        presets = store.load_session_presets()
        if not presets.presets:
            await reply_ephemeral(query.message, "No session presets found.")
            return
        rows = []
        for i, p in enumerate(presets.presets):
            label = p.name
            if p.description:
                label = f"{p.name} — {p.description[:30]}"
            rows.append([InlineKeyboardButton(
                label,
                callback_data=f"settings:apply_session_preset:{i}",
            )])
        rows.append([InlineKeyboardButton(
            "⬅ Back", callback_data="menu:settings",
        )])
        try:
            await query.edit_message_text(
                text="💾 Session Presets",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        except BadRequest:
            pass
        return

    if data.startswith("settings:apply_session_preset:"):
        idx = int(data[len("settings:apply_session_preset:"):])
        presets = store.load_session_presets()
        if idx < 0 or idx >= len(presets.presets):
            await reply_ephemeral(query.message, "❌ Invalid preset.")
            return
        preset = presets.presets[idx]
        # Apply session preset values to current session
        preset_data = preset.settings.model_dump()
        for key, value in preset_data.items():
            setattr(session.settings, key, value)
        store.update_session(session)
        await reply_ephemeral(query.message, f"✅ Session preset '{preset.name}' applied.")
        return

    # --- Model-scoped setting prompts ---
    model_setting_prompts = {
        "settings:model:gpu": "Enter GPU setting (auto, max, or 0.0–1.0):",
        "settings:model:context_length": "Enter context length (integer ≥ 512):",
        "settings:model:identifier": "Enter model identifier:",
    }
    if data in model_setting_prompts:
        await request_input(query.message, context, data, model_setting_prompts[data])
        return

    # --- Session-scoped setting prompts ---
    session_setting_prompts = {
        "settings:session:prompt": "Enter the system prompt (or send empty to clear):",
        "settings:session:temperature": "Enter temperature (0.0–2.0):",
        "settings:session:max_tokens": "Enter max tokens (integer ≥ -1, use -1 for unlimited):",
        "settings:session:top_p": "Enter top-p (0.0–1.0):",
        "settings:session:top_k": "Enter top-k (integer ≥ 1, or 'none' to clear):",
        "settings:session:repeat_penalty": "Enter repeat penalty (> 0, or 'none' to clear):",
        "settings:session:stop_strings": (
            "Enter stop strings (comma-separated, or 'none' to clear):"
        ),
        "settings:session:seed": "Enter seed (integer ≥ 0, or 'none' for random):",
    }
    if data in session_setting_prompts:
        await request_input(query.message, context, data, session_setting_prompts[data])
        return

    # Legacy compat — old settings: keys
    legacy_prompts = {
        "settings:prompt": "Enter the system prompt (or send empty to clear):",
        "settings:temperature": "Enter temperature (0.0–2.0):",
        "settings:max_tokens": "Enter max tokens (integer ≥ -1, use -1 for unlimited):",
        "settings:top_p": "Enter top-p (0.0–1.0):",
    }
    if data in legacy_prompts:
        await request_input(query.message, context, data, legacy_prompts[data])
        return


async def _execute_inference_regenerate(query, context) -> None:
    await inference.run_regenerate(query.message, context)
