from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ModelSettings(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=-1, ge=-1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stop: list[str] = Field(default_factory=list, max_length=4)


class LoadConfig(BaseModel):
    gpu: str = "auto"
    context_length: int | None = Field(default=None, ge=512)
    identifier: str | None = Field(default=None, max_length=64)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    image_path: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(max_length=64)
    model_identifier: str | None = None
    system_prompt: str = Field(default="", max_length=4096)
    settings: ModelSettings = Field(default_factory=ModelSettings)
    history: list[ChatMessage] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionStore(BaseModel):
    active_session_id: str | None = None
    sessions: dict[str, ChatSession] = Field(default_factory=dict)
