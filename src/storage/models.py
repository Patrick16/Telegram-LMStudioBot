from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# History Reuse Policy
# ---------------------------------------------------------------------------

class HistoryReusePolicy(BaseModel):
    mode: Literal[
        "off", "fit_budget_recent", "last_n_pairs", "full_if_possible",
    ] = "fit_budget_recent"
    message_pair_limit: int | None = None


# ---------------------------------------------------------------------------
# Split-scope settings
# ---------------------------------------------------------------------------

class ModelRuntimeSettings(BaseModel):
    gpu: str = "auto"
    context_length: int | None = Field(default=None, ge=512)
    identifier: str | None = Field(default=None, max_length=64)


class SessionGenerationSettings(BaseModel):
    system_prompt: str = Field(default="", max_length=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=-1, ge=-1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    repeat_penalty: float | None = Field(default=None, gt=0)
    stop_strings: list[str] = Field(default_factory=list, max_length=4)
    seed: int | None = None
    history_policy: HistoryReusePolicy = Field(default_factory=HistoryReusePolicy)


# ---------------------------------------------------------------------------
# Legacy settings (kept for backward compat during migration)
# ---------------------------------------------------------------------------

class ModelSettings(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=-1, ge=-1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stop: list[str] = Field(default_factory=list, max_length=4)


class LoadConfig(BaseModel):
    gpu: str = "auto"
    context_length: int | None = Field(default=None, ge=512)
    identifier: str | None = Field(default=None, max_length=64)


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    image_path: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Session models
# ---------------------------------------------------------------------------

class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(max_length=64)
    model_identifier: str | None = None
    system_prompt: str = Field(default="", max_length=4096)
    settings: SessionGenerationSettings = Field(default_factory=SessionGenerationSettings)
    history: list[ChatMessage] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionStore(BaseModel):
    active_session_id: str | None = None
    sessions: dict[str, ChatSession] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# History file
# ---------------------------------------------------------------------------

class SessionHistoryFile(BaseModel):
    session_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

class ModelPreset(BaseModel):
    name: str
    settings: ModelRuntimeSettings
    description: str | None = None


class SessionPreset(BaseModel):
    name: str
    settings: SessionGenerationSettings
    description: str | None = None


class ModelPresetsFile(BaseModel):
    presets: list[ModelPreset] = Field(default_factory=list)


class SessionPresetsFile(BaseModel):
    presets: list[SessionPreset] = Field(default_factory=list)
