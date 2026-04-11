import pytest

from src.storage.session_store import SessionStoreManager


@pytest.fixture
def store_path(tmp_path):
    return str(tmp_path / "sessions.json")


@pytest.fixture
def manager(store_path):
    return SessionStoreManager(store_path)


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
