"""Stage 4: shared setting specs, parameter screens, creativity modes, readable summary, presets."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.handlers.menu import _handle_settings_action, handle_pending_input
from src.bot.handlers.menu.keyboards import render_current_settings
from src.bot.handlers.menu.params import (
    CREATIVITY_MODES,
    current_mode,
    display_value,
    render_param_text,
)
from src.bot.handlers.menu.screens import SCREEN_SESSION_SETTINGS, render_screen
from src.bot.handlers.settings import set_command, setprompt_command
from src.bot.handlers.settings_spec import (
    SETTING_SPECS,
    apply_text,
    confirmation_for,
    step_value,
)
from src.storage.models import (
    ModelPreset,
    ModelPresetsFile,
    ModelRuntimeSettings,
    SessionGenerationSettings,
)
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store(tmp_path):
    return SessionStoreManager(
        str(tmp_path / "s.json"),
        histories_dir=str(tmp_path / "h"),
        model_presets_file=str(tmp_path / "p" / "model.json"),
        session_presets_file=str(tmp_path / "p" / "session.json"),
    )


@pytest.fixture
def context(store):
    ctx = MagicMock()
    ctx.bot_data = {
        "config": MagicMock(TELEGRAM_OWNER_ID=1, LMS_HOST="h", LMS_PORT=1),
        "store": store,
    }
    ctx.chat_data = {}
    ctx.args = []
    ctx.bot.edit_message_text = AsyncMock()
    return ctx


@pytest.fixture
def query():
    q = MagicMock()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock(return_value=MagicMock())
    q.message.chat_id = 5
    q.message.message_id = 77
    return q


@pytest.fixture
def update():
    u = MagicMock()
    u.effective_user.id = 1
    u.effective_message.reply_text = AsyncMock(return_value=MagicMock())
    return u


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def shown(query):
    return query.edit_message_text.await_args.kwargs


async def open_param(query, context, key):
    await _handle_settings_action(query, context, f"settings:session:{key}")


# --- specs ---------------------------------------------------------------------------

def test_apply_text_parses_clears_and_reports_errors():
    assert apply_text(SETTING_SPECS["temperature"], " 0.4 ") == (0.4, "✅ Temperature set to 0.4")
    assert apply_text(SETTING_SPECS["top_k"], "none") == (None, "✅ Top-K cleared")
    value, message = apply_text(SETTING_SPECS["stop_strings"], "a, b")
    assert value == ["a", "b"] and message.startswith("✅ Stop strings set")
    with pytest.raises(ValueError, match="between 0.0 and 2.0"):
        apply_text(SETTING_SPECS["temperature"], "9")


def test_step_value_moves_and_stops_at_limits():
    spec = SETTING_SPECS["temperature"]
    assert step_value(spec, 0.7, 1) == 0.8
    assert step_value(spec, 0.1, -1) == 0.0
    with pytest.raises(ValueError):
        step_value(spec, 0.0, -1)
    with pytest.raises(ValueError):
        step_value(spec, 2.0, 1)
    assert step_value(SETTING_SPECS["repeat_penalty"], None, 1) == 1.05   # unset starts at 1.0
    with pytest.raises(ValueError):
        step_value(SETTING_SPECS["top_k"], 40, 1)                          # no step defined


def test_confirmation_for_cleared_choice():
    assert confirmation_for(SETTING_SPECS["seed"], None) == "✅ Seed cleared (random)"
    assert confirmation_for(SETTING_SPECS["seed"], 42) == "✅ Seed set to 42"


def test_every_numeric_choice_is_valid_for_its_spec():
    for key, spec in SETTING_SPECS.items():
        for _, value in spec.choices:
            if value is not None and key != "prompt":
                assert spec.parse(str(value)) == value, (key, value)


# --- /set shares the specs --------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("args,attr,expected", [
    (["temperature", "0.3"], "temperature", 0.3),
    (["top_k", "none"], "top_k", None),
    (["stop_strings", "a,", "b"], "stop_strings", ["a", "b"]),
    (["seed", "random"], "seed", None),
])
async def test_set_command_uses_shared_parsing(store, update, context, args, attr, expected):
    session = store.create_session("S")
    session.settings.top_k, session.settings.seed = 5, 5
    store.update_session(session)
    context.args = args
    await set_command(update, context)
    assert getattr(store.get_active_session().settings, attr) == expected


@pytest.mark.asyncio
async def test_set_command_reports_spec_error_and_valid_names(store, update, context):
    store.create_session("S")
    context.args = ["top_p", "7"]
    await set_command(update, context)
    assert "between 0.0 and 1.0" in update.effective_message.reply_text.await_args.args[0]

    context.args = ["nope", "1"]
    await set_command(update, context)
    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Unknown setting" in reply and "temperature" in reply and "seed" in reply


@pytest.mark.asyncio
async def test_setprompt_still_works(store, update, context):
    store.create_session("S")
    context.args = ["Be", "brief"]
    await setprompt_command(update, context)
    assert store.get_active_session().settings.system_prompt == "Be brief"


# --- parameter screen -------------------------------------------------------------------

def test_param_text_shows_current_default_and_range():
    settings = SessionGenerationSettings(temperature=1.2)
    text = render_param_text("temperature", settings)
    assert "<code>1.2</code>" in text and "Default: <code>0.7</code>" in text
    assert "0.0 – 2.0" in text


def test_display_values_are_readable():
    assert display_value("max_tokens", -1) == "unlimited"
    assert display_value("seed", None) == "random"
    assert display_value("top_k", None) == "default"
    assert display_value("stop_strings", []) == "none"


@pytest.mark.asyncio
async def test_tapping_a_setting_opens_its_screen_with_marked_choice(store, context, query):
    store.create_session("S")
    await open_param(query, context, "temperature")
    labels = dict(buttons(shown(query)["reply_markup"]))
    assert labels["✅ 0.7"] == "settings:param:pick:2"
    assert labels["➖ 0.1"] == "settings:param:step:-1"
    assert "settings:param:input" in labels.values() and "settings:param:reset" in labels.values()
    assert "Temperature" in shown(query)["text"]


@pytest.mark.asyncio
async def test_pick_sets_value_and_shows_banner(store, context, query):
    store.create_session("S")
    await open_param(query, context, "temperature")
    await _handle_settings_action(query, context, "settings:param:pick:0")
    assert store.get_active_session().settings.temperature == 0.0
    assert shown(query)["text"].startswith("✅ Temperature set to 0.0")


@pytest.mark.asyncio
async def test_pick_none_returns_to_default(store, context, query):
    session = store.create_session("S")
    session.settings.top_k = 40
    store.update_session(session)
    await open_param(query, context, "top_k")
    await _handle_settings_action(query, context, "settings:param:pick:0")
    assert store.get_active_session().settings.top_k is None


@pytest.mark.asyncio
async def test_step_up_down_and_limit(store, context, query):
    store.create_session("S")
    await open_param(query, context, "temperature")
    await _handle_settings_action(query, context, "settings:param:step:1")
    assert store.get_active_session().settings.temperature == 0.8
    store.get_active_session().settings.temperature = 2.0
    await _handle_settings_action(query, context, "settings:param:step:1")
    assert "Already at the limit" in shown(query)["text"]
    assert store.get_active_session().settings.temperature == 2.0


@pytest.mark.asyncio
async def test_reset_returns_default(store, context, query):
    session = store.create_session("S")
    session.settings.max_tokens = 100
    store.update_session(session)
    await open_param(query, context, "max_tokens")
    await _handle_settings_action(query, context, "settings:param:reset")
    assert store.get_active_session().settings.max_tokens == -1
    assert "Max Tokens reset to default" in shown(query)["text"]


@pytest.mark.asyncio
async def test_system_prompt_quick_pick(store, context, query):
    store.create_session("S")
    await open_param(query, context, "prompt")
    await _handle_settings_action(query, context, "settings:param:pick:1")
    assert store.get_active_session().settings.system_prompt == "Answer briefly and to the point."


@pytest.mark.asyncio
async def test_stop_strings_screen_has_no_quick_picks(store, context, query):
    store.create_session("S")
    await open_param(query, context, "stop_strings")
    data = [d for _, d in buttons(shown(query)["reply_markup"])]
    assert not any(d.startswith("settings:param:pick:") for d in data)


@pytest.mark.asyncio
async def test_param_action_without_open_screen_goes_to_session_settings(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:param:pick:0")
    assert "Session Settings" in shown(query)["text"]


@pytest.mark.asyncio
async def test_typed_value_returns_to_parameter_screen(store, context, query, update):
    store.create_session("S")
    await open_param(query, context, "top_p")
    await _handle_settings_action(query, context, "settings:param:input")
    update.effective_message.text = "0.55"
    await handle_pending_input(update, context)
    assert store.get_active_session().settings.top_p == 0.55
    assert "<code>0.55</code>" in context.bot.edit_message_text.await_args.kwargs["text"]


# --- creativity modes -------------------------------------------------------------------

def test_mode_detection():
    assert current_mode(SessionGenerationSettings()) == "balanced"
    assert current_mode(SessionGenerationSettings(temperature=0.2, top_p=0.9)) == "precise"
    assert current_mode(SessionGenerationSettings(temperature=0.5)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(CREATIVITY_MODES))
async def test_mode_button_applies_values(store, context, query, mode):
    store.create_session("S")
    await _handle_settings_action(query, context, f"settings:mode:{mode}")
    settings = store.get_active_session().settings
    for attr, value in CREATIVITY_MODES[mode][1].items():
        assert getattr(settings, attr) == value
    assert f"✅ Mode: {CREATIVITY_MODES[mode][0]}" in shown(query)["text"]
    labels = [t for t, _ in buttons(shown(query)["reply_markup"])]
    assert f"✅ {CREATIVITY_MODES[mode][0]}" in labels


@pytest.mark.asyncio
async def test_custom_mode_is_labelled(store, context):
    session = store.create_session("S")
    session.settings.temperature = 0.5
    store.update_session(session)
    screen = await render_screen(context, SCREEN_SESSION_SETTINGS)
    assert "Custom" in screen.text


# --- history policy ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_policy_screen_marks_current_with_friendly_names(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:history_policy")
    labels = [t for t, _ in buttons(shown(query)["reply_markup"])]
    assert "✅ 📐 Fit to context" in labels
    assert "Fit to context" in shown(query)["text"]


@pytest.mark.asyncio
async def test_history_policy_choice_shows_friendly_banner(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:history_policy:off")
    assert "✅ History: 🚫 No history" in shown(query)["text"]


# --- readable summary -----------------------------------------------------------------------

def test_summary_is_readable(store):
    session = store.create_session("S")
    session.settings.max_tokens = -1
    session.settings.history_policy.mode = "last_n_pairs"
    session.settings.history_policy.message_pair_limit = 3
    text = render_current_settings(session, "qwen")
    assert "unlimited" in text and "random" in text
    assert "Last N exchanges (3)" in text and "fit_budget_recent" not in text
    assert "🎭 Mode: ⚖️ Balanced" in text and "qwen" in text


# --- presets ----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_session_presets_screen_still_offers_save(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:session_presets")
    assert "No session presets" in shown(query)["text"]
    assert ("💾 Save current as preset", "settings:save_session_preset") in buttons(
        shown(query)["reply_markup"]
    )


@pytest.mark.asyncio
async def test_save_current_settings_as_preset(store, context, query, update):
    session = store.create_session("S")
    session.settings.temperature = 1.4
    store.update_session(session)
    await _handle_settings_action(query, context, "settings:session_presets")
    await _handle_settings_action(query, context, "settings:save_session_preset")
    assert context.chat_data["pending_input"] == "settings:save_preset"

    update.effective_message.text = "Wild"
    await handle_pending_input(update, context)

    saved = store.load_session_presets().presets
    assert [p.name for p in saved] == ["Wild"] and saved[0].settings.temperature == 1.4
    # the presets screen was refreshed and now lists it
    assert "Wild" in str(context.bot.edit_message_text.await_args.kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_save_preset_rejects_empty_and_long_names(store, context, update):
    store.create_session("S")
    context.chat_data["pending_input"] = "settings:save_preset"
    update.effective_message.text = ""
    await handle_pending_input(update, context)
    update.effective_message.text = "x" * 41
    await handle_pending_input(update, context)
    assert store.load_session_presets().presets == []
    assert context.chat_data["pending_input"] == "settings:save_preset"


def test_saving_same_name_replaces_and_delete_validates(store):
    settings = SessionGenerationSettings()
    store.save_session_preset("A", settings)
    settings.temperature = 1.9
    store.save_session_preset("A", settings)
    presets = store.load_session_presets().presets
    assert len(presets) == 1 and presets[0].settings.temperature == 1.9
    assert store.delete_session_preset(5) is False
    assert store.delete_session_preset(0) is True
    assert store.load_session_presets().presets == []


@pytest.mark.asyncio
async def test_preset_preview_apply_and_delete(store, context, query):
    session = store.create_session("S")
    wild = SessionGenerationSettings(temperature=1.4, system_prompt="Be wild")
    wild.history_policy.mode = "off"
    store.save_session_preset("Wild", wild)

    await _handle_settings_action(query, context, "settings:preset:session:0")
    call = shown(query)
    assert "Wild" in call["text"] and "1.4" in call["text"] and "Be wild" in call["text"]
    data = [d for _, d in buttons(call["reply_markup"])]
    assert "settings:apply_session_preset:0" in data and "settings:del_session_preset:0" in data
    assert store.get_active_session().settings.temperature == 0.7   # preview changes nothing

    await _handle_settings_action(query, context, "settings:apply_session_preset:0")
    applied = store.get_active_session().settings
    assert applied.temperature == 1.4 and applied.system_prompt == "Be wild"
    assert applied.history_policy.mode == "off"      # stays a model, not a plain dict
    assert session.id == store.get_active_session().id

    await _handle_settings_action(query, context, "settings:del_session_preset:0")
    assert store.load_session_presets().presets == []
    assert "✅ Preset deleted." in shown(query)["text"]


@pytest.mark.asyncio
async def test_model_preset_preview_and_apply_stages_values(store, context, query):
    store.create_session("S")
    preset = ModelPreset(
        name="Fast", settings=ModelRuntimeSettings(gpu="max", context_length=4096),
        description="all on GPU",
    )
    from src.storage.session_store import _atomic_write_json
    _atomic_write_json(store._model_presets_file, ModelPresetsFile(presets=[preset]).model_dump())

    await _handle_settings_action(query, context, "settings:model_presets")
    assert "Model Presets" in shown(query)["text"]
    await _handle_settings_action(query, context, "settings:preset:model:0")
    assert "max" in shown(query)["text"] and "4096" in shown(query)["text"]
    await _handle_settings_action(query, context, "settings:apply_model_preset:0")
    assert context.chat_data["staged_model_settings"]["gpu"] == "max"
    assert "staged" in shown(query)["text"]


@pytest.mark.asyncio
async def test_invalid_preset_index_is_reported(store, context, query):
    store.create_session("S")
    await _handle_settings_action(query, context, "settings:apply_session_preset:9")
    assert "Invalid preset" in shown(query)["text"]
