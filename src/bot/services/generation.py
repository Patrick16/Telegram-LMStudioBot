"""Tracks the running model generation per chat so it can be stopped."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator


class GenerationManager:
    """At most one active generation per chat; cancellable via :meth:`stop`."""

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}

    def is_active(self, chat_id: int) -> bool:
        return chat_id in self._tasks

    @contextlib.asynccontextmanager
    async def track(self, chat_id: int) -> AsyncIterator[None]:
        """Register the current task as the chat's generation for the ``with`` body."""
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - always inside a task
            yield
            return
        self._tasks[chat_id] = task
        try:
            yield
        finally:
            if self._tasks.get(chat_id) is task:
                del self._tasks[chat_id]

    def stop(self, chat_id: int) -> bool:
        """Cancel the chat's generation. Returns False if nothing was running."""
        task = self._tasks.get(chat_id)
        if task is None:
            return False
        task.cancel()
        return True


def get_generations(context) -> GenerationManager:
    """Return the application-wide manager, creating it on first use."""
    return context.bot_data.setdefault("generations", GenerationManager())
