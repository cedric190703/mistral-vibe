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


class RoutingPickerApp(Container):
    can_focus_children = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False)
    ]

    class RoutingSelected(Message):
        def __init__(self, enabled: bool) -> None:
            super().__init__()
            self.enabled = enabled

    class Cancelled(Message):
        pass

    def __init__(self, *, enabled: bool, **kwargs: Any) -> None:
        super().__init__(id="routingpicker-app", **kwargs)
        self._enabled = enabled

    def compose(self) -> ComposeResult:
        options = (
            Option(
                f"{'✓' if self._enabled else '○'} Auto routing — use a local model when available",
                id="auto",
            ),
            Option(
                f"{'✓' if not self._enabled else '○'} Default model — always use active_model",
                id="default",
            ),
        )
        with Vertical(id="routingpicker-content"):
            yield NoMarkupStatic("Model routing", classes="modelpicker-title")
            yield NavigableOptionList(*options, id="routingpicker-options")
            yield NoMarkupStatic(
                shortcut_hint(
                    f"{shortcut('↑↓/jk')} Navigate  {shortcut('Enter')} Select  "
                    f"{shortcut('Esc')} Cancel"
                ),
                classes="modelpicker-help",
            )

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.highlighted = 0 if self._enabled else 1
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.post_message(self.RoutingSelected(event.option.id == "auto"))

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
