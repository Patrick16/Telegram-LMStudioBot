"""Stage 5: translations, language switch, command registry, persistent errors, onboarding."""

import ast
import pathlib
import re
import string
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import Application, CommandHandler

from src.bot import i18n
from src.bot.commands import ALL_COMMAND_NAMES, COMMANDS, bot_commands, render_help
from src.bot.ephemeral import CB_DISMISS, reply_error
from src.bot.handlers import quickbar
from src.bot.handlers.help import render_welcome, start_command
from src.bot.handlers.menu import _handle_settings_action, menu_callback_handler
from src.bot.handlers.menu.keyboards import build_main_menu, render_main_menu_text
from src.bot.i18n import RU, mark, tr, translate
from src.bot.main import register_handlers
from src.bot.services import inference
from src.storage.session_store import SessionStoreManager

SRC = pathlib.Path(__file__).resolve().parents[2] / "src"


def literal_keys() -> set[str]:
    """Every English literal passed to ``tr()`` / ``mark()`` anywhere in the source."""
    keys = set()
    for path in SRC.rglob("*.py"):
        if path.name in ("i18n.py", "i18n_ru.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("tr", "mark")
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
    return keys


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def tags(text: str) -> list[str]:
    return sorted(re.findall(r"</?(?:b|i|code|pre|a|u|s|blockquote)[^>]*>", text))


# --- catalog completeness -----------------------------------------------------------------

def test_every_ui_string_has_a_russian_translation():
    missing = sorted(literal_keys() - set(RU))
    assert not missing, f"untranslated: {missing}"


def test_no_stale_translations():
    stale = sorted(set(RU) - literal_keys())
    assert not stale, f"unused translations: {stale}"


def test_placeholders_and_html_tags_match_the_english_text():
    for english, russian in RU.items():
        assert fields(english) == fields(russian), english
        assert tags(english) == tags(russian), english


def test_no_translation_is_left_in_english():
    # Allowed to stay equal: language-neutral labels and technical names.
    neutral = {"Top-P", "Top-K", "Seed", "🖥 GPU", "📊 Top-P", "🔝 Top-K", "🎲 Seed", "🖥 GPU: {value}"}
    same = [k for k, v in RU.items() if k == v and k not in neutral]
    assert not same, same


# --- tr / translate -------------------------------------------------------------------------

def test_tr_follows_active_language_and_formats():
    assert tr("🔄 Retry") == "🔄 Retry"
    i18n.set_language("ru")
    assert tr("🔄 Retry") == "🔄 Повторить"
    assert tr("✅ Chat renamed to: {name}", name="X") == "✅ Чат переименован: X"
    i18n.set_language("xx")                      # unknown → default
    assert i18n.get_language() == "en"


def test_missing_translation_falls_back_to_english():
    i18n.set_language("ru")
    assert tr("a string nobody translated") == "a string nobody translated"
    assert mark("x") == "x"


def test_translate_ignores_active_language():
    i18n.set_language("ru")
    assert translate("⏹ Stop", "en") == "⏹ Stop"
    assert translate("⏹ Stop", "ru") == "⏹ Стоп"


def test_ui_renders_in_russian():
    i18n.set_language("ru")
    labels = [b.text for row in build_main_menu().inline_keyboard for b in row]
    assert "➕ Новый чат" in labels and "📦 Модели" in labels
    store = MagicMock()
    store.get_active_session.return_value = None
    assert "Главное меню" in render_main_menu_text(store)


# --- language switch ------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "s.json"), histories_dir=str(tmp_path / "h"),
        session_presets_file=str(tmp_path / "p.json"),
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
    q.message.chat_id = 5
    return q


@pytest.mark.asyncio
async def test_language_screen_lists_languages_without_needing_a_chat(context, query):
    await _handle_settings_action(query, context, "settings:language")
    rows = [(b.text, b.callback_data) for r in query.edit_message_text.await_args.kwargs[
        "reply_markup"].inline_keyboard for b in r]
    assert ("✅ English", "settings:language:en") in rows
    assert ("Русский", "settings:language:ru") in rows


@pytest.mark.asyncio
async def test_switching_language_persists_and_refreshes_screen_and_keyboard(store, context, query):
    with patch("src.bot.handlers.menu.router.reply_ephemeral", AsyncMock()) as notice:
        await _handle_settings_action(query, context, "settings:language:ru")
    assert i18n.get_language() == "ru" and store.get_language() == "ru"
    text = query.edit_message_text.await_args.kwargs["text"]
    assert "✅ Язык: Русский" in text and "Выберите язык" in text
    markup = notice.await_args.kwargs["reply_markup"]
    assert [b.text for r in markup.keyboard for b in r] == [
        "📋 Меню", "⏹ Стоп", "➕ Новый чат", "📊 Статус"]

    reloaded = SessionStoreManager(store._file_path, histories_dir=store._histories_dir)
    reloaded.load()
    assert reloaded.get_language() == "ru"


@pytest.mark.asyncio
async def test_unknown_language_is_ignored(store, context, query):
    await _handle_settings_action(query, context, "settings:language:zz")
    assert store.get_language() == "en"


# --- bottom keyboard in both languages ------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("language,label", [("en", "⏹ Stop"), ("ru", "⏹ Стоп"), ("en", "⏹ Стоп")])
async def test_quickbar_understands_every_languages_labels(language, label):
    i18n.set_language(language)
    update, ctx = MagicMock(), MagicMock()
    update.effective_message.text = label
    mock = AsyncMock()
    with patch.dict(quickbar._ACTIONS, {quickbar.BTN_STOP: mock}):
        await quickbar.quickbar_handler(update, ctx)
    mock.assert_awaited_once_with(update, ctx)


def test_quickbar_filter_covers_all_languages():
    labels = quickbar._all_labels()
    assert "📋 Menu" in labels and "📋 Меню" in labels


# --- command registry -----------------------------------------------------------------------

def test_registry_matches_registered_command_handlers():
    app = Application.builder().token("123456:TEST").build()
    register_handlers(app)
    registered = {
        command
        for group in app.handlers.values()
        for handler in group
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    assert registered == ALL_COMMAND_NAMES


def test_help_lists_every_command_grouped():
    text = render_help()
    for command in COMMANDS:
        assert f"/{command.name}" in text
    assert text.index("Model Management") < text.index("Chat Sessions") < text.index("Settings")
    assert "&lt;model&gt;" in text and "<code>" in text


def test_help_is_translated():
    i18n.set_language("ru")
    text = render_help()
    assert "Управление моделями" in text and "/models — Список моделей на диске" in text


def test_telegram_menu_commands_per_language():
    english = {c.command: c.description for c in bot_commands("en")}
    russian = {c.command: c.description for c in bot_commands("ru")}
    assert english.keys() == russian.keys() >= {"menu", "status", "stop", "newchat", "help"}
    assert russian["stop"] == "Остановить текущий ответ"
    assert english["stop"] == "Stop the current reply"
    assert all(len(d) <= 256 for d in russian.values())


@pytest.mark.asyncio
async def test_commands_help_topic_in_menu(context, query):
    update = MagicMock()
    update.effective_user.id = 1
    query.data = "menu:help:commands"
    update.callback_query = query
    await menu_callback_handler(update, context)
    assert "/newchat" in query.edit_message_text.await_args.kwargs["text"]


# --- persistent errors with actions ---------------------------------------------------------

@pytest.mark.asyncio
async def test_reply_error_stays_and_offers_actions_and_close():
    source = MagicMock()
    source.reply_text = AsyncMock(return_value=MagicMock())
    with patch("src.bot.ephemeral.schedule_delete") as scheduled:
        await reply_error(source, "❌ boom", (("🔄 Retry", "x:retry"), ("📊 Status", "menu:status")))
    scheduled.assert_not_called()                 # not auto-deleted
    rows = source.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
    assert [b.callback_data for b in rows[0]] == ["x:retry", "menu:status"]
    assert rows[-1][0].callback_data == CB_DISMISS


@pytest.mark.asyncio
async def test_close_button_deletes_the_error(context, query):
    update = MagicMock()
    update.effective_user.id = 1
    query.data = CB_DISMISS
    query.message.delete = AsyncMock()
    update.callback_query = query
    await menu_callback_handler(update, context)
    query.message.delete.assert_awaited_once()


def test_unreachable_error_offers_status_button():
    markup = inference.error_keyboard(ConnectionError("down"), inference.CB_RETRY)
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == [inference.CB_RETRY, "menu:status"]
    generic = inference.error_keyboard(RuntimeError("x"), inference.CB_RETRY)
    assert [b.callback_data for row in generic.inline_keyboard for b in row] == [inference.CB_RETRY]


@pytest.mark.asyncio
async def test_lm_studio_down_when_listing_models_gives_a_persistent_error_with_actions(context):
    from src.bot.handlers.models import models_command

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    context.args = []
    context.bot_data["config"].LMS_HOST = "h"
    with patch("src.lms.sdk.list_downloaded_models", AsyncMock(side_effect=ConnectionError)):
        await models_command(update, context)
    markup = update.effective_message.reply_text.await_args.kwargs["reply_markup"]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "menu:models" in data and "menu:status" in data and CB_DISMISS in data


# --- onboarding -----------------------------------------------------------------------------

def test_welcome_has_quick_start_and_model_hint():
    text = render_welcome("STATUS", no_model_loaded=True)
    assert "Quick start" in text and "STATUS" in text and "No model is loaded yet" in text
    assert "No model is loaded yet" not in render_welcome("STATUS", no_model_loaded=False)


@pytest.mark.asyncio
async def test_start_hints_when_no_model_is_loaded(store, context):
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_chat.id = 7
    update.effective_message.reply_text = AsyncMock(return_value=MagicMock(message_id=1))
    with patch("src.lms.sdk.list_loaded_models", AsyncMock(return_value=[])):
        await start_command(update, context)
    welcome = update.effective_message.reply_text.await_args_list[0]
    assert "No model is loaded yet" in welcome.args[0]
