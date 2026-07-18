from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
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
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("space", "select_highlighted", "Mark", show=False),
    ]

    class RoutingSelected(Message):
        def __init__(self, enabled: bool) -> None:
            super().__init__()
            self.enabled = enabled

    class Cancelled(Message):
        pass

    def __init__(
        self,
        *,
        enabled: bool,
        current_model: str,
        fast_model: str | None = None,
        capable_model: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(id="routingpicker-app", **kwargs)
        self._enabled = enabled
        self._selected_enabled: bool | None = None
        self._current_model = current_model
        self._fast_model = fast_model or "local model"
        self._capable_model = capable_model or current_model

    def compose(self) -> ComposeResult:
        options = (
            Option(self._option(True), id="auto"),
            Option(self._option(False), id="default"),
        )
        with Vertical(id="routingpicker-content"):
            yield NoMarkupStatic("ROUTING MODE", classes="modelpicker-title")
            yield NoMarkupStatic(
                "Control how Vibe chooses a model for each task.",
                classes="modelpicker-description",
            )
            yield NoMarkupStatic(
                f"CURRENT  {'AUTOMATIC' if self._enabled else self._current_model}",
                classes="modelpicker-current",
            )
            yield NavigableOptionList(*options, id="routingpicker-options")
            yield NoMarkupStatic(
                shortcut_hint(
                    f"{shortcut('↑↓/jk')} Navigate  {shortcut('Space')} Mark  "
                    f"{shortcut('Enter')} Apply  "
                    f"{shortcut('Esc')} Cancel"
                ),
                classes="modelpicker-help",
            )

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.highlighted = 0 if self._enabled else 1
        option_list.focus()

    def _option(self, enabled: bool) -> Text:
        marker = (
            "[✓]"
            if self._selected_enabled == enabled
            else "[•]"
            if self._enabled == enabled
            else "[ ]"
        )
        title = "Automatic routing" if enabled else "Selected model only"
        detail = (
            f"Simple → {self._fast_model}  ·  Complex → {self._capable_model}"
            if enabled
            else f"Every task → {self._current_model}"
        )
        text = Text(no_wrap=True)
        text.append(
            f"{marker} ",
            style="bold #FF8205" if self._selected_enabled == enabled else "bold",
        )
        text.append(title, style="bold")
        text.append(f"  {detail}", style="dim")
        return text

    async def on_option_list_option_selected(
        self, _event: OptionList.OptionSelected
    ) -> None:
        if self._selected_enabled is not None:
            self.post_message(self.RoutingSelected(self._selected_enabled))

    async def action_select_highlighted(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            return
        self._selected_enabled = option_list.highlighted == 0
        highlighted = option_list.highlighted
        await self.recompose()
        option_list = self.query_one(OptionList)
        option_list.highlighted = highlighted
        option_list.focus()

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
