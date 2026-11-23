"""Files sent to the bot: text/code, PDF, DOCX and images sent as files.

All the safety checks live in :mod:`src.bot.files`; this module only talks to Telegram.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot import files
from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral
from src.bot.formatting import _format_size
from src.bot.handlers.vision import model_supports_vision, run_image_bytes
from src.bot.i18n import mark, tr
from src.bot.services import inference

logger = logging.getLogger(__name__)

REJECTION_MESSAGES = {
    "refused": mark(
        "🛡 Programs, archives and documents with macros are not opened, for safety."
    ),
    "unsupported": mark(
        "❌ This file type is not supported. Send text or code, PDF, DOCX or an image."
    ),
    "mismatch": mark(
        "🛡 The file's content does not match its name, so it was not opened."
    ),
    "binary": mark("❌ This file is not text, so it cannot be read."),
    "damaged": mark("❌ The file could not be read: it looks damaged."),
    "encrypted": mark("❌ The PDF is password-protected."),
    "empty": mark("❌ No text found in the file (a scanned PDF needs OCR)."),
    "timeout": mark("❌ Reading the file took too long and was stopped."),
    "no_pdf_support": mark(
        "❌ PDF support is not installed. Run: pip install -r requirements.txt"
    ),
}

DEFAULT_QUESTION = mark("Summarize this file and say what it contains.")


def rejection_text(code: str) -> str:
    return tr(REJECTION_MESSAGES.get(code, REJECTION_MESSAGES["damaged"]))


@require_owner
async def document_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    document = message.document
    name = files.safe_name(document.file_name)
    caption = (message.caption or "").strip()

    if document.file_size and document.file_size > files.MAX_FILE_BYTES:
        await message.reply_text(tr(
            "❌ The file is too large ({size}). The limit is {limit}.",
            size=_format_size(document.file_size), limit=_format_size(files.MAX_FILE_BYTES),
        ))
        return

    telegram_file = await context.bot.get_file(document.file_id)
    data = bytes(await telegram_file.download_as_bytearray())   # kept in memory only
    if len(data) > files.MAX_FILE_BYTES:
        await message.reply_text(tr(
            "❌ The file is too large ({size}). The limit is {limit}.",
            size=_format_size(len(data)), limit=_format_size(files.MAX_FILE_BYTES),
        ))
        return

    try:
        kind = files.classify(name, data)
        if kind == "image":
            if await model_supports_vision(message, context):
                await run_image_bytes(
                    message, context, data, files.image_suffix(name, data), caption
                )
            return
        result = await files.extract(kind, data)
    except files.FileRejected as exc:
        logger.info("File %r rejected: %s", name, exc)
        await message.reply_text(rejection_text(exc.code))
        return

    session = inference.ensure_session(context.bot_data["store"])
    files.truncate(result, await inference.file_char_limit(session, context))
    if result.truncated:
        await reply_ephemeral(message, tr(
            "✂️ The file is long: only the first {count} characters were sent to the model.",
            count=len(result.text),
        ))
    prompt = files.build_prompt(name, result, caption or tr(DEFAULT_QUESTION))
    await inference.run_text_turn(
        message, context, prompt, status=tr("📎 Reading {name}...", name=name)
    )
