from unittest.mock import MagicMock, patch

import pytest

from src.lms.sdk import chat_stream, get_model_info
from src.storage.models import ChatMessage, ChatSession


def _make_session(**kwargs) -> ChatSession:
    defaults = {
        "name": "Test",
        "model_identifier": "test/model",
        "history": [],
    }
    defaults.update(kwargs)
    return ChatSession(**defaults)


def _make_fragment(content: str):
    f = MagicMock()
    f.content = content
    return f


@pytest.mark.asyncio
@patch("src.lms.sdk._sync_respond_stream")
async def test_chat_stream(mock_stream):
    mock_stream.return_value = iter(["Hello", " world"])

    session = _make_session(history=[ChatMessage(role="user", content="Hi")])

    chunks = []
    async for chunk in chat_stream(session):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
@patch("src.lms.sdk._sync_respond_stream")
async def test_chat_stream_with_system_prompt(mock_stream):
    mock_stream.return_value = iter(["response"])

    session = _make_session(
        system_prompt="You are a helper",
        history=[ChatMessage(role="user", content="test")],
    )

    chunks = []
    async for chunk in chat_stream(session):
        chunks.append(chunk)

    assert chunks == ["response"]


@pytest.mark.asyncio
@patch("src.lms.sdk.asyncio.to_thread")
async def test_get_model_info(mock_to_thread):
    mock_info = MagicMock()
    mock_info.vision = True
    mock_to_thread.return_value = mock_info

    info = await get_model_info("test/model")
    assert info.vision is True
