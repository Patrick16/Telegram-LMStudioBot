from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.chats import (
    chats_command,
    newchat_command,
    removechat_command,
    switchchat_command,
)
from src.bot.handlers.menu import (
    handle_pending_input,
    menu_callback_handler,
    menu_command_handler,
)
from src.bot.handlers.messages import regenerate_command, text_message_handler
from src.bot.handlers.models import (
    load_command,
    loaded_command,
    models_command,
    unload_command,
)
from src.bot.handlers.settings import set_command, setprompt_command
from src.lms.cli import LmsCliError
from src.storage.models import ChatMessage
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.TELEGRAM_OWNER_ID = 12345
    cfg.LMS_HOST = "localhost"
    cfg.LMS_PORT = 1234
    return cfg


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "sessions.json"),
        histories_dir=str(tmp_path / "histories"),
    )


@pytest.fixture
def context(config, store):
    ctx = MagicMock()
    ctx.bot_data = {"config": config, "store": store}
    ctx.chat_data = {}
    ctx.args = []
    ctx.bot = MagicMock()
    ctx.bot.edit_message_text = AsyncMock()
    return ctx


@pytest.fixture
def update():
    u = MagicMock()
    u.effective_user.id = 12345
    u.effective_message.reply_text = AsyncMock()
    u.effective_message.text = "Hello"
    return u


def make_downloaded_model(model_key: str, size_bytes: int):
    return SimpleNamespace(
        model_key=model_key,
        info=SimpleNamespace(size_bytes=size_bytes),
    )


def make_loaded_handle(identifier: str, size_bytes: int, model_key: str | None = None):
    info = SimpleNamespace(
        identifier=identifier,
        size_bytes=size_bytes,
        model_key=model_key or identifier,
    )
    handle = MagicMock()
    # Set both direct attributes and get_info() method for compatibility
    handle.identifier = identifier
    handle.size_bytes = size_bytes
    handle.get_info.return_value = info
    return handle


# --- US1: /models, /loaded ---

@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_downloaded_models", new_callable=AsyncMock)
async def test_models_success(mock_list, update, context):
    mock_list.return_value = [
        make_downloaded_model("qwen/qwen3-4b", 3 * 1024 * 1024 * 1024),
        make_downloaded_model("mistral/mistral-7b", 512 * 1024 * 1024),
    ]

    await models_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    assert "📦 Available models:" in reply
    assert "• qwen/qwen3-4b  3.0 GB" in reply
    assert "• mistral/mistral-7b  512 MB" in reply
    assert "|" not in reply
    assert update.effective_message.reply_text.call_args.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_downloaded_models", new_callable=AsyncMock)
async def test_models_empty(mock_list, update, context):
    mock_list.return_value = []

    await models_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    assert reply == "No models found."


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_downloaded_models", new_callable=AsyncMock)
async def test_models_unreachable(mock_list, update, context):
    mock_list.side_effect = RuntimeError("Connection refused")

    await models_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    assert "Could not connect" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_loaded_models", new_callable=AsyncMock)
async def test_loaded_success(mock_loaded, update, context):
    mock_loaded.return_value = [make_loaded_handle("my-model", 3 * 1024 * 1024 * 1024)]

    await loaded_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    assert "🧠 Loaded models:" in reply
    assert "• my-model  3.0 GB" in reply
    assert "|" not in reply
    assert update.effective_message.reply_text.call_args.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_loaded_models", new_callable=AsyncMock)
async def test_loaded_empty(mock_loaded, update, context):
    mock_loaded.return_value = []

    await loaded_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    assert reply == "No models are currently loaded."


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_loaded_models", new_callable=AsyncMock)
async def test_loaded_unreachable(mock_loaded, update, context):
    mock_loaded.side_effect = RuntimeError("Connection refused")

    await loaded_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    assert "Could not connect" in reply


# --- US2: /load, /unload ---

@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_loaded_models", new_callable=AsyncMock)
@patch("src.bot.handlers.models.sdk.list_downloaded_models", new_callable=AsyncMock)
async def test_load_no_args_shows_keyboard(mock_downloaded, mock_loaded, update, context):
    context.args = []
    mock_downloaded.return_value = [
        make_downloaded_model("qwen/qwen3-4b", 3 * 1024 * 1024 * 1024),
    ]
    mock_loaded.return_value = [
        make_loaded_handle("qwen/qwen3-4b", 3 * 1024 * 1024 * 1024, "qwen/qwen3-4b"),
    ]

    await load_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    keyboard = update.effective_message.reply_text.call_args.kwargs["reply_markup"]
    assert "Select a model to load:" in reply
    assert keyboard.inline_keyboard[0][0].text.startswith("🟢 qwen/qwen3-4b")


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_loaded_models", new_callable=AsyncMock)
@patch("src.bot.handlers.models.sdk.list_downloaded_models", new_callable=AsyncMock)
async def test_load_no_args_paginates_long_lists(mock_downloaded, mock_loaded, update, context):
    context.args = []
    mock_downloaded.return_value = [
        make_downloaded_model(f"model-{i}", 1024 * 1024 * 1024) for i in range(120)
    ]
    mock_loaded.return_value = []

    await load_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    keyboard = update.effective_message.reply_text.call_args.kwargs["reply_markup"]
    assert "page 1/15" in reply
    # 8 models + one navigation row (counter and "next" button)
    assert len(keyboard.inline_keyboard) == 9
    nav = [b.callback_data for b in keyboard.inline_keyboard[-1]]
    assert nav == ["noop", "models:loadpage:1"]


@pytest.mark.asyncio
@patch("src.bot.handlers.models.sdk.list_loaded_models", new_callable=AsyncMock)
async def test_unload_no_args_shows_keyboard(mock_loaded, update, context):
    context.args = []
    mock_loaded.return_value = [
        make_loaded_handle("my-model", 1024 * 1024 * 1024),
    ]

    await unload_command(update, context)

    reply = update.effective_message.reply_text.call_args.args[0]
    keyboard = update.effective_message.reply_text.call_args.kwargs["reply_markup"]
    assert "Select a model to unload:" in reply
    assert keyboard.inline_keyboard[0][0].text.startswith("my-model")


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.load_model", new_callable=AsyncMock)
async def test_load_success(mock_load, update, context):
    context.args = ["qwen/qwen3-4b", "gpu=max", "ctx=4096"]
    mock_load.return_value = "OK"
    await load_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "loaded successfully" in reply


@pytest.mark.asyncio
async def test_load_invalid_gpu(update, context):
    context.args = ["qwen/qwen3-4b", "gpu=invalid"]
    await load_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Invalid gpu value" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.load_model", new_callable=AsyncMock)
async def test_load_model_not_found(mock_load, update, context):
    context.args = ["nonexistent/model"]
    mock_load.side_effect = LmsCliError("Model not found")
    await load_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Load failed" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.unload_model", new_callable=AsyncMock)
async def test_unload_success(mock_unload, update, context):
    context.args = ["qwen/qwen3-4b"]
    mock_unload.return_value = "OK"
    await unload_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "unloaded" in reply


@pytest.mark.asyncio
@patch("src.bot.handlers.models.cli.unload_model", new_callable=AsyncMock)
async def test_unload_not_loaded(mock_unload, update, context):
    context.args = ["qwen/qwen3-4b"]
    mock_unload.side_effect = LmsCliError("Model not loaded")
    await unload_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Model not loaded" in reply


# --- US3: /setprompt, /set ---

@pytest.mark.asyncio
async def test_setprompt_no_chat(update, context):
    context.args = ["You", "are", "a", "helper"]
    await setprompt_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


@pytest.mark.asyncio
async def test_setprompt_set(update, context, store):
    store.create_session("Test")
    context.args = ["You", "are", "a", "helper"]
    await setprompt_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "updated" in reply
    session = store.get_active_session()
    assert session.settings.system_prompt == "You are a helper"


@pytest.mark.asyncio
async def test_setprompt_clear(update, context, store):
    s = store.create_session("Test")
    s.system_prompt = "old prompt"
    store.update_session(s)
    context.args = []
    await setprompt_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "cleared" in reply


@pytest.mark.asyncio
async def test_set_temperature(update, context, store):
    store.create_session("Test")
    context.args = ["temperature", "0.5"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "temperature set to 0.5" in reply.lower()


@pytest.mark.asyncio
async def test_set_invalid_value(update, context, store):
    store.create_session("Test")
    context.args = ["temperature", "5.0"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "between 0.0 and 2.0" in reply


@pytest.mark.asyncio
async def test_set_unknown_setting(update, context, store):
    store.create_session("Test")
    context.args = ["unknown_param", "1.0"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Unknown setting" in reply


@pytest.mark.asyncio
async def test_set_no_chat(update, context):
    context.args = ["temperature", "0.5"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


# --- US4: /newchat, /chats, /switchchat ---

@pytest.mark.asyncio
async def test_newchat(update, context, store):
    context.args = ["My", "Chat"]
    await newchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "My Chat" in reply
    assert len(store.list_sessions()) == 1


@pytest.mark.asyncio
async def test_newchat_default_name(update, context, store):
    context.args = []
    await newchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Chat 1" in reply


@pytest.mark.asyncio
async def test_chats_empty(update, context, store):
    await chats_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No chats" in reply


@pytest.mark.asyncio
async def test_chats_list(update, context, store):
    store.create_session("Alpha")
    store.create_session("Beta")
    await chats_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Alpha" in reply
    assert "Beta" in reply
    assert "▶" in reply


@pytest.mark.asyncio
async def test_switchchat_valid(update, context, store):
    s1 = store.create_session("First")
    store.create_session("Second")
    context.args = ["1"]
    await switchchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "First" in reply
    assert store.store.active_session_id == s1.id


@pytest.mark.asyncio
async def test_switchchat_invalid(update, context, store):
    context.args = ["99"]
    await switchchat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "not found" in reply


# --- US6: /removechat ---

@pytest.mark.asyncio
async def test_removechat_existing(update, context, store):
    store.create_session("ToRemove")
    store.create_session("Keep")
    context.args = ["1"]
    await removechat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "removed" in reply
    assert len(store.list_sessions()) == 1


@pytest.mark.asyncio
async def test_removechat_last(update, context, store):
    store.create_session("Only")
    context.args = ["1"]
    await removechat_command(update, context)
    assert store.store.active_session_id is None


@pytest.mark.asyncio
async def test_removechat_not_found(update, context):
    context.args = ["99"]
    await removechat_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "not found" in reply


# --- US7: text handler, /regenerate ---

class MockStream:
    def __init__(self, fragments):
        self._fragments = list(fragments)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._fragments:
            raise StopAsyncIteration
        return self._fragments.pop(0)


@pytest.mark.asyncio
@patch("src.lms.sdk.chat_stream")
async def test_text_handler_creates_first_chat(mock_stream, update, context, store):
    mock_stream.return_value = MockStream(["Hi there"])
    update.effective_message.text = "Hello"
    assert store.get_active_session() is None
    await text_message_handler(update, context)
    session = store.get_active_session()
    assert session is not None and session.name == "Chat 1"
    assert [m.content for m in store.load_history(session.id)] == ["Hello", "Hi there"]


@pytest.mark.asyncio
@patch("src.lms.sdk.chat_stream")
async def test_text_handler_success(mock_stream, update, context, store):
    store.create_session("Test")
    raw_response = "<think>hidden</think>Hello `there` & <tag>"
    mock_stream.return_value = MockStream([raw_response])
    sent_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=sent_msg)
    update.effective_message.text = "Hi"
    update.effective_user.id = 12345

    await text_message_handler(update, context)

    session = store.get_active_session()
    history = store.load_history(session.id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert history[1].content == "Hello `there` & <tag>"  # <think> not persisted
    assert (
        sent_msg.edit_text.await_args_list[-1].args[0]
        == "Hello <code>there</code> &amp; &lt;tag&gt;"
    )
    assert sent_msg.edit_text.await_args_list[-1].kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_regenerate_no_chat(update, context):
    await regenerate_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "No active chat" in reply


@pytest.mark.asyncio
async def test_regenerate_empty_history(update, context, store):
    store.create_session("Test")
    await regenerate_command(update, context)
    reply = update.effective_message.reply_text.call_args[0][0]
    assert "Nothing to regenerate" in reply


@pytest.mark.asyncio
@patch("src.lms.sdk.chat_stream")
async def test_regenerate_success(mock_stream, update, context, store):
    s = store.create_session("Test")
    store.append_message(s.id, ChatMessage(role="user", content="Hello"))
    store.append_message(s.id, ChatMessage(role="assistant", content="Old response"))

    raw_response = "<think>hidden</think>New response"
    mock_stream.return_value = MockStream([raw_response])
    sent_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=sent_msg)

    await regenerate_command(update, context)
    session = store.get_active_session()
    history = store.load_history(session.id)
    assert history[-1].content == "New response"  # <think> not persisted
    assert sent_msg.edit_text.await_args_list[-1].args[0] == "New response"
    assert sent_msg.edit_text.await_args_list[-1].kwargs["parse_mode"] == "HTML"


# --- T033: Auth integration for menu ---

@pytest.mark.asyncio
async def test_menu_command_non_owner(update, context):
    update.effective_user.id = 99999
    await menu_command_handler(update, context)
    update.effective_message.reply_text.assert_not_called()  # non-owners are ignored silently


@pytest.mark.asyncio
async def test_menu_callback_non_owner(update, context):
    update.effective_user.id = 99999
    query = MagicMock()
    query.data = "menu:main"
    update.callback_query = query
    await menu_callback_handler(update, context)
    update.effective_message.reply_text.assert_not_called()  # non-owners are ignored silently


# --- T034: /menu clears pending_input (FR-006) ---

@pytest.mark.asyncio
async def test_menu_clears_pending_input(update, context):
    context.chat_data["pending_input"] = "models:load"
    msg = MagicMock()
    msg.message_id = 42
    update.effective_message.reply_text = AsyncMock(return_value=msg)
    await menu_command_handler(update, context)
    assert context.chat_data["pending_input"] is None


# --- T035: text_message_handler delegates to pending_input ---

@pytest.mark.asyncio
async def test_text_handler_delegates_pending_input(update, context, store):
    store.create_session("Test")
    context.chat_data["pending_input"] = "sessions:new"
    update.effective_message.text = "My New Chat"
    await text_message_handler(update, context)
    # Should have created a session via pending input, not done inference
    assert len(store.list_sessions()) == 2  # original + new
    assert context.chat_data.get("pending_input") is None


@pytest.mark.asyncio
@patch("src.lms.sdk.chat_stream")
async def test_text_handler_proceeds_without_pending(mock_stream, update, context, store):
    store.create_session("Test")
    context.chat_data["pending_input"] = None
    mock_stream.return_value = MockStream(["Hi"])
    sent_msg = AsyncMock()
    update.effective_message.reply_text = AsyncMock(return_value=sent_msg)
    update.effective_message.text = "Hello"
    await text_message_handler(update, context)
    mock_stream.assert_called_once()


# --- T036: Parity test matrix (SC-003) ---

COMMAND_BUTTON_PARITY = [
    ("/models", "models:list"),
    ("/loaded", "models:loaded"),
    ("/load", "models:load"),
    ("/unload", "models:unload"),
    ("/newchat", "sessions:new"),
    ("/chats", "sessions:list"),
    ("/switchchat", "sessions:switch:<id>"),
    ("/removechat", "sessions:confirm_remove:<id>"),
    ("/setprompt", "settings:session:prompt"),
    ("/set temperature", "settings:session:temperature"),
    ("/set max_tokens", "settings:session:max_tokens"),
    ("/set top_p", "settings:session:top_p"),
    ("/regenerate", "menu:regenerate"),
]


def test_parity_matrix_completeness():
    """Verify every slash command has a corresponding button callback path."""
    from src.bot.handlers import menu
    # Check that the menu module has handlers for each callback prefix
    import pathlib
    package_dir = pathlib.Path(menu.__file__).parent
    source = "".join(f.read_text(encoding="utf-8") for f in package_dir.glob("*.py"))
    # Some callbacks are generated from tables (one button per setting): add the real ones.
    from src.bot.handlers.menu.keyboards import build_session_settings_menu
    from src.storage.models import SessionGenerationSettings

    built = build_session_settings_menu(SessionGenerationSettings())
    source += " ".join(b.callback_data for row in built.inline_keyboard for b in row)
    for _cmd, cb in COMMAND_BUTTON_PARITY:
        # Strip dynamic segment for parametric buttons
        prefix = cb.split("<")[0].rstrip(":")
        assert prefix in source, f"Missing button path for {_cmd} → {cb}"


# --- T037: End-to-end workflow (SC-004) ---

@pytest.mark.asyncio
@patch("src.lms.sdk.list_loaded_models", new_callable=AsyncMock)
async def test_e2e_menu_workflow(mock_loaded, update, context, store):
    """Open menu → loaded models → new chat → (pending input flow)."""
    # 1. Open menu
    msg = MagicMock()
    msg.message_id = 42
    update.effective_message.reply_text = AsyncMock(return_value=msg)
    await menu_command_handler(update, context)
    assert context.chat_data["menu_message_id"] == 42

    # 2. Simulate "loaded models" callback
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    query.data = "models:loaded"
    update.callback_query = query
    mock_loaded.return_value = [make_loaded_handle("qwen/qwen3-4b", 3 * 1024 * 1024 * 1024)]
    downloaded = [make_downloaded_model("qwen/qwen3-4b", 3 * 1024 * 1024 * 1024)]
    with patch("src.lms.sdk.list_downloaded_models", AsyncMock(return_value=downloaded)):
        await menu_callback_handler(update, context)
    shown = query.edit_message_text.call_args.kwargs
    assert "Models" in shown["text"]
    assert any(
        "qwen" in b.text for row in shown["reply_markup"].inline_keyboard for b in row
    )

    # 3. Create chat via pending input
    context.chat_data["pending_input"] = "sessions:new"
    update.effective_message.text = "Test Chat"
    await handle_pending_input(update, context)
    assert len(store.list_sessions()) == 1
    assert context.chat_data.get("pending_input") is None
