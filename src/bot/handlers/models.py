import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.formatting import _format_size
from src.lms import cli, sdk
from src.lms.cli import LmsCliError
from src.storage.models import LoadConfig

logger = logging.getLogger(__name__)

_CMD_MSG_KEY = "cmd_msg"


async def cmd_reply(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
) -> Message:
    """Send or edit the single persistent command-response message for this chat.

    Edits the previously stored command message if possible so the chat stays
    tidy (one response slot per chat). Falls back to a fresh reply when the
    old message can no longer be edited (deleted, too old, etc.).
    Always pass a Message object (use update.effective_message for command handlers).
    """
    prev: Message | None = context.chat_data.get(_CMD_MSG_KEY)
    if prev is not None:
        try:
            edited = await prev.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            context.chat_data[_CMD_MSG_KEY] = edited
            return edited
        except BadRequest:
            pass  # stale / deleted / unchanged — fall through to fresh message

    sent = await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    context.chat_data[_CMD_MSG_KEY] = sent
    return sent


def _format_downloaded_list(models) -> str:
    if not models:
        return "No models found."

    lines = []
    for model in models:
        model_key = getattr(model, "model_key", "unknown")
        info = getattr(model, "info", None)
        size_bytes = getattr(info, "size_bytes", 0) or 0
        lines.append(f"• {model_key}  {_format_size(int(size_bytes))}")

    return "📦 Available models:\n" + "\n".join(lines)


def _format_loaded_list(handles) -> str:
    if not handles:
        return "No models are currently loaded."

    lines = []
    for handle in handles:
        # Use direct attributes to avoid calling .get_info() which may trigger
        # a failed websocket reconnection on inactive connections
        identifier = getattr(handle, "identifier", "unknown")
        size_bytes = getattr(handle, "size_bytes", 0) or 0
        lines.append(f"• {identifier}  {_format_size(int(size_bytes))}")

    return "🧠 Loaded models:\n" + "\n".join(lines)


_MAX_BUTTONS = 100
_MAX_BUTTON_LABEL_LENGTH = 64
_MAX_CALLBACK_DATA_BYTES = 64


def _truncate_button_label(label: str) -> str:
    if len(label) <= _MAX_BUTTON_LABEL_LENGTH:
        return label
    return label[: _MAX_BUTTON_LABEL_LENGTH - 3] + "..."


def _truncate_callback_data(prefix: str, value: str) -> str:
    callback_data = f"{prefix}{value}"
    while len(callback_data.encode("utf-8")) > _MAX_CALLBACK_DATA_BYTES and value:
        value = value[:-1]
        callback_data = f"{prefix}{value}"
    return callback_data


def _build_limit_note(total: int) -> str:
    if total <= _MAX_BUTTONS:
        return ""
    return f"\n(showing 100 of {total}; {total - 100} model(s) not shown)"


def _build_load_keyboard(models, loaded_keys: set[str]) -> InlineKeyboardMarkup:
    rows = []
    for model in models[:_MAX_BUTTONS]:
        model_key = getattr(model, "model_key", "unknown")
        info = getattr(model, "info", None)
        size_bytes = getattr(info, "size_bytes", 0) or 0
        prefix = "🟢 " if model_key in loaded_keys else ""
        label = _truncate_button_label(f"{prefix}{model_key}  {_format_size(int(size_bytes))}")
        callback_data = _truncate_callback_data("models:loadmodel:", model_key)
        rows.append([InlineKeyboardButton(label, callback_data=callback_data)])
    return InlineKeyboardMarkup(rows)


def _build_unload_keyboard(handles) -> InlineKeyboardMarkup:
    rows = []
    for handle in handles[:_MAX_BUTTONS]:
        # Use identifier directly to avoid calling .get_info() which may trigger
        # a failed websocket reconnection on inactive connections
        identifier = getattr(handle, "identifier", "unknown")
        if not identifier:
            continue
        # Try to get size from direct attribute, fallback to 0 if not available
        size_bytes = getattr(handle, "size_bytes", 0) or 0
        label = _truncate_button_label(f"{identifier}  {_format_size(int(size_bytes))}")
        callback_data = _truncate_callback_data("models:unloadmodel:", identifier)
        rows.append([InlineKeyboardButton(label, callback_data=callback_data)])
    return InlineKeyboardMarkup(rows)


def _resolve_message(target):
    return getattr(target, "effective_message", target)


async def _send_load_keyboard(target, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = _resolve_message(target)
    config = context.bot_data["config"]

    try:
        models, handles = await asyncio.gather(
            sdk.list_downloaded_models(config.LMS_HOST, config.LMS_PORT),
            sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT),
        )
    except Exception:
        await cmd_reply(message, context, "❌ Could not connect to LM Studio. Is it running?")
        return

    if not models:
        await cmd_reply(message, context, "No models available to load.")
        return

    # Extract model keys without calling .get_info() to avoid triggering
    # websocket reconnection on inactive connections
    loaded_keys = {
        getattr(handle, "identifier", None)
        for handle in handles
        if handle is not None and getattr(handle, "identifier", None)
    }
    keyboard = _build_load_keyboard(models, loaded_keys)
    note = _build_limit_note(len(models))
    await cmd_reply(
        message, context,
        f"Select a model to load:{note}",
        reply_markup=keyboard,
    )


async def _send_unload_keyboard(target, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = _resolve_message(target)
    config = context.bot_data["config"]

    try:
        handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
    except Exception:
        await cmd_reply(message, context, "❌ Could not connect to LM Studio. Is it running?")
        return

    if not handles:
        await cmd_reply(message, context, "No models are currently loaded.")
        return

    keyboard = _build_unload_keyboard(handles)
    note = _build_limit_note(len(handles))
    await cmd_reply(
        message, context,
        f"Select a model to unload:{note}",
        reply_markup=keyboard,
    )


@require_owner
async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]

    try:
        models = await sdk.list_downloaded_models(config.LMS_HOST, config.LMS_PORT)
        await cmd_reply(
            update.effective_message, context, _format_downloaded_list(models), parse_mode="HTML"
        )
    except Exception:
        await cmd_reply(
            update.effective_message, context, "❌ Could not connect to LM Studio. Is it running?"
        )


@require_owner
async def loaded_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]

    try:
        handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
        await cmd_reply(
            update.effective_message, context, _format_loaded_list(handles), parse_mode="HTML"
        )
    except Exception:
        await cmd_reply(
            update.effective_message, context, "❌ Could not connect to LM Studio. Is it running?"
        )


@require_owner
async def load_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await _send_load_keyboard(update, context)
        return

    model = args[0]
    gpu = "auto"
    context_length = None
    identifier = None

    for arg in args[1:]:
        if arg.startswith("gpu="):
            gpu = arg[4:]
            valid_gpu = gpu in ("max", "auto")
            if not valid_gpu:
                try:
                    gpu_val = float(gpu)
                    if not (0.0 <= gpu_val <= 1.0):
                        await cmd_reply(
                            update.effective_message, context,
                            "❌ Invalid gpu value: must be max, auto, or a float between 0.0 and 1.0"
                        )
                        return
                except ValueError:
                    await cmd_reply(
                        update.effective_message, context,
                        "❌ Invalid gpu value: must be max, auto, or a float between 0.0 and 1.0"
                    )
                    return
        elif arg.startswith("ctx="):
            try:
                context_length = int(arg[4:])
                if context_length < 512:
                    await cmd_reply(
                        update.effective_message, context, "❌ Context length must be >= 512"
                    )
                    return
            except ValueError:
                await cmd_reply(update.effective_message, context, "❌ Invalid context length value")
                return
        elif arg.startswith("id="):
            identifier = arg[3:]

    config = LoadConfig(gpu=gpu, context_length=context_length, identifier=identifier)

    try:
        await cli.load_model(model, config)
        await cmd_reply(update.effective_message, context, f"✅ Model {model} loaded successfully.")
    except LmsCliError as e:
        await cmd_reply(update.effective_message, context, f"❌ Load failed: {e}")


@require_owner
async def unload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await _send_unload_keyboard(update, context)
        return

    identifier = args[0]

    try:
        await cli.unload_model(identifier)
        await cmd_reply(update.effective_message, context, f"✅ Model {identifier} unloaded.")
    except LmsCliError as e:
        await cmd_reply(update.effective_message, context, f"❌ {e}")
