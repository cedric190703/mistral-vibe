from __future__ import annotations

from dataclasses import dataclass
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

_ROUTE_STYLES = {
    WorkflowNodeState.PENDING: "dim",
    WorkflowNodeState.RUNNING: "bold #FF8205",
    WorkflowNodeState.COMPLETED: "bold #52B788",
    WorkflowNodeState.FAILED: "bold #E76F51",
    WorkflowNodeState.CANCELLED: "dim",
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


@dataclass(frozen=True)
class WorkflowMapNode:
    node: WorkflowNode
    depth: int
    connector: str


class WorkflowRail(NoMarkupStatic):
    def __init__(self) -> None:
        super().__init__(id="workflow-rail")
        self.display = False

    def set_workflow(self, workflow: Workflow, *, visible: bool = True) -> None:
        self.display = workflow.active and visible
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

    def __init__(self, entry: WorkflowMapNode, *, selected: bool) -> None:
        self.node = entry.node
        self.connector = entry.connector
        self.depth = entry.depth
        self._pulse = False
        super().__init__(
            self._content(),
            classes=f"workflow-node workflow-{entry.node.state.value}"
            + (" workflow-phase" if entry.depth == 0 else "")
            + (" selected" if selected else ""),
        )
        self.node_id = entry.node.id

    def on_mount(self) -> None:
        if self.node.state == WorkflowNodeState.RUNNING:
            self.set_interval(0.8, self._toggle_pulse)

    def _toggle_pulse(self) -> None:
        self._pulse = not self._pulse
        self.update(self._content())

    def _content(self) -> Text:
        marker = "●" if self._pulse else _SYMBOLS[self.node.state]
        text = Text(self.connector, style="bold #FF8205")
        text.append(f"{marker} ")
        text.append(self.node.title)
        if self.depth == 0:
            text.append(f"  {self.node.state.upper()}", style="dim")
        elif self.node.duration is not None:
            text.append(f"  {_elapsed(self.node)}", style="dim")
        return text

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
        with Horizontal(id="workflow-map-heading"):
            yield NoMarkupStatic(self.workflow.title, id="workflow-map-title")
            yield NoMarkupStatic(self._header_status(), id="workflow-map-status")
        if self.view_mode != WorkflowViewMode.TEXT:
            yield NoMarkupStatic(self._metro_route(), id="workflow-metro-route")
        match self.view_mode:
            case WorkflowViewMode.TEXT:
                with VerticalScroll(id="workflow-map-body"):
                    if text_view := self._text_view():
                        yield NoMarkupStatic(text_view, id="workflow-text-view")
                    else:
                        yield NoMarkupStatic(
                            self._empty_state(), id="workflow-empty-state"
                        )
            case WorkflowViewMode.GRAPH:
                with VerticalScroll(
                    id="workflow-map-body", classes="workflow-graph-only"
                ):
                    if self.workflow.phases:
                        yield NoMarkupStatic(
                            "STATIONS", classes="workflow-section-label"
                        )
                        yield from self._node_rows()
                    else:
                        yield NoMarkupStatic(
                            self._empty_state(), id="workflow-empty-state"
                        )
            case WorkflowViewMode.BOTH:
                with Horizontal(id="workflow-map-body"):
                    with VerticalScroll(id="workflow-nodes"):
                        yield NoMarkupStatic(
                            "STATIONS", classes="workflow-section-label"
                        )
                        yield from self._node_rows()
                    yield NoMarkupStatic(self._detail(), id="workflow-detail")
        yield NoMarkupStatic(
            "G graph · T text · B both · ↑↓ navigate · Esc / Ctrl+W return",
            id="workflow-map-help",
        )

    def refresh_workflow(self, workflow: Workflow) -> None:
        self.workflow = workflow
        ids = {entry.node.id for entry in self._workflow_nodes()}
        if self.selected_id not in ids:
            self.selected_id = self._preferred_node_id()
        self.call_later(self.recompose)

    def _preferred_node_id(self) -> str | None:
        nodes = self._workflow_nodes()
        return next(
            (
                entry.node.id
                for entry in nodes
                if entry.depth and entry.node.state == WorkflowNodeState.RUNNING
            ),
            next((entry.node.id for entry in nodes), None),
        )

    def _header_status(self) -> str:
        nodes = [entry.node for entry in self._workflow_nodes() if entry.depth]
        running = sum(node.state == WorkflowNodeState.RUNNING for node in nodes)
        completed = sum(node.state == WorkflowNodeState.COMPLETED for node in nodes)
        return f"LIVE · {running} active · {completed} completed"

    def _workflow_nodes(self) -> list[WorkflowMapNode]:
        nodes: list[WorkflowMapNode] = []
        for phase in self.workflow.phases:
            nodes.append(WorkflowMapNode(phase, 0, "◆━━ "))
            for child_index, child in enumerate(phase.children):
                child_connector = (
                    "┃  └─ " if child_index == len(phase.children) - 1 else "┃  ├─ "
                )
                nodes.append(WorkflowMapNode(child, 1, child_connector))
                for grandchild_index, grandchild in enumerate(child.children):
                    grandchild_connector = (
                        "┃  │  └─ "
                        if grandchild_index == len(child.children) - 1
                        else "┃  │  ├─ "
                    )
                    nodes.append(WorkflowMapNode(grandchild, 2, grandchild_connector))
        return nodes

    def _node_rows(self) -> list[WorkflowNodeRow]:
        return [
            WorkflowNodeRow(entry, selected=entry.node.id == self.selected_id)
            for entry in self._workflow_nodes()
        ]

    def _metro_route(self) -> Text:
        if not self.workflow.phases:
            return Text("Route will appear when the agent starts working.", style="dim")
        route = Text()
        for index, phase in enumerate(self.workflow.phases):
            route.append(f" {_SYMBOLS[phase.state]} ", style=_ROUTE_STYLES[phase.state])
            route.append(phase.title.upper(), style=_ROUTE_STYLES[phase.state])
            if index != len(self.workflow.phases) - 1:
                route.append(" ─── ", style="bold #FF8205")
        return route

    def _text_view(self) -> str:
        lines: list[str] = []
        for entry in self._workflow_nodes():
            node = entry.node
            prefix = "  " * entry.depth
            if entry.depth == 0:
                lines.extend([
                    f"{_SYMBOLS[node.state]} {node.title.upper()} — {node.state}",
                    "",
                ])
                continue
            lines.append(f"{prefix}{_SYMBOLS[node.state]} {node.title}")
            lines.append(f"{prefix}  {node.summary}")
            if node.input_preview:
                lines.append(f"{prefix}  Input  {node.input_preview}")
            if node.output_preview:
                label = "Error" if node.state == WorkflowNodeState.FAILED else "Result"
                lines.append(f"{prefix}  {label}  {node.output_preview}")
            lines.extend(f"{prefix}  File  {path}" for path in node.affected_files)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _empty_state() -> str:
        return "No active workflow yet.\n\nSend a prompt that uses tools, then press Ctrl+W to follow it live."

    def _detail(self) -> str:
        node = next(
            (
                entry.node
                for entry in self._workflow_nodes()
                if entry.node.id == self.selected_id
            ),
            None,
        )
        if node is None:
            return "Select a workflow step to inspect it."
        lines = [
            "STATION DETAIL",
            f"{_SYMBOLS[node.state]} {node.title}",
            f"{node.state.upper()}  ·  {_elapsed(node)} elapsed",
            "",
            "ACTIVITY",
            node.summary,
        ]
        if node.input_preview:
            lines.extend(["", "INPUT", node.input_preview])
        if node.output_preview:
            lines.extend([
                "",
                "RESULT" if node.state != WorkflowNodeState.FAILED else "ERROR",
                node.output_preview,
            ])
        if node.affected_files:
            lines.extend(["", "AFFECTED FILES", *node.affected_files])
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
        ids = [entry.node.id for entry in self._workflow_nodes()]
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
