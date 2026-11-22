"""Free-text input collected after a menu button asked the user for a value."""

import logging
import re
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot.i18n import tr
from src.bot.ephemeral import reply_ephemeral
from src.bot.handlers.models import perform_load, perform_unload
from src.bot.handlers.menu.screens import refresh_screen
from src.bot.handlers.settings_spec import SETTING_SPECS, apply_text
from src.lms.cli import LmsCliError

logger = logging.getLogger(__name__)

INPUT_TIMEOUT = 120.0  # seconds a value prompt stays active
CB_INPUT_CANCEL = "input:cancel"


def input_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("❌ Cancel"), callback_data=CB_INPUT_CANCEL)]]
    )


async def request_input(message, context, key: str, prompt: str) -> None:
    """Ask the user for a value: remember what we wait for and offer a Cancel button."""
    context.chat_data["pending_input"] = key
    context.chat_data["pending_input_at"] = time.monotonic()
    # Remember which screen asked, so it can be refreshed once the value is saved.
    screen = context.chat_data.get("menu_screen")
    context.chat_data["pending_return"] = (
        {"chat_id": message.chat_id, "message_id": message.message_id, "screen": screen}
        if screen
        else None
    )
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
    context.chat_data["pending_return"] = None
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
    elif pending.startswith("sessions:rename:"):
        await _execute_sessions_rename(
            text, update, context, session_id=pending[len("sessions:rename:"):]
        )
    elif pending == "sessions:new":
        await _execute_sessions_new(text, update, context)
    elif pending.startswith("settings:model:"):
        key = pending[len("settings:model:"):]
        await _execute_model_settings_update(key, text, update, context)
    elif pending.startswith("settings:session:"):
        key = pending[len("settings:session:"):]
        await _execute_settings_update(key, text, update, context)
    elif pending == "settings:save_preset":
        await _execute_save_preset(text, update, context)
    elif pending.startswith("settings:history_policy:"):
        await _execute_history_policy_update(pending, text, update, context)
    else:
        logger.warning("Unknown pending_input key: %s", pending)
        context.chat_data["pending_input"] = None

    if context.chat_data.get("pending_input") is None:
        await _refresh_origin_screen(context)


async def _refresh_origin_screen(context) -> None:
    """After a value was saved, re-render the screen whose button asked for it."""
    origin = context.chat_data.pop("pending_return", None)
    if origin:
        await refresh_screen(
            context, origin["chat_id"], origin["message_id"], origin["screen"]
        )


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

async def _execute_models_load(text: str, update: Update, context) -> None:
    if not text:
        await reply_ephemeral(update.effective_message, tr("❌ Model identifier cannot be empty."))
        return
    try:
        result = await perform_load(context, text)
        await reply_ephemeral(
            update.effective_message,
            tr("✅ Model loaded successfully.\n{result}", result=result),
        )
        context.chat_data["pending_input"] = None
        logger.info("Model loaded via menu: %s", text)
    except LmsCliError as e:
        await reply_ephemeral(update.effective_message, tr("❌ Load failed: {error}", error=e))
        context.chat_data["pending_input"] = None


async def _execute_models_unload(text: str, update: Update, context) -> None:
    if not text:
        await reply_ephemeral(update.effective_message, tr("❌ Model identifier cannot be empty."))
        return
    try:
        result = await perform_unload(context, text)
        await reply_ephemeral(
            update.effective_message, tr("✅ Model unloaded.\n{result}", result=result)
        )
        context.chat_data["pending_input"] = None
        logger.info("Model unloaded via menu: %s", text)
    except LmsCliError as e:
        await reply_ephemeral(update.effective_message, tr("❌ Unload failed: {error}", error=e))
        context.chat_data["pending_input"] = None


async def _execute_sessions_new(text: str, update: Update, context) -> None:
    store = context.bot_data["store"]
    name = text if text else tr("Chat {n}", n=len(store.list_sessions()) + 1)
    session = store.create_session(name)
    await reply_ephemeral(update.effective_message, tr("✅ Created chat: {name}", name=session.name))
    context.chat_data["pending_input"] = None
    logger.info("Session created via menu: %s", session.name)


async def _execute_settings_update(
    key: str, text: str, update: Update, context
) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()

    if session is None:
        await reply_ephemeral(update.effective_message, tr("❌ No active chat. Create one first."))
        context.chat_data["pending_input"] = None
        return

    spec = SETTING_SPECS.get(key)
    if spec is None:
        logger.warning("Unknown session setting key: %s", key)
        context.chat_data["pending_input"] = None
        return

    try:
        value, message = apply_text(spec, text)
    except ValueError as err:
        # Invalid input: keep waiting so the user can retry (or /menu to cancel).
        await reply_ephemeral(update.effective_message, str(err))
        return

    setattr(session.settings, spec.attr, value)
    store.update_session(session)
    await reply_ephemeral(update.effective_message, message)
    context.chat_data["pending_input"] = None
    logger.info("Setting %s updated via menu", key)


MAX_CHAT_NAME = 64
MAX_PRESET_NAME = 40


async def _execute_sessions_rename(
    text: str, update: Update, context, session_id: str | None = None
) -> None:
    store = context.bot_data["store"]
    session = store.store.sessions.get(session_id) if session_id else store.get_active_session()
    if session is None:
        await reply_ephemeral(update.effective_message, tr("❌ No active chat."))
        context.chat_data["pending_input"] = None
        return
    if not text:
        await reply_ephemeral(update.effective_message, tr("❌ The name cannot be empty."))
        return
    if len(text) > MAX_CHAT_NAME:
        await reply_ephemeral(
            update.effective_message,
            tr("❌ The name must be {limit} characters or fewer.", limit=MAX_CHAT_NAME),
        )
        return
    session.name = text
    store.update_session(session)
    await reply_ephemeral(update.effective_message, tr("✅ Chat renamed to: {name}", name=text))
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
                tr("❌ GPU must be 'auto', 'max', or a fraction 0.0–1.0.")
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
                tr("❌ Context length must be an integer ≥ 512.")
            )
            return
        staged["context_length"] = val

    elif key == "identifier":
        staged["identifier"] = text

    else:
        await reply_ephemeral(
            update.effective_message, tr("❌ Unknown model setting: {key}", key=key)
        )
        context.chat_data["pending_input"] = None
        return

    context.chat_data["staged_model_settings"] = staged
    await reply_ephemeral(
        update.effective_message,
        tr(
            "✅ Model {key} staged to '{value}'. Will apply on the next model load.",
            key=key, value=staged[key],
        )
    )
    context.chat_data["pending_input"] = None


async def _execute_history_policy_update(
    pending: str, text: str, update: Update, context
) -> None:
    """Handle history policy pending input (currently only last_n_pairs count)."""
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await reply_ephemeral(update.effective_message, tr("❌ No active chat."))
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
                tr("❌ Must be a positive integer.")
            )
            return
        from src.storage.models import HistoryReusePolicy
        session.settings.history_policy = HistoryReusePolicy(
            mode="last_n_pairs", message_pair_limit=val
        )
        store.update_session(session)
        await reply_ephemeral(
            update.effective_message,
            tr("✅ History policy set to last_n_pairs ({count} pairs)", count=val)
        )
        context.chat_data["pending_input"] = None
        return


async def _execute_save_preset(text: str, update: Update, context) -> None:
    """Save the active chat's settings under the typed name."""
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await reply_ephemeral(update.effective_message, tr("❌ No active chat."))
        context.chat_data["pending_input"] = None
        return
    if not text:
        await reply_ephemeral(update.effective_message, tr("❌ The name cannot be empty."))
        return
    if len(text) > MAX_PRESET_NAME:
        await reply_ephemeral(
            update.effective_message,
            tr("❌ The name must be {limit} characters or fewer.", limit=MAX_PRESET_NAME),
        )
        return
    store.save_session_preset(text, session.settings)
    await reply_ephemeral(update.effective_message, tr("✅ Preset saved: {name}", name=text))
    context.chat_data["pending_input"] = None
