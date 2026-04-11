"""Inline button menu handler for LMStudioBot.

Provides keyboard builders, callback routing, and pending input handling
for the persistent inline menu navigation system.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
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
# Help text constants (US6)
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
    "• *System Prompt* — Set or clear the system prompt for the active chat.\n"
    "• *Temperature* — Controls randomness (0.0–2.0). Lower = more deterministic.\n"
    "• *Max Tokens* — Maximum response length (-1 for unlimited).\n"
    "• *Top-P* — Nucleus sampling (0.0–1.0). Lower = more focused."
)

HELP_INFERENCE = (
    "🔮 *Inference Help*\n\n"
    "• *Send Message* — Sends a text message to the active model.\n"
    "• *Regenerate* — Re-generates the last assistant response.\n\n"
    "You can also just type a message directly — the bot will infer with the active model."
)

# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


def build_main_menu() -> InlineKeyboardMarkup:
    """Build the top-level 5-section menu keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Model Management", callback_data="menu:models"),
            InlineKeyboardButton("🧠 Chat Sessions", callback_data="menu:sessions"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
            InlineKeyboardButton("🔮 Inference", callback_data="menu:inference"),
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
    """Settings sub-menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 System Prompt", callback_data="settings:prompt")],
        [
            InlineKeyboardButton("🌡 Temperature", callback_data="settings:temperature"),
            InlineKeyboardButton("🔢 Max Tokens", callback_data="settings:max_tokens"),
            InlineKeyboardButton("📊 Top-P", callback_data="settings:top_p"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_inference_menu(active_model: str | None) -> InlineKeyboardMarkup:
    """Inference sub-menu showing the active model name."""
    label = active_model or "No model loaded"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔮 {label}", callback_data="inference:noop")],
        [
            InlineKeyboardButton("💬 Send Message", callback_data="inference:send"),
            InlineKeyboardButton("🔄 Regenerate", callback_data="inference:regenerate"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
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
            InlineKeyboardButton("🔮 Inference Help", callback_data="menu:help:inference"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_sessions_list_keyboard(sessions, action: str) -> InlineKeyboardMarkup:
    """Build dynamic keyboard with one button per session.

    *action* is ``"switch"`` or ``"confirm_remove"``.
    """
    rows = []
    for s in sessions:
        cb = f"sessions:{action}:{s.id}"
        rows.append([InlineKeyboardButton(s.name, callback_data=cb)])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:sessions")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Help topic builders (US6)
# ---------------------------------------------------------------------------

def build_help_models() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_MODELS, build_back_button("menu:help")


def build_help_sessions() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_SESSIONS, build_back_button("menu:help")


def build_help_settings() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_SETTINGS, build_back_button("menu:help")


def build_help_inference() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_INFERENCE, build_back_button("menu:help")


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
    elif section == "menu:inference":
        store = context.bot_data["store"]
        session = store.get_active_session()
        model = session.model_identifier if session else None
        text = "🔮 Inference"
        keyboard = build_inference_menu(model)
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
            return  # idempotent no-op
        # Stale or deleted message
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
                "menu:settings", "menu:inference", "menu:help"):
        await _show_section(query, context, data)
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

    # Inference actions
    if data.startswith("inference:"):
        await _handle_inference_action(query, context, data)
        return

    # Settings actions
    if data.startswith("settings:"):
        await _handle_settings_action(query, context, data)
        return

    logger.warning("Unrecognised callback key: %s", data)


# ---------------------------------------------------------------------------
# Help section handler (US6)
# ---------------------------------------------------------------------------

HELP_TOPIC_BUILDERS = {
    "menu:help:models": build_help_models,
    "menu:help:sessions": build_help_sessions,
    "menu:help:settings": build_help_settings,
    "menu:help:inference": build_help_inference,
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
# Model actions handler (US2)
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
            await query.message.reply_text(f"❌ Could not list models: {e}")
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
            await query.message.reply_text(f"❌ Could not list loaded models: {e}")
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
# Sessions actions handler (US3)
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
            await query.message.reply_text(f"✅ Switched to chat: {result.name}")
        else:
            await query.message.reply_text("❌ Chat not found.")
        logger.info("Session switch via menu: %s", session_id)
        # Return to sessions sub-menu
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
            await query.message.reply_text("✅ Chat removed.")
        else:
            await query.message.reply_text("❌ Chat not found.")
        logger.info("Session removed via menu: %s", session_id)
        try:
            await query.edit_message_text(
                text="🧠 Chat Sessions", reply_markup=build_sessions_menu()
            )
        except BadRequest:
            pass
        return


# ---------------------------------------------------------------------------
# Inference actions handler (US4)
# ---------------------------------------------------------------------------

async def _handle_inference_action(query, context, data: str) -> None:
    if data == "inference:noop":
        return

    store = context.bot_data["store"]
    session = store.get_active_session()

    if data == "inference:send":
        if session is None:
            await query.message.reply_text("❌ No active chat. Create one first.")
            return
        context.chat_data["pending_input"] = "inference:send"
        await query.message.reply_text("Enter your message:")
        logger.info("Pending input set: inference:send")
        return

    if data == "inference:regenerate":
        if session is None:
            await query.message.reply_text("❌ No active chat. Create one first.")
            return
        await _execute_inference_regenerate(query, context)
        return


# ---------------------------------------------------------------------------
# Settings actions handler (US5)
# ---------------------------------------------------------------------------

async def _handle_settings_action(query, context, data: str) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()

    if session is None:
        await query.message.reply_text(
            "❌ No active chat. Create one in Chat Sessions first."
        )
        return

    prompts = {
        "settings:prompt": "Enter the system prompt (or send empty to clear):",
        "settings:temperature": "Enter temperature (0.0–2.0):",
        "settings:max_tokens": "Enter max tokens (integer ≥ -1, use -1 for unlimited):",
        "settings:top_p": "Enter top-p (0.0–1.0):",
    }

    if data in prompts:
        context.chat_data["pending_input"] = data
        await query.message.reply_text(prompts[data])
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
        await update.effective_message.reply_text("❌ Model identifier cannot be empty.")
        return  # keep pending_input set for re-prompt
    try:
        result = await cli.load_model(text)
        await update.effective_message.reply_text(f"✅ Model loaded successfully.\n{result}")
        context.chat_data["pending_input"] = None
        logger.info("Model loaded via menu: %s", text)
    except LmsCliError as e:
        await update.effective_message.reply_text(f"❌ Load failed: {e}")
        context.chat_data["pending_input"] = None


async def _execute_models_unload(text: str, update: Update, context) -> None:
    if not text:
        await update.effective_message.reply_text("❌ Model identifier cannot be empty.")
        return
    try:
        result = await cli.unload_model(text)
        await update.effective_message.reply_text(f"✅ Model unloaded.\n{result}")
        context.chat_data["pending_input"] = None
        logger.info("Model unloaded via menu: %s", text)
    except LmsCliError as e:
        await update.effective_message.reply_text(f"❌ Unload failed: {e}")
        context.chat_data["pending_input"] = None


async def _execute_sessions_new(text: str, update: Update, context) -> None:
    store = context.bot_data["store"]
    name = text if text else f"Chat {len(store.list_sessions()) + 1}"
    session = store.create_session(name)
    await update.effective_message.reply_text(f"✅ Created chat: {session.name}")
    context.chat_data["pending_input"] = None
    logger.info("Session created via menu: %s", session.name)


async def _execute_inference_send(text: str, update: Update, context) -> None:
    if not text:
        await update.effective_message.reply_text("❌ Message cannot be empty.")
        return

    from src.lms import sdk

    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = store.get_active_session()

    if session is None:
        await update.effective_message.reply_text("❌ No active chat. Create one first.")
        context.chat_data["pending_input"] = None
        return

    context.chat_data["pending_input"] = None
    session.history.append(ChatMessage(role="user", content=text))

    sent_message = await update.effective_message.reply_text("⏳ Thinking...")
    full_response = ""

    try:
        async for chunk in sdk.chat_stream(
            session, host=config.LMS_HOST, port=config.LMS_PORT
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
            session.history.append(ChatMessage(role="assistant", content=full_response))
            store.update_session(session)
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

    if not session or not session.history:
        await query.message.reply_text(
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    if session.history[-1].role == "assistant":
        session.history.pop()

    if not session.history or session.history[-1].role != "user":
        await query.message.reply_text(
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    sent_message = await query.message.reply_text("⏳ Regenerating...")
    full_response = ""

    try:
        async for chunk in sdk.chat_stream(
            session, host=config.LMS_HOST, port=config.LMS_PORT
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
            session.history.append(ChatMessage(role="assistant", content=full_response))
            store.update_session(session)
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
        await update.effective_message.reply_text(
            "❌ No active chat. Create one first."
        )
        context.chat_data["pending_input"] = None
        return

    if key == "prompt":
        session.system_prompt = text
        store.update_session(session)
        if text:
            await update.effective_message.reply_text("✅ System prompt updated.")
        else:
            await update.effective_message.reply_text("✅ System prompt cleared.")
        context.chat_data["pending_input"] = None
        logger.info("System prompt updated via menu")
        return

    if key == "temperature":
        try:
            val = float(text)
            if not (0.0 <= val <= 2.0):
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Temperature must be a number between 0.0 and 2.0."
            )
            return  # keep pending_input for re-prompt
        session.settings.temperature = val
        store.update_session(session)
        await update.effective_message.reply_text(f"✅ Temperature set to {val}")
        context.chat_data["pending_input"] = None
        logger.info("Temperature updated via menu: %s", val)
        return

    if key == "max_tokens":
        try:
            val = int(text)
            if val < -1:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Max tokens must be an integer ≥ -1 (use -1 for unlimited)."
            )
            return
        session.settings.max_tokens = val
        store.update_session(session)
        await update.effective_message.reply_text(f"✅ Max tokens set to {val}")
        context.chat_data["pending_input"] = None
        logger.info("Max tokens updated via menu: %s", val)
        return

    if key == "top_p":
        try:
            val = float(text)
            if not (0.0 <= val <= 1.0):
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text(
                "❌ Top-P must be a number between 0.0 and 1.0."
            )
            return
        session.settings.top_p = val
        store.update_session(session)
        await update.effective_message.reply_text(f"✅ Top-P set to {val}")
        context.chat_data["pending_input"] = None
        logger.info("Top-P updated via menu: %s", val)
        return
