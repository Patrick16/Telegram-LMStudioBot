from __future__ import annotations

import asyncio
import logging

from src.storage.models import LoadConfig

logger = logging.getLogger(__name__)


class LmsCliError(Exception):
    pass


async def _run_lms(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "lms",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        error_msg = stderr.decode().strip() or stdout.decode().strip()
        raise LmsCliError(error_msg)
    return stdout.decode().strip()


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
    return await _run_lms(*args)


async def unload_model(identifier: str) -> str:
    return await _run_lms("unload", identifier)
