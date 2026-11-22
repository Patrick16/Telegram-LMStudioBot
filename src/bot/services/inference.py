"""One code path for every model turn: text, image and regenerate.

Responsibilities: build the context, stream the reply, deliver it to Telegram,
and persist the turn *transactionally* — nothing is written to history unless the
model actually answered, so failures never leave dangling or lost messages.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import timedelta

import lmstudio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TelegramError

from src.bot.i18n import mark, tr
from src.bot.formatting import format_stream_preview
from src.bot.responses import history_content, send_response
from src.bot.services.generation import get_generations
from src.lms import sdk
from src.storage.models import ChatMessage

logger = logging.getLogger(__name__)

MSG_NO_CHAT = mark("❌ No active chat. Use /newchat first.")
MSG_NOTHING_TO_REGENERATE = mark("❌ Nothing to regenerate (no messages in this chat).")
MSG_BUSY = mark("⏳ A reply is already being generated. Send /stop to cancel it.")
MSG_NO_RESPONSE = mark("❌ No response from model.")
MSG_STOPPED = mark("⏹ Stopped.")
CB_STOP = "gen:stop"
CB_REGENERATE = "gen:regen"
CB_RETRY = "gen:retry"
CB_CONTINUE = "gen:continue"
CB_NEW_CHAT = "gen:newchat"
CB_MENU = "gen:menu"
CONTINUE_PROMPT = "Continue."

STREAM_EDIT_INTERVAL = 1.5  # seconds between live edits (Telegram rate limits apply)
TYPING_INTERVAL = 4.0       # a chat action lasts ~5s


def generating_keyboard() -> InlineKeyboardMarkup:
    """Shown under the placeholder while a reply is being generated."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(tr("⏹ Stop"), callback_data=CB_STOP)]])


def reply_keyboard() -> InlineKeyboardMarkup:
    """Shown under a finished reply."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr("🔄 Regenerate"), callback_data=CB_REGENERATE),
            InlineKeyboardButton(tr("▶ Continue"), callback_data=CB_CONTINUE),
        ],
        [
            InlineKeyboardButton(tr("➕ New chat"), callback_data=CB_NEW_CHAT),
            InlineKeyboardButton(tr("📋 Menu"), callback_data=CB_MENU),
        ],
    ])


_UNREACHABLE_ERRORS = (
    lmstudio.LMStudioWebsocketError, lmstudio.LMStudioTimeoutError, ConnectionError, OSError,
)


def _is_unreachable(exc: BaseException | None) -> bool:
    return isinstance(exc, _UNREACHABLE_ERRORS)


def error_keyboard(exc: BaseException | None, retry_callback: str | None):
    """Action buttons for a failed turn: load a model, retry, check LM Studio's status."""
    rows = []
    if isinstance(exc, lmstudio.LMStudioModelNotFoundError):
        rows.append([InlineKeyboardButton(tr("📦 Load a model"), callback_data="models:load")])
    if retry_callback:
        rows.append([InlineKeyboardButton(tr("🔁 Retry"), callback_data=retry_callback)])
    if _is_unreachable(exc):
        rows.append([InlineKeyboardButton(tr("📊 Status"), callback_data="menu:status")])
    return InlineKeyboardMarkup(rows) if rows else None


MSG_INTERRUPTED = mark(
    "⚠️ The connection to LM Studio dropped — the reply above is incomplete."
)


def describe_error(exc: BaseException) -> str:
    """Turn an exception into a short, accurate message for the user."""
    if isinstance(exc, lmstudio.LMStudioModelNotFoundError):
        return tr("❌ No model is loaded. Load one from the menu or with /load.")
    if _is_unreachable(exc):
        return tr("❌ LM Studio is unreachable. Is it running?")
    if isinstance(exc, TelegramError):
        return tr("❌ Telegram error: {error}", error=exc)
    return tr("❌ Generation failed: {error}", error=exc or type(exc).__name__)


async def _safe_edit(message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramError as exc:
        logger.warning("Could not edit status message: %s", exc)


async def _keep_typing(message) -> None:
    """Show the "typing…" chat action until cancelled."""
    while True:
        try:
            await message.chat.send_action("typing")
        except TelegramError:
            pass
        await asyncio.sleep(TYPING_INTERVAL)


async def _generate(
    message,
    context,
    session,
    stream,
    *,
    status: str,
    persist,
    retry_callback: str | None = None,
    retry_text: str | None = None,
) -> None:
    """Stream *stream* live, deliver the final reply and call ``persist(text)`` on success."""
    generations = get_generations(context)
    chat_id = message.chat_id
    if generations.is_active(chat_id):
        await message.reply_text(tr(MSG_BUSY))
        return

    placeholder = await message.reply_text(status, reply_markup=generating_keyboard())
    text = ""
    interrupted = False
    last_edit = time.monotonic()
    shown = status
    interval = STREAM_EDIT_INTERVAL

    async with generations.track(chat_id):
        typing = asyncio.create_task(_keep_typing(message))
        try:
            try:
                async for chunk in stream:
                    text += chunk
                    now = time.monotonic()
                    if now - last_edit < interval:
                        continue
                    preview = format_stream_preview(text)
                    if preview == shown:
                        continue
                    last_edit = now
                    try:
                        await placeholder.edit_text(
                            preview, reply_markup=generating_keyboard()
                        )
                        shown = preview
                    except RetryAfter as exc:
                        wait = exc.retry_after
                        seconds = wait.total_seconds() if isinstance(wait, timedelta) else wait
                        interval = max(interval, float(seconds) + 1)
                    except TelegramError as exc:  # not modified, message gone, ...
                        logger.debug("Live edit skipped: %s", exc)
            except sdk.StreamInterrupted:
                interrupted = True
        except asyncio.CancelledError:
            await _safe_edit(placeholder, tr(MSG_STOPPED))
            return
        except Exception as exc:
            logger.error("Inference error: %s", exc)
            if retry_text is not None:
                context.chat_data["retry_text"] = retry_text
            await _safe_edit(
                placeholder, describe_error(exc), error_keyboard(exc, retry_callback)
            )
            return
        finally:
            typing.cancel()

        stored = history_content(text)
        if not stored:
            await _safe_edit(
                placeholder, tr(MSG_NO_RESPONSE), error_keyboard(None, retry_callback)
            )
            return

        try:
            await send_response(
                placeholder, text, reply_markup=reply_keyboard(),
                show_reasoning=session.settings.show_reasoning,
            )
        except Exception as exc:
            logger.error("Could not deliver reply: %s", exc)
            await _safe_edit(placeholder, describe_error(exc))
            return

        persist(stored)
        if interrupted:
            try:
                await message.reply_text(tr(MSG_INTERRUPTED))
            except TelegramError:
                pass


async def _context_budget(session, context) -> int | None:
    """Character budget for history, or None if the model's context size is unknown."""
    config = context.bot_data["config"]
    try:
        length = await sdk.get_context_length(
            session.model_identifier, host=config.LMS_HOST, port=config.LMS_PORT
        )
    except Exception as exc:  # LM Studio down / no model: the turn itself will report it
        logger.debug("Could not read context length: %s", exc)
        return None
    settings = session.settings
    return sdk.compute_context_budget(length, settings.max_tokens, settings.system_prompt)


def ensure_session(store):
    """Return the active chat, creating "Chat N" on first use so users can just type."""
    session = store.get_active_session()
    if session is None:
        session = store.create_session(tr("Chat {n}", n=len(store.list_sessions()) + 1))
    return session


def _stream_args(context):
    config = context.bot_data["config"]
    return {"host": config.LMS_HOST, "port": config.LMS_PORT}


async def run_text_turn(message, context, user_text: str) -> None:
    store = context.bot_data["store"]
    session = ensure_session(store)

    user_msg = ChatMessage(role="user", content=user_text)
    # The prompt includes the new user message, but it is only persisted with the reply.
    context_msgs = sdk.trim_history(
        store.load_history(session.id) + [user_msg],
        session.settings.history_policy,
        await _context_budget(session, context),
    )
    stream = sdk.chat_stream(session, history_messages=context_msgs, **_stream_args(context))

    def persist(reply: str) -> None:
        store.append_messages(
            session.id, [user_msg, ChatMessage(role="assistant", content=reply)]
        )

    await _generate(
        message, context, session, stream, status=tr("⏳ Thinking..."), persist=persist,
        retry_callback=CB_RETRY, retry_text=user_text,
    )


async def run_image_turn(message, context, image_path: str, caption: str) -> None:
    store = context.bot_data["store"]
    session = ensure_session(store)

    user_content = caption or "What do you see in this image?"
    # The temp file is deleted after the turn, so history keeps only a text marker.
    user_msg = ChatMessage(role="user", content=f"[image] {user_content}")
    # The SDK appends the current (image) message itself, so context excludes it.
    context_msgs = sdk.trim_history(
        store.load_history(session.id),
        session.settings.history_policy,
        await _context_budget(session, context),
    )
    stream = sdk.infer_with_image(
        session, image_path, caption=caption, history_messages=context_msgs,
        **_stream_args(context),
    )

    def persist(reply: str) -> None:
        store.append_messages(
            session.id, [user_msg, ChatMessage(role="assistant", content=reply)]
        )

    await _generate(
        message, context, session, stream, status=tr("⏳ Processing image..."), persist=persist
    )


async def run_retry(message, context) -> None:
    """Re-send the text of the last failed turn."""
    text = context.chat_data.pop("retry_text", None)
    if not text:
        await message.reply_text(tr("Nothing to retry."))
        return
    await run_text_turn(message, context, text)


async def run_regenerate(message, context) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await message.reply_text(tr(MSG_NO_CHAT))
        return

    history = store.load_history(session.id)
    if history and history[-1].role == "assistant":
        history = history[:-1]  # the old answer stays in storage until the new one succeeds
    if not history or history[-1].role != "user":
        await message.reply_text(tr(MSG_NOTHING_TO_REGENERATE))
        return

    context_msgs = sdk.trim_history(
        history, session.settings.history_policy, await _context_budget(session, context)
    )
    stream = sdk.chat_stream(session, history_messages=context_msgs, **_stream_args(context))

    def persist(reply: str) -> None:
        store.replace_last_assistant(session.id, ChatMessage(role="assistant", content=reply))

    await _generate(
        message, context, session, stream, status=tr("⏳ Regenerating..."), persist=persist,
        retry_callback=CB_REGENERATE,
    )


def cleanup_temp_file(path: str | None) -> None:
    """Best-effort removal of a downloaded temp file."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass
