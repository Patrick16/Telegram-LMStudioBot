import logging
import os
import sys
import tempfile

from dotenv import load_dotenv
from filelock import FileLock, Timeout
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from src.bot import i18n
from src.bot.commands import bot_commands
from src.bot.config import BotConfig
from src.bot.handlers.chats import (
    chats_command,
    newchat_command,
    removechat_command,
    renamechat_command,
    switchchat_command,
)
from src.bot.handlers.help import help_command, start_command
from src.bot.handlers.menu import menu_callback_handler, menu_command_handler
from src.bot.handlers.messages import regenerate_command, stop_command, text_message_handler
from src.bot.handlers.models import (
    load_command,
    loaded_command,
    models_command,
    unload_command,
)
from src.bot.handlers.quickbar import quickbar_message_handler
from src.bot.handlers.settings import set_command, setprompt_command
from src.bot.handlers.status import status_command
from src.bot.handlers.vision import photo_message_handler
from src.storage.session_store import SessionStoreManager

logger = logging.getLogger(__name__)

_LOCK_FILE = os.path.join(tempfile.gettempdir(), "lmstudiobot.lock")
_instance_lock = FileLock(_LOCK_FILE)


def _acquire_lock() -> None:
    """Exit immediately if another instance is already running.

    Uses an OS-level file lock, which is released automatically if the process
    dies, so there are no stale locks and no PID probing (``os.kill(pid, 0)``
    would terminate the process on Windows).
    """
    try:
        _instance_lock.acquire(timeout=0)
    except Timeout:
        print(
            "ERROR: Bot is already running. Stop it before starting a new instance.",
            file=sys.stderr,
        )
        sys.exit(1)


def _release_lock() -> None:
    try:
        _instance_lock.release()
    except OSError:
        pass


async def post_init(app: Application) -> None:
    # Default list in English plus a Russian one for clients set to Russian.
    await app.bot.set_my_commands(bot_commands("en"))
    await app.bot.set_my_commands(bot_commands("ru"), language_code="ru")


async def error_handler(update, context) -> None:
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)


def register_handlers(app: Application) -> None:
    """Attach every command, callback and message handler to *app*."""
    # Help
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command_handler))
    app.add_handler(CommandHandler("status", status_command))

    # Inline menu callback handler
    # block=False: long actions (model load, regenerate) must not freeze other updates.
    app.add_handler(CallbackQueryHandler(menu_callback_handler, block=False))

    # Model management
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("loaded", loaded_command))
    app.add_handler(CommandHandler("load", load_command, block=False))
    app.add_handler(CommandHandler("unload", unload_command, block=False))

    # Chat sessions
    app.add_handler(CommandHandler("newchat", newchat_command))
    app.add_handler(CommandHandler("chats", chats_command))
    app.add_handler(CommandHandler("switchchat", switchchat_command))
    app.add_handler(CommandHandler("removechat", removechat_command))
    app.add_handler(CommandHandler("renamechat", renamechat_command))

    # Settings
    app.add_handler(CommandHandler("setprompt", setprompt_command))
    app.add_handler(CommandHandler("set", set_command))

    # Inference
    # Generation runs in its own task so /stop and the menu stay responsive.
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("regenerate", regenerate_command, block=False))
    # Bottom-keyboard shortcuts must win over the generic text handler.
    app.add_handler(quickbar_message_handler())
    app.add_handler(MessageHandler(filters.PHOTO, photo_message_handler, block=False))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler, block=False)
    )


def main() -> None:
    _acquire_lock()
    try:
        load_dotenv()
        config = BotConfig()

        logging.basicConfig(
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        )
        # httpx logs full request URLs, which contain the bot token.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        store = SessionStoreManager(
            config.SESSIONS_FILE,
            histories_dir=config.HISTORIES_DIR,
            model_presets_file=config.MODEL_PRESETS_FILE,
            session_presets_file=config.SESSION_PRESETS_FILE,
        )
        store.load()
        i18n.set_language(store.get_language())

        # Ensure preset/history directories exist
        os.makedirs(config.HISTORIES_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(config.MODEL_PRESETS_FILE), exist_ok=True)

        app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

        app.bot_data["config"] = config
        app.bot_data["store"] = store

        register_handlers(app)

        # Error handler
        app.add_error_handler(error_handler)

        logger.info("Starting LMStudioBot...")
        app.run_polling(drop_pending_updates=True)
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
