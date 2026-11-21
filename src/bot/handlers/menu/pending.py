"""Free-text input collected after a menu button asked the user for a value."""

import logging
import re
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot.ephemeral import reply_ephemeral
from src.bot.handlers.models import perform_load, perform_unload
from src.bot.handlers.settings_spec import SETTING_SPECS
from src.lms.cli import LmsCliError

logger = logging.getLogger(__name__)

INPUT_TIMEOUT = 120.0  # seconds a value prompt stays active
CB_INPUT_CANCEL = "input:cancel"


def input_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=CB_INPUT_CANCEL)]])


async def request_input(message, context, key: str, prompt: str) -> None:
    """Ask the user for a value: remember what we wait for and offer a Cancel button."""
    context.chat_data["pending_input"] = key
    context.chat_data["pending_input_at"] = time.monotonic()
    await message.reply_text(prompt, reply_markup=input_cancel_keyboard())
    logger.info("Pending input set: %s", key)


def expire_pending_if_stale(context) -> bool:
    """Drop a value prompt nobody answered. Returns True if one was expired."""
    if not context.chat_data.get("pending_input"):
        return False
    requested_at = context.chat_data.get("pending_input_at")
    if requested_at is None or time.monotonic() - requested_at <= INPUT_TIMEOUT:
        return False
    context.chat_data["pending_input"] = None
    context.chat_data["pending_input_at"] = None
    return True


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
    elif pending == "sessions:rename":
        await _execute_sessions_rename(text, update, context)
    elif pending == "sessions:new":
        await _execute_sessions_new(text, update, context)
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
        result = await perform_load(context, text)
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
        result = await perform_unload(context, text)
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


async def _execute_settings_update(
    key: str, text: str, update: Update, context
) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()

    if session is None:
        await reply_ephemeral(update.effective_message, "❌ No active chat. Create one first.")
        context.chat_data["pending_input"] = None
        return

    spec = SETTING_SPECS.get(key)
    if spec is None:
        logger.warning("Unknown session setting key: %s", key)
        context.chat_data["pending_input"] = None
        return

    if text.lower() in spec.clear_words:
        value, message = spec.cleared_value, spec.on_clear
    else:
        try:
            value = spec.parse(text)
        except ValueError:
            # Invalid input: keep waiting so the user can retry (or /menu to cancel).
            await reply_ephemeral(update.effective_message, spec.error)
            return
        message = spec.on_set(value)

    setattr(session.settings, spec.attr, value)
    store.update_session(session)
    await reply_ephemeral(update.effective_message, message)
    context.chat_data["pending_input"] = None
    logger.info("Setting %s updated via menu", key)


MAX_CHAT_NAME = 64


async def _execute_sessions_rename(text: str, update: Update, context) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await reply_ephemeral(update.effective_message, "❌ No active chat.")
        context.chat_data["pending_input"] = None
        return
    if not text:
        await reply_ephemeral(update.effective_message, "❌ The name cannot be empty.")
        return
    if len(text) > MAX_CHAT_NAME:
        await reply_ephemeral(
            update.effective_message, f"❌ The name must be {MAX_CHAT_NAME} characters or fewer."
        )
        return
    session.name = text
    store.update_session(session)
    await reply_ephemeral(update.effective_message, f"✅ Chat renamed to: {text}")
    context.chat_data["pending_input"] = None


async def _execute_model_settings_update(
    key: str, text: str, update: Update, context
) -> None:
    """Handle model-scoped runtime setting updates (staged for next load)."""
    staged = context.chat_data.get("staged_model_settings", {})

    if key == "gpu":
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
        f"✅ Model {key} staged to '{staged[key]}'. Will apply on the next model load."
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
