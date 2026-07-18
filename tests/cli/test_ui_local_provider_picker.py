from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import build_test_vibe_app
from vibe.cli.textual_ui.app import BottomApp
from vibe.cli.textual_ui.widgets.local_provider_picker import LocalProviderPickerApp
from vibe.core.local_providers import LocalModel, LocalProvider


@pytest.mark.asyncio
async def test_local_opens_picker_with_discovered_models() -> None:
    app = build_test_vibe_app()
    models = [LocalModel(LocalProvider("Ollama", 11434), "qwen3")]

    async with app.run_test() as pilot:
        with patch(
            "vibe.cli.textual_ui.app.discover_local_models",
            new=AsyncMock(return_value=models),
        ):
            await app._show_local()
        await pilot.pause()

        assert app._current_bottom_app == BottomApp.LocalProviderPicker
        assert app.query_one(LocalProviderPickerApp)._models == models


@pytest.mark.asyncio
async def test_local_picker_selection_persists_provider_model_and_active_model() -> (
    None
):
    app = build_test_vibe_app()
    local_model = LocalModel(LocalProvider("Ollama", 11434), "qwen3")

    async with app.run_test() as pilot:
        with patch.object(app, "_reload_config", new=AsyncMock()):
            orchestrator = app.agent_loop.config_orchestrator
            with patch.object(
                orchestrator, "set_field", new=AsyncMock(return_value=[])
            ) as set_field:
                await app._switch_from_input(LocalProviderPickerApp([local_model]))
                await pilot.press("enter")
                await pilot.pause()

        assert set_field.await_count == 3
        assert set_field.await_args_list[-1].args == (
            "/active_model",
            "local-11434-qwen3",
        )
        assert app._current_bottom_app == BottomApp.Input


@pytest.mark.asyncio
async def test_local_picker_escape_returns_to_input() -> None:
    app = build_test_vibe_app()
    local_model = LocalModel(LocalProvider("Ollama", 11434), "qwen3")

    async with app.run_test() as pilot:
        await app._switch_from_input(LocalProviderPickerApp([local_model]))
        await pilot.press("escape")
        await pilot.pause()

        assert app._current_bottom_app == BottomApp.Input
