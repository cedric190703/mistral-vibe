from __future__ import annotations

from httpx import Response
import pytest
import respx

from vibe.core.local_providers import discover_local_models


@pytest.mark.asyncio
async def test_discover_local_models_returns_models_from_running_servers() -> None:
    with respx.mock:
        respx.get("http://127.0.0.1:11434/v1/models").mock(
            return_value=Response(200, json={"data": [{"id": "qwen3"}]})
        )
        respx.get("http://127.0.0.1:1234/v1/models").mock(
            return_value=Response(200, json={"data": [{"id": "local-model"}]})
        )

        models = await discover_local_models()

    assert [(model.provider.name, model.name) for model in models] == [
        ("Ollama", "qwen3"),
        ("LM Studio", "local-model"),
    ]


@pytest.mark.asyncio
async def test_discover_local_models_ignores_unavailable_servers() -> None:
    with respx.mock:
        models = await discover_local_models()

    assert models == []


@pytest.mark.asyncio
async def test_discover_local_models_uses_lm_studio_downloaded_models_fallback() -> (
    None
):
    with respx.mock:
        respx.get("http://127.0.0.1:1234/v1/models").mock(
            return_value=Response(200, json={"data": []})
        )
        respx.get("http://127.0.0.1:1234/api/v1/models").mock(
            return_value=Response(200, json={"models": [{"key": "downloaded-qwen"}]})
        )

        models = await discover_local_models()

    assert [(model.provider.name, model.name) for model in models] == [
        ("LM Studio", "downloaded-qwen")
    ]
