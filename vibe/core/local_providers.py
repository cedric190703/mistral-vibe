from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from typing import Any

from vibe.core.utils.http import VibeAsyncHTTPClient

_PROBE_TIMEOUT_SECONDS = 0.3


@dataclass(frozen=True, slots=True)
class LocalProvider:
    name: str
    port: int
    api_key_env_var: str = ""

    @property
    def api_base(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def headers(self) -> dict[str, str]:
        api_key = os.getenv(self.api_key_env_var, "") if self.api_key_env_var else ""
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}


@dataclass(frozen=True, slots=True)
class LocalModel:
    provider: LocalProvider
    name: str


@dataclass(frozen=True, slots=True)
class LocalProviderDiscovery:
    provider: LocalProvider
    models: list[LocalModel]


LOCAL_PROVIDERS = (
    LocalProvider("llama.cpp", 8080),
    LocalProvider("Ollama", 11434),
    LocalProvider("LM Studio", 1234),
    LocalProvider("vLLM", 8000),
    LocalProvider("SGLang", 30000),
    LocalProvider("Jan", 1337, "JAN_API_KEY"),
)


async def discover_local_models() -> list[LocalModel]:
    return [
        model
        for discovery in await discover_local_providers()
        for model in discovery.models
    ]


async def discover_local_providers() -> list[LocalProviderDiscovery]:
    async with VibeAsyncHTTPClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(
            *(_probe_provider(client, provider) for provider in LOCAL_PROVIDERS)
        )
    return results


async def _probe_provider(
    client: VibeAsyncHTTPClient, provider: LocalProvider
) -> LocalProviderDiscovery:
    payload: Any = None
    try:
        response = await client.get(
            f"{provider.api_base}/models", headers=provider.headers
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        pass

    models = _openai_models(provider, payload)
    if provider.name == "LM Studio":
        models = await _lm_studio_models(client, provider) or models
    return LocalProviderDiscovery(provider, models)


def _openai_models(provider: LocalProvider, payload: Any) -> list[LocalModel]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return []
    return [
        LocalModel(provider, model_id)
        for item in payload["data"]
        if isinstance(item, dict)
        and isinstance(model_id := item.get("id"), str)
        and model_id
    ]


async def _lm_studio_models(
    client: VibeAsyncHTTPClient, provider: LocalProvider
) -> list[LocalModel]:
    try:
        response = await client.get(
            f"http://127.0.0.1:{provider.port}/api/v1/models", headers=provider.headers
        )
        response.raise_for_status()
        payload: Any = response.json()
    except Exception:
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return []
    return [
        LocalModel(provider, model_id)
        for item in payload["models"]
        if isinstance(item, dict)
        and isinstance(model_id := item.get("key") or item.get("id"), str)
        and model_id
    ]
