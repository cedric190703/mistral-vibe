from __future__ import annotations

from enum import StrEnum, auto
from time import monotonic
from typing import ClassVar

from rich.text import Text
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


class WorkflowViewMode(StrEnum):
    GRAPH = auto()
    TEXT = auto()
    BOTH = auto()


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
        active_phase = next(
            (
                phase
                for phase in workflow.phases
                if phase.state == WorkflowNodeState.RUNNING
            ),
            None,
        )
        completed = sum(
            node.state == WorkflowNodeState.COMPLETED
            for phase in workflow.phases
            for node in phase.children
        )
        text = Text()
        text.append("WORKFLOW  ", style="bold #FF8205")
        text.append(
            active_phase.title.upper() if active_phase else "PREPARING", style="bold"
        )
        text.append(f" · {completed} complete\n", style="dim")
        text.append(workflow.live_activity or "Preparing response", style="italic")
        self.update(text)


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
            + (" workflow-phase" if depth == 0 else "")
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
        Binding("g", "show_graph", "Graph", show=False),
        Binding("t", "show_text", "Text", show=False),
        Binding("b", "show_both", "Both", show=False),
    ]

    def __init__(
        self, workflow: Workflow, view_mode: WorkflowViewMode = WorkflowViewMode.BOTH
    ) -> None:
        super().__init__(id="workflow-map")
        self.workflow = workflow
        self.selected_id = self._preferred_node_id()
        self.view_mode = view_mode

    def compose(self) -> ComposeResult:
        yield NoMarkupStatic("WORKFLOW MAP", id="workflow-map-eyebrow")
        yield NoMarkupStatic(self.workflow.title, id="workflow-map-title")
        yield NoMarkupStatic(self._header_status(), id="workflow-map-status")
        match self.view_mode:
            case WorkflowViewMode.TEXT:
                with VerticalScroll(id="workflow-map-body"):
                    yield NoMarkupStatic(self._text_view(), id="workflow-text-view")
            case WorkflowViewMode.GRAPH:
                with VerticalScroll(
                    id="workflow-map-body", classes="workflow-graph-only"
                ):
                    yield from self._node_rows()
            case WorkflowViewMode.BOTH:
                with Horizontal(id="workflow-map-body"):
                    with VerticalScroll(id="workflow-nodes"):
                        yield from self._node_rows()
                    yield NoMarkupStatic(self._detail(), id="workflow-detail")
        yield NoMarkupStatic(
            "G graph · T text · B both · ↑↓ navigate · Esc / Ctrl+W return",
            id="workflow-map-help",
        )

    def refresh_workflow(self, workflow: Workflow) -> None:
        self.workflow = workflow
        ids = {node.id for node, _ in self._workflow_nodes()}
        if self.selected_id not in ids:
            self.selected_id = self._preferred_node_id()
        self.call_later(self.recompose)

    def _preferred_node_id(self) -> str | None:
        nodes = self._workflow_nodes()
        return next(
            (
                node.id
                for node, depth in nodes
                if depth and node.state == WorkflowNodeState.RUNNING
            ),
            next((node.id for node, _ in nodes), None),
        )

    def _header_status(self) -> str:
        nodes = [node for node, depth in self._workflow_nodes() if depth]
        running = sum(node.state == WorkflowNodeState.RUNNING for node in nodes)
        completed = sum(node.state == WorkflowNodeState.COMPLETED for node in nodes)
        return f"LIVE · {running} active · {completed} completed"

    def _workflow_nodes(self) -> list[tuple[WorkflowNode, int]]:
        nodes: list[tuple[WorkflowNode, int]] = []
        for phase in self.workflow.phases:
            nodes.append((phase, 0))
            for child in phase.children:
                nodes.append((child, 1))
                nodes.extend((grandchild, 2) for grandchild in child.children)
        return nodes

    def _node_rows(self) -> list[WorkflowNodeRow]:
        return [
            WorkflowNodeRow(node, depth=depth, selected=node.id == self.selected_id)
            for node, depth in self._workflow_nodes()
        ]

    def _text_view(self) -> str:
        lines: list[str] = []
        for node, depth in self._workflow_nodes():
            prefix = "  " * depth
            lines.append(f"{prefix}{_SYMBOLS[node.state]} {node.title}")
            if depth:
                lines.append(f"{prefix}  {node.summary}")
            if node.input_preview:
                lines.append(f"{prefix}  Input: {node.input_preview}")
            if node.output_preview:
                label = "Error" if node.state == WorkflowNodeState.FAILED else "Result"
                lines.append(f"{prefix}  {label}: {node.output_preview}")
            lines.extend(f"{prefix}  File: {path}" for path in node.affected_files)
        return "\n".join(lines)

    def _detail(self) -> str:
        node = next(
            (item for item, _ in self._workflow_nodes() if item.id == self.selected_id),
            None,
        )
        if node is None:
            return "Select a workflow step to inspect it."
        lines = [
            f"{_SYMBOLS[node.state]} {node.state.title()}",
            f"Elapsed: {_elapsed(node)}",
            "",
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

    async def action_show_graph(self) -> None:
        await self._set_view_mode(WorkflowViewMode.GRAPH)

    async def action_show_text(self) -> None:
        await self._set_view_mode(WorkflowViewMode.TEXT)

    async def action_show_both(self) -> None:
        await self._set_view_mode(WorkflowViewMode.BOTH)

    async def _set_view_mode(self, view_mode: WorkflowViewMode) -> None:
        if self.view_mode == view_mode:
            return
        self.view_mode = view_mode
        await self.recompose()

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
