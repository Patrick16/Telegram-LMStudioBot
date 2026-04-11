from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest

from src.bot.handlers.menu import (
    _execute_inference_send,
    _execute_models_load,
    _execute_models_unload,
    _execute_sessions_new,
    _execute_settings_update,
    _handle_help_section,
    _handle_inference_action,
    _handle_models_action,
    _handle_sessions_action,
    _handle_settings_action,
    _show_section,
    build_back_button,
    build_help_inference,
    build_help_menu,
    build_help_models,
    build_help_sessions,
    build_help_settings,
    build_inference_menu,
    build_main_menu,
    build_models_menu,
    build_sessions_list_keyboard,
    build_sessions_menu,
    build_settings_menu,
    handle_pending_input,
    menu_callback_handler,
    menu_command_handler,
)
from src.lms.cli import LmsCliError
from src.storage.session_store import SessionStoreManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.TELEGRAM_OWNER_ID = 12345
    cfg.LMS_HOST = "localhost"
    cfg.LMS_PORT = 1234
    return cfg


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(str(tmp_path / "sessions.json"))


@pytest.fixture
def context(config, store):
    ctx = MagicMock()
    ctx.bot_data = {"config": config, "store": store}
    ctx.chat_data = {}
    ctx.bot = MagicMock()
    ctx.bot.edit_message_text = AsyncMock()
    return ctx


@pytest.fixture
def update():
    u = MagicMock()
    u.effective_user.id = 12345
    u.effective_chat.id = 99
    u.effective_message.reply_text = AsyncMock()
    u.effective_message.text = "test input"
    return u


@pytest.fixture
def query():
    q = MagicMock()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message = MagicMock()
    q.message.reply_text = AsyncMock()
    q.message.chat.send_message = AsyncMock()
    q.data = ""
    return q


# ---------------------------------------------------------------------------
# Keyboard builder tests (T008, T012)
# ---------------------------------------------------------------------------

class TestBuildMainMenu:
    def test_has_five_buttons(self):
        kb = build_main_menu()
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 5

    def test_button_labels(self):
        kb = build_main_menu()
        labels = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "📦 Model Management" in labels
        assert "🧠 Chat Sessions" in labels
        assert "⚙️ Settings" in labels
        assert "🔮 Inference" in labels
        assert "❓ Help" in labels

    def test_callback_data(self):
        kb = build_main_menu()
        data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "menu:models" in data
        assert "menu:sessions" in data
        assert "menu:settings" in data
        assert "menu:inference" in data
        assert "menu:help" in data


class TestBuildBackButton:
    def test_single_row(self):
        kb = build_back_button("menu:main")
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 1

    def test_button_label(self):
        kb = build_back_button("menu:main")
        assert kb.inline_keyboard[0][0].text == "⬅ Back"

    def test_callback_data(self):
        kb = build_back_button("menu:help")
        assert kb.inline_keyboard[0][0].callback_data == "menu:help"


class TestBuildModelsMenu:
    def test_has_back_button(self):
        kb = build_models_menu()
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"

    def test_action_buttons(self):
        kb = build_models_menu()
        data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "models:list" in data
        assert "models:loaded" in data
        assert "models:load" in data
        assert "models:unload" in data


class TestBuildSessionsMenu:
    def test_has_back_button(self):
        kb = build_sessions_menu()
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"

    def test_action_buttons(self):
        kb = build_sessions_menu()
        data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "sessions:new" in data
        assert "sessions:list" in data
        assert "sessions:remove" in data


class TestBuildSettingsMenu:
    def test_has_back_button(self):
        kb = build_settings_menu()
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"

    def test_action_buttons(self):
        kb = build_settings_menu()
        data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "settings:prompt" in data
        assert "settings:temperature" in data
        assert "settings:max_tokens" in data
        assert "settings:top_p" in data


class TestBuildInferenceMenu:
    def test_shows_active_model(self):
        kb = build_inference_menu("qwen/qwen3-4b")
        label = kb.inline_keyboard[0][0].text
        assert "qwen/qwen3-4b" in label

    def test_shows_no_model(self):
        kb = build_inference_menu(None)
        label = kb.inline_keyboard[0][0].text
        assert "No model loaded" in label

    def test_action_buttons(self):
        kb = build_inference_menu("model")
        data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "inference:send" in data
        assert "inference:regenerate" in data

    def test_has_back_button(self):
        kb = build_inference_menu(None)
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"


class TestBuildHelpMenu:
    def test_has_back_button(self):
        kb = build_help_menu()
        last_row = kb.inline_keyboard[-1]
        assert last_row[0].callback_data == "menu:main"

    def test_topic_buttons(self):
        kb = build_help_menu()
        data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "menu:help:models" in data
        assert "menu:help:sessions" in data
        assert "menu:help:settings" in data
        assert "menu:help:inference" in data


class TestBuildSessionsListKeyboard:
    def test_one_button_per_session(self):
        sessions = [MagicMock(name="ChatA", id="id1"), MagicMock(name="ChatB", id="id2")]
        sessions[0].name = "ChatA"
        sessions[1].name = "ChatB"
        kb = build_sessions_list_keyboard(sessions, "switch")
        # 2 session rows + 1 back row
        assert len(kb.inline_keyboard) == 3
        assert kb.inline_keyboard[0][0].callback_data == "sessions:switch:id1"
        assert kb.inline_keyboard[1][0].callback_data == "sessions:switch:id2"

    def test_back_button_at_end(self):
        sessions = [MagicMock(id="id1")]
        sessions[0].name = "Chat"
        kb = build_sessions_list_keyboard(sessions, "confirm_remove")
        last = kb.inline_keyboard[-1][0]
        assert last.callback_data == "menu:sessions"

    def test_empty_sessions(self):
        kb = build_sessions_list_keyboard([], "switch")
        assert len(kb.inline_keyboard) == 1  # just back button


# ---------------------------------------------------------------------------
# Help topic builder tests (T032)
# ---------------------------------------------------------------------------

class TestHelpTopicBuilders:
    def test_help_models(self):
        text, kb = build_help_models()
        assert "Model Management" in text
        assert kb.inline_keyboard[0][0].callback_data == "menu:help"

    def test_help_sessions(self):
        text, kb = build_help_sessions()
        assert "Sessions" in text
        assert kb.inline_keyboard[0][0].callback_data == "menu:help"

    def test_help_settings(self):
        text, kb = build_help_settings()
        assert "Settings" in text
        assert kb.inline_keyboard[0][0].callback_data == "menu:help"

    def test_help_inference(self):
        text, kb = build_help_inference()
        assert "Inference" in text
        assert kb.inline_keyboard[0][0].callback_data == "menu:help"


# ---------------------------------------------------------------------------
# _show_section tests (T008)
# ---------------------------------------------------------------------------

class TestShowSection:
    @pytest.mark.asyncio
    async def test_show_main_menu(self, query, context):
        await _show_section(query, context, "menu:main")
        query.edit_message_text.assert_called_once()
        call_kwargs = query.edit_message_text.call_args[1]
        assert call_kwargs["text"] == "🏠 Main Menu"

    @pytest.mark.asyncio
    async def test_show_models(self, query, context):
        await _show_section(query, context, "menu:models")
        query.edit_message_text.assert_called_once()
        call_kwargs = query.edit_message_text.call_args[1]
        assert call_kwargs["text"] == "📦 Model Management"

    @pytest.mark.asyncio
    async def test_show_inference_with_model(self, query, context, store):
        s = store.create_session("Test")
        s.model_identifier = "qwen/qwen3-4b"
        store.update_session(s)
        await _show_section(query, context, "menu:inference")
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_stale_message_recovery(self, query, context):
        query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message to edit not found")
        )
        sent_msg = MagicMock()
        sent_msg.message_id = 999
        query.message.chat.send_message = AsyncMock(return_value=sent_msg)
        await _show_section(query, context, "menu:main")
        query.answer.assert_called_once_with("Menu expired — opening a fresh menu.")
        assert context.chat_data["menu_message_id"] == 999

    @pytest.mark.asyncio
    async def test_not_modified_is_noop(self, query, context):
        query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )
        await _show_section(query, context, "menu:main")
        # Should not raise or send fresh menu


# ---------------------------------------------------------------------------
# menu_command_handler tests (T012)
# ---------------------------------------------------------------------------

class TestMenuCommandHandler:
    @pytest.mark.asyncio
    async def test_sends_new_menu(self, update, context):
        msg = MagicMock()
        msg.message_id = 42
        update.effective_message.reply_text = AsyncMock(return_value=msg)
        await menu_command_handler(update, context)
        assert context.chat_data["menu_message_id"] == 42

    @pytest.mark.asyncio
    async def test_clears_pending_input(self, update, context):
        context.chat_data["pending_input"] = "models:load"
        msg = MagicMock()
        msg.message_id = 42
        update.effective_message.reply_text = AsyncMock(return_value=msg)
        await menu_command_handler(update, context)
        assert context.chat_data["pending_input"] is None

    @pytest.mark.asyncio
    async def test_edits_existing_menu(self, update, context):
        context.chat_data["menu_message_id"] = 10
        await menu_command_handler(update, context)
        context.bot.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_new_if_stale(self, update, context):
        context.chat_data["menu_message_id"] = 10
        context.bot.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message not found")
        )
        msg = MagicMock()
        msg.message_id = 55
        update.effective_message.reply_text = AsyncMock(return_value=msg)
        await menu_command_handler(update, context)
        assert context.chat_data["menu_message_id"] == 55

    @pytest.mark.asyncio
    async def test_non_owner_denied(self, update, context):
        update.effective_user.id = 99999
        await menu_command_handler(update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Access denied" in reply


# ---------------------------------------------------------------------------
# menu_callback_handler tests
# ---------------------------------------------------------------------------

class TestMenuCallbackHandler:
    @pytest.mark.asyncio
    async def test_routes_navigation(self, update, context):
        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.data = "menu:models"
        update.callback_query = query
        await menu_callback_handler(update, context)
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_owner_denied(self, update, context):
        update.effective_user.id = 99999
        query = MagicMock()
        query.data = "menu:main"
        update.callback_query = query
        await menu_callback_handler(update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Access denied" in reply


# ---------------------------------------------------------------------------
# Model actions tests (T017)
# ---------------------------------------------------------------------------

class TestModelsAction:
    @pytest.mark.asyncio
    @patch("src.bot.handlers.menu.cli.list_models", new_callable=AsyncMock)
    async def test_list_models(self, mock_list, query, context):
        mock_list.return_value = "model1\nmodel2"
        await _handle_models_action(query, context, "models:list")
        query.message.reply_text.assert_called_once()
        assert "model1" in query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch("src.bot.handlers.menu.cli.list_models", new_callable=AsyncMock)
    async def test_list_models_error(self, mock_list, query, context):
        mock_list.side_effect = LmsCliError("Connection refused")
        await _handle_models_action(query, context, "models:list")
        reply = query.message.reply_text.call_args[0][0]
        assert "Could not list" in reply

    @pytest.mark.asyncio
    @patch("src.bot.handlers.menu.cli.list_loaded", new_callable=AsyncMock)
    async def test_loaded_models(self, mock_loaded, query, context):
        mock_loaded.return_value = "model1 [id1]"
        await _handle_models_action(query, context, "models:loaded")
        assert "model1" in query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_load_sets_pending(self, query, context):
        await _handle_models_action(query, context, "models:load")
        assert context.chat_data["pending_input"] == "models:load"
        query.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_sets_pending(self, query, context):
        await _handle_models_action(query, context, "models:unload")
        assert context.chat_data["pending_input"] == "models:unload"


class TestExecuteModelsLoad:
    @pytest.mark.asyncio
    @patch("src.bot.handlers.menu.cli.load_model", new_callable=AsyncMock)
    async def test_success(self, mock_load, update, context):
        mock_load.return_value = "OK"
        context.chat_data["pending_input"] = "models:load"
        update.effective_message.text = "qwen/qwen3-4b"
        await _execute_models_load("qwen/qwen3-4b", update, context)
        assert "loaded successfully" in update.effective_message.reply_text.call_args[0][0]
        assert context.chat_data["pending_input"] is None

    @pytest.mark.asyncio
    async def test_empty_identifier(self, update, context):
        context.chat_data["pending_input"] = "models:load"
        await _execute_models_load("", update, context)
        assert "cannot be empty" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch("src.bot.handlers.menu.cli.load_model", new_callable=AsyncMock)
    async def test_cli_error(self, mock_load, update, context):
        mock_load.side_effect = LmsCliError("Not found")
        context.chat_data["pending_input"] = "models:load"
        await _execute_models_load("bad-model", update, context)
        assert "Load failed" in update.effective_message.reply_text.call_args[0][0]


class TestExecuteModelsUnload:
    @pytest.mark.asyncio
    @patch("src.bot.handlers.menu.cli.unload_model", new_callable=AsyncMock)
    async def test_success(self, mock_unload, update, context):
        mock_unload.return_value = "OK"
        context.chat_data["pending_input"] = "models:unload"
        await _execute_models_unload("model-id", update, context)
        assert "unloaded" in update.effective_message.reply_text.call_args[0][0].lower()
        assert context.chat_data["pending_input"] is None

    @pytest.mark.asyncio
    async def test_empty_identifier(self, update, context):
        await _execute_models_unload("", update, context)
        assert "cannot be empty" in update.effective_message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
# Sessions action tests (T022)
# ---------------------------------------------------------------------------

class TestSessionsAction:
    @pytest.mark.asyncio
    async def test_new_sets_pending(self, query, context):
        await _handle_sessions_action(query, context, "sessions:new")
        assert context.chat_data["pending_input"] == "sessions:new"

    @pytest.mark.asyncio
    async def test_list_empty(self, query, context):
        await _handle_sessions_action(query, context, "sessions:list")
        call_kwargs = query.edit_message_text.call_args[1]
        assert "No chats" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_list_with_sessions(self, query, context, store):
        store.create_session("Alpha")
        store.create_session("Beta")
        await _handle_sessions_action(query, context, "sessions:list")
        call_kwargs = query.edit_message_text.call_args[1]
        assert "Select a chat" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_switch_session(self, query, context, store):
        s = store.create_session("MyChat")
        store.create_session("Other")
        await _handle_sessions_action(query, context, f"sessions:switch:{s.id}")
        assert store.store.active_session_id == s.id
        assert "Switched" in query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_remove_session(self, query, context, store):
        s = store.create_session("ToRemove")
        await _handle_sessions_action(query, context, f"sessions:confirm_remove:{s.id}")
        assert "removed" in query.message.reply_text.call_args[0][0].lower()
        assert len(store.list_sessions()) == 0

    @pytest.mark.asyncio
    async def test_remove_empty(self, query, context):
        await _handle_sessions_action(query, context, "sessions:remove")
        call_kwargs = query.edit_message_text.call_args[1]
        assert "No chats to remove" in call_kwargs["text"]


class TestExecuteSessionsNew:
    @pytest.mark.asyncio
    async def test_with_name(self, update, context, store):
        await _execute_sessions_new("My Chat", update, context)
        assert "My Chat" in update.effective_message.reply_text.call_args[0][0]
        assert context.chat_data.get("pending_input") is None

    @pytest.mark.asyncio
    async def test_auto_name(self, update, context, store):
        await _execute_sessions_new("", update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Chat 1" in reply


# ---------------------------------------------------------------------------
# Inference action tests (T026)
# ---------------------------------------------------------------------------

class TestInferenceAction:
    @pytest.mark.asyncio
    async def test_send_no_session(self, query, context):
        await _handle_inference_action(query, context, "inference:send")
        assert "No active chat" in query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_send_sets_pending(self, query, context, store):
        store.create_session("Test")
        await _handle_inference_action(query, context, "inference:send")
        assert context.chat_data["pending_input"] == "inference:send"

    @pytest.mark.asyncio
    async def test_regenerate_no_session(self, query, context):
        await _handle_inference_action(query, context, "inference:regenerate")
        assert "No active chat" in query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_noop(self, query, context):
        await _handle_inference_action(query, context, "inference:noop")
        query.message.reply_text.assert_not_called()


class TestExecuteInferenceSend:
    @pytest.mark.asyncio
    async def test_empty_message(self, update, context):
        await _execute_inference_send("", update, context)
        assert "cannot be empty" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_no_session(self, update, context):
        context.chat_data["pending_input"] = "inference:send"
        await _execute_inference_send("Hello", update, context)
        assert "No active chat" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch("src.lms.sdk.chat_stream")
    async def test_success(self, mock_stream, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "inference:send"

        async def fake_stream(*a, **kw):
            yield "Hello"
            yield " world"

        mock_stream.return_value = fake_stream()
        sent_msg = AsyncMock()
        update.effective_message.reply_text = AsyncMock(return_value=sent_msg)

        await _execute_inference_send("Hi", update, context)
        session = store.get_active_session()
        assert len(session.history) == 2
        assert session.history[0].role == "user"
        assert session.history[1].role == "assistant"


# ---------------------------------------------------------------------------
# Settings action tests (T029)
# ---------------------------------------------------------------------------

class TestSettingsAction:
    @pytest.mark.asyncio
    async def test_no_session_guard(self, query, context):
        await _handle_settings_action(query, context, "settings:temperature")
        assert "No active chat" in query.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_temperature_sets_pending(self, query, context, store):
        store.create_session("Test")
        await _handle_settings_action(query, context, "settings:temperature")
        assert context.chat_data["pending_input"] == "settings:temperature"

    @pytest.mark.asyncio
    async def test_prompt_sets_pending(self, query, context, store):
        store.create_session("Test")
        await _handle_settings_action(query, context, "settings:prompt")
        assert context.chat_data["pending_input"] == "settings:prompt"


class TestExecuteSettingsUpdate:
    @pytest.mark.asyncio
    async def test_temperature_valid(self, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "settings:temperature"
        await _execute_settings_update("temperature", "0.5", update, context)
        session = store.get_active_session()
        assert session.settings.temperature == 0.5
        assert context.chat_data["pending_input"] is None

    @pytest.mark.asyncio
    async def test_temperature_out_of_range(self, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "settings:temperature"
        await _execute_settings_update("temperature", "5.0", update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "0.0 and 2.0" in reply
        # pending_input should remain for re-prompt
        assert context.chat_data.get("pending_input") == "settings:temperature"

    @pytest.mark.asyncio
    async def test_temperature_not_a_number(self, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "settings:temperature"
        await _execute_settings_update("temperature", "abc", update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "0.0 and 2.0" in reply

    @pytest.mark.asyncio
    async def test_max_tokens_valid(self, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "settings:max_tokens"
        await _execute_settings_update("max_tokens", "1024", update, context)
        session = store.get_active_session()
        assert session.settings.max_tokens == 1024
        assert context.chat_data["pending_input"] is None

    @pytest.mark.asyncio
    async def test_max_tokens_minus_one(self, update, context, store):
        store.create_session("Test")
        await _execute_settings_update("max_tokens", "-1", update, context)
        session = store.get_active_session()
        assert session.settings.max_tokens == -1

    @pytest.mark.asyncio
    async def test_max_tokens_invalid(self, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "settings:max_tokens"
        await _execute_settings_update("max_tokens", "-5", update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "integer" in reply

    @pytest.mark.asyncio
    async def test_top_p_valid(self, update, context, store):
        store.create_session("Test")
        await _execute_settings_update("top_p", "0.9", update, context)
        session = store.get_active_session()
        assert session.settings.top_p == 0.9

    @pytest.mark.asyncio
    async def test_top_p_out_of_range(self, update, context, store):
        store.create_session("Test")
        context.chat_data["pending_input"] = "settings:top_p"
        await _execute_settings_update("top_p", "1.5", update, context)
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "0.0 and 1.0" in reply

    @pytest.mark.asyncio
    async def test_prompt_set(self, update, context, store):
        store.create_session("Test")
        await _execute_settings_update("prompt", "Be helpful", update, context)
        session = store.get_active_session()
        assert session.system_prompt == "Be helpful"
        assert "updated" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_prompt_clear(self, update, context, store):
        s = store.create_session("Test")
        s.system_prompt = "old"
        store.update_session(s)
        await _execute_settings_update("prompt", "", update, context)
        session = store.get_active_session()
        assert session.system_prompt == ""
        assert "cleared" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_no_session(self, update, context):
        context.chat_data["pending_input"] = "settings:temperature"
        await _execute_settings_update("temperature", "0.5", update, context)
        assert "No active chat" in update.effective_message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
# Handle pending input tests
# ---------------------------------------------------------------------------

class TestHandlePendingInput:
    @pytest.mark.asyncio
    async def test_no_pending(self, update, context):
        context.chat_data["pending_input"] = None
        await handle_pending_input(update, context)
        update.effective_message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_models_load(self, update, context):
        context.chat_data["pending_input"] = "models:load"
        update.effective_message.text = "  "
        await handle_pending_input(update, context)
        # Empty identifier → error
        assert "cannot be empty" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_routes_sessions_new(self, update, context, store):
        context.chat_data["pending_input"] = "sessions:new"
        update.effective_message.text = "New Chat"
        await handle_pending_input(update, context)
        assert "New Chat" in update.effective_message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unknown_key_clears(self, update, context):
        context.chat_data["pending_input"] = "unknown:action"
        update.effective_message.text = "stuff"
        await handle_pending_input(update, context)
        assert context.chat_data["pending_input"] is None


# ---------------------------------------------------------------------------
# Help section handler tests (T032)
# ---------------------------------------------------------------------------

class TestHandleHelpSection:
    @pytest.mark.asyncio
    async def test_models_help(self, query, context):
        await _handle_help_section(query, context, "menu:help:models")
        call_kwargs = query.edit_message_text.call_args[1]
        assert "Model Management" in call_kwargs["text"]
        assert call_kwargs["parse_mode"] == "Markdown"

    @pytest.mark.asyncio
    async def test_sessions_help(self, query, context):
        await _handle_help_section(query, context, "menu:help:sessions")
        call_kwargs = query.edit_message_text.call_args[1]
        assert "Sessions" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_unknown_topic(self, query, context):
        await _handle_help_section(query, context, "menu:help:unknown")
        query.edit_message_text.assert_not_called()
