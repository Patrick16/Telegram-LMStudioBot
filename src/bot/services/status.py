"""Human-readable bot / LM Studio status (Telegram HTML)."""

from __future__ import annotations

import html

from src.bot.i18n import tr
from src.lms import sdk


def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


async def build_status_text(context) -> str:
    config = context.bot_data["config"]
    store = context.bot_data["store"]
    lines = [tr("📊 <b>Status</b>"), ""]

    online = True
    handles: list = []
    try:
        handles = await sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT)
    except Exception:
        online = False

    endpoint = f"{config.LMS_HOST}:{config.LMS_PORT}"
    if not online:
        lines.append(tr("🔴 LM Studio: unreachable ({endpoint})", endpoint=_code(endpoint)))
        lines.append(tr("Start LM Studio and enable its local server."))
    else:
        lines.append(tr("🟢 LM Studio: online ({endpoint})", endpoint=_code(endpoint)))
        names = [getattr(h, "identifier", "?") for h in handles]
        loaded = ", ".join(_code(n) for n in names) if names else tr("<i>none</i>")
        lines.append(tr("🧠 Loaded: {models}", models=loaded))

    lines.append("")
    session = store.get_active_session()
    if session is None:
        lines.append(tr("💬 Chat: <i>none yet</i>"))
    else:
        count = len(store.load_history(session.id))
        name = html.escape(session.name, quote=False)
        lines.append(tr("💬 Chat: <b>{name}</b> · {count} message(s)", name=name, count=count))
        bound = session.model_identifier
        model = _code(bound) if bound else tr("<i>any loaded model</i>")
        lines.append(tr("🔗 Model: {model}", model=model))
        if online and handles:
            try:
                length = await sdk.get_context_length(
                    bound, config.LMS_HOST, config.LMS_PORT
                )
                lines.append(tr("📏 Context window: {length} tokens", length=_code(length)))
            except Exception:
                pass
        policy = _code(session.settings.history_policy.mode)
        lines.append(tr("📜 History policy: {policy}", policy=policy))
    return "\n".join(lines)
