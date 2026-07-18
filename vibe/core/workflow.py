from __future__ import annotations

from enum import StrEnum, auto
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field

from vibe.core.types import BaseEvent, ToolCallEvent, ToolResultEvent, UserMessageEvent


class WorkflowNodeState(StrEnum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class WorkflowPhase(StrEnum):
    UNDERSTAND = auto()
    PLAN = auto()
    IMPLEMENT = auto()
    VERIFY = auto()
    ANSWER = auto()


class WorkflowNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    summary: str
    state: WorkflowNodeState = WorkflowNodeState.PENDING
    started_at: float | None = None
    duration: float | None = None
    input_preview: str | None = None
    output_preview: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    children: list[WorkflowNode] = Field(default_factory=list)


class Workflow(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = "Workflow"
    active: bool = False
    phases: list[WorkflowNode] = Field(default_factory=list)

    @property
    def live_activity(self) -> str | None:
        for phase in self.phases:
            for node in phase.children:
                if node.state == WorkflowNodeState.RUNNING:
                    return node.summary
        return None


def _bounded(value: object | None, limit: int = 320) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x1b", "").strip()
    if not text:
        return None
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _event_files(event: ToolCallEvent) -> list[str]:
    if event.args is None:
        return []
    data = event.args.model_dump(mode="json")
    paths = [
        str(value)
        for key, value in data.items()
        if key in {"file_path", "path", "paths"} and isinstance(value, str)
    ]
    return paths[:5]


def _phase_for(event: ToolCallEvent) -> WorkflowPhase:
    name = event.tool_name.lower()
    if name in {"read_file", "grep", "glob", "web_search", "web_fetch"}:
        return WorkflowPhase.UNDERSTAND
    if name in {"todo", "exit_plan_mode"}:
        return WorkflowPhase.PLAN
    if name in {"edit", "write_file", "apply_patch"}:
        return WorkflowPhase.IMPLEMENT
    if name in {"bash", "experimental_bash"}:
        return WorkflowPhase.VERIFY
    return WorkflowPhase.IMPLEMENT


def _call_summary(event: ToolCallEvent, files: list[str]) -> str:
    verb = {
        "read_file": "Reading",
        "grep": "Searching",
        "glob": "Finding files",
        "edit": "Editing",
        "write_file": "Writing",
        "bash": "Running",
        "experimental_bash": "Running",
        "todo": "Planning",
        "task": "Running subagent",
    }.get(event.tool_name, f"Running {event.tool_name}")
    if files:
        return f"{verb} {files[0]}"
    return verb


class WorkflowProjector:
    """Projects the public event stream into compact, safe workflow state."""

    def __init__(self) -> None:
        self.workflow = Workflow()

    def start_turn(self, prompt: str) -> Workflow:
        phases = [
            WorkflowNode(
                id=phase.value, title=phase.value.title(), summary=phase.value.title()
            )
            for phase in WorkflowPhase
        ]
        self.workflow = Workflow(
            title=f"Workflow — {_bounded(prompt, 80) or 'Agent turn'}",
            active=True,
            phases=phases,
        )
        return self.workflow

    def finish_turn(self, *, cancelled: bool = False, failed: bool = False) -> Workflow:
        phases = []
        for phase in self.workflow.phases:
            children = [
                node.model_copy(
                    update={
                        "state": WorkflowNodeState.CANCELLED
                        if cancelled
                        else WorkflowNodeState.FAILED
                    }
                )
                if (cancelled or failed) and node.state == WorkflowNodeState.RUNNING
                else node
                for node in phase.children
            ]
            phase_state = (
                WorkflowNodeState.COMPLETED
                if children
                and all(node.state == WorkflowNodeState.COMPLETED for node in children)
                else phase.state
            )
            phases.append(
                phase.model_copy(update={"children": children, "state": phase_state})
            )
        self.workflow = self.workflow.model_copy(
            update={"active": False, "phases": phases}
        )
        return self.workflow

    def apply(self, event: BaseEvent) -> Workflow:
        if isinstance(event, UserMessageEvent):
            return self.start_turn(event.content)
        if isinstance(event, ToolCallEvent):
            return self._start_tool(event)
        if isinstance(event, ToolResultEvent):
            return self._finish_tool(event)
        return self.workflow

    def _start_tool(self, event: ToolCallEvent) -> Workflow:
        phase = _phase_for(event)
        files = _event_files(event)
        args = event.args.model_dump(mode="json") if event.args else None
        node = WorkflowNode(
            id=event.tool_call_id,
            title=_call_summary(event, files),
            summary=_call_summary(event, files),
            state=WorkflowNodeState.RUNNING,
            started_at=monotonic(),
            input_preview=_bounded(args),
            affected_files=files,
        )
        if event.tool_name == "task":
            node = node.model_copy(
                update={
                    "children": [
                        WorkflowNode(
                            id=f"{event.tool_call_id}:agent",
                            title="Subagent task",
                            summary="Working in a nested agent",
                            state=WorkflowNodeState.RUNNING,
                        )
                    ]
                }
            )
        self.workflow = self._replace_phase(phase, node, WorkflowNodeState.RUNNING)
        return self.workflow

    def _finish_tool(self, event: ToolResultEvent) -> Workflow:
        state = (
            WorkflowNodeState.CANCELLED
            if event.cancelled
            else WorkflowNodeState.FAILED
            if event.error or event.skipped
            else WorkflowNodeState.COMPLETED
        )
        output = event.error or event.skip_reason or event.result
        phases = []
        for phase in self.workflow.phases:
            children = []
            for node in phase.children:
                if node.id != event.tool_call_id:
                    children.append(node)
                    continue
                children.append(
                    node.model_copy(
                        update={
                            "state": state,
                            "duration": event.duration,
                            "output_preview": _bounded(output),
                            "children": [
                                child.model_copy(update={"state": state})
                                for child in node.children
                            ],
                        }
                    )
                )
            phases.append(phase.model_copy(update={"children": children}))
        self.workflow = self.workflow.model_copy(update={"phases": phases})
        return self.workflow

    def _replace_phase(
        self, target: WorkflowPhase, node: WorkflowNode, state: WorkflowNodeState
    ) -> Workflow:
        phases = [
            phase.model_copy(
                update={"state": state, "children": [*phase.children, node]}
            )
            if phase.id == target.value
            else phase
            for phase in self.workflow.phases
        ]
        return self.workflow.model_copy(update={"phases": phases})
