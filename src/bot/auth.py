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
            logger.debug("Unauthorized access attempt dropped")
            await update.effective_message.reply_text("⛔ Access denied.")
            return
        return await func(update, context)

    return wrapper
