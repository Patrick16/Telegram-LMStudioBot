import asyncio
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.bot.i18n import tr
from src.bot.auth import require_owner
from src.bot.ephemeral import reply_error, schedule_delete
from src.bot.formatting import _format_size
from src.bot.pagination import nav_row, paginate
from src.lms import cli, sdk
from src.lms.cli import LmsCliError
from src.storage.models import LoadConfig

logger = logging.getLogger(__name__)

_CMD_MSG_KEY = "cmd_msg"


def _UNREACHABLE_TEXT() -> str:
    return tr("❌ Could not connect to LM Studio. Is it running?")


def _UNREACHABLE_ACTIONS() -> tuple[tuple[str, str], ...]:
    """Buttons offered when LM Studio cannot be reached."""
    return ((tr("🔄 Retry"), "menu:models"), (tr("📊 Status"), "menu:status"))


async def cmd_reply(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
    ephemeral: bool = True,
) -> Message:
    """Send or edit the single persistent command-response message for this chat.

    Edits the previously stored command message if possible so the chat stays
    tidy (one response slot per chat). Falls back to a fresh reply when the
    old message can no longer be edited (deleted, too old, etc.).
    When *ephemeral* is True, schedules the message for auto-deletion after 5 s.
    """
    prev: Message | None = context.chat_data.get(_CMD_MSG_KEY)
    if prev is not None:
        try:
            edited = await prev.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            if isinstance(edited, Message):  # edit_text returns True for inline messages
                context.chat_data[_CMD_MSG_KEY] = edited
                if ephemeral:
                    schedule_delete(edited)
                return edited
        except BadRequest:
            pass  # stale / deleted / unchanged — fall through to fresh message

    sent = await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    context.chat_data[_CMD_MSG_KEY] = sent
    if ephemeral:
        schedule_delete(sent)
    return sent


async def perform_load(
    context: ContextTypes.DEFAULT_TYPE,
    model: str,
    *,
    gpu: str | None = None,
    context_length: int | None = None,
    identifier: str | None = None,
) -> str:
    """Load *model*, applying staged model settings, and bind it to the active chat.

    Explicit arguments win over staged values (set via model presets or the model
    settings menu). Staged values are consumed only after a successful load.
    """
    staged = context.chat_data.get("staged_model_settings") or {}
    config = LoadConfig(
        gpu=gpu or staged.get("gpu") or "auto",
        context_length=context_length if context_length is not None
        else staged.get("context_length"),
        identifier=identifier or staged.get("identifier"),
    )
    result = await cli.load_model(model, config)
    context.chat_data.pop("staged_model_settings", None)

    store = context.bot_data.get("store")
    session = store.get_active_session() if store is not None else None
    if session is not None:
        session.model_identifier = config.identifier or model
        store.update_session(session)
    return result


async def perform_unload(context: ContextTypes.DEFAULT_TYPE, identifier: str) -> str:
    """Unload a model and clear it from any chat that was bound to it."""
    result = await cli.unload_model(identifier)
    store = context.bot_data.get("store")
    if store is not None:
        for session in store.list_sessions():
            if session.model_identifier == identifier:
                session.model_identifier = None
                store.update_session(session)
    return result


def _format_downloaded_list(models) -> str:
    if not models:
        return tr("No models found.")

    lines = []
    for model in models:
        model_key = getattr(model, "model_key", "unknown")
        info = getattr(model, "info", None)
        size_bytes = getattr(info, "size_bytes", 0) or 0
        lines.append(f"• {html.escape(str(model_key))}  {_format_size(int(size_bytes))}")

    return tr("📦 Available models:") + "\n" + "\n".join(lines)


def _format_loaded_list(handles) -> str:
    if not handles:
        return tr("No models are currently loaded.")

    lines = []
    for handle in handles:
        # Use direct attributes to avoid calling .get_info() which may trigger
        # a failed websocket reconnection on inactive connections
        identifier = getattr(handle, "identifier", "unknown")
        size_bytes = getattr(handle, "size_bytes", 0) or 0
        lines.append(f"• {html.escape(str(identifier))}  {_format_size(int(size_bytes))}")

    return tr("🧠 Loaded models:") + "\n" + "\n".join(lines)


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
    return "\n" + tr(
        "(showing 100 of {total}; {hidden} model(s) not shown)", total=total, hidden=total - 100
    )


def _build_load_keyboard(models, loaded_keys: set[str], page: int = 0) -> InlineKeyboardMarkup:
    shown, page, pages = paginate(models, page)
    rows = []
    for model in shown:
        model_key = getattr(model, "model_key", "unknown")
        info = getattr(model, "info", None)
        size_bytes = getattr(info, "size_bytes", 0) or 0
        prefix = "🟢 " if model_key in loaded_keys else ""
        label = _truncate_button_label(f"{prefix}{model_key}  {_format_size(int(size_bytes))}")
        callback_data = _truncate_callback_data("models:loadmodel:", model_key)
        rows.append([InlineKeyboardButton(label, callback_data=callback_data)])
    navigation = nav_row("models:loadpage:", page, pages)
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(rows)


def _load_prompt(total: int, page: int) -> str:
    _, page, pages = paginate(range(total), page)
    if pages > 1:
        return tr("Select a model to load (page {page}/{pages}):", page=page + 1, pages=pages)
    return tr("Select a model to load:")


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
        await reply_error(message, _UNREACHABLE_TEXT(), _UNREACHABLE_ACTIONS())
        return

    if not models:
        await cmd_reply(message, context, tr("No models available to load."))
        return

    # Extract model keys without calling .get_info() to avoid triggering
    # websocket reconnection on inactive connections
    loaded_keys = {
        getattr(handle, "identifier", None)
        for handle in handles
        if handle is not None and getattr(handle, "identifier", None)
    }
    keyboard = _build_load_keyboard(models, loaded_keys)
    await cmd_reply(
        message, context,
        _load_prompt(len(models), 0),
        reply_markup=keyboard,
        ephemeral=False,
    )


async def _send_unload_keyboard(target, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = _resolve_message(target)
    config = context.bot_data["config"]

    try:
        handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
    except Exception:
        await reply_error(message, _UNREACHABLE_TEXT(), _UNREACHABLE_ACTIONS())
        return

    if not handles:
        await cmd_reply(message, context, "No models are currently loaded.")
        return

    keyboard = _build_unload_keyboard(handles)
    note = _build_limit_note(len(handles))
    await cmd_reply(
        message, context,
        tr("Select a model to unload:") + note,
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
        await reply_error(update.effective_message, _UNREACHABLE_TEXT(), _UNREACHABLE_ACTIONS())


@require_owner
async def loaded_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]

    try:
        handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
        await cmd_reply(
            update.effective_message, context, _format_loaded_list(handles), parse_mode="HTML"
        )
    except Exception:
        await reply_error(update.effective_message, _UNREACHABLE_TEXT(), _UNREACHABLE_ACTIONS())


@require_owner
async def load_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await _send_load_keyboard(update, context)
        return

    model = args[0]
    gpu = None
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
                            tr("❌ Invalid gpu value: must be max, auto, or a float "
                               "between 0.0 and 1.0")
                        )
                        return
                except ValueError:
                    await cmd_reply(
                        update.effective_message, context,
                        tr("❌ Invalid gpu value: must be max, auto, or a float between 0.0 and 1.0")
                    )
                    return
        elif arg.startswith("ctx="):
            try:
                context_length = int(arg[4:])
                if context_length < 512:
                    await cmd_reply(
                        update.effective_message, context, tr("❌ Context length must be >= 512")
                    )
                    return
            except ValueError:
                await cmd_reply(
                    update.effective_message, context, tr("❌ Invalid context length value")
                )
                return
        elif arg.startswith("id="):
            identifier = arg[3:]

    try:
        await perform_load(
            context, model, gpu=gpu, context_length=context_length, identifier=identifier
        )
        await cmd_reply(
            update.effective_message, context,
            tr("✅ Model {name} loaded successfully.", name=model),
        )
    except LmsCliError as e:
        await reply_error(
            update.effective_message, tr("❌ Load failed: {error}", error=e),
            ((tr("📦 Models"), "menu:models"),),
        )


@require_owner
async def unload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await _send_unload_keyboard(update, context)
        return

    identifier = args[0]

    try:
        await perform_unload(context, identifier)
        await cmd_reply(
            update.effective_message, context, tr("✅ Model {name} unloaded.", name=identifier)
        )
    except LmsCliError as e:
        await cmd_reply(update.effective_message, context, f"❌ {e}")
