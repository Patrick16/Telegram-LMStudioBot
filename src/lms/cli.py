from __future__ import annotations

import asyncio
import logging

from src.storage.models import LoadConfig

logger = logging.getLogger(__name__)


class LmsCliError(Exception):
    pass


DEFAULT_TIMEOUT = 60.0
LOAD_TIMEOUT = 600.0  # loading large models can take minutes


async def _run_lms(*args: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "lms",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise LmsCliError(
            "The `lms` command was not found. Install the LM Studio CLI and add it to PATH."
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise LmsCliError(f"`lms {args[0]}` timed out after {int(timeout)}s") from exc

    if proc.returncode != 0:
        error_msg = (
            stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
        )
        raise LmsCliError(error_msg)
    return stdout.decode(errors="replace").strip()


async def list_models() -> str:
    return await _run_lms("ls")


async def list_loaded() -> str:
    return await _run_lms("ps")


async def load_model(model: str, config: LoadConfig | None = None) -> str:
    args = ["load", model]
    if config:
        if config.gpu != "auto":
            args.extend(["--gpu", config.gpu])
        if config.context_length is not None:
            args.extend(["--context-length", str(config.context_length)])
        if config.identifier is not None:
            args.extend(["--identifier", config.identifier])
    args.append("-y")
    return await _run_lms(*args, timeout=LOAD_TIMEOUT)


async def unload_model(identifier: str) -> str:
    return await _run_lms("unload", identifier)
