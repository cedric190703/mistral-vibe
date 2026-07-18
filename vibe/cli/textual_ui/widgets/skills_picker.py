from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from vibe.cli.textual_ui.shortcut_hints import shortcut, shortcut_hint
from vibe.cli.textual_ui.skills_commands import skill_source_label
from vibe.cli.textual_ui.widgets.navigable_option_list import NavigableOptionList
from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.core.skills.models import SkillInfo, SkillSource


class SkillsPickerApp(Container):
    can_focus_children = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("space", "toggle_highlighted", "Toggle", show=False),
        Binding("enter", "apply", "Apply", show=False, priority=True),
    ]

    class Applied(Message):
        def __init__(self, enabled_names: frozenset[str]) -> None:
            super().__init__()
            self.enabled_names = enabled_names

    class Cancelled(Message):
        pass

    def __init__(
        self, skills: Mapping[str, SkillInfo], enabled_names: set[str], **kwargs: Any
    ) -> None:
        super().__init__(id="skillspicker-app", **kwargs)
        source_order = {"Built-in": 0, "Project": 1, "Global": 2, "Registry": 3}
        self._skills = dict(
            sorted(
                skills.items(),
                key=lambda item: (
                    source_order[skill_source_label(item[1])],
                    item[0].casefold(),
                ),
            )
        )
        self._skill_names = list(self._skills)
        self._initial_enabled_names = frozenset(enabled_names)
        self._enabled_names = set(enabled_names)

    def compose(self) -> ComposeResult:
        enabled_count = sum(name in self._enabled_names for name in self._skill_names)
        with Vertical(id="skillspicker-content"):
            yield NoMarkupStatic("SKILLS SELECTOR", classes="modelpicker-title")
            yield NoMarkupStatic(
                "Choose which discovered skills are available in this project.",
                classes="modelpicker-description",
            )
            yield NoMarkupStatic(
                f"ACTIVE  {enabled_count} · INACTIVE  {len(self._skills) - enabled_count}",
                classes="modelpicker-current",
            )
            yield NavigableOptionList(
                *(
                    Option(self._option(name, skill), id=name)
                    for name, skill in self._skills.items()
                ),
                id="skillspicker-options",
            )
            yield NoMarkupStatic(
                shortcut_hint(
                    f"{shortcut('↑↓/jk')} Navigate  {shortcut('Space')} Toggle  "
                    f"{shortcut('Enter')} Apply  {shortcut('Esc')} Cancel"
                ),
                classes="modelpicker-help",
            )

    def _option(self, name: str, skill: SkillInfo) -> Text:
        enabled = name in self._enabled_names
        changed = enabled != (name in self._initial_enabled_names)
        builtin = skill.source == SkillSource.BUILTIN
        marker = "[✓]" if enabled else "[ ]"
        text = Text(no_wrap=True)
        text.append(f"{marker} ", style="bold #FF8205" if enabled else "bold")
        text.append(name, style="bold")
        text.append(f"  {skill_source_label(skill).upper()}", style="dim")
        if builtin:
            text.append("  BUILT-IN", style="bold #FF8205")
        elif changed:
            text.append("  PENDING", style="bold #FF8205")
        description = " ".join(skill.description.split())
        text.append(f"  — {description}", style="dim")
        return text

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id is None:
            return
        await self._toggle(event.option.id, event.option_index)

    async def action_toggle_highlighted(self) -> None:
        option_list = self.query_one(OptionList)
        if option_list.highlighted is None:
            return
        index = option_list.highlighted
        await self._toggle(self._skill_names[index], index)

    async def _toggle(self, name: str, highlighted: int) -> None:
        if self._skills[name].source == SkillSource.BUILTIN:
            return
        if name in self._enabled_names:
            self._enabled_names.remove(name)
        else:
            self._enabled_names.add(name)
        await self.recompose()
        option_list = self.query_one(OptionList)
        option_list.highlighted = highlighted
        option_list.focus()

    def action_apply(self) -> None:
        self.post_message(self.Applied(frozenset(self._enabled_names)))

    def action_cancel(self) -> None:
        self.post_message(self.Cancelled())
