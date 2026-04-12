from __future__ import annotations

import asyncio
import logging
import threading
import time
import warnings
from collections.abc import AsyncGenerator
from typing import Any

import lmstudio

from src.storage.models import ChatMessage, ChatSession, HistoryReusePolicy

logger = logging.getLogger(__name__)

_STREAM_SENTINEL = object()


# ---------------------------------------------------------------------------
# History trimming helpers
# ---------------------------------------------------------------------------

def trim_history(
    messages: list[ChatMessage],
    policy: HistoryReusePolicy,
    context_budget: int | None = None,
) -> list[ChatMessage]:
    """Return a subset of *messages* according to *policy*.

    ``context_budget`` is an optional rough character budget used by
    ``fit_budget_recent`` and ``full_if_possible``.  When *None* the
    budget-aware modes fall back to returning all messages (best effort).
    """
    if policy.mode == "off":
        return []

    if policy.mode == "last_n_pairs":
        limit = policy.message_pair_limit or 0
        if limit <= 0:
            return []
        # Take last N user+assistant pairs
        pairs: list[ChatMessage] = []
        pair_count = 0
        for msg in reversed(messages):
            if msg.role == "assistant":
                pairs.append(msg)
            elif msg.role == "user":
                pairs.append(msg)
                pair_count += 1
                if pair_count >= limit:
                    break
        pairs.reverse()
        return pairs

    if policy.mode == "fit_budget_recent":
        if context_budget is None:
            return list(messages)
        result: list[ChatMessage] = []
        total = 0
        for msg in reversed(messages):
            total += len(msg.content)
            if total > context_budget:
                break
            result.append(msg)
        result.reverse()
        return result

    # full_if_possible
    if context_budget is None:
        return list(messages)
    total_len = sum(len(m.content) for m in messages)
    if total_len <= context_budget:
        return list(messages)
    # Fall back to fit_budget_recent
    return trim_history(
        messages,
        HistoryReusePolicy(mode="fit_budget_recent"),
        context_budget,
    )


# ---------------------------------------------------------------------------
# Chat / config builders
# ---------------------------------------------------------------------------

def _build_chat(
    session: ChatSession,
    history_messages: list[ChatMessage] | None = None,
) -> lmstudio.Chat:
    chat = lmstudio.Chat()
    system_prompt = (
        session.settings.system_prompt
        if hasattr(session.settings, "system_prompt")
        else getattr(session, "system_prompt", "")
    )
    if system_prompt:
        chat.add_system_prompt(system_prompt)
    msgs = history_messages if history_messages is not None else session.history
    for msg in msgs:
        if msg.role == "user":
            chat.add_user_message(msg.content)
        elif msg.role == "assistant":
            chat.add_assistant_response(msg.content)
    return chat


def _build_config(session: ChatSession) -> dict[str, Any] | None:
    settings = session.settings
    config: dict[str, Any] = {}
    if settings.temperature != 0.7:
        config["temperature"] = settings.temperature
    if settings.max_tokens != -1:
        config["maxPredictedTokens"] = settings.max_tokens
    if settings.top_p != 1.0:
        config["topPSampling"] = settings.top_p
    if settings.top_k is not None:
        config["topKSampling"] = settings.top_k
    if settings.repeat_penalty is not None:
        config["repeatPenalty"] = settings.repeat_penalty
    if settings.stop_strings:
        config["stopStrings"] = settings.stop_strings
    if settings.seed is not None:
        config["seed"] = settings.seed
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


_MAX_RETRIES = 3


def _sync_respond_stream(
    session: ChatSession,
    host: str,
    port: int,
    history_messages: list[ChatMessage] | None = None,
):
    """Sync generator: yields string chunks from lmstudio respond_stream.

    Retries up to _MAX_RETRIES times if the connection fails before any tokens
    are received. If the connection drops mid-stream, ends the generator cleanly
    so the caller gets the partial response instead of an error.
    """
    for attempt in range(_MAX_RETRIES):
        client = lmstudio.Client(api_host=f"{host}:{port}")
        tokens_yielded = 0
        try:
            model = client.llm.model(session.model_identifier)
            chat = _build_chat(session, history_messages)
            config = _build_config(session)
            for fragment in model.respond_stream(chat, config=config):
                tokens_yielded += 1
                yield fragment.content
            return  # clean completion
        except Exception as exc:
            if tokens_yielded > 0:
                logger.warning(
                    "Stream interrupted after %d token(s): %s — returning partial response",
                    tokens_yielded, exc,
                )
                return  # end generator cleanly; caller displays partial response
            if attempt < _MAX_RETRIES - 1:
                delay = 2 ** attempt
                logger.warning(
                    "Connection attempt %d/%d failed: %s — retrying in %ds…",
                    attempt + 1, _MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                raise
        finally:
            client.close()


def _sync_respond_stream_with_image(
    session: ChatSession,
    image_path: str,
    caption: str,
    host: str,
    port: int,
    history_messages: list[ChatMessage] | None = None,
):
    """Sync generator: yields string chunks from lmstudio respond_stream with image.

    Same retry/partial-response behaviour as _sync_respond_stream.
    """
    for attempt in range(_MAX_RETRIES):
        client = lmstudio.Client(api_host=f"{host}:{port}")
        tokens_yielded = 0
        try:
            model = client.llm.model(session.model_identifier)
            image_handle = lmstudio.prepare_image(image_path)
            chat = _build_chat(session, history_messages)
            user_content = caption or "What do you see in this image?"
            chat.add_user_message(user_content, images=[image_handle])
            config = _build_config(session)
            for fragment in model.respond_stream(chat, config=config):
                tokens_yielded += 1
                yield fragment.content
            return  # clean completion
        except Exception as exc:
            if tokens_yielded > 0:
                logger.warning(
                    "Vision stream interrupted after %d token(s): %s — returning partial response",
                    tokens_yielded, exc,
                )
                return  # end generator cleanly; caller displays partial response
            if attempt < _MAX_RETRIES - 1:
                delay = 2 ** attempt
                logger.warning(
                    "Vision connection attempt %d/%d failed: %s — retrying in %ds…",
                    attempt + 1, _MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
            else:
                raise
        finally:
            client.close()


async def list_downloaded_models(
    host: str = "localhost", port: int = 1234
) -> list[Any]:
    """Return all downloaded models from the local LM Studio instance."""

    def _sync() -> list[Any]:
        # Suppress RuntimeWarning from lmstudio SDK about unawaited coroutines
        # when handling websocket reconnection failures (known SDK issue)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=RuntimeWarning,
                message="coroutine.*was never awaited",
            )
            client = lmstudio.Client(api_host=f"{host}:{port}")
            try:
                return list(client.list_downloaded_models())
            finally:
                client.close()

    return await asyncio.to_thread(_sync)


async def list_loaded_models(
    host: str = "localhost", port: int = 1234
) -> list[Any]:
    """Return all currently loaded models from the local LM Studio instance."""

    def _sync() -> list[Any]:
        # Suppress RuntimeWarning from lmstudio SDK about unawaited coroutines
        # when handling websocket reconnection failures (known SDK issue)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=RuntimeWarning,
                message="coroutine.*was never awaited",
            )
            client = lmstudio.Client(api_host=f"{host}:{port}")
            try:
                return list(client.list_loaded_models())
            finally:
                client.close()

    return await asyncio.to_thread(_sync)


async def chat_stream(
    session: ChatSession,
    host: str = "localhost",
    port: int = 1234,
    history_messages: list[ChatMessage] | None = None,
) -> AsyncGenerator[str, None]:
    async for chunk in _stream_in_thread(
        _sync_respond_stream, session, host, port, history_messages
    ):
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
    history_messages: list[ChatMessage] | None = None,
) -> AsyncGenerator[str, None]:
    async for chunk in _stream_in_thread(
        _sync_respond_stream_with_image, session, image_path, caption, host, port, history_messages
    ):
        yield chunk
