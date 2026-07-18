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
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("space", "select_highlighted", "Select", show=False),
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
        super().__init__(id="local_provider_picker-app", **kwargs)
        self._discoveries = discoveries
        self._models = [model for item in discoveries for model in item.models]
        self._current_model = current_model
        self._selected_index: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="local-provider-picker-content"):
            yield NoMarkupStatic("LOCAL MODEL DISCOVERY", classes="modelpicker-title")
            yield NoMarkupStatic(
                "Choose a model served by Ollama, LM Studio, Jan, or another local provider.",
                classes="modelpicker-description",
            )
            yield NoMarkupStatic(
                f"CURRENT  {self._current_model}", classes="modelpicker-current"
            )
            yield NoMarkupStatic(self._provider_status(), id="local-provider-status")
            yield NavigableOptionList(
                *(
                    Option(self._option(index, model), id=str(index))
                    for index, model in enumerate(self._models)
                ),
                id="local-provider-options",
            )
            yield NoMarkupStatic(
                shortcut_hint(
                    f"{shortcut('↑↓/jk')} Navigate  {shortcut('Space')} Mark  {shortcut('Enter')} Apply  {shortcut('Esc')} Cancel"
                ),
                classes="modelpicker-help",
            )

    def _option(self, index: int, model: LocalModel) -> Text:
        text = Text(no_wrap=True)
        is_selected = self._selected_index == index
        is_current = self._current_model == f"local-{model.provider.port}-{model.name}"
        is_checked = is_selected if self._selected_index is not None else is_current
        marker = "[✓]" if is_checked else "[ ]"
        text.append(f"{marker} ", style="bold #FF8205" if is_checked else "bold")
        text.append(model.name, style="bold" if is_checked or is_current else "")
        text.append(
            f"  {model.provider.name.upper()} :{model.provider.port}", style="dim"
        )
        if is_current:
            text.append("  CURRENT", style="bold #FF8205")
        return text

    def _provider_status(self) -> str:
        online = [item for item in self._discoveries if item.models]
        model_count = sum(len(item.models) for item in online)
        providers = " · ".join(
            f"{item.provider.name} :{item.provider.port} ({len(item.models)})"
            for item in online
        )
        offline_count = len(self._discoveries) - len(online)
        headline = (
            f"{len(online)} online · {offline_count} offline · {model_count} models"
        )
        return f"{headline}\nDETECTED  {providers}" if providers else headline

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id is None:
            return
        index = int(event.option.id)
        if self._selected_index != index:
            self._selected_index = index
            await self._refresh_options(index)
            return
        self.post_message(self.ModelSelected(self._models[index]))

    async def action_select_highlighted(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            return
        index = option_list.highlighted
        self._selected_index = None if self._selected_index == index else index
        await self._refresh_options(index)

    async def _refresh_options(self, highlighted: int) -> None:
        await self.recompose()
        option_list = self.query_one(OptionList)
        option_list.highlighted = highlighted
        option_list.focus()

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
