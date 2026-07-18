from __future__ import annotations

from time import monotonic
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.screen import Screen

from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.core.workflow import Workflow, WorkflowNode, WorkflowNodeState

_SYMBOLS = {
    WorkflowNodeState.PENDING: "○",
    WorkflowNodeState.RUNNING: "◉",
    WorkflowNodeState.COMPLETED: "✓",
    WorkflowNodeState.FAILED: "✕",
    WorkflowNodeState.CANCELLED: "■",
}


def _elapsed(node: WorkflowNode) -> str:
    seconds = node.duration
    if seconds is None and node.started_at is not None:
        seconds = monotonic() - node.started_at
    return f"{seconds:.1f}s" if seconds is not None else "—"


class WorkflowRail(NoMarkupStatic):
    def __init__(self) -> None:
        super().__init__(id="workflow-rail")
        self.display = False

    def set_workflow(self, workflow: Workflow) -> None:
        self.display = workflow.active
        route = " ── ".join(
            f"{_SYMBOLS[phase.state]} {phase.title}" for phase in workflow.phases
        )
        activity = workflow.live_activity or "Preparing response"
        self.update(f"{route}\n{activity}")


class WorkflowNodeRow(NoMarkupStatic):
    class Selected(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    def __init__(self, node: WorkflowNode, *, depth: int, selected: bool) -> None:
        prefix = "  " * depth
        branch = "└─ " if depth else ""
        super().__init__(
            f"{prefix}{branch}{_SYMBOLS[node.state]} {node.title}",
            classes=f"workflow-node workflow-{node.state.value}"
            + (" selected" if selected else ""),
        )
        self.node_id = node.id

    def on_click(self) -> None:
        self.post_message(self.Selected(self.node_id))


class WorkflowMapScreen(Screen[None]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "Back", show=False),
        Binding("ctrl+w", "close", "Back", show=False),
        Binding("up", "select_previous", "Previous", show=False),
        Binding("down", "select_next", "Next", show=False),
        Binding("enter", "select_next", "Next", show=False),
    ]

    def __init__(self, workflow: Workflow) -> None:
        super().__init__(id="workflow-map")
        self.workflow = workflow
        self.selected_id: str | None = None

    def compose(self) -> ComposeResult:
        yield NoMarkupStatic(self.workflow.title, id="workflow-map-title")
        with Horizontal(id="workflow-map-body"):
            with VerticalScroll(id="workflow-nodes"):
                for node, depth in self._workflow_nodes():
                    yield WorkflowNodeRow(
                        node, depth=depth, selected=node.id == self.selected_id
                    )
            yield NoMarkupStatic(self._detail(), id="workflow-detail")
        yield NoMarkupStatic(
            "↑↓ select · Enter next · Esc / Ctrl+W return to chat",
            id="workflow-map-help",
        )

    def refresh_workflow(self, workflow: Workflow) -> None:
        self.workflow = workflow
        ids = {node.id for node, _ in self._workflow_nodes()}
        if self.selected_id not in ids:
            self.selected_id = next(iter(ids), None)
        self.call_later(self.recompose)

    def _workflow_nodes(self) -> list[tuple[WorkflowNode, int]]:
        nodes: list[tuple[WorkflowNode, int]] = []
        for phase in self.workflow.phases:
            nodes.append((phase, 0))
            for child in phase.children:
                nodes.append((child, 1))
                nodes.extend((grandchild, 2) for grandchild in child.children)
        return nodes

    def _detail(self) -> str:
        node = next(
            (item for item, _ in self._workflow_nodes() if item.id == self.selected_id),
            None,
        )
        if node is None:
            return "Select a workflow step to inspect it."
        lines = [
            node.title,
            f"Status: {node.state.value}",
            f"Elapsed: {_elapsed(node)}",
            node.summary,
        ]
        if node.input_preview:
            lines.extend(["", "Input", node.input_preview])
        if node.output_preview:
            lines.extend([
                "",
                "Result" if node.state != WorkflowNodeState.FAILED else "Error",
                node.output_preview,
            ])
        if node.affected_files:
            lines.extend(["", "Files", *node.affected_files])
        return "\n".join(lines)

    async def on_workflow_node_row_selected(
        self, message: WorkflowNodeRow.Selected
    ) -> None:
        self.selected_id = message.node_id
        await self.recompose()

    async def action_select_previous(self) -> None:
        await self._move_selection(-1)

    async def action_select_next(self) -> None:
        await self._move_selection(1)

    async def _move_selection(self, offset: int) -> None:
        ids = [node.id for node, _ in self._workflow_nodes()]
        if not ids:
            return
        try:
            index = ids.index(self.selected_id) if self.selected_id else 0
        except ValueError:
            index = 0
        self.selected_id = ids[(index + offset) % len(ids)]
        await self.recompose()

    def action_close(self) -> None:
        self.dismiss()
