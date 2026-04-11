import logging
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.lms import sdk
from src.storage.models import ChatMessage

logger = logging.getLogger(__name__)

STREAM_UPDATE_INTERVAL = 50


@require_owner
async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = store.get_active_session()

    if session is None:
        await update.effective_message.reply_text("❌ No active chat. Use /newchat first.")
        return

    # Download highest resolution photo
    photo = update.effective_message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        image_path = tmp.name

    caption = update.effective_message.caption or ""

    # Check if model supports vision
    try:
        model_info = await sdk.get_model_info(
            session.model_identifier,
            host=config.LMS_HOST,
            port=config.LMS_PORT,
        )
        # Check for vision capability in model info
        vision_supported = bool(getattr(model_info, "vision", False))
    except Exception:
        await update.effective_message.reply_text("❌ No model loaded. Use /load <model> first.")
        return

    if not vision_supported:
        await update.effective_message.reply_text(
            "❌ The loaded model does not support image input."
        )
        return

    user_content = caption or "What do you see in this image?"
    session.history.append(ChatMessage(role="user", content=user_content, image_path=image_path))

    sent_message = await update.effective_message.reply_text("⏳ Processing image...")
    full_response = ""
    token_count = 0

    try:
        async for chunk in sdk.infer_with_image(
            session, image_path, caption=caption,
            host=config.LMS_HOST, port=config.LMS_PORT,
        ):
            full_response += chunk
            token_count += 1
            if token_count % STREAM_UPDATE_INTERVAL == 0:
                try:
                    await sent_message.edit_text(full_response)
                except Exception:
                    pass

        if full_response:
            try:
                await sent_message.edit_text(full_response)
            except Exception:
                pass
            session.history.append(ChatMessage(role="assistant", content=full_response))
            store.update_session(session)
        else:
            await sent_message.edit_text("❌ No response from model.")
    except Exception as e:
        logger.error("Vision inference error: %s", e)
        await sent_message.edit_text("❌ LM Studio is unreachable.")
