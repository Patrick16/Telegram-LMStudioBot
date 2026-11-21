from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.handlers.menu import menu_command_handler
from src.bot.services.inference import ensure_session
from src.bot.services.status import build_status_text

MENU_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("/menu")]],
    resize_keyboard=True,
    is_persistent=True,
)

HELP_TEXT = """🤖 <b>LMStudioBot</b> — Control LM Studio from Telegram

<b>Model Management</b>
/models — List available models on disk
/loaded — List currently loaded models
/load <code>&lt;model&gt;</code> <code>[gpu=max|auto|0.0-1.0]</code> <code>[ctx=N]</code> \
<code>[id=name]</code> — Load a model
/unload <code>&lt;model&gt;</code> — Unload a model

<b>Chat Sessions</b>
/newchat <code>[name]</code> — Create a new chat session
/chats — List all chat sessions
/switchchat <code>&lt;id_or_number&gt;</code> — Switch active chat
/removechat <code>&lt;id_or_number&gt;</code> — Delete a chat session
/renamechat <code>&lt;name&gt;</code> — Rename the active chat

<b>Settings</b>
/setprompt <code>[prompt]</code> — Set/clear the system prompt
/set <code>&lt;setting&gt; &lt;value&gt;</code> — Adjust inference settings
  ↳ temperature, max_tokens, top_p, top_k, repeat_penalty, stop_strings, seed

<b>Chat</b>
Send any text message — Chat with the model
Send a photo — Analyze image with vision model
/regenerate — Regenerate last model answer
/stop — Stop the reply being generated

/status — LM Studio and chat status
/menu — Open the inline menu
/help — Show this help message"""


@require_owner
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_session(context.bot_data["store"])
    status = await build_status_text(context)
    await update.effective_message.reply_text(
        "👋 <b>Welcome to LMStudioBot</b>\n"
        "Just send a message to chat, or use the menu below.\n\n" + status,
        reply_markup=MENU_REPLY_KEYBOARD,
        parse_mode="HTML",
    )
    await menu_command_handler.__wrapped__(update, context)


@require_owner
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="HTML")
