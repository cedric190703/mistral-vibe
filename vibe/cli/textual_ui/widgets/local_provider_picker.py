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
from vibe.core.local_providers import LocalModel, LocalProviderDiscovery


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

    def __init__(
        self,
        discoveries: list[LocalProviderDiscovery],
        current_model: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(id="local-provider-picker", **kwargs)
        self._discoveries = discoveries
        self._models = [model for item in discoveries for model in item.models]
        self._current_model = current_model

    def compose(self) -> ComposeResult:
        with Vertical(id="local-provider-picker-content"):
            yield NoMarkupStatic("Local Providers", classes="modelpicker-title")
            yield NoMarkupStatic(self._provider_status(), id="local-provider-status")
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

    def _option(self, model: LocalModel) -> Text:
        marker = "✓" if model.name in self._current_model else "○"
        return Text(
            f"{marker} {model.provider.name} ({model.provider.port})  {model.name}",
            no_wrap=True,
        )

    def _provider_status(self) -> str:
        return "\n".join(
            f"{'●' if item.models else '○'} {item.provider.name} ({item.provider.port}) — "
            f"{len(item.models)} model{'s' if len(item.models) != 1 else ''}"
            for item in self._discoveries
        )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self.post_message(self.ModelSelected(self._models[int(event.option.id)]))

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
