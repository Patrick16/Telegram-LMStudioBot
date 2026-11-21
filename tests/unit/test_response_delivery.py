"""Regression tests for B4 (vision duplicate), B6 (plain fallback), B7 (HTML split), B8."""

import html.parser
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest

from src.bot.formatting import format_response, html_to_plain, split_message
from src.bot.handlers.vision import photo_message_handler
from src.bot.responses import history_content, send_response
from src.storage.models import ChatMessage
from src.storage.session_store import SessionStoreManager


class _TagChecker(html.parser.HTMLParser):
    """Fails if tags are not properly nested/closed."""

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> with stack {self.stack}")
        else:
            self.stack.pop()


def _assert_valid_html(chunk: str) -> None:
    checker = _TagChecker()
    checker.feed(chunk)
    assert not checker.errors, checker.errors
    assert not checker.stack, f"unclosed tags: {checker.stack}"


# --- B7 ---------------------------------------------------------------------

def test_split_keeps_code_block_valid_across_chunks():
    code = "\n".join(f"line {i} = {i} & <x>" for i in range(600))
    text = format_response(f"intro\n\n```python\n{code}\n```\n\noutro **bold**")
    chunks = split_message(text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4096
        _assert_valid_html(chunk)
    # nothing lost (ignoring re-opened/closed tags and boundary whitespace)
    joined = "".join(html_to_plain(c) for c in chunks)
    assert "line 599 = 599 & <x>" in joined
    assert joined.strip().endswith("outro bold")


def test_split_bold_spanning_boundary_is_reopened():
    text = "<b>" + "word " * 1500 + "</b>"
    chunks = split_message(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.startswith("<b>")
        _assert_valid_html(chunk)


def test_split_does_not_cut_entities():
    text = "&amp;" * 2000
    for chunk in split_message(text):
        assert len(chunk) <= 4096
        assert chunk.count("&") == chunk.count(";")


def test_split_never_returns_empty_chunks():
    text = "a" * 4096 + "\n\n\n" + "b" * 10
    assert all(html_to_plain(c).strip() for c in split_message(text))


# --- B6 ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_sends_plain_text_not_html():
    placeholder = AsyncMock()
    placeholder.edit_text.side_effect = [BadRequest("can't parse entities"), None]

    await send_response(placeholder, "Hello **world** & `code`")

    first, second = placeholder.edit_text.await_args_list
    assert first.kwargs["parse_mode"] == "HTML"
    assert "parse_mode" not in second.kwargs
    assert second.args[0] == "Hello world & code"
    assert "<" not in second.args[0]


@pytest.mark.asyncio
async def test_overflow_chunk_fallback_is_plain():
    placeholder = AsyncMock()
    calls = {"n": 0}

    async def flaky_reply(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BadRequest("bad")

    placeholder.reply_text.side_effect = flaky_reply
    text = ("para " * 700 + "\n\n") * 3

    await send_response(placeholder, text)

    plain_call = placeholder.reply_text.await_args_list[1]
    assert "parse_mode" not in plain_call.kwargs


# --- B8 ---------------------------------------------------------------------

def test_history_content_strips_think():
    assert history_content("<think>secret</think>Answer") == "Answer"
    assert history_content("<think>only reasoning</think>") == ""
    assert history_content("<think>unfinished") == ""


# --- B4 ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vision_does_not_duplicate_current_user_message(tmp_path):
    store = SessionStoreManager(
        str(tmp_path / "sessions.json"), histories_dir=str(tmp_path / "histories")
    )
    session = store.create_session("Vision")
    store.append_message(session.id, ChatMessage(role="user", content="earlier"))
    store.append_message(session.id, ChatMessage(role="assistant", content="reply"))

    config = MagicMock(TELEGRAM_OWNER_ID=1, LMS_HOST="h", LMS_PORT=1)
    context = MagicMock()
    context.bot_data = {"config": config, "store": store}
    context.bot.get_file = AsyncMock(return_value=MagicMock(download_to_drive=AsyncMock()))

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.photo = [MagicMock(file_id="f")]
    update.effective_message.caption = "what is this?"
    update.effective_message.reply_text = AsyncMock(return_value=AsyncMock())

    captured = {}

    async def fake_infer(session, image_path, caption="", host="", port=0, history_messages=None):
        captured["history"] = list(history_messages)
        yield "It is a cat"

    with patch("src.bot.handlers.vision.sdk.get_model_info",
               AsyncMock(return_value=MagicMock(vision=True))), \
         patch("src.bot.handlers.vision.sdk.infer_with_image", fake_infer):
        await photo_message_handler(update, context)

    assert [m.content for m in captured["history"]] == ["earlier", "reply"]
    saved = store.load_history(session.id)
    assert [m.role for m in saved] == ["user", "assistant", "user", "assistant"]
    assert saved[-1].content == "It is a cat"


# --- Property-style: any model output yields valid, in-limit Telegram HTML ---------

_FRAGMENTS = [
    "word ", "longer sentence here. ", "\n", "\n\n", "**", "*", "`", "```\n", "```python\n",
    "<", ">", "&", "&amp;", "<think>", "</think>", "[link](https://x.io/a)", "# Title\n",
    "~~", "x" * 300, "é ", "* item\n", "2 * 3 ",
]


@pytest.mark.parametrize("seed", range(40))
def test_random_model_output_always_yields_valid_chunks(seed):
    import random

    rng = random.Random(seed)
    raw = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 1500)))

    chunks = split_message(format_response(raw))

    assert chunks
    for chunk in chunks:
        assert 0 < len(chunk) <= 4096
        assert html_to_plain(chunk).strip(), "chunk has no visible text"
        _assert_valid_html(chunk)
