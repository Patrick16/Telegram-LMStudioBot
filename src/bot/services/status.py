"""Human-readable bot / LM Studio status (Telegram HTML)."""

from __future__ import annotations

import html

from src.lms import sdk


def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


async def build_status_text(context) -> str:
    config = context.bot_data["config"]
    store = context.bot_data["store"]
    lines = ["📊 <b>Status</b>", ""]

    online = True
    handles: list = []
    try:
        handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
    except Exception:
        online = False

    endpoint = f"{config.LMS_HOST}:{config.LMS_PORT}"
    if not online:
        lines.append(f"🔴 LM Studio: unreachable ({_code(endpoint)})")
        lines.append("Start LM Studio and enable its local server.")
    else:
        lines.append(f"🟢 LM Studio: online ({_code(endpoint)})")
        names = [getattr(h, "identifier", "?") for h in handles]
        loaded = ", ".join(_code(n) for n in names) if names else "<i>none</i>"
        lines.append(f"🧠 Loaded: {loaded}")

    lines.append("")
    session = store.get_active_session()
    if session is None:
        lines.append("💬 Chat: <i>none yet</i>")
    else:
        count = len(store.load_history(session.id))
        name = html.escape(session.name, quote=False)
        lines.append(f"💬 Chat: <b>{name}</b> · {count} message(s)")
        bound = session.model_identifier
        lines.append("🔗 Model: " + (_code(bound) if bound else "<i>any loaded model</i>"))
        if online and handles:
            try:
                length = await sdk.get_context_length(
                    bound, config.LMS_HOST, config.LMS_PORT
                )
                lines.append(f"📏 Context window: {_code(length)} tokens")
            except Exception:
                pass
        lines.append(f"📜 History policy: {_code(session.settings.history_policy.mode)}")
    return "\n".join(lines)
