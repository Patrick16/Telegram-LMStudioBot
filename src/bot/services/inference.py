"""One code path for every model turn: text, image and regenerate.

Responsibilities: build the context, stream the reply, deliver it to Telegram,
and persist the turn *transactionally* — nothing is written to history unless the
model actually answered, so failures never leave dangling or lost messages.
"""

from __future__ import annotations

import asyncio
import logging
import os

import lmstudio
from telegram.error import TelegramError

from src.bot.responses import history_content, send_response
from src.bot.services.generation import get_generations
from src.lms import sdk
from src.storage.models import ChatMessage

logger = logging.getLogger(__name__)

MSG_NO_CHAT = "❌ No active chat. Use /newchat first."
MSG_NOTHING_TO_REGENERATE = "❌ Nothing to regenerate (no messages in this chat)."
MSG_BUSY = "⏳ A reply is already being generated. Send /stop to cancel it."
MSG_NO_RESPONSE = "❌ No response from model."
MSG_STOPPED = "⏹ Stopped."
MSG_INTERRUPTED = (
    "⚠️ The connection to LM Studio dropped — the reply above is incomplete."
)


def describe_error(exc: BaseException) -> str:
    """Turn an exception into a short, accurate message for the user."""
    if isinstance(exc, lmstudio.LMStudioModelNotFoundError):
        return "❌ No model is loaded. Load one from the menu or with /load."
    if isinstance(
        exc,
        (lmstudio.LMStudioWebsocketError, lmstudio.LMStudioTimeoutError, ConnectionError, OSError),
    ):
        return "❌ LM Studio is unreachable. Is it running?"
    if isinstance(exc, TelegramError):
        return f"❌ Telegram error: {exc}"
    return f"❌ Generation failed: {exc or type(exc).__name__}"


async def _safe_edit(message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramError as exc:
        logger.warning("Could not edit status message: %s", exc)


async def _generate(
    message,
    context,
    session,
    stream,
    *,
    status: str,
    persist,
) -> None:
    """Stream *stream*, deliver the reply and call ``persist(text)`` on success."""
    generations = get_generations(context)
    chat_id = message.chat_id
    if generations.is_active(chat_id):
        await message.reply_text(MSG_BUSY)
        return

    placeholder = await message.reply_text(status)
    text = ""
    interrupted = False

    async with generations.track(chat_id):
        try:
            try:
                async for chunk in stream:
                    text += chunk
            except sdk.StreamInterrupted:
                interrupted = True
        except asyncio.CancelledError:
            await _safe_edit(placeholder, MSG_STOPPED)
            return
        except Exception as exc:
            logger.error("Inference error: %s", exc)
            await _safe_edit(placeholder, describe_error(exc))
            return

        stored = history_content(text)
        if not stored:
            await _safe_edit(placeholder, MSG_NO_RESPONSE)
            return

        try:
            await send_response(placeholder, text)
        except Exception as exc:
            logger.error("Could not deliver reply: %s", exc)
            await _safe_edit(placeholder, describe_error(exc))
            return

        persist(stored)
        if interrupted:
            try:
                await message.reply_text(MSG_INTERRUPTED)
            except TelegramError:
                pass


def _stream_args(context):
    config = context.bot_data["config"]
    return {"host": config.LMS_HOST, "port": config.LMS_PORT}


async def run_text_turn(message, context, user_text: str) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await message.reply_text(MSG_NO_CHAT)
        return

    user_msg = ChatMessage(role="user", content=user_text)
    # The prompt includes the new user message, but it is only persisted with the reply.
    context_msgs = sdk.trim_history(
        store.load_history(session.id) + [user_msg], session.settings.history_policy
    )
    stream = sdk.chat_stream(session, history_messages=context_msgs, **_stream_args(context))

    def persist(reply: str) -> None:
        store.append_messages(
            session.id, [user_msg, ChatMessage(role="assistant", content=reply)]
        )

    await _generate(message, context, session, stream, status="⏳ Thinking...", persist=persist)


async def run_image_turn(message, context, image_path: str, caption: str) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await message.reply_text(MSG_NO_CHAT)
        return

    user_content = caption or "What do you see in this image?"
    # The temp file is deleted after the turn, so history keeps only a text marker.
    user_msg = ChatMessage(role="user", content=f"[image] {user_content}")
    # The SDK appends the current (image) message itself, so context excludes it.
    context_msgs = sdk.trim_history(
        store.load_history(session.id), session.settings.history_policy
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
        message, context, session, stream, status="⏳ Processing image...", persist=persist
    )


async def run_regenerate(message, context) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await message.reply_text(MSG_NO_CHAT)
        return

    history = store.load_history(session.id)
    if history and history[-1].role == "assistant":
        history = history[:-1]  # the old answer stays in storage until the new one succeeds
    if not history or history[-1].role != "user":
        await message.reply_text(MSG_NOTHING_TO_REGENERATE)
        return

    context_msgs = sdk.trim_history(history, session.settings.history_policy)
    stream = sdk.chat_stream(session, history_messages=context_msgs, **_stream_args(context))

    def persist(reply: str) -> None:
        store.replace_last_assistant(session.id, ChatMessage(role="assistant", content=reply))

    await _generate(
        message, context, session, stream, status="⏳ Regenerating...", persist=persist
    )


def cleanup_temp_file(path: str | None) -> None:
    """Best-effort removal of a downloaded temp file."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass
