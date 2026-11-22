"""Persistent bottom keyboard: one-tap shortcuts that mirror the main menu."""

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from src.bot.handlers.chats import newchat_command
from src.bot.handlers.menu import menu_command_handler
from src.bot.handlers.messages import stop_command
from src.bot.handlers.status import status_command
from src.bot.i18n import LANGUAGES, mark, tr, translate

BTN_MENU = mark("📋 Menu")
BTN_STOP = mark("⏹ Stop")
BTN_NEW_CHAT = mark("➕ New chat")
BTN_STATUS = mark("📊 Status")

# English label -> handler. Incoming text is matched against every language's label.
_ACTIONS = {
    BTN_MENU: menu_command_handler,
    BTN_STOP: stop_command,
    BTN_NEW_CHAT: newchat_command,
    BTN_STATUS: status_command,
}


def quickbar_keyboard() -> ReplyKeyboardMarkup:
    """The bottom keyboard in the active language."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(tr(BTN_MENU)), KeyboardButton(tr(BTN_STOP))],
         [KeyboardButton(tr(BTN_NEW_CHAT)), KeyboardButton(tr(BTN_STATUS))]],
        resize_keyboard=True,
        is_persistent=True,
    )


def _all_labels() -> list[str]:
    return [translate(label, lang) for label in _ACTIONS for lang in LANGUAGES]


def _action_for(text: str):
    for label, action in _ACTIONS.items():
        if any(translate(label, lang) == text for lang in LANGUAGES):
            return action
    return None


async def quickbar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run the command behind a pressed bottom-keyboard button (never sent to the model)."""
    action = _action_for(update.effective_message.text)
    if action is not None:
        await action(update, context)


def quickbar_message_handler() -> MessageHandler:
    return MessageHandler(filters.Text(_all_labels()), quickbar_handler)
