"""Unit tests for src.bot.ephemeral."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.bot.ephemeral import (
    DEFAULT_DELAY,
    _delete_after,
    reply_ephemeral,
    schedule_delete,
)


@pytest.mark.asyncio
async def test_delete_after_deletes_message():
    msg = AsyncMock()
    msg.message_id = 42
    await _delete_after(msg, 0)
    msg.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_after_handles_bad_request():
    from telegram.error import BadRequest

    msg = AsyncMock()
    msg.message_id = 99
    msg.delete.side_effect = BadRequest("Message to delete not found")
    # Should not raise
    await _delete_after(msg, 0)
    msg.delete.assert_awaited_once()


def test_schedule_delete_creates_task():
    msg = AsyncMock()
    msg.message_id = 1

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with patch("src.bot.ephemeral.asyncio.ensure_future") as mock_ef:
            schedule_delete(msg, delay=3)
            mock_ef.assert_called_once()
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.mark.asyncio
async def test_reply_ephemeral_sends_and_schedules():
    source = AsyncMock()
    reply_msg = AsyncMock()
    reply_msg.message_id = 10
    source.reply_text.return_value = reply_msg

    with patch("src.bot.ephemeral.schedule_delete") as mock_sched:
        result = await reply_ephemeral(source, "hello", delay=7)

    source.reply_text.assert_awaited_once_with("hello")
    mock_sched.assert_called_once_with(reply_msg, 7)
    assert result is reply_msg


@pytest.mark.asyncio
async def test_reply_ephemeral_passes_kwargs():
    source = AsyncMock()
    reply_msg = AsyncMock()
    source.reply_text.return_value = reply_msg

    with patch("src.bot.ephemeral.schedule_delete"):
        await reply_ephemeral(source, "hi", parse_mode="HTML")

    source.reply_text.assert_awaited_once_with("hi", parse_mode="HTML")


@pytest.mark.asyncio
async def test_reply_ephemeral_uses_default_delay():
    source = AsyncMock()
    reply_msg = AsyncMock()
    source.reply_text.return_value = reply_msg

    with patch("src.bot.ephemeral.schedule_delete") as mock_sched:
        await reply_ephemeral(source, "test")

    mock_sched.assert_called_once_with(reply_msg, DEFAULT_DELAY)
