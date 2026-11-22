"""Ephemeral command-response helpers.

Provides send/edit/delete-after-delay behaviour for command-generated
status messages.  The persistent menu message and chat/inference replies
are intentionally excluded — only command confirmations auto-delete.
"""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest

from src.bot.i18n import tr

logger = logging.getLogger(__name__)

CB_DISMISS = "ui:dismiss"

DEFAULT_DELAY = 5  # seconds
ERROR_DELAY = 15  # error messages stay longer so they can be read


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
    if text.startswith("❌"):
        delay = max(delay, ERROR_DELAY)
    schedule_delete(msg, delay)
    return msg


async def reply_error(
    source_message: Message,
    text: str,
    actions: tuple[tuple[str, str], ...] = (),
    **kwargs,
) -> Message:
    """Reply with an error that stays until dismissed, with buttons for what to do next.

    *actions* are ``(label, callback_data)`` pairs; a "Close" button is always added.
    """
    rows = []
    if actions:
        rows.append([InlineKeyboardButton(label, callback_data=data) for label, data in actions])
    rows.append([InlineKeyboardButton(tr("✖ Close"), callback_data=CB_DISMISS)])
    return await source_message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(rows), **kwargs
    )
