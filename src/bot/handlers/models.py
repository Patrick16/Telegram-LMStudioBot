import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.lms import cli
from src.lms.cli import LmsCliError
from src.storage.models import LoadConfig

logger = logging.getLogger(__name__)


@require_owner
async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = await cli.list_models()
        await update.effective_message.reply_text(f"📦 Available models:\n{result}")
    except LmsCliError:
        await update.effective_message.reply_text(
            "❌ Could not connect to LM Studio. Is it running?"
        )


@require_owner
async def loaded_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = await cli.list_loaded()
        await update.effective_message.reply_text(f"🧠 Loaded models:\n{result}")
    except LmsCliError:
        await update.effective_message.reply_text(
            "❌ Could not connect to LM Studio. Is it running?"
        )


@require_owner
async def load_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.effective_message.reply_text(
            "❌ Usage: /load <model> [gpu=max|auto|0.0-1.0] [ctx=N] [id=name]"
        )
        return

    model = args[0]
    gpu = "auto"
    context_length = None
    identifier = None

    for arg in args[1:]:
        if arg.startswith("gpu="):
            gpu = arg[4:]
            valid_gpu = gpu in ("max", "auto")
            if not valid_gpu:
                try:
                    gpu_val = float(gpu)
                    if not (0.0 <= gpu_val <= 1.0):
                        await update.effective_message.reply_text(
                            "❌ Invalid gpu value: must be max, auto, or a float between 0.0 and 1.0"
                        )
                        return
                except ValueError:
                    await update.effective_message.reply_text(
                        "❌ Invalid gpu value: must be max, auto, or a float between 0.0 and 1.0"
                    )
                    return
        elif arg.startswith("ctx="):
            try:
                context_length = int(arg[4:])
                if context_length < 512:
                    await update.effective_message.reply_text("❌ Context length must be >= 512")
                    return
            except ValueError:
                await update.effective_message.reply_text("❌ Invalid context length value")
                return
        elif arg.startswith("id="):
            identifier = arg[3:]

    config = LoadConfig(gpu=gpu, context_length=context_length, identifier=identifier)

    try:
        await cli.load_model(model, config)
        await update.effective_message.reply_text(f"✅ Model {model} loaded successfully.")
    except LmsCliError as e:
        await update.effective_message.reply_text(f"❌ Load failed: {e}")


@require_owner
async def unload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.effective_message.reply_text("❌ Usage: /unload <model_or_identifier>")
        return

    identifier = args[0]

    try:
        await cli.unload_model(identifier)
        await update.effective_message.reply_text(f"✅ Model {identifier} unloaded.")
    except LmsCliError as e:
        await update.effective_message.reply_text(f"❌ {e}")
