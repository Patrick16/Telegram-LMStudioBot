import json
import os

import pytest

from src.storage.models import ChatMessage, ModelPresetsFile, SessionPresetsFile
from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store_path(tmp_path):
    return str(tmp_path / "sessions.json")


@pytest.fixture
def histories_dir(tmp_path):
    d = str(tmp_path / "histories")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def manager(store_path, histories_dir):
    return SessionStoreManager(store_path, histories_dir=histories_dir)


def test_create_session(manager):
    session = manager.create_session("Test Chat")
    assert session.name == "Test Chat"
    assert manager.store.active_session_id == session.id
    assert session.id in manager.store.sessions


def test_list_sessions(manager):
    manager.create_session("A")
    manager.create_session("B")
    sessions = manager.list_sessions()
    assert len(sessions) == 2
    names = {s.name for s in sessions}
    assert names == {"A", "B"}


def test_switch_session(manager):
    s1 = manager.create_session("First")
    s2 = manager.create_session("Second")
    assert manager.store.active_session_id == s2.id
    result = manager.switch_session(s1.id)
    assert result is not None
    assert manager.store.active_session_id == s1.id


def test_switch_nonexistent(manager):
    result = manager.switch_session("nonexistent-id")
    assert result is None


def test_delete_session(manager):
    s1 = manager.create_session("First")
    s2 = manager.create_session("Second")
    assert manager.delete_session(s1.id)
    assert s1.id not in manager.store.sessions
    assert manager.store.active_session_id == s2.id


def test_delete_active_session(manager):
    s1 = manager.create_session("First")
    manager.create_session("Second")
    manager.switch_session(s1.id)
    manager.delete_session(s1.id)
    assert manager.store.active_session_id is not None
    assert manager.store.active_session_id != s1.id


def test_delete_last_session(manager):
    s = manager.create_session("Only")
    manager.delete_session(s.id)
    assert manager.store.active_session_id is None
    assert len(manager.store.sessions) == 0


def test_delete_nonexistent(manager):
    assert not manager.delete_session("nonexistent")


def test_load_save_roundtrip(manager, store_path):
    manager.create_session("Persisted")
    new_manager = SessionStoreManager(store_path)
    new_manager.load()
    assert len(new_manager.store.sessions) == 1
    sessions = new_manager.list_sessions()
    assert sessions[0].name == "Persisted"


def test_load_no_file(store_path):
    m = SessionStoreManager(store_path)
    m.load()
    assert len(m.store.sessions) == 0


def test_resolve_by_uuid(manager):
    s = manager.create_session("Test")
    assert manager.resolve_session_id(s.id) == s.id


def test_resolve_by_prefix(manager):
    s = manager.create_session("Test")
    prefix = s.id[:8]
    assert manager.resolve_session_id(prefix) == s.id


def test_resolve_by_number(manager):
    s1 = manager.create_session("A")
    s2 = manager.create_session("B")
    assert manager.resolve_session_id("1") == s1.id
    assert manager.resolve_session_id("2") == s2.id


def test_resolve_invalid(manager):
    assert manager.resolve_session_id("99") is None
    assert manager.resolve_session_id("not-a-uuid") is None


def test_get_active_session_none(manager):
    assert manager.get_active_session() is None


def test_update_session(manager):
    s = manager.create_session("Test")
    s.system_prompt = "You are a helper."
    manager.update_session(s)
    loaded = manager.store.sessions[s.id]
    assert loaded.system_prompt == "You are a helper."


# ---------------------------------------------------------------------------
# History file CRUD tests
# ---------------------------------------------------------------------------

def test_load_history_empty(manager):
    msgs = manager.load_history("nonexistent-id")
    assert msgs == []


def test_save_and_load_history(manager):
    sid = "test-session-id"
    messages = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there"),
    ]
    manager.save_history(sid, messages)
    loaded = manager.load_history(sid)
    assert len(loaded) == 2
    assert loaded[0].role == "user"
    assert loaded[0].content == "Hello"
    assert loaded[1].role == "assistant"
    assert loaded[1].content == "Hi there"


def test_append_message(manager):
    sid = "test-session-id"
    manager.save_history(sid, [ChatMessage(role="user", content="First")])
    manager.append_message(sid, ChatMessage(role="assistant", content="Reply"))
    loaded = manager.load_history(sid)
    assert len(loaded) == 2
    assert loaded[1].content == "Reply"


def test_pop_last_assistant(manager):
    sid = "test-session-id"
    manager.save_history(sid, [
        ChatMessage(role="user", content="Q"),
        ChatMessage(role="assistant", content="A"),
    ])
    removed = manager.pop_last_assistant(sid)
    assert removed is not None
    assert removed.content == "A"
    loaded = manager.load_history(sid)
    assert len(loaded) == 1
    assert loaded[0].role == "user"


def test_pop_last_assistant_no_assistant(manager):
    sid = "test-session-id"
    manager.save_history(sid, [ChatMessage(role="user", content="Q")])
    removed = manager.pop_last_assistant(sid)
    assert removed is None


def test_delete_session_removes_history_file(manager, histories_dir):
    s = manager.create_session("Test")
    manager.save_history(s.id, [ChatMessage(role="user", content="Hello")])
    history_file = os.path.join(histories_dir, f"{s.id}.json")
    assert os.path.exists(history_file)
    manager.delete_session(s.id)
    assert not os.path.exists(history_file)


def test_load_history_corrupt_file(manager, histories_dir):
    sid = "corrupt-session"
    path = os.path.join(histories_dir, f"{sid}.json")
    with open(path, "w") as f:
        f.write("NOT JSON")
    msgs = manager.load_history(sid)
    assert msgs == []


# ---------------------------------------------------------------------------
# Preset loading tests
# ---------------------------------------------------------------------------

def test_load_model_presets_missing_file(manager):
    result = manager.load_model_presets()
    assert isinstance(result, ModelPresetsFile)
    assert result.presets == []


def test_load_model_presets(tmp_path):
    preset_file = str(tmp_path / "model-presets.json")
    with open(preset_file, "w") as f:
        json.dump({
            "presets": [{
                "name": "Fast GPU",
                "settings": {"gpu": "max", "context_length": 4096},
            }]
        }, f)
    mgr = SessionStoreManager(
        str(tmp_path / "sessions.json"),
        model_presets_file=preset_file,
    )
    result = mgr.load_model_presets()
    assert len(result.presets) == 1
    assert result.presets[0].name == "Fast GPU"
    assert result.presets[0].settings.gpu == "max"


def test_load_session_presets_missing_file(manager):
    result = manager.load_session_presets()
    assert isinstance(result, SessionPresetsFile)
    assert result.presets == []


def test_load_session_presets(tmp_path):
    preset_file = str(tmp_path / "session-presets.json")
    with open(preset_file, "w") as f:
        json.dump({
            "presets": [{
                "name": "Creative",
                "settings": {
                    "temperature": 1.2,
                    "max_tokens": 1000,
                    "top_p": 0.95,
                },
            }]
        }, f)
    mgr = SessionStoreManager(
        str(tmp_path / "sessions.json"),
        session_presets_file=preset_file,
    )
    result = mgr.load_session_presets()
    assert len(result.presets) == 1
    assert result.presets[0].name == "Creative"
    assert result.presets[0].settings.temperature == 1.2


# ---------------------------------------------------------------------------
# Data-safety regressions (B2, B3)
# ---------------------------------------------------------------------------

def test_corrupt_history_is_quarantined_not_overwritten(manager, histories_dir):
    session = manager.create_session("Chat")
    path = os.path.join(histories_dir, f"{session.id}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"session_id": "x", "messages": [')  # truncated JSON

    manager.append_message(session.id, ChatMessage(role="user", content="new"))

    leftovers = [n for n in os.listdir(histories_dir) if ".corrupt-" in n]
    assert len(leftovers) == 1
    with open(os.path.join(histories_dir, leftovers[0]), encoding="utf-8") as f:
        assert f.read().startswith('{"session_id": "x"')
    assert [m.content for m in manager.load_history(session.id)] == ["new"]


def test_corrupt_sessions_file_does_not_crash_load(store_path, histories_dir):
    with open(store_path, "w", encoding="utf-8") as f:
        f.write("{not json")
    mgr = SessionStoreManager(store_path, histories_dir=histories_dir)
    mgr.load()  # must not raise
    assert mgr.list_sessions() == []
    assert any(".corrupt-" in n for n in os.listdir(os.path.dirname(store_path)))


def test_save_is_atomic_and_leaves_no_temp_files(manager, store_path, monkeypatch):
    manager.create_session("Keep me")
    before = open(store_path, encoding="utf-8").read()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("src.storage.session_store.os.replace", boom)
    with pytest.raises(OSError):
        manager.create_session("Lost")

    assert open(store_path, encoding="utf-8").read() == before
    assert not [n for n in os.listdir(os.path.dirname(store_path)) if n.startswith(".tmp-")]


def test_resolve_prefix_that_looks_like_a_number(manager):
    # ids are UUIDs: an all-digit prefix must still resolve (used to be a flaky miss)
    manager.create_session("A")
    manager.store.sessions["12345678-aaaa-bbbb-cccc-000000000000"] = manager.create_session("B")
    sid = "12345678-aaaa-bbbb-cccc-000000000000"
    assert manager.resolve_session_id("12345678") == sid


def test_resolve_ambiguous_prefix_is_none(manager):
    a = manager.create_session("A")
    b = manager.create_session("B")
    manager.store.sessions.pop(a.id)
    manager.store.sessions.pop(b.id)
    a.id, b.id = "abc-1", "abc-2"
    manager.store.sessions.update({a.id: a, b.id: b})
    assert manager.resolve_session_id("abc") is None
