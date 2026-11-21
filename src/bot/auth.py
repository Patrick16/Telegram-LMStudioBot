import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def require_owner(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        config = context.bot_data["config"]
        user = update.effective_user
        if user is None or user.id != config.TELEGRAM_OWNER_ID:
            # Stay silent: replying would reveal the bot and invite spam.
            logger.warning(
                "Ignored update from non-owner user id=%s", user.id if user else None
            )
            return
        return await func(update, context)

    return wrapper
