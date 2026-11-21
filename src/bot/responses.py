"""Shared helpers for delivering model output to Telegram."""

from __future__ import annotations

import logging

from telegram.error import BadRequest

from src.bot.formatting import format_response, html_to_plain, split_message, strip_think_tags

logger = logging.getLogger(__name__)


def history_content(raw_text: str) -> str:
    """Return the text to persist in chat history: the reply without ``<think>`` blocks."""
    return strip_think_tags(raw_text)


async def send_response(placeholder_message, raw_text: str, reply_markup=None) -> None:
    """Edit the placeholder with the first chunk; send overflow as follow-up messages.

    Chunks are sent as HTML. If Telegram rejects a chunk, that chunk is re-sent as
    plain text (tags removed, entities decoded) so the user never sees raw markup.
    *reply_markup* (e.g. a Regenerate button) is attached to the last chunk only.
    """
    chunks = split_message(format_response(raw_text))
    last = len(chunks) - 1

    def markup_for(index: int):
        return reply_markup if index == last else None

    try:
        await placeholder_message.edit_text(
            chunks[0], parse_mode="HTML", reply_markup=markup_for(0)
        )
    except BadRequest as err:
        logger.warning("HTML send failed (%s), retrying as plain text", err)
        await placeholder_message.edit_text(
            html_to_plain(chunks[0]), reply_markup=markup_for(0)
        )

    for index, chunk in enumerate(chunks[1:], start=1):
        try:
            await placeholder_message.reply_text(
                chunk, parse_mode="HTML", reply_markup=markup_for(index)
            )
        except BadRequest as err:
            logger.warning("HTML send failed for overflow chunk (%s), sending plain", err)
            await placeholder_message.reply_text(
                html_to_plain(chunk), reply_markup=markup_for(index)
            )
