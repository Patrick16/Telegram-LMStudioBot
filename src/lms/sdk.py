from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncGenerator
from typing import Any

import lmstudio

from src.storage.models import ChatSession

logger = logging.getLogger(__name__)

_STREAM_SENTINEL = object()


def _build_chat(session: ChatSession) -> lmstudio.Chat:
    chat = lmstudio.Chat()
    if session.system_prompt:
        chat.add_system_prompt(session.system_prompt)
    for msg in session.history:
        if msg.role == "user":
            chat.add_user_message(msg.content)
        elif msg.role == "assistant":
            chat.add_assistant_response(msg.content)
    return chat


def _build_config(session: ChatSession) -> dict[str, Any] | None:
    config: dict[str, Any] = {}
    if session.settings.temperature != 0.7:
        config["temperature"] = session.settings.temperature
    if session.settings.max_tokens != -1:
        config["maxPredictedTokens"] = session.settings.max_tokens
    if session.settings.top_p != 1.0:
        config["topP"] = session.settings.top_p
    if session.settings.stop:
        config["stop"] = session.settings.stop
    return config or None


async def _stream_in_thread(target, *args) -> AsyncGenerator[str, None]:
    """Run a sync streaming function in a thread and yield its string chunks."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run():
        try:
            for chunk in target(*args):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _STREAM_SENTINEL)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    while True:
        item = await queue.get()
        if item is _STREAM_SENTINEL:
            break
        if isinstance(item, Exception):
            raise item
        yield item


def _sync_respond_stream(session: ChatSession, host: str, port: int):
    """Sync generator: yields string chunks from lmstudio respond_stream."""
    client = lmstudio.Client(api_host=f"{host}:{port}")
    try:
        model = client.llm.model(session.model_identifier)
        chat = _build_chat(session)
        config = _build_config(session)
        for fragment in model.respond_stream(chat, config=config):
            yield fragment.content
    finally:
        client.close()


def _sync_respond_stream_with_image(
    session: ChatSession, image_path: str, caption: str, host: str, port: int
):
    """Sync generator: yields string chunks from lmstudio respond_stream with image."""
    client = lmstudio.Client(api_host=f"{host}:{port}")
    try:
        model = client.llm.model(session.model_identifier)
        image_handle = lmstudio.prepare_image(image_path)
        chat = _build_chat(session)
        user_content = caption or "What do you see in this image?"
        chat.add_user_message(user_content, images=[image_handle])
        config = _build_config(session)
        for fragment in model.respond_stream(chat, config=config):
            yield fragment.content
    finally:
        client.close()


async def chat_stream(
    session: ChatSession, host: str = "localhost", port: int = 1234
) -> AsyncGenerator[str, None]:
    async for chunk in _stream_in_thread(_sync_respond_stream, session, host, port):
        yield chunk


async def get_model_info(
    identifier: str | None = None, host: str = "localhost", port: int = 1234
) -> Any:
    def _sync():
        client = lmstudio.Client(api_host=f"{host}:{port}")
        try:
            model = client.llm.model(identifier)
            return model.get_info()
        finally:
            client.close()

    return await asyncio.to_thread(_sync)


async def infer_with_image(
    session: ChatSession,
    image_path: str,
    caption: str = "",
    host: str = "localhost",
    port: int = 1234,
) -> AsyncGenerator[str, None]:
    async for chunk in _stream_in_thread(
        _sync_respond_stream_with_image, session, image_path, caption, host, port
    ):
        yield chunk
