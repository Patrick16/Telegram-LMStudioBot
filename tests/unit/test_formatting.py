from src.bot.formatting import _format_size, format_response, split_message, strip_think_tags


class TestStripThinkTags:
    def test_strip_think_single(self):
        text = "<think>internal</think>Visible answer"
        assert strip_think_tags(text) == "Visible answer"

    def test_strip_think_multiple(self):
        text = "A<think>1</think>B<think>2</think>C"
        assert strip_think_tags(text) == "ABC"

    def test_strip_think_none(self):
        text = "Visible answer only"
        assert strip_think_tags(text) == text

    def test_strip_think_unclosed(self):
        text = "Visible<think>unfinished reasoning"
        assert strip_think_tags(text) == "Visible"


class TestFormatResponse:
    def test_empty_after_strip(self):
        assert format_response("<think>only reasoning</think>") == "<i>(no response)</i>"

    def test_plain_prose_markdown_converted(self):
        text = "Hello world. **bold** [link](https://x.io)"
        expected = 'Hello world. <b>bold</b> <a href="https://x.io">link</a>'
        assert format_response(text) == expected

    def test_html_escape_plain_text(self):
        text = "Use <tag> & compare > values"
        assert format_response(text) == "Use &lt;tag&gt; &amp; compare &gt; values"

    def test_bold_converted(self):
        assert format_response("**title**") == "<b>title</b>"

    def test_italic_converted(self):
        assert format_response("*word*") == "<i>word</i>"

    def test_bold_italic_converted(self):
        assert format_response("***both***") == "<b><i>both</i></b>"

    def test_strikethrough_converted(self):
        assert format_response("~~old~~") == "<s>old</s>"

    def test_link_converted(self):
        result = format_response("[click](https://example.com)")
        assert result == '<a href="https://example.com">click</a>'

    def test_heading_converted(self):
        assert format_response("# Section Title") == "<b>Section Title</b>"

    def test_fenced_code_no_lang(self):
        text = "Here:\n```\nprint('hi')\n```"
        assert format_response(text) == "Here:\n<pre><code>print('hi')\n</code></pre>"

    def test_fenced_code_with_lang(self):
        text = "```python\nprint(1 < 2)\n```"
        assert format_response(text) == (
            '<pre><code class="language-python">print(1 &lt; 2)\n</code></pre>'
        )

    def test_fenced_multiple_blocks(self):
        text = "```\na\n```\ntext\n```\nb\n```"
        expected = "<pre><code>a\n</code></pre>\ntext\n<pre><code>b\n</code></pre>"
        assert format_response(text) == expected

    def test_inline_code(self):
        text = "Use `pip install` now"
        assert format_response(text) == "Use <code>pip install</code> now"

    def test_html_escape_inside_code(self):
        text = "`<br>` and ```\n<div>\n```"
        expected = "<code>&lt;br&gt;</code> and <pre><code>&lt;div&gt;\n</code></pre>"
        assert format_response(text) == expected

    def test_markdown_not_applied_inside_code(self):
        assert format_response("```\n**not bold**\n```") == "<pre><code>**not bold**\n</code></pre>"


class TestFormatSize:
    def test_format_size_gb(self):
        assert _format_size(3 * 1024 * 1024 * 1024) == "3.0 GB"

    def test_format_size_mb(self):
        assert _format_size(512 * 1024 * 1024) == "512 MB"


class TestSplitMessage:
    def test_short_message_not_split(self):
        text = "Hello world"
        assert split_message(text) == [text]

    def test_exact_limit_not_split(self):
        text = "x" * 4096
        assert split_message(text) == [text]

    def test_splits_on_blank_line(self):
        para1 = "a" * 3000
        para2 = "b" * 3000
        text = para1 + "\n\n" + para2
        chunks = split_message(text)
        assert len(chunks) == 2
        assert chunks[0] == para1
        assert chunks[1] == para2

    def test_splits_on_newline_if_no_blank_line(self):
        line1 = "a" * 3000
        line2 = "b" * 3000
        text = line1 + "\n" + line2
        chunks = split_message(text)
        assert len(chunks) == 2
        assert chunks[0] == line1
        assert chunks[1] == line2

    def test_hard_split_if_no_whitespace(self):
        text = "a" * 5000
        chunks = split_message(text)
        assert len(chunks) == 2
        assert all(len(c) <= 4096 for c in chunks)

    def test_all_chunks_within_limit(self):
        # Simulate a very long response
        text = ("word " * 1000).strip()
        chunks = split_message(text)
        assert all(len(c) <= 4096 for c in chunks)


class TestMarkdownEdgeCases:
    def test_arithmetic_asterisks_not_italic(self):
        assert format_response("2 * 3 * 4") == "2 * 3 * 4"

    def test_bullet_list_rendered_as_bullets(self):
        assert format_response("* one\n* two") == "• one\n• two"

    def test_safe_link_rendered(self):
        out = format_response("[site](https://example.com/a?b=1)")
        assert out == '<a href="https://example.com/a?b=1">site</a>'

    def test_unsafe_link_scheme_not_rendered(self):
        out = format_response("[x](javascript:alert(1))")
        assert "<a " not in out

    def test_quote_in_url_cannot_break_attribute(self):
        out = format_response('[x](https://e.com/"onclick="y)')
        assert '"onclick' not in out

    def test_small_sizes(self):
        assert _format_size(512 * 1024) == "512 KB"
        assert _format_size(100) == "100 B"


class TestModelListEscaping:
    def test_names_are_html_escaped(self):
        from types import SimpleNamespace

        from src.bot.handlers.models import _format_downloaded_list, _format_loaded_list

        model = SimpleNamespace(model_key="a<b>&c", info=SimpleNamespace(size_bytes=0))
        handle = SimpleNamespace(identifier="x<y", size_bytes=0)
        assert "a&lt;b&gt;&amp;c" in _format_downloaded_list([model])
        assert "x&lt;y" in _format_loaded_list([handle])


class TestMenuTextsAreValidHtml:
    def test_all_static_texts_parse(self):
        import html.parser

        from src.bot import i18n
        from src.bot.commands import render_help
        from src.bot.handlers.help import render_welcome
        from src.bot.handlers.menu.keyboards import (
            help_models_text,
            help_sessions_text,
            help_settings_text,
        )

        for language in i18n.LANGUAGES:
            i18n.set_language(language)
            for text in (render_help(), help_models_text(), help_sessions_text(),
                         help_settings_text(), render_welcome("status", True)):
                parser = html.parser.HTMLParser()
                parser.feed(text)
                assert "*" not in text.replace("* ", "")  # no leftover Markdown markers
                assert "`" not in text

    def test_current_settings_escapes_user_input(self):
        from types import SimpleNamespace

        from src.bot.handlers.menu.keyboards import render_current_settings
        from src.storage.models import SessionGenerationSettings

        settings = SessionGenerationSettings(system_prompt="<b>&`x`", stop_strings=["<end>"])
        text = render_current_settings(SimpleNamespace(settings=settings))
        assert "&lt;b&gt;&amp;`x`" in text
        assert "&lt;end&gt;" in text
