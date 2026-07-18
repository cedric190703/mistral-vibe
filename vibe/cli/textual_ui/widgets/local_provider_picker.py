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
from vibe.core.local_providers import LocalModel


class LocalProviderPickerApp(Container):
    can_focus_children = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False)
    ]

    class ModelSelected(Message):
        def __init__(self, model: LocalModel) -> None:
            super().__init__()
            self.model = model

    class Cancelled(Message):
        pass

    def __init__(self, models: list[LocalModel], **kwargs: Any) -> None:
        super().__init__(id="local-provider-picker", **kwargs)
        self._models = models

    def compose(self) -> ComposeResult:
        with Vertical(id="local-provider-picker-content"):
            yield NoMarkupStatic("Local Models", classes="modelpicker-title")
            yield NavigableOptionList(
                *(
                    Option(self._option(model), id=str(index))
                    for index, model in enumerate(self._models)
                ),
                id="local-provider-options",
            )
            yield NoMarkupStatic(
                shortcut_hint(
                    f"{shortcut('↑↓/jk')} Navigate  {shortcut('Enter')} Select  {shortcut('Esc')} Cancel"
                ),
                classes="modelpicker-help",
            )

    @staticmethod
    def _option(model: LocalModel) -> Text:
        return Text(
            f"● {model.provider.name} ({model.provider.port})  {model.name}",
            no_wrap=True,
        )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self.post_message(self.ModelSelected(self._models[int(event.option.id)]))

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
