from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lms.cli import LmsCliError, list_loaded, list_models, load_model, unload_model
from src.storage.models import LoadConfig


async def _mock_process(returncode=0, stdout=b"", stderr=b""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_list_models(mock_exec):
    mock_exec.return_value = await _mock_process(stdout=b"model1\nmodel2\n")
    result = await list_models()
    assert "model1" in result
    assert "model2" in result
    mock_exec.assert_called_once()
    args = mock_exec.call_args[0]
    assert args[0] == "lms"
    assert args[1] == "ls"


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_list_loaded(mock_exec):
    mock_exec.return_value = await _mock_process(stdout=b"qwen/qwen3-4b [my-model]\n")
    result = await list_loaded()
    assert "qwen/qwen3-4b" in result


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_load_model_default(mock_exec):
    mock_exec.return_value = await _mock_process(stdout=b"Model loaded")
    result = await load_model("qwen/qwen3-4b")
    assert "loaded" in result.lower()
    args = mock_exec.call_args[0]
    assert "load" in args
    assert "qwen/qwen3-4b" in args


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_load_model_with_config(mock_exec):
    mock_exec.return_value = await _mock_process(stdout=b"OK")
    config = LoadConfig(gpu="max", context_length=4096, identifier="mymodel")
    await load_model("qwen/qwen3-4b", config)
    args = mock_exec.call_args[0]
    assert "--gpu" in args
    assert "max" in args
    assert "--context-length" in args
    assert "4096" in args
    assert "--identifier" in args
    assert "mymodel" in args


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_unload_model(mock_exec):
    mock_exec.return_value = await _mock_process(stdout=b"Unloaded")
    result = await unload_model("qwen/qwen3-4b")
    assert "Unloaded" in result


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_cli_error(mock_exec):
    mock_exec.return_value = await _mock_process(returncode=1, stderr=b"Model not found")
    with pytest.raises(LmsCliError, match="Model not found"):
        await list_models()


@pytest.mark.asyncio
@patch("src.lms.cli.asyncio.create_subprocess_exec")
async def test_load_auto_gpu_not_passed(mock_exec):
    mock_exec.return_value = await _mock_process(stdout=b"OK")
    config = LoadConfig(gpu="auto")
    await load_model("test/model", config)
    args = mock_exec.call_args[0]
    assert "--gpu" not in args
