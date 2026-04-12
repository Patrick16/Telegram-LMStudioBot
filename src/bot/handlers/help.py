from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.handlers.menu import menu_command_handler

MENU_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("/menu")]],
    resize_keyboard=True,
    is_persistent=True,
)

HELP_TEXT = """🤖 *LMStudioBot* — Control LM Studio from Telegram

*Model Management*
/models — List available models on disk
/loaded — List currently loaded models
/load `<model>` `[gpu=max|auto|0.0-1.0]` `[ctx=N]` `[id=name]` — Load a model
/unload `<model>` — Unload a model

*Chat Sessions*
/newchat `[name]` — Create a new chat session
/chats — List all chat sessions
/switchchat `<id_or_number>` — Switch active chat
/removechat `<id_or_number>` — Delete a chat session

*Settings*
/setprompt `[prompt]` — Set/clear the system prompt
/set `<setting>` `<value>` — Adjust inference settings
  ↳ temperature, max\\_tokens, top\\_p, top\\_k, repeat\\_penalty, stop\\_strings, seed

*Chat*
Send any text message — Chat with the model
Send a photo — Analyze image with vision model
/regenerate — Regenerate last model answer

/menu — Open the inline menu
/help — Show this help message"""


@require_owner
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📌 Tap the button below anytime to open the menu.",
        reply_markup=MENU_REPLY_KEYBOARD,
    )
    await menu_command_handler.__wrapped__(update, context)


@require_owner
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")
