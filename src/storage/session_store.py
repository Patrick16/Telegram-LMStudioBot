from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from src.storage.models import (
    ChatMessage,
    ChatSession,
    ModelPresetsFile,
    SessionHistoryFile,
    SessionPreset,
    SessionPresetsFile,
    SessionStore,
)

logger = logging.getLogger(__name__)


def _atomic_write_json(path: str, data: Any) -> None:
    """Write *data* as JSON to *path* atomically (temp file + ``os.replace``).

    A crash mid-write leaves the previous file intact instead of a truncated one.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _quarantine(path: str) -> str | None:
    """Move an unreadable file aside as ``<path>.corrupt-<ts>`` so it is never overwritten."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = f"{path}.corrupt-{stamp}"
    try:
        os.replace(path, target)
    except OSError as exc:
        logger.error("Could not quarantine corrupt file %s: %s", path, exc)
        return None
    logger.error("Corrupt file %s moved to %s", path, target)
    return target


class SessionStoreManager:
    def __init__(
        self,
        file_path: str,
        histories_dir: str = "data/histories",
        model_presets_file: str = "data/model-presets.json",
        session_presets_file: str = "data/session-presets.json",
    ):
        self._file_path = file_path
        self._histories_dir = histories_dir
        self._model_presets_file = model_presets_file
        self._session_presets_file = session_presets_file
        self._store = SessionStore()

    @property
    def store(self) -> SessionStore:
        return self._store

    # ------------------------------------------------------------------
    # Session metadata persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        if not os.path.exists(self._file_path):
            logger.info("No sessions file found, starting with empty store")
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._store = SessionStore.model_validate(data)
        except (ValueError, OSError) as exc:  # JSONDecodeError and pydantic errors are ValueErrors
            logger.error("Failed to read sessions file %s: %s", self._file_path, exc)
            _quarantine(self._file_path)
            self._store = SessionStore()
            return
        logger.info("Loaded %d sessions from %s", len(self._store.sessions), self._file_path)

    def save(self) -> None:
        _atomic_write_json(self._file_path, self._store.model_dump())

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def create_session(self, name: str) -> ChatSession:
        session = ChatSession(name=name)
        self._store.sessions[session.id] = session
        self._store.active_session_id = session.id
        self.save()
        return session

    def get_language(self) -> str:
        return self._store.language

    def set_language(self, code: str) -> None:
        self._store.language = code
        self.save()

    def get_active_session(self) -> ChatSession | None:
        if self._store.active_session_id is None:
            return None
        return self._store.sessions.get(self._store.active_session_id)

    def list_sessions(self) -> list[ChatSession]:
        return list(self._store.sessions.values())

    def switch_session(self, session_id: str) -> ChatSession | None:
        if session_id not in self._store.sessions:
            return None
        self._store.active_session_id = session_id
        self.save()
        return self._store.sessions[session_id]

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._store.sessions:
            return False
        del self._store.sessions[session_id]
        if self._store.active_session_id == session_id:
            remaining = list(self._store.sessions.keys())
            self._store.active_session_id = remaining[0] if remaining else None
        self.save()
        # Remove history file
        self._delete_history_file(session_id)
        return True

    def resolve_session_id(self, id_or_number: str) -> str | None:
        """Resolve an exact id, a 1-based list number, or a unique id prefix (3+ chars)."""
        if id_or_number in self._store.sessions:
            return id_or_number
        if id_or_number.isdigit():
            index = int(id_or_number) - 1
            ids = list(self._store.sessions.keys())
            if 0 <= index < len(ids):
                return ids[index]
        # A number outside the list may still be the start of an id (ids are UUIDs).
        if len(id_or_number) > 2:
            matches = [sid for sid in self._store.sessions if sid.startswith(id_or_number)]
            if len(matches) == 1:
                return matches[0]
        return None

    def update_session(self, session: ChatSession) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._store.sessions[session.id] = session
        self.save()

    # ------------------------------------------------------------------
    # Per-session history file persistence
    # ------------------------------------------------------------------

    def _history_path(self, session_id: str) -> str:
        return os.path.join(self._histories_dir, f"{session_id}.json")

    def load_history(self, session_id: str) -> list[ChatMessage]:
        path = self._history_path(session_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            hfile = SessionHistoryFile.model_validate(data)
            return hfile.messages
        except (ValueError, OSError) as exc:
            # Never let the next append overwrite unreadable data: move it aside first.
            logger.error("Failed to load history for session %s: %s", session_id, exc)
            _quarantine(path)
            return []

    def save_history(self, session_id: str, messages: list[ChatMessage]) -> None:
        hfile = SessionHistoryFile(
            session_id=session_id,
            messages=messages,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        _atomic_write_json(self._history_path(session_id), hfile.model_dump())

    def append_message(self, session_id: str, message: ChatMessage) -> None:
        messages = self.load_history(session_id)
        messages.append(message)
        self.save_history(session_id, messages)

    def append_messages(self, session_id: str, new_messages: list[ChatMessage]) -> None:
        """Append several messages with a single atomic write (one conversation turn)."""
        messages = self.load_history(session_id)
        messages.extend(new_messages)
        self.save_history(session_id, messages)
        self._touch(session_id)

    def replace_last_assistant(self, session_id: str, message: ChatMessage) -> None:
        """Replace the trailing assistant message (or append if there is none) atomically."""
        messages = self.load_history(session_id)
        if messages and messages[-1].role == "assistant":
            messages.pop()
        messages.append(message)
        self.save_history(session_id, messages)
        self._touch(session_id)

    def _touch(self, session_id: str) -> None:
        """Mark the chat as recently active (shown as "last activity" in the menu)."""
        session = self._store.sessions.get(session_id)
        if session is not None:
            session.updated_at = datetime.now(timezone.utc).isoformat()
            self.save()

    def pop_last_assistant(self, session_id: str) -> ChatMessage | None:
        messages = self.load_history(session_id)
        if messages and messages[-1].role == "assistant":
            removed = messages.pop()
            self.save_history(session_id, messages)
            return removed
        return None

    def _delete_history_file(self, session_id: str) -> None:
        path = self._history_path(session_id)
        try:
            os.remove(path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Preset loading
    # ------------------------------------------------------------------

    def load_model_presets(self) -> ModelPresetsFile:
        if not os.path.exists(self._model_presets_file):
            return ModelPresetsFile()
        try:
            with open(self._model_presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ModelPresetsFile.model_validate(data)
        except Exception:
            logger.warning("Failed to load model presets, returning empty")
            return ModelPresetsFile()

    def load_session_presets(self) -> SessionPresetsFile:
        if not os.path.exists(self._session_presets_file):
            return SessionPresetsFile()
        try:
            with open(self._session_presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionPresetsFile.model_validate(data)
        except Exception:
            logger.warning("Failed to load session presets, returning empty")
            return SessionPresetsFile()

    def save_session_preset(self, name: str, settings, description: str | None = None) -> None:
        """Store a copy of *settings* as a preset; an existing preset of that name is replaced."""
        presets = self.load_session_presets()
        preset = SessionPreset(
            name=name, settings=settings.model_copy(deep=True), description=description
        )
        presets.presets = [p for p in presets.presets if p.name != name] + [preset]
        _atomic_write_json(self._session_presets_file, presets.model_dump())

    def delete_session_preset(self, index: int) -> bool:
        presets = self.load_session_presets()
        if not 0 <= index < len(presets.presets):
            return False
        del presets.presets[index]
        _atomic_write_json(self._session_presets_file, presets.model_dump())
        return True
