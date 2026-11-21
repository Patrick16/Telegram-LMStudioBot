import pytest
from filelock import FileLock

from src.bot import main as bot_main


def test_second_instance_exits(tmp_path, monkeypatch):
    lock_path = str(tmp_path / "bot.lock")
    first = FileLock(lock_path)
    second = FileLock(lock_path)
    monkeypatch.setattr(bot_main, "_instance_lock", second)

    first.acquire(timeout=0)
    try:
        with pytest.raises(SystemExit) as exc:
            bot_main._acquire_lock()
        assert exc.value.code == 1
    finally:
        first.release()

    bot_main._acquire_lock()  # free again -> succeeds
    bot_main._release_lock()
