import logging
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.services import inference
from src.lms import sdk

logger = logging.getLogger(__name__)


@require_owner
async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    config = context.bot_data["config"]
    message = update.effective_message
    session = inference.ensure_session(store)

    # Check vision support before downloading anything.
    try:
        model_info = await sdk.get_model_info(
            session.model_identifier, host=config.LMS_HOST, port=config.LMS_PORT,
        )
    except Exception as exc:
        logger.warning("Could not query model info: %s", exc)
        await message.reply_text(inference.describe_error(exc))
        return

    if not bool(getattr(model_info, "vision", False)):
        await message.reply_text("❌ The loaded model does not support image input.")
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
