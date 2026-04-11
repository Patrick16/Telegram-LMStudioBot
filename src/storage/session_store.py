from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from src.storage.models import ChatSession, SessionStore

logger = logging.getLogger(__name__)


class SessionStoreManager:
    def __init__(self, file_path: str):
        self._file_path = file_path
        self._store = SessionStore()

    @property
    def store(self) -> SessionStore:
        return self._store

    def load(self) -> None:
        if not os.path.exists(self._file_path):
            logger.info("No sessions file found, starting with empty store")
            return
        with open(self._file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._store = SessionStore.model_validate(data)
        logger.info("Loaded %d sessions from %s", len(self._store.sessions), self._file_path)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._store.model_dump(), f, indent=2, ensure_ascii=False)

    def create_session(self, name: str) -> ChatSession:
        session = ChatSession(name=name)
        self._store.sessions[session.id] = session
        self._store.active_session_id = session.id
        self.save()
        return session

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
        return True

    def resolve_session_id(self, id_or_number: str) -> str | None:
        # Exact UUID match
        if id_or_number in self._store.sessions:
            return id_or_number
        # Integer index (1-based) — check before prefix to avoid collisions with UUIDs
        try:
            idx = int(id_or_number) - 1
            sessions_list = list(self._store.sessions.keys())
            if 0 <= idx < len(sessions_list):
                return sessions_list[idx]
            return None
        except ValueError:
            pass
        # UUID prefix match (only for non-integer strings longer than 2 chars)
        if len(id_or_number) > 2:
            for sid in self._store.sessions:
                if sid.startswith(id_or_number):
                    return sid
        return None

    def update_session(self, session: ChatSession) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._store.sessions[session.id] = session
        self.save()
