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


def _build_option_text(
    alias: str, provider: str, *, is_current: bool, is_selected: bool
) -> Text:
    text = Text(no_wrap=True)
    marker = "[✓]" if is_selected else "[•]" if is_current else "[ ]"
    text.append(f"{marker} ", style="bold #FF8205" if is_selected else "bold")
    text.append(alias, style="bold" if is_current or is_selected else "")
    text.append(f"  {provider.upper()}", style="dim")
    if is_current:
        text.append("  CURRENT", style="bold #FF8205")
    return text


class ModelPickerApp(Container):
    """Model picker bottom app for selecting the active model."""

    can_focus_children = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("space", "select_highlighted", "Mark", show=False),
    ]

    class ModelSelected(Message):
        def __init__(self, alias: str) -> None:
            self.alias = alias
            super().__init__()

    class Cancelled(Message):
        pass

    def __init__(
        self,
        model_aliases: list[str],
        current_model: str,
        model_providers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(id="modelpicker-app", **kwargs)
        self._model_aliases = model_aliases
        self._current_model = current_model
        self._model_providers = model_providers or {}
        self._selected_alias: str | None = None

    def compose(self) -> ComposeResult:
        options = [
            Option(
                _build_option_text(
                    alias,
                    self._model_providers.get(alias, "model"),
                    is_current=alias == self._current_model,
                    is_selected=alias == self._selected_alias,
                ),
                id=alias,
            )
            for alias in self._model_aliases
        ]
        with Vertical(id="modelpicker-content"):
            yield NoMarkupStatic("MODEL SELECTOR", classes="modelpicker-title")
            yield NoMarkupStatic(
                "Choose the default model used when automatic routing is off.",
                classes="modelpicker-description",
            )
            yield NoMarkupStatic(
                f"CURRENT  {self._current_model}", classes="modelpicker-current"
            )
            yield NavigableOptionList(*options, id="modelpicker-options")
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
        # Pre-select the current model
        for i, alias in enumerate(self._model_aliases):
            if alias == self._current_model:
                option_list.highlighted = i
                break
        option_list.focus()

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id is None:
            return
        if self._selected_alias != event.option.id:
            self._selected_alias = event.option.id
            await self._refresh_options(event.option_index)
            return
        self.post_message(self.ModelSelected(event.option.id))

    async def action_select_highlighted(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            return
        alias = self._model_aliases[option_list.highlighted]
        self._selected_alias = None if self._selected_alias == alias else alias
        await self._refresh_options(option_list.highlighted)

    async def _refresh_options(self, highlighted: int) -> None:
        await self.recompose()
        option_list = self.query_one(OptionList)
        option_list.highlighted = highlighted
        option_list.focus()

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
