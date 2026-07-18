from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from rich.text import Text
from textual.widgets import OptionList

from tests.conftest import build_test_vibe_app
from vibe.cli.textual_ui.app import BottomApp
from vibe.cli.textual_ui.widgets.local_provider_picker import LocalProviderPickerApp
from vibe.core.local_providers import LocalModel, LocalProvider, LocalProviderDiscovery


def _checked_options(option_list: OptionList) -> list[bool]:
    return [
        isinstance(option.prompt, Text) and option.prompt.plain.startswith("[✓]")
        for option in option_list.options
    ]


@pytest.mark.asyncio
async def test_local_opens_picker_with_discovered_models() -> None:
    app = build_test_vibe_app()
    models = [LocalModel(LocalProvider("Ollama", 11434), "qwen3")]

    async with app.run_test() as pilot:
        with patch(
            "vibe.cli.textual_ui.app.discover_local_providers",
            new=AsyncMock(
                return_value=[LocalProviderDiscovery(models[0].provider, models)]
            ),
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
                await app._switch_from_input(
                    LocalProviderPickerApp(
                        [LocalProviderDiscovery(local_model.provider, [local_model])],
                        current_model="alpha",
                    )
                )
                await pilot.press("space")
                await pilot.press("enter")
                await pilot.pause()

        assert set_field.await_count == 3
        assert set_field.await_args_list[-1].args == (
            "/active_model",
            "local-11434-qwen3",
        )
        assert app._current_bottom_app == BottomApp.Input
        assert len(app.query(LocalProviderPickerApp)) == 0


@pytest.mark.asyncio
async def test_local_picker_escape_returns_to_input() -> None:
    app = build_test_vibe_app()
    local_model = LocalModel(LocalProvider("Ollama", 11434), "qwen3")

    async with app.run_test() as pilot:
        await app._switch_from_input(
            LocalProviderPickerApp(
                [LocalProviderDiscovery(local_model.provider, [local_model])],
                current_model="alpha",
            )
        )
        await pilot.press("escape")
        await pilot.pause()

        assert app._current_bottom_app == BottomApp.Input


@pytest.mark.asyncio
async def test_local_picker_space_selects_the_highlighted_model() -> None:
    app = build_test_vibe_app()
    local_model = LocalModel(LocalProvider("Ollama", 11434), "qwen3")

    async with app.run_test() as pilot:
        with patch.object(app, "_select_local_model", new=AsyncMock()) as select:
            await app._switch_from_input(
                LocalProviderPickerApp(
                    [LocalProviderDiscovery(local_model.provider, [local_model])],
                    current_model="alpha",
                )
            )
            await pilot.press("space")
            await pilot.pause()
            select.assert_not_awaited()
            await pilot.press("enter")
            await pilot.pause()

        select.assert_awaited_once_with(local_model)
        assert app._current_bottom_app == BottomApp.Input


@pytest.mark.asyncio
async def test_local_picker_moves_the_only_check_to_the_marked_model() -> None:
    app = build_test_vibe_app()
    provider = LocalProvider("Ollama", 11434)
    models = [LocalModel(provider, "qwen3"), LocalModel(provider, "mistral")]

    async with app.run_test() as pilot:
        await app._switch_from_input(
            LocalProviderPickerApp(
                [LocalProviderDiscovery(provider, models)],
                current_model="local-11434-qwen3",
            )
        )
        await pilot.pause()

        option_list = app.query_one("#local-provider-options", OptionList)
        assert _checked_options(option_list) == [True, False]

        await pilot.press("down", "space")
        await pilot.pause()

        option_list = app.query_one("#local-provider-options", OptionList)
        assert _checked_options(option_list) == [False, True]


@pytest.mark.asyncio
async def test_local_can_be_opened_again_after_a_selection() -> None:
    app = build_test_vibe_app()
    local_model = LocalModel(LocalProvider("Ollama", 11434), "qwen3")
    discoveries = [LocalProviderDiscovery(local_model.provider, [local_model])]

    async with app.run_test() as pilot:
        with (
            patch(
                "vibe.cli.textual_ui.app.discover_local_providers",
                new=AsyncMock(return_value=discoveries),
            ),
            patch.object(app, "_select_local_model", new=AsyncMock()),
        ):
            await app._show_local()
            await pilot.press("space")
            await pilot.pause()
            await app._show_local()
            await pilot.pause()

        assert len(app.query(LocalProviderPickerApp)) == 1
