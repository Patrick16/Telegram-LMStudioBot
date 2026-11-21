"""Stage 4d (part 2): values on settings buttons, reset, reasoning toggle and display."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.formatting import extract_reasoning, format_response, split_message
from src.bot.handlers.menu import (
    _handle_settings_action,
    build_session_settings_menu,
    render_current_settings,
)
from src.bot.services import inference
from src.storage.models import SessionGenerationSettings
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
def query():
    q = MagicMock()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock(return_value=MagicMock())
    return q


def _labels(markup):
    return {b.callback_data: b.text for row in markup.inline_keyboard for b in row}


# --- values on buttons ----------------------------------------------------------------

def test_buttons_show_current_values():
    settings = SessionGenerationSettings(
        temperature=0.3, top_k=40, stop_strings=["a", "b"], system_prompt="be brief"
    )
    labels = _labels(build_session_settings_menu(settings))
    assert labels["settings:session:temperature"] == "🌡 Temperature · 0.3"
    assert labels["settings:session:top_k"] == "🔝 Top-K · 40"
    assert labels["settings:session:top_p"] == "📊 Top-P · 1.0"
    assert labels["settings:session:repeat_penalty"] == "🔁 Repeat Penalty · default"
    assert labels["settings:session:seed"] == "🎲 Seed · default"
    assert labels["settings:session:stop_strings"] == "🛑 Stop Strings · 2 set"
    assert labels["settings:session:prompt"] == "📝 System Prompt · set"
    assert labels["settings:session:toggle_reasoning"] == "💭 Show reasoning: off"


def test_menu_without_settings_keeps_plain_labels():
    labels = _labels(build_session_settings_menu())
    assert labels["settings:session:temperature"] == "🌡 Temperature"
    assert "settings:session:reset" not in labels


@pytest.mark.asyncio
async def test_session_menu_is_rendered_with_values(store, context, query):
    session = store.create_session("S")
    session.settings.temperature = 1.2
    store.update_session(session)
    await _handle_settings_action(query, context, "settings:session_menu")
    markup = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert _labels(markup)["settings:session:temperature"] == "🌡 Temperature · 1.2"


# --- toggle and reset --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toggle_reasoning_flips_and_refreshes_menu(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:session:toggle_reasoning")
    assert store.get_active_session().settings.show_reasoning is True
    markup = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert _labels(markup)["settings:session:toggle_reasoning"] == "💭 Show reasoning: on"

    await _handle_settings_action(query, context, "settings:session:toggle_reasoning")
    assert store.get_active_session().settings.show_reasoning is False


@pytest.mark.asyncio
async def test_reset_restores_sampling_but_keeps_prompt_policy_and_reasoning(
    store, context, query
):
    session = store.create_session("S")
    s = session.settings
    s.temperature, s.top_p, s.top_k, s.seed, s.max_tokens = 1.9, 0.2, 5, 7, 100
    s.stop_strings = ["x"]
    s.system_prompt, s.show_reasoning = "keep me", True
    s.history_policy.mode = "off"
    store.update_session(session)

    await _handle_settings_action(query, context, "settings:session:reset")

    s = store.get_active_session().settings
    assert (s.temperature, s.top_p, s.top_k, s.seed, s.max_tokens) == (0.7, 1.0, None, None, -1)
    assert s.stop_strings == []
    assert (s.system_prompt, s.show_reasoning, s.history_policy.mode) == ("keep me", True, "off")


def test_current_settings_lists_reasoning(store):
    session = store.create_session("S")
    assert "Show reasoning" in render_current_settings(session)


# --- reasoning rendering -----------------------------------------------------------------

def test_extract_reasoning():
    assert extract_reasoning("<think>a</think>X<think>b</think>") == "a\n\nb"
    assert extract_reasoning("<think>unfinished") == "unfinished"
    assert extract_reasoning("no thinking") == ""


def test_reasoning_hidden_by_default():
    assert format_response("<think>secret</think>Answer") == "Answer"


def test_reasoning_shown_as_expandable_quote():
    out = format_response("<think>a < b</think>Answer", show_reasoning=True)
    assert out == "<blockquote expandable>💭 a &lt; b</blockquote>\nAnswer"


def test_reasoning_only_reply_is_still_no_response():
    assert format_response("<think>x</think>", show_reasoning=True) == "<i>(no response)</i>"


def test_long_reasoning_splits_into_valid_chunks():
    out = format_response("<think>" + "word " * 2000 + "</think>Answer", show_reasoning=True)
    chunks = split_message(out)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4096
        assert chunk.count("<blockquote expandable>") == chunk.count("</blockquote>")


@pytest.mark.asyncio
async def test_final_reply_includes_reasoning_when_enabled(store, context):
    session = store.create_session("S")
    session.settings.show_reasoning = True
    store.update_session(session)

    message = MagicMock()
    message.chat_id = 1
    message.chat.send_action = AsyncMock()
    placeholder = AsyncMock()
    message.reply_text = AsyncMock(return_value=placeholder)

    async def stream(*args, **kwargs):
        yield "<think>hmm</think>Answer"

    with patch("src.lms.sdk.chat_stream", stream):
        await inference.run_text_turn(message, context, "q")

    final = placeholder.edit_text.await_args
    assert final.args[0] == "<blockquote expandable>💭 hmm</blockquote>\nAnswer"
    # history stays free of reasoning
    assert store.load_history(session.id)[-1].content == "Answer"
