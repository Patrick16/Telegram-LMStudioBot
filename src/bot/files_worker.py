"""Isolated extractor: ``python -m src.bot.files_worker <kind>`` reads the file from stdin.

Runs in its own process so the bot can kill it on timeout and a parser crash cannot take
the bot down. Writes one JSON object to stdout.
"""

from __future__ import annotations

import json
import sys

from src.bot.files import FileRejected, extract_sync


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    data = sys.stdin.buffer.read()
    try:
        result = extract_sync(kind, data)
        reply = {"ok": True, "text": result.text, "pages": result.pages}
    except FileRejected as exc:
        reply = {"ok": False, "code": exc.code, "detail": str(exc)[:200]}
    except Exception as exc:  # any parser failure means "cannot read", never a crash upstream
        reply = {"ok": False, "code": "damaged", "detail": type(exc).__name__}
    sys.stdout.buffer.write(json.dumps(reply, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
