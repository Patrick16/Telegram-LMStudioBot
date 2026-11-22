"""Persistent bottom keyboard: one-tap shortcuts that mirror the main menu."""

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from src.bot.handlers.chats import newchat_command
from src.bot.handlers.menu import menu_command_handler
from src.bot.handlers.messages import stop_command
from src.bot.handlers.status import status_command

BTN_MENU = "📋 Menu"
BTN_STOP = "⏹ Stop"
BTN_NEW_CHAT = "➕ New chat"
BTN_STATUS = "📊 Status"

QUICKBAR_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_MENU), KeyboardButton(BTN_STOP)],
     [KeyboardButton(BTN_NEW_CHAT), KeyboardButton(BTN_STATUS)]],
    resize_keyboard=True,
    is_persistent=True,
)

_ACTIONS = {
    BTN_MENU: menu_command_handler,
    BTN_STOP: stop_command,
    BTN_NEW_CHAT: newchat_command,
    BTN_STATUS: status_command,
}


async def quickbar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run the command behind a pressed bottom-keyboard button (never sent to the model)."""
    action = _ACTIONS.get(update.effective_message.text)
    if action is not None:
        await action(update, context)


def quickbar_message_handler() -> MessageHandler:
    return MessageHandler(filters.Text(list(_ACTIONS)), quickbar_handler)
