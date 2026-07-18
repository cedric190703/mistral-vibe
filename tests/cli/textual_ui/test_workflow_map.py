from __future__ import annotations

import pytest

from tests.conftest import build_test_vibe_app
from vibe.cli.textual_ui.widgets.workflow import WorkflowMapScreen, WorkflowRail
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
