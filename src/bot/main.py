import logging

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.bot.config import BotConfig
from src.bot.handlers.chats import (
    chats_command,
    newchat_command,
    removechat_command,
    switchchat_command,
)
from src.bot.handlers.help import help_command, start_command
from src.bot.handlers.messages import regenerate_command, text_message_handler
from src.bot.handlers.models import (
    load_command,
    loaded_command,
    models_command,
    unload_command,
)
from src.bot.handlers.settings import set_command, setprompt_command
from src.bot.handlers.vision import photo_message_handler
from src.storage.session_store import SessionStoreManager

logger = logging.getLogger(__name__)


async def error_handler(update, context) -> None:
    logger.error("Unhandled exception: %s", context.error)


def main() -> None:
    load_dotenv()
    config = BotConfig()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    )

    store = SessionStoreManager(config.SESSIONS_FILE)
    store.load()

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.bot_data["config"] = config
    app.bot_data["store"] = store

    # Help
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # Model management
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("loaded", loaded_command))
    app.add_handler(CommandHandler("load", load_command))
    app.add_handler(CommandHandler("unload", unload_command))

    # Chat sessions
    app.add_handler(CommandHandler("newchat", newchat_command))
    app.add_handler(CommandHandler("chats", chats_command))
    app.add_handler(CommandHandler("switchchat", switchchat_command))
    app.add_handler(CommandHandler("removechat", removechat_command))

    # Settings
    app.add_handler(CommandHandler("setprompt", setprompt_command))
    app.add_handler(CommandHandler("set", set_command))

    # Inference
    app.add_handler(CommandHandler("regenerate", regenerate_command))
    app.add_handler(MessageHandler(filters.PHOTO, photo_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Starting LMStudioBot...")
    app.run_polling()


if __name__ == "__main__":
    main()
