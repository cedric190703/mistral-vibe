from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from vibe.cli.textual_ui.shortcut_hints import shortcut, shortcut_hint
from vibe.cli.textual_ui.widgets.navigable_option_list import NavigableOptionList
from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.cli.textual_ui.widgets.workflow import WorkflowViewMode


class WorkflowViewPickerApp(Container):
    can_focus_children = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False)
    ]

    class ViewSelected(Message):
        def __init__(self, view_mode: WorkflowViewMode) -> None:
            super().__init__()
            self.view_mode = view_mode

    class Cancelled(Message):
        pass

    def __init__(self, current_view: WorkflowViewMode, **kwargs: Any) -> None:
        super().__init__(id="workflowviewpicker-app", **kwargs)
        self._current_view = current_view

    def compose(self) -> ComposeResult:
        with Vertical(id="workflow-view-picker-content"):
            yield NoMarkupStatic("Workflow view", classes="modelpicker-title")
            yield NavigableOptionList(
                *(
                    Option(
                        f"{'✓' if mode == self._current_view else '○'} {label}",
                        id=mode.value,
                    )
                    for mode, label in (
                        (WorkflowViewMode.GRAPH, "Graph only"),
                        (WorkflowViewMode.TEXT, "Text only"),
                        (WorkflowViewMode.BOTH, "Graph and text"),
                    )
                ),
                id="workflow-view-options",
            )
            yield NoMarkupStatic(
                shortcut_hint(
                    f"{shortcut('↑↓/jk')} Navigate  {shortcut('Enter')} Select  {shortcut('Esc')} Cancel"
                ),
                classes="modelpicker-help",
            )

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.highlighted = list(WorkflowViewMode).index(self._current_view)
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.post_message(self.ViewSelected(WorkflowViewMode(event.option.id)))

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
