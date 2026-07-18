from __future__ import annotations

import pytest

from tests.conftest import build_test_vibe_app
from vibe.cli.textual_ui.widgets.workflow import (
    WorkflowMapScreen,
    WorkflowRail,
    WorkflowViewMode,
)
from vibe.cli.textual_ui.widgets.workflow_view_picker import WorkflowViewPickerApp
from vibe.core.workflow import WorkflowProjector


@pytest.mark.asyncio
async def test_ctrl_w_opens_and_closes_workflow_map_without_removing_chat() -> None:
    app = build_test_vibe_app()
    app._workflow_projector.start_turn("Fix authentication")

    async with app.run_test() as pilot:
        await pilot.press("ctrl+w")
        await pilot.pause()
        assert isinstance(app.screen, WorkflowMapScreen)

        await pilot.press("ctrl+w")
        await pilot.pause()
        assert app.query_one("#chat")


@pytest.mark.asyncio
async def test_workflow_rail_and_map_update_while_chat_remains_mounted() -> None:
    app = build_test_vibe_app()
    projector = WorkflowProjector()
    workflow = projector.start_turn("Fix authentication")

    async with app.run_test() as pilot:
        app._refresh_workflow(workflow)
        await pilot.pause()
        rail = app.query_one(WorkflowRail)
        assert rail.display
        assert app.query_one("#chat")

        await pilot.press("ctrl+w")
        await pilot.pause()
        assert isinstance(app.screen, WorkflowMapScreen)
        assert "Workflow" in str(app.screen.query_one("#workflow-map-title").render())


@pytest.mark.asyncio
async def test_workflow_map_switches_between_graph_text_and_both_views() -> None:
    app = build_test_vibe_app()
    app._workflow_projector.start_turn("Fix authentication")

    async with app.run_test() as pilot:
        await pilot.press("ctrl+w", "t")
        await pilot.pause()
        assert isinstance(app.screen, WorkflowMapScreen)
        assert app.screen.query_one("#workflow-text-view")

        await pilot.press("g")
        await pilot.pause()
        assert app.screen.query_one("#workflow-map-body")
        assert not app.screen.query("#workflow-detail")

        await pilot.press("b")
        await pilot.pause()
        assert app.screen.query_one("#workflow-detail")


@pytest.mark.asyncio
async def test_workflow_command_picker_applies_the_selected_view() -> None:
    app = build_test_vibe_app()

    async with app.run_test() as pilot:
        await app._show_workflow_picker()
        await pilot.pause()
        assert app.query_one(WorkflowViewPickerApp)

        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, WorkflowMapScreen)

        app.action_toggle_workflow_map()
        await pilot.pause()
        assert isinstance(app.screen, WorkflowMapScreen)
        assert app.screen.view_mode == WorkflowViewMode.BOTH


@pytest.mark.asyncio
async def test_empty_graph_view_explains_how_to_start_a_workflow() -> None:
    app = build_test_vibe_app()

    async with app.run_test() as pilot:
        app._workflow_view_mode = WorkflowViewMode.GRAPH
        app.action_toggle_workflow_map()
        await pilot.pause()

        assert isinstance(app.screen, WorkflowMapScreen)
        assert "No active workflow" in str(
            app.screen.query_one("#workflow-empty-state").render()
        )
