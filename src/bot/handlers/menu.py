"""Inline button menu handler for LMStudioBot.

Provides keyboard builders, callback routing, and pending input handling
for the persistent inline menu navigation system.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral
from src.bot.formatting import format_response, split_message
from src.bot.handlers.models import (
    _format_downloaded_list,
    _format_loaded_list,
    _send_load_keyboard,
    _send_unload_keyboard,
)
from src.lms import cli, sdk
from src.lms.cli import LmsCliError
from src.storage.models import ChatMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Help text constants
# ---------------------------------------------------------------------------

HELP_MODELS = (
    "📦 *Model Management Help*\n\n"
    "• *List Models* — Shows all models available on disk in LM Studio.\n"
    "• *Loaded Models* — Shows models currently loaded into memory.\n"
    "• *Load Model* — Loads a model by its identifier (e.g. `qwen/qwen3-4b`).\n"
    "• *Unload Model* — Unloads a model by its identifier to free memory."
)

HELP_SESSIONS = (
    "🧠 *Sessions Help*\n\n"
    "• *New Chat* — Creates a new chat session (auto-named if no name given).\n"
    "• *List Chats* — Shows all sessions; tap one to switch to it.\n"
    "• *Remove Chat* — Shows all sessions; tap one to delete it."
)

HELP_SETTINGS = (
    "⚙️ *Settings Help*\n\n"
    "• *Current Settings* — View both model and session settings at a glance.\n"
    "• *Model Settings* — Adjust model-scoped runtime settings "
    "(GPU, context length, identifier).\n"
    "• *Session Settings* — Adjust session-scoped generation "
    "settings (temperature, max tokens, etc.).\n"
    "• *Model Presets* — Browse and apply saved model setting presets.\n"
    "• *Session Presets* — Browse and apply saved session setting presets.\n"
    "• *History Reuse Policy* — Control how chat history is assembled for inference."
)

# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


def build_main_menu() -> InlineKeyboardMarkup:
    """Build the top-level menu keyboard (no Inference section, Regenerate at top)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Model Management", callback_data="menu:models"),
            InlineKeyboardButton("🧠 Chat Sessions", callback_data="menu:sessions"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
            InlineKeyboardButton("🔄 Regenerate", callback_data="menu:regenerate"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="menu:help")],
    ])


def build_back_button(target: str) -> InlineKeyboardMarkup:
    """Build a single-row keyboard with a Back button pointing to *target*."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data=target)],
    ])


def build_models_menu() -> InlineKeyboardMarkup:
    """Model Management sub-menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 List Models", callback_data="models:list"),
            InlineKeyboardButton("🧠 Loaded Models", callback_data="models:loaded"),
        ],
        [
            InlineKeyboardButton("⬆ Load Model", callback_data="models:load"),
            InlineKeyboardButton("⬇ Unload Model", callback_data="models:unload"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_sessions_menu() -> InlineKeyboardMarkup:
    """Chat Sessions sub-menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ New Chat", callback_data="sessions:new"),
            InlineKeyboardButton("🗂 List Chats", callback_data="sessions:list"),
        ],
        [InlineKeyboardButton("🗑 Remove Chat", callback_data="sessions:remove")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_settings_menu() -> InlineKeyboardMarkup:
    """Settings sub-menu with split scopes, presets, and history policy."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Current Settings", callback_data="settings:current")],
        [
            InlineKeyboardButton("🖥 Model Settings", callback_data="settings:model_menu"),
            InlineKeyboardButton("💬 Session Settings", callback_data="settings:session_menu"),
        ],
        [
            InlineKeyboardButton("📦 Model Presets", callback_data="settings:model_presets"),
            InlineKeyboardButton("💾 Session Presets", callback_data="settings:session_presets"),
        ],
        [InlineKeyboardButton("📜 History Reuse Policy", callback_data="settings:history_policy")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_model_settings_menu() -> InlineKeyboardMarkup:
    """Model-scoped runtime settings menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖥 GPU", callback_data="settings:model:gpu"),
            InlineKeyboardButton("📏 Context Length", callback_data="settings:model:context_length"),
        ],
        [InlineKeyboardButton("🏷 Identifier", callback_data="settings:model:identifier")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:settings")],
    ])


def build_session_settings_menu() -> InlineKeyboardMarkup:
    """Session-scoped generation settings menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 System Prompt", callback_data="settings:session:prompt")],
        [
            InlineKeyboardButton("🌡 Temperature", callback_data="settings:session:temperature"),
            InlineKeyboardButton("🔢 Max Tokens", callback_data="settings:session:max_tokens"),
        ],
        [
            InlineKeyboardButton("📊 Top-P", callback_data="settings:session:top_p"),
            InlineKeyboardButton("🔝 Top-K", callback_data="settings:session:top_k"),
        ],
        [
            InlineKeyboardButton(
                "🔁 Repeat Penalty",
                callback_data="settings:session:repeat_penalty",
            ),
            InlineKeyboardButton(
                "🛑 Stop Strings",
                callback_data="settings:session:stop_strings",
            ),
        ],
        [InlineKeyboardButton("🎲 Seed", callback_data="settings:session:seed")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:settings")],
    ])


def build_history_policy_menu() -> InlineKeyboardMarkup:
    """History reuse policy selection menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Off", callback_data="settings:history_policy:off")],
        [InlineKeyboardButton(
            "📐 Fit Budget (Recent)",
            callback_data="settings:history_policy:fit_budget_recent",
        )],
        [InlineKeyboardButton(
            "🔢 Last N Pairs",
            callback_data="settings:history_policy:last_n_pairs",
        )],
        [InlineKeyboardButton(
            "📋 Full If Possible",
            callback_data="settings:history_policy:full_if_possible",
        )],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:settings")],
    ])


def build_help_menu() -> InlineKeyboardMarkup:
    """Help sub-menu with topic buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Model Help", callback_data="menu:help:models"),
            InlineKeyboardButton("🧠 Sessions Help", callback_data="menu:help:sessions"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings Help", callback_data="menu:help:settings"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_sessions_list_keyboard(sessions, action: str) -> InlineKeyboardMarkup:
    """Build dynamic keyboard with one button per session."""
    rows = []
    for s in sessions:
        cb = f"sessions:{action}:{s.id}"
        rows.append([InlineKeyboardButton(s.name, callback_data=cb)])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:sessions")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Help topic builders
# ---------------------------------------------------------------------------

def build_help_models() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_MODELS, build_back_button("menu:help")


def build_help_sessions() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_SESSIONS, build_back_button("menu:help")


def build_help_settings() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_SETTINGS, build_back_button("menu:help")


# ---------------------------------------------------------------------------
# Current settings renderer
# ---------------------------------------------------------------------------

def render_current_settings(session, model_info: str | None = None) -> str:
    """Build a combined current-settings text for both scopes."""
    s = session.settings
    lines = ["📋 *Current Settings*\n"]

    lines.append("*Session Settings*")
    prompt_display = (
        s.system_prompt[:60] + '…'
        if len(s.system_prompt) > 60
        else s.system_prompt or '(none)'
    )
    lines.append(f"  System Prompt: `{prompt_display}`")
    lines.append(f"  Temperature: `{s.temperature}`")
    lines.append(f"  Max Tokens: `{s.max_tokens}`")
    lines.append(f"  Top-P: `{s.top_p}`")
    lines.append(f"  Top-K: `{s.top_k if s.top_k is not None else '(default)'}`")
    lines.append(
        f"  Repeat Penalty: "
        f"`{s.repeat_penalty if s.repeat_penalty is not None else '(default)'}`"
    )
    lines.append(f"  Stop Strings: `{s.stop_strings or '(none)'}`")
    lines.append(f"  Seed: `{s.seed if s.seed is not None else '(random)'}`")
    lines.append(f"  History Policy: `{s.history_policy.mode}`")
    if s.history_policy.mode == "last_n_pairs" and s.history_policy.message_pair_limit is not None:
        lines.append(f"    Pair Limit: `{s.history_policy.message_pair_limit}`")

    lines.append("")
    lines.append("*Model Runtime*")
    if model_info:
        lines.append(f"  Loaded: `{model_info}`")
    else:
        lines.append("  _(No model loaded)_")

    return "\n".join(lines)


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
    if section == "menu:main":
        text, keyboard = "🏠 Main Menu", build_main_menu()
    elif section in SECTION_BUILDERS:
        text, builder = SECTION_BUILDERS[section]
        keyboard = builder()
    else:
        logger.warning("Unknown section: %s", section)
        return

    try:
        await query.edit_message_text(text=text, reply_markup=keyboard)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.info("Stale menu detected, sending fresh menu: %s", e)
        await query.answer("Menu expired — opening a fresh menu.")
        context.chat_data["menu_message_id"] = None
        msg = await query.message.chat.send_message(
            text="🏠 Main Menu", reply_markup=build_main_menu()
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
                text="🏠 Main Menu",
                reply_markup=build_main_menu(),
            )
            return
        except BadRequest:
            logger.info("Previous menu message stale, sending new one")

    msg = await update.effective_message.reply_text(
        "🏠 Main Menu", reply_markup=build_main_menu()
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
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")
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
        await cli.load_model(model_key)
        await query.edit_message_text(f"✅ Loaded {model_key}.")
    except LmsCliError as e:
        await query.edit_message_text(f"❌ Failed to load {model_key}: {e}")


async def _handle_unload_model_callback(query, context, data: str) -> None:
    identifier = data[len("models:unloadmodel:"):]
    try:
        await query.edit_message_text(f"⏳ Unloading {identifier}…")
        await cli.unload_model(identifier)
        await query.edit_message_text(f"✅ Unloaded {identifier}.")
    except LmsCliError as e:
        await query.edit_message_text(f"❌ Failed to unload {identifier}: {e}")


# ---------------------------------------------------------------------------
# Sessions actions handler
# ---------------------------------------------------------------------------

async def _handle_sessions_action(query, context, data: str) -> None:
    store = context.bot_data["store"]

    if data == "sessions:new":
        context.chat_data["pending_input"] = "sessions:new"
        await query.message.reply_text(
            "Enter a name for the new chat (or send empty for auto-name):"
        )
        logger.info("Pending input set: sessions:new")
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
        keyboard = build_sessions_list_keyboard(sessions, "confirm_remove")
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
                parse_mode="Markdown",
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
                text=f"📜 History Reuse Policy\nCurrent: `{current}`",
                reply_markup=build_history_policy_menu(),
                parse_mode="Markdown",
            )
        except BadRequest:
            pass
        return

    if data.startswith("settings:history_policy:"):
        mode = data[len("settings:history_policy:"):]
        if mode == "last_n_pairs":
            context.chat_data["pending_input"] = "settings:history_policy:last_n_pairs"
            await query.message.reply_text("Enter the number of message pairs to keep:")
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
            f"✅ Model preset '{preset.name}' staged. Values will apply on next /load."
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
        context.chat_data["pending_input"] = data
        await query.message.reply_text(model_setting_prompts[data])
        logger.info("Pending input set: %s", data)
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
        context.chat_data["pending_input"] = data
        await query.message.reply_text(session_setting_prompts[data])
        logger.info("Pending input set: %s", data)
        return

    # Legacy compat — old settings: keys
    legacy_prompts = {
        "settings:prompt": "Enter the system prompt (or send empty to clear):",
        "settings:temperature": "Enter temperature (0.0–2.0):",
        "settings:max_tokens": "Enter max tokens (integer ≥ -1, use -1 for unlimited):",
        "settings:top_p": "Enter top-p (0.0–1.0):",
    }
    if data in legacy_prompts:
        context.chat_data["pending_input"] = data
        await query.message.reply_text(legacy_prompts[data])
        logger.info("Pending input set: %s", data)
        return


# ---------------------------------------------------------------------------
# Pending input handler
# ---------------------------------------------------------------------------

async def handle_pending_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch user text to the correct pending-input handler."""
    pending = context.chat_data.get("pending_input")
    if pending is None:
        return

    text = update.effective_message.text.strip()
    logger.info("Processing pending input: %s", pending)

    if pending == "models:load":
        await _execute_models_load(text, update, context)
    elif pending == "models:unload":
        await _execute_models_unload(text, update, context)
    elif pending == "sessions:new":
        await _execute_sessions_new(text, update, context)
    elif pending == "inference:send":
        await _execute_inference_send(text, update, context)
    elif pending.startswith("settings:model:"):
        key = pending[len("settings:model:"):]
        await _execute_model_settings_update(key, text, update, context)
    elif pending.startswith("settings:session:"):
        key = pending[len("settings:session:"):]
        await _execute_settings_update(key, text, update, context)
    elif pending.startswith("settings:history_policy:"):
        await _execute_history_policy_update(pending, text, update, context)
    elif pending.startswith("settings:"):
        key = pending[len("settings:"):]
        await _execute_settings_update(key, text, update, context)
    else:
        logger.warning("Unknown pending_input key: %s", pending)
        context.chat_data["pending_input"] = None


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

async def _execute_models_load(text: str, update: Update, context) -> None:
    if not text:
        await reply_ephemeral(update.effective_message, "❌ Model identifier cannot be empty.")
        return
    try:
        result = await cli.load_model(text)
        await reply_ephemeral(update.effective_message, f"✅ Model loaded successfully.\n{result}")
        context.chat_data["pending_input"] = None
        logger.info("Model loaded via menu: %s", text)
    except LmsCliError as e:
        await reply_ephemeral(update.effective_message, f"❌ Load failed: {e}")
        context.chat_data["pending_input"] = None


async def _execute_models_unload(text: str, update: Update, context) -> None:
    if not text:
        await reply_ephemeral(update.effective_message, "❌ Model identifier cannot be empty.")
        return
    try:
        result = await cli.unload_model(text)
        await reply_ephemeral(update.effective_message, f"✅ Model unloaded.\n{result}")
        context.chat_data["pending_input"] = None
        logger.info("Model unloaded via menu: %s", text)
    except LmsCliError as e:
        await reply_ephemeral(update.effective_message, f"❌ Unload failed: {e}")
        context.chat_data["pending_input"] = None


async def _execute_sessions_new(text: str, update: Update, context) -> None:
    store = context.bot_data["store"]
    name = text if text else f"Chat {len(store.list_sessions()) + 1}"
    session = store.create_session(name)
    await reply_ephemeral(update.effective_message, f"✅ Created chat: {session.name}")
    context.chat_data["pending_input"] = None
    logger.info("Session created via menu: %s", session.name)


async def _execute_inference_send(text: str, update: Update, context) -> None:
    if not text:
        await reply_ephemeral(update.effective_message, "❌ Message cannot be empty.")
        return

    from src.lms import sdk

    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = store.get_active_session()

    if session is None:
        await reply_ephemeral(update.effective_message, "❌ No active chat. Create one first.")
        context.chat_data["pending_input"] = None
        return

    context.chat_data["pending_input"] = None
    user_msg = ChatMessage(role="user", content=text)
    store.append_message(session.id, user_msg)

    # Load history and trim by policy
    history = store.load_history(session.id)
    trimmed = sdk.trim_history(history, session.settings.history_policy)

    sent_message = await update.effective_message.reply_text("⏳ Thinking...")
    full_response = ""

    try:
        async for chunk in sdk.chat_stream(
            session, host=config.LMS_HOST, port=config.LMS_PORT,
            history_messages=trimmed,
        ):
            full_response += chunk

        if full_response:
            formatted = format_response(full_response)
            chunks = split_message(formatted)
            try:
                await sent_message.edit_text(chunks[0], parse_mode="HTML")
            except BadRequest as fmt_err:
                logger.warning("HTML send failed (%s), retrying as plain text", fmt_err)
                await sent_message.edit_text(chunks[0])
            for chunk in chunks[1:]:
                try:
                    await sent_message.reply_text(chunk, parse_mode="HTML")
                except BadRequest as fmt_err:
                    logger.warning("HTML overflow chunk failed (%s), sending plain", fmt_err)
                    await sent_message.reply_text(chunk)
            store.append_message(
                session.id,
                ChatMessage(role="assistant", content=full_response),
            )
        else:
            await sent_message.edit_text("❌ No response from model.")
    except Exception as e:
        logger.error("Inference error (menu): %s", e)
        await sent_message.edit_text("❌ LM Studio is unreachable.")


async def _execute_inference_regenerate(query, context) -> None:
    from src.lms import sdk

    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = store.get_active_session()

    if not session:
        await reply_ephemeral(
            query.message,
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    history = store.load_history(session.id)

    if not history:
        await reply_ephemeral(
            query.message,
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    if history[-1].role == "assistant":
        store.pop_last_assistant(session.id)
        history = history[:-1]

    if not history or history[-1].role != "user":
        await reply_ephemeral(
            query.message,
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    trimmed = sdk.trim_history(history, session.settings.history_policy)

    sent_message = await query.message.reply_text("⏳ Regenerating...")
    full_response = ""

    try:
        async for chunk in sdk.chat_stream(
            session, host=config.LMS_HOST, port=config.LMS_PORT,
            history_messages=trimmed,
        ):
            full_response += chunk

        if full_response:
            formatted = format_response(full_response)
            chunks = split_message(formatted)
            try:
                await sent_message.edit_text(chunks[0], parse_mode="HTML")
            except BadRequest as fmt_err:
                logger.warning("HTML send failed (%s), retrying as plain text", fmt_err)
                await sent_message.edit_text(chunks[0])
            for chunk in chunks[1:]:
                try:
                    await sent_message.reply_text(chunk, parse_mode="HTML")
                except BadRequest as fmt_err:
                    logger.warning("HTML overflow chunk failed (%s), sending plain", fmt_err)
                    await sent_message.reply_text(chunk)
            store.append_message(
                session.id,
                ChatMessage(role="assistant", content=full_response),
            )
        else:
            await sent_message.edit_text("❌ No response from model.")
    except Exception as e:
        logger.error("Regeneration error (menu): %s", e)
        await sent_message.edit_text("❌ LM Studio is unreachable.")


async def _execute_settings_update(
    key: str, text: str, update: Update, context
) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()

    if session is None:
        await reply_ephemeral(
            update.effective_message,
            "❌ No active chat. Create one first."
        )
        context.chat_data["pending_input"] = None
        return

    if key == "prompt":
        session.settings.system_prompt = text
        store.update_session(session)
        if text:
            await reply_ephemeral(update.effective_message, "✅ System prompt updated.")
        else:
            await reply_ephemeral(update.effective_message, "✅ System prompt cleared.")
        context.chat_data["pending_input"] = None
        logger.info("System prompt updated via menu")
        return

    if key == "temperature":
        try:
            val = float(text)
            if not (0.0 <= val <= 2.0):
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Temperature must be a number between 0.0 and 2.0."
            )
            return
        session.settings.temperature = val
        store.update_session(session)
        await reply_ephemeral(update.effective_message, f"✅ Temperature set to {val}")
        context.chat_data["pending_input"] = None
        logger.info("Temperature updated via menu: %s", val)
        return

    if key == "max_tokens":
        try:
            val = int(text)
            if val < -1:
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Max tokens must be an integer ≥ -1 (use -1 for unlimited)."
            )
            return
        session.settings.max_tokens = val
        store.update_session(session)
        await reply_ephemeral(update.effective_message, f"✅ Max tokens set to {val}")
        context.chat_data["pending_input"] = None
        logger.info("Max tokens updated via menu: %s", val)
        return

    if key == "top_p":
        try:
            val = float(text)
            if not (0.0 <= val <= 1.0):
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Top-P must be a number between 0.0 and 1.0."
            )
            return
        session.settings.top_p = val
        store.update_session(session)
        await reply_ephemeral(update.effective_message, f"✅ Top-P set to {val}")
        context.chat_data["pending_input"] = None
        logger.info("Top-P updated via menu: %s", val)
        return

    if key == "top_k":
        if text.lower() in ("none", "null", "default"):
            session.settings.top_k = None
            store.update_session(session)
            await reply_ephemeral(update.effective_message, "✅ Top-K cleared")
            context.chat_data["pending_input"] = None
            return
        try:
            val = int(text)
            if val < 1:
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Top-K must be an integer ≥ 1, or 'none' to clear."
            )
            return
        session.settings.top_k = val
        store.update_session(session)
        await reply_ephemeral(update.effective_message, f"✅ Top-K set to {val}")
        context.chat_data["pending_input"] = None
        return

    if key == "repeat_penalty":
        if text.lower() in ("none", "null", "default"):
            session.settings.repeat_penalty = None
            store.update_session(session)
            await reply_ephemeral(update.effective_message, "✅ Repeat penalty cleared")
            context.chat_data["pending_input"] = None
            return
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Repeat penalty must be a number > 0, or 'none' to clear."
            )
            return
        session.settings.repeat_penalty = val
        store.update_session(session)
        await reply_ephemeral(update.effective_message, f"✅ Repeat penalty set to {val}")
        context.chat_data["pending_input"] = None
        return

    if key == "stop_strings":
        if text.lower() in ("none", "clear", "[]"):
            session.settings.stop_strings = []
            store.update_session(session)
            await reply_ephemeral(update.effective_message, "✅ Stop strings cleared")
            context.chat_data["pending_input"] = None
            return
        session.settings.stop_strings = [s.strip() for s in text.split(",") if s.strip()]
        store.update_session(session)
        await reply_ephemeral(
            update.effective_message,
            f"✅ Stop strings set to {session.settings.stop_strings}"
        )
        context.chat_data["pending_input"] = None
        return

    if key == "seed":
        if text.lower() in ("none", "null", "random"):
            session.settings.seed = None
            store.update_session(session)
            await reply_ephemeral(update.effective_message, "✅ Seed cleared (random)")
            context.chat_data["pending_input"] = None
            return
        try:
            val = int(text)
            if val < 0:
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Seed must be an integer ≥ 0, or 'none' for random."
            )
            return
        session.settings.seed = val
        store.update_session(session)
        await reply_ephemeral(update.effective_message, f"✅ Seed set to {val}")
        context.chat_data["pending_input"] = None
        return


async def _execute_model_settings_update(
    key: str, text: str, update: Update, context
) -> None:
    """Handle model-scoped runtime setting updates (staged for next load)."""
    staged = context.chat_data.get("staged_model_settings", {})

    if key == "gpu":
        import re
        if text not in ("auto", "max") and not re.match(r"^0?\.\d+$|^1(\.0)?$|^0$", text):
            await reply_ephemeral(
                update.effective_message,
                "❌ GPU must be 'auto', 'max', or a fraction 0.0–1.0."
            )
            return
        staged["gpu"] = text

    elif key == "context_length":
        try:
            val = int(text)
            if val < 512:
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Context length must be an integer ≥ 512."
            )
            return
        staged["context_length"] = val

    elif key == "identifier":
        staged["identifier"] = text

    else:
        await reply_ephemeral(update.effective_message, f"❌ Unknown model setting: {key}")
        context.chat_data["pending_input"] = None
        return

    context.chat_data["staged_model_settings"] = staged
    await reply_ephemeral(
        update.effective_message,
        f"✅ Model {key} staged to '{staged[key]}'. Will apply on next /load."
    )
    context.chat_data["pending_input"] = None


async def _execute_history_policy_update(
    pending: str, text: str, update: Update, context
) -> None:
    """Handle history policy pending input (currently only last_n_pairs count)."""
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await reply_ephemeral(update.effective_message, "❌ No active chat.")
        context.chat_data["pending_input"] = None
        return

    if pending == "settings:history_policy:last_n_pairs":
        try:
            val = int(text)
            if val < 1:
                raise ValueError
        except ValueError:
            await reply_ephemeral(
                update.effective_message,
                "❌ Must be a positive integer."
            )
            return
        from src.storage.models import HistoryReusePolicy
        session.settings.history_policy = HistoryReusePolicy(
            mode="last_n_pairs", message_pair_limit=val
        )
        store.update_session(session)
        await reply_ephemeral(
            update.effective_message,
            f"✅ History policy set to last_n_pairs ({val} pairs)"
        )
        context.chat_data["pending_input"] = None
        return
