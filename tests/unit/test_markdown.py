"""Markdown → Telegram HTML: structure survives, syntax characters do not."""

import html.parser
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest

from src.bot.formatting import format_stream_preview, html_to_plain
from src.bot.markdown import markdown_to_html
from src.bot.services import inference


class _Balance(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, (tag, self.stack)
        self.stack.pop()


def assert_valid(out: str) -> None:
    parser = _Balance()
    parser.feed(out)
    assert not parser.stack, parser.stack


SAMPLE = """# Plan

Intro with **bold**, *italic*, __also bold__, _also italic_, ~~gone~~ and `code`.

## Steps
1. First **step**
2. Second
   - nested *item*
     - deeper

- [x] done
- [ ] todo

> A quote with **emphasis**
> second line

---

| Name | Value |
|------|------:|
| **a** | `1` |
| bb | 22 |

```python
x = a * b ** 2
```
"""


def test_full_sample_has_no_markdown_syntax_left():
    out = markdown_to_html(SAMPLE)
    assert_valid(out)
    plain = html_to_plain(out)
    for marker in ("**", "__", "~~", "`", "# ", "|---", "- [", "> "):
        assert marker not in plain.replace("x = a * b ** 2", ""), marker
    assert "<b>Plan</b>" in out and "<b>Steps</b>" in out
    assert "<b>also bold</b>" in out and "<i>also italic</i>" in out
    assert "1. First <b>step</b>" in out
    assert "    ◦ nested <i>item</i>" in out and "        ▪ deeper" in out
    assert "☑ done" in out and "☐ todo" in out
    assert "<blockquote>A quote with <b>emphasis</b>\nsecond line</blockquote>" in out
    assert "──────────" in out
    assert '<pre><code class="language-python">x = a * b ** 2\n</code></pre>' in out


def test_table_becomes_aligned_monospace_block():
    out = markdown_to_html("| Name | Value |\n|---|---|\n| **a** | `1` |\n| bb | 22 |")
    assert out == (
        "<pre>Name │ Value\n"
        "─────┼──────\n"
        "a    │ 1\n"
        "bb   │ 22</pre>"
    )


def test_pipes_without_separator_row_are_not_a_table():
    assert markdown_to_html("a | b | c") == "a | b | c"


def test_snake_case_and_urls_keep_underscores():
    assert markdown_to_html("call my_func_name now") == "call my_func_name now"
    out = markdown_to_html("see https://x.io/a_b_c/*x* here")
    assert out == "see https://x.io/a_b_c/*x* here"


def test_links_and_autolinks():
    out = markdown_to_html("[**docs**](https://d.io) and <https://e.io>")
    assert out == (
        '<a href="https://d.io"><b>docs</b></a> and '
        '<a href="https://e.io">https://e.io</a>'
    )


def test_escaped_markers_stay_literal():
    assert markdown_to_html(r"\*not italic\* and \# hash") == "*not italic* and # hash"


def test_spoiler():
    assert markdown_to_html("||secret||") == "<tg-spoiler>secret</tg-spoiler>"
    assert markdown_to_html("a || b") == "a || b"


def test_html_in_text_is_escaped_everywhere():
    out = markdown_to_html("# <b>x</b>\n- <i>\n> <s>")
    assert "<b>&lt;b&gt;x&lt;/b&gt;</b>" in out
    assert "• &lt;i&gt;" in out and "<blockquote>&lt;s&gt;</blockquote>" in out


def test_unclosed_fence_while_streaming_renders_as_code():
    out = markdown_to_html("Look:\n```js\nconst a = 1")
    assert out == 'Look:\n<pre><code class="language-js">const a = 1</code></pre>'


def test_unclosed_emphasis_stays_literal_and_valid():
    out = markdown_to_html("this is **bol")
    assert out == "this is **bol"


def test_stream_preview_is_formatted_html():
    assert format_stream_preview("**Hi** there") == "<b>Hi</b> there ▌"


def test_long_stream_preview_keeps_valid_tail():
    preview = format_stream_preview("```\n" + "line\n" * 2000)
    assert len(preview) < 4096
    assert preview.startswith("… <pre>")
    assert_valid(preview.replace(" ▌", ""))


@pytest.mark.asyncio
async def test_preview_falls_back_to_plain_text_when_html_is_rejected():
    placeholder = MagicMock()
    placeholder.edit_text = AsyncMock(side_effect=[BadRequest("Can't parse entities"), None])
    await inference._edit_preview(placeholder, "<b>x</b> &amp; y ▌")
    plain = placeholder.edit_text.await_args_list[1]
    assert plain.args[0] == "x & y ▌" and "parse_mode" not in plain.kwargs


@pytest.mark.asyncio
async def test_preview_not_modified_is_propagated_without_retry():
    placeholder = MagicMock()
    placeholder.edit_text = AsyncMock(side_effect=BadRequest("Message is not modified"))
    with pytest.raises(BadRequest):
        await inference._edit_preview(placeholder, "x")
    assert placeholder.edit_text.await_count == 1
