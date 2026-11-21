"""Tests for InferenceService, GenerationManager and cancellable streaming (B9-B13, B16, B17)."""

import asyncio
import os
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import lmstudio
import pytest

from src.bot.handlers.messages import stop_command
from src.bot.handlers.vision import photo_message_handler
from src.bot.services import inference
from src.lms import sdk
from src.storage.models import ChatMessage
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "sessions.json"), histories_dir=str(tmp_path / "histories")
    )


@pytest.fixture
def context(store):
    ctx = MagicMock()
    ctx.bot_data = {
        "config": MagicMock(TELEGRAM_OWNER_ID=1, LMS_HOST="h", LMS_PORT=1),
        "store": store,
    }
    ctx.chat_data = {}
    return ctx


@pytest.fixture
def message():
    msg = MagicMock()
    msg.chat_id = 42
    msg.text = "Hi"
    placeholder = AsyncMock()
    msg.reply_text = AsyncMock(return_value=placeholder)
    msg.placeholder = placeholder
    return msg


def _stream(chunks, error=None):
    async def gen(*args, **kwargs):
        for c in chunks:
            yield c
        if error:
            raise error

    return gen


def _contents(store, session):
    return [(m.role, m.content) for m in store.load_history(session.id)]


def _stop_update(chat_id):
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.chat_id = chat_id
    update.effective_message.reply_text = AsyncMock()
    return update


# --- B12: transactional history ------------------------------------------------

@pytest.mark.asyncio
async def test_failure_persists_nothing(store, context, message):
    session = store.create_session("S")
    with patch("src.lms.sdk.chat_stream", _stream([], error=RuntimeError("boom"))):
        await inference.run_text_turn(message, context, "Hi")
    assert store.load_history(session.id) == []
    assert "boom" in message.placeholder.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_success_persists_user_and_assistant_together(store, context, message):
    session = store.create_session("S")
    with patch("src.lms.sdk.chat_stream", _stream(["<think>x</think>Hel", "lo"])):
        await inference.run_text_turn(message, context, "Hi")
    assert _contents(store, session) == [("user", "Hi"), ("assistant", "Hello")]


@pytest.mark.asyncio
async def test_prompt_includes_new_user_message(store, context, message):
    session = store.create_session("S")
    seen = {}

    async def fake(session, host="", port=0, history_messages=None):
        seen["msgs"] = [m.content for m in history_messages]
        yield "ok"

    store.append_messages(
        session.id,
        [ChatMessage(role="user", content="a"), ChatMessage(role="assistant", content="b")],
    )
    with patch("src.lms.sdk.chat_stream", fake):
        await inference.run_text_turn(message, context, "c")
    assert seen["msgs"] == ["a", "b", "c"]


def test_describe_error_is_accurate():
    assert "unreachable" in inference.describe_error(lmstudio.LMStudioWebsocketError("x"))
    assert "No model is loaded" in inference.describe_error(
        lmstudio.LMStudioModelNotFoundError("m")
    )
    assert "Generation failed: weird" in inference.describe_error(ValueError("weird"))


# --- B10: partial answers ------------------------------------------------------

@pytest.mark.asyncio
async def test_interrupted_stream_keeps_partial_and_warns(store, context, message):
    session = store.create_session("S")
    stream = _stream(["partial"], error=sdk.StreamInterrupted("x"))
    with patch("src.lms.sdk.chat_stream", stream):
        await inference.run_text_turn(message, context, "Hi")
    assert _contents(store, session)[-1] == ("assistant", "partial")
    assert message.reply_text.await_args_list[-1].args[0] == inference.MSG_INTERRUPTED


def test_respond_with_retry_raises_stream_interrupted_after_chunks():
    def fake_stream(chat, config=None):
        yield MagicMock(content="a")
        raise RuntimeError("socket closed")

    client = MagicMock()
    client.llm.model.return_value.respond_stream = fake_stream
    session = MagicMock(model_identifier=None)
    settings = session.settings
    settings.system_prompt = ""
    settings.temperature = 0.7
    settings.max_tokens = -1
    settings.top_p = 1.0
    settings.top_k = settings.repeat_penalty = settings.seed = None
    settings.stop_strings = []

    got = []
    with patch("src.lms.sdk.lmstudio.Client", return_value=client):
        with pytest.raises(sdk.StreamInterrupted):
            for chunk in sdk._respond_with_retry(session, "h", 1, []):
                got.append(chunk)
    assert got == ["a"]
    client.close.assert_called()


# --- B13: regenerate -----------------------------------------------------------

@pytest.mark.asyncio
async def test_regenerate_failure_keeps_old_answer(store, context, message):
    session = store.create_session("S")
    store.append_messages(
        session.id,
        [ChatMessage(role="user", content="q"), ChatMessage(role="assistant", content="old")],
    )
    with patch("src.lms.sdk.chat_stream", _stream([], error=RuntimeError("down"))):
        await inference.run_regenerate(message, context)
    assert _contents(store, session) == [("user", "q"), ("assistant", "old")]


@pytest.mark.asyncio
async def test_regenerate_success_replaces_answer(store, context, message):
    session = store.create_session("S")
    store.append_messages(
        session.id,
        [ChatMessage(role="user", content="q"), ChatMessage(role="assistant", content="old")],
    )
    with patch("src.lms.sdk.chat_stream", _stream(["new"])):
        await inference.run_regenerate(message, context)
    assert _contents(store, session) == [("user", "q"), ("assistant", "new")]


# --- B9/B11: stop and concurrency ---------------------------------------------

@pytest.mark.asyncio
async def test_stop_cancels_generation_and_persists_nothing(store, context, message):
    session = store.create_session("S")
    started = asyncio.Event()

    async def slow(*args, **kwargs):
        yield "partial"
        started.set()
        await asyncio.sleep(10)
        yield "never"

    with patch("src.lms.sdk.chat_stream", slow):
        task = asyncio.create_task(inference.run_text_turn(message, context, "Hi"))
        await started.wait()
        await stop_command(_stop_update(42), context)
        await asyncio.wait_for(task, 2)

    assert message.placeholder.edit_text.await_args.args[0] == inference.MSG_STOPPED
    assert store.load_history(session.id) == []
    assert not context.bot_data["generations"].is_active(42)


@pytest.mark.asyncio
async def test_second_generation_in_same_chat_is_rejected(store, context, message):
    store.create_session("S")
    release = asyncio.Event()

    async def blocked(*args, **kwargs):
        await release.wait()
        yield "done"

    with patch("src.lms.sdk.chat_stream", blocked):
        first = asyncio.create_task(inference.run_text_turn(message, context, "one"))
        await asyncio.sleep(0.05)
        await inference.run_text_turn(message, context, "two")
        assert message.reply_text.await_args_list[-1].args[0] == inference.MSG_BUSY
        release.set()
        await first


@pytest.mark.asyncio
async def test_stop_when_idle(context):
    update = _stop_update(7)
    await stop_command(update, context)
    assert "Nothing" in update.effective_message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_stream_thread_stops_when_consumer_breaks():
    closed = threading.Event()

    def endless():
        try:
            i = 0
            while True:
                i += 1
                time.sleep(0.01)
                yield str(i)
        finally:
            closed.set()

    gen = sdk._stream_in_thread(endless)
    async for _ in gen:
        break
    await gen.aclose()
    assert await asyncio.to_thread(closed.wait, 2), "worker generator was not closed"


# --- B16: temp files and specific errors --------------------------------------

@pytest.mark.asyncio
async def test_photo_errors_are_specific_and_temp_file_removed(store, context):
    store.create_session("S")
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.photo = [MagicMock(file_id="f")]
    update.effective_message.caption = ""
    update.effective_message.reply_text = AsyncMock()

    failing = AsyncMock(side_effect=lmstudio.LMStudioWebsocketError("x"))
    with patch("src.lms.sdk.get_model_info", failing):
        await photo_message_handler(update, context)
    assert "unreachable" in update.effective_message.reply_text.await_args.args[0]

    paths = []

    async def download(path):
        paths.append(path)
        with open(path, "wb") as f:
            f.write(b"x")

    context.bot.get_file = AsyncMock(return_value=MagicMock(download_to_drive=download))
    with patch("src.lms.sdk.get_model_info", AsyncMock(return_value=MagicMock(vision=True))), \
         patch("src.bot.handlers.vision.inference.run_image_turn", AsyncMock()):
        await photo_message_handler(update, context)
    assert paths and not os.path.exists(paths[0])


# --- context budget -----------------------------------------------------------

@pytest.mark.asyncio
async def test_history_is_trimmed_to_model_context(store, context, message):
    session = store.create_session("S")
    store.append_messages(
        session.id,
        [
            ChatMessage(role="user", content="old" * 2000),
            ChatMessage(role="assistant", content="older" * 2000),
        ],
    )
    seen = {}

    async def fake(session, host="", port=0, history_messages=None):
        seen["msgs"] = [m.content for m in history_messages]
        yield "ok"

    # tiny 512-token window -> minimum budget (1500 chars) -> old turns dropped
    window = AsyncMock(return_value=512)
    with patch("src.lms.sdk.get_context_length", window), patch("src.lms.sdk.chat_stream", fake):
        await inference.run_text_turn(message, context, "new question")
    assert seen["msgs"] == ["new question"]
