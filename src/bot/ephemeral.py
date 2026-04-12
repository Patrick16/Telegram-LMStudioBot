"""Ephemeral command-response helpers.

Provides send/edit/delete-after-delay behaviour for command-generated
status messages.  The persistent menu message and chat/inference replies
are intentionally excluded — only command confirmations auto-delete.
"""

import asyncio
import logging

from telegram import Message
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

DEFAULT_DELAY = 5  # seconds


async def _delete_after(message: Message, delay: float) -> None:
    """Wait *delay* seconds then delete *message*. Failures are silently logged."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except BadRequest as e:
        logger.debug("Could not delete ephemeral message %s: %s", message.message_id, e)


def schedule_delete(message: Message, delay: float = DEFAULT_DELAY) -> None:
    """Schedule *message* for deletion after *delay* seconds.

    Creates a fire-and-forget asyncio task — no await needed.
    """
    asyncio.ensure_future(_delete_after(message, delay))


async def reply_ephemeral(
    source_message: Message,
    text: str,
    delay: float = DEFAULT_DELAY,
    **kwargs,
) -> Message:
    """Reply to *source_message* and schedule the reply for auto-deletion."""
    msg = await source_message.reply_text(text, **kwargs)
    schedule_delete(msg, delay)
    return msg
