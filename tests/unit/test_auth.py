from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.auth import require_owner


@require_owner
async def dummy_handler(update, context):
    return "ok"


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.TELEGRAM_OWNER_ID = 12345
    return cfg


@pytest.fixture
def context(config):
    ctx = MagicMock()
    ctx.bot_data = {"config": config}
    return ctx


def _make_update(user_id: int | None):
    update = MagicMock()
    if user_id is not None:
        update.effective_user.id = user_id
    else:
        update.effective_user = None
    update.effective_message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_authorized_user(context):
    update = _make_update(12345)
    result = await dummy_handler(update, context)
    assert result == "ok"
    update.effective_message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_unauthorized_user(context):
    update = _make_update(99999)
    result = await dummy_handler(update, context)
    assert result is None
    update.effective_message.reply_text.assert_not_called()  # ignored silently


@pytest.mark.asyncio
async def test_no_user(context):
    update = _make_update(None)
    result = await dummy_handler(update, context)
    assert result is None
