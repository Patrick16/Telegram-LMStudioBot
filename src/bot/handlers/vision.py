import logging
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.i18n import tr
from src.bot.auth import require_owner
from src.bot.services import inference
from src.lms import sdk

logger = logging.getLogger(__name__)


async def model_supports_vision(message, context) -> bool:
    """Check the bound/loaded model before anything is downloaded; replies if it cannot."""
    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = inference.ensure_session(store)
    try:
        model_info = await sdk.get_model_info(
            session.model_identifier, host=config.LMS_HOST, port=config.LMS_PORT,
        )
    except Exception as exc:
        logger.warning("Could not query model info: %s", exc)
        await message.reply_text(inference.describe_error(exc))
        return False

    if not bool(getattr(model_info, "vision", False)):
        await message.reply_text(tr("❌ The loaded model does not support image input."))
        return False
    return True


async def run_image_bytes(message, context, data: bytes, suffix: str, caption: str) -> None:
    """Run a vision turn on an image held in memory (e.g. a picture sent as a file)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        image_path = tmp.name
    try:
        await inference.run_image_turn(message, context, image_path, caption)
    finally:
        inference.cleanup_temp_file(image_path)


@require_owner
async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not await model_supports_vision(message, context):
        return

    # Download the highest resolution photo; the temp file is removed after the turn.
    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        image_path = tmp.name
    try:
        await file.download_to_drive(image_path)
        await inference.run_image_turn(message, context, image_path, message.caption or "")
    finally:
        inference.cleanup_temp_file(image_path)
