from unittest.mock import MagicMock, patch

import pytest

from src.lms.sdk import (
    _build_config, chat_stream, get_model_info, trim_history,
)
from src.storage.models import (
    ChatMessage, ChatSession, HistoryReusePolicy,
    SessionGenerationSettings,
)


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


def _make_messages(count: int) -> list[ChatMessage]:
    msgs = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append(ChatMessage(role=role, content=f"msg-{i}"))
    return msgs


# ---------------------------------------------------------------------------
# trim_history tests
# ---------------------------------------------------------------------------

class TestTrimHistory:
    def test_off_returns_empty(self):
        policy = HistoryReusePolicy(mode="off")
        msgs = _make_messages(6)
        assert trim_history(msgs, policy) == []

    def test_last_n_pairs(self):
        policy = HistoryReusePolicy(mode="last_n_pairs", message_pair_limit=2)
        msgs = _make_messages(8)  # 4 pairs
        result = trim_history(msgs, policy)
        assert len(result) == 4  # 2 pairs = 4 messages
        assert result[0].content == "msg-4"

    def test_last_n_pairs_zero_limit(self):
        policy = HistoryReusePolicy(mode="last_n_pairs", message_pair_limit=0)
        msgs = _make_messages(4)
        assert trim_history(msgs, policy) == []

    def test_fit_budget_recent(self):
        policy = HistoryReusePolicy(mode="fit_budget_recent")
        msgs = [
            ChatMessage(role="user", content="a" * 100),
            ChatMessage(role="assistant", content="b" * 100),
            ChatMessage(role="user", content="c" * 50),
        ]
        result = trim_history(msgs, policy, context_budget=160)
        assert len(result) == 2  # last two fit in 150 chars

    def test_fit_budget_no_budget_returns_all(self):
        policy = HistoryReusePolicy(mode="fit_budget_recent")
        msgs = _make_messages(4)
        result = trim_history(msgs, policy)
        assert len(result) == 4

    def test_full_if_possible_fits(self):
        policy = HistoryReusePolicy(mode="full_if_possible")
        msgs = _make_messages(4)
        result = trim_history(msgs, policy, context_budget=10000)
        assert len(result) == 4

    def test_full_if_possible_falls_back(self):
        policy = HistoryReusePolicy(mode="full_if_possible")
        msgs = [
            ChatMessage(role="user", content="a" * 100),
            ChatMessage(role="assistant", content="b" * 100),
            ChatMessage(role="user", content="c" * 50),
        ]
        result = trim_history(msgs, policy, context_budget=160)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _build_config tests
# ---------------------------------------------------------------------------

class TestBuildConfig:
    def test_default_returns_none(self):
        session = _make_session()
        assert _build_config(session) is None

    def test_expanded_settings(self):
        session = _make_session(settings=SessionGenerationSettings(
            temperature=0.5,
            max_tokens=256,
            top_p=0.9,
            top_k=40,
            repeat_penalty=1.1,
            stop_strings=["END"],
            seed=42,
        ))
        config = _build_config(session)
        assert config["temperature"] == 0.5
        assert config["maxPredictedTokens"] == 256
        assert config["topPSampling"] == 0.9
        assert config["topKSampling"] == 40
        assert config["repeatPenalty"] == 1.1
        assert config["stopStrings"] == ["END"]
        assert config["seed"] == 42


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
