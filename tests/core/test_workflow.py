from __future__ import annotations

from tests.stubs.fake_tool import FakeTool, FakeToolArgs
from vibe.core.tools.builtins.todo import TodoArgs, TodoItem, TodoStatus
from vibe.core.types import ToolCallEvent, ToolResultEvent, UserMessageEvent
from vibe.core.workflow import WorkflowNodeState, WorkflowProjector


def _call(call_id: str, *, tool_name: str = "edit") -> ToolCallEvent:
    return ToolCallEvent(
        tool_call_id=call_id,
        tool_name=tool_name,
        tool_class=FakeTool,
        args=FakeToolArgs(),
    )


def test_projector_creates_workflow_from_user_turn_and_tool_events() -> None:
    projector = WorkflowProjector()

    workflow = projector.apply(UserMessageEvent(content="Fix auth", message_id="turn"))
    workflow = projector.apply(_call("edit-1"))

    implement = next(phase for phase in workflow.phases if phase.id == "implement")
    assert workflow.active
    assert implement.children[0].state == WorkflowNodeState.RUNNING
    assert workflow.live_activity == "Editing"


def test_projector_marks_completed_failed_and_cancelled_results() -> None:
    projector = WorkflowProjector()
    projector.start_turn("Fix auth")

    projector.apply(_call("ok"))
    projector.apply(
        ToolResultEvent(tool_name="edit", tool_class=FakeTool, tool_call_id="ok")
    )
    projector.apply(_call("bad"))
    workflow = projector.apply(
        ToolResultEvent(
            tool_name="edit", tool_class=FakeTool, tool_call_id="bad", error="boom"
        )
    )
    projector.apply(_call("cancelled"))
    workflow = projector.finish_turn(cancelled=True)

    states = [node.state for phase in workflow.phases for node in phase.children]
    assert states == [
        WorkflowNodeState.COMPLETED,
        WorkflowNodeState.FAILED,
        WorkflowNodeState.CANCELLED,
    ]


def test_projector_nests_subagent_task_under_its_workflow_node() -> None:
    projector = WorkflowProjector()
    projector.start_turn("Investigate")

    workflow = projector.apply(_call("task-1", tool_name="task"))
    implement = next(phase for phase in workflow.phases if phase.id == "implement")

    assert implement.children[0].children[0].title == "Subagent"
    assert implement.children[0].children[0].state == WorkflowNodeState.RUNNING


def test_projector_finishes_phases_and_exposes_todo_items() -> None:
    projector = WorkflowProjector()
    projector.start_turn("Fix auth")
    todo_call = ToolCallEvent(
        tool_call_id="plan-1",
        tool_name="todo",
        tool_class=FakeTool,
        args=TodoArgs(
            action="write",
            todos=[
                TodoItem(id="read", content="Read the authentication flow"),
                TodoItem(
                    id="test",
                    content="Add a regression test",
                    status=TodoStatus.COMPLETED,
                ),
            ],
        ),
    )

    workflow = projector.apply(todo_call)
    plan = next(phase for phase in workflow.phases if phase.id == "plan")
    assert [item.title for item in plan.children[0].children] == [
        "Read the authentication flow",
        "Add a regression test",
    ]

    workflow = projector.apply(
        ToolResultEvent(tool_name="todo", tool_class=FakeTool, tool_call_id="plan-1")
    )
    plan = next(phase for phase in workflow.phases if phase.id == "plan")
    assert plan.state == WorkflowNodeState.COMPLETED
    assert plan.children[0].children[0].state == WorkflowNodeState.PENDING

    workflow = projector.finish_turn()
    answer = next(phase for phase in workflow.phases if phase.id == "answer")
    assert answer.children[0].title == "Response ready"
    assert answer.state == WorkflowNodeState.COMPLETED
