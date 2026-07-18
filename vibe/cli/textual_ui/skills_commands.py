from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import get_close_matches
from enum import StrEnum, auto
import json
import shlex

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from vibe.cli.textual_ui.widgets.messages import ExpandingBorder
from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.core.skills.models import SkillInfo, SkillScope, SkillSource
from vibe.core.utils import name_matches

SKILLS_USAGE = (
    "Usage: /skills [-v|--verbose] [--json] | "
    "enable <name> [<name> ...] | disable <name> [<name> ...] | "
    "toggle <name> | status"
)
_TOGGLE_ARGUMENT_COUNT = 2


class SkillsAction(StrEnum):
    LIST = auto()
    ENABLE = auto()
    DISABLE = auto()
    TOGGLE = auto()
    STATUS = auto()


@dataclass(frozen=True)
class SkillsCommand:
    action: SkillsAction
    names: tuple[str, ...] = ()
    verbose: bool = False
    json_output: bool = False


@dataclass(frozen=True)
class SkillStateUpdate:
    enabled_skills: list[str]
    disabled_skills: list[str]
    changed_names: tuple[str, ...]
    target_enabled: bool


@dataclass(frozen=True)
class SkillDisplayLine:
    text: str
    disabled: bool = False
    header: bool = False


class SkillsCommandMessage(Static):
    def __init__(self, lines: Sequence[SkillDisplayLine]) -> None:
        super().__init__()
        self.add_class("skills-command-message")
        self._lines = lines

    def compose(self) -> ComposeResult:
        with Horizontal(classes="user-command-container"):
            yield ExpandingBorder(classes="user-command-border")
            with Vertical(classes="skills-command-content"):
                for line in self._lines:
                    classes = "skills-command-line"
                    if line.disabled:
                        classes += " skills-command-line--disabled"
                    if line.header:
                        classes += " skills-command-line--header"
                    yield NoMarkupStatic(line.text, classes=classes)


def parse_skills_command(raw_args: str) -> SkillsCommand:
    try:
        args = shlex.split(raw_args)
    except ValueError as exc:
        raise ValueError(SKILLS_USAGE) from exc

    if not args:
        return SkillsCommand(action=SkillsAction.LIST)

    action = args[0].lower()
    if action == SkillsAction.STATUS:
        if len(args) != 1:
            raise ValueError("Usage: /skills status")
        return SkillsCommand(action=SkillsAction.STATUS)

    if action in {SkillsAction.ENABLE, SkillsAction.DISABLE}:
        if len(args) == 1:
            raise ValueError(f"Usage: /skills {action} <name> [<name> ...]")
        return SkillsCommand(action=SkillsAction(action), names=tuple(args[1:]))

    if action == SkillsAction.TOGGLE:
        if len(args) != _TOGGLE_ARGUMENT_COUNT:
            raise ValueError("Usage: /skills toggle <name>")
        return SkillsCommand(action=SkillsAction.TOGGLE, names=(args[1],))

    allowed_flags = {"-v", "--verbose", "--json"}
    if any(arg not in allowed_flags for arg in args):
        raise ValueError(SKILLS_USAGE)
    return SkillsCommand(
        action=SkillsAction.LIST,
        verbose="-v" in args or "--verbose" in args,
        json_output="--json" in args,
    )


def skill_source_label(skill: SkillInfo) -> str:
    if skill.source == SkillSource.BUILTIN:
        return "Built-in"
    if skill.source == SkillSource.REGISTRY:
        return "Registry"
    if skill.scope == SkillScope.PROJECT:
        return "Project"
    return "Global"


def is_skill_enabled(name: str, enabled_names: set[str]) -> bool:
    return name in enabled_names


def format_skills_text(
    skills: Mapping[str, SkillInfo], enabled_names: set[str], *, verbose: bool
) -> list[SkillDisplayLine]:
    groups = {label: [] for label in ("Built-in", "Project", "Global", "Registry")}
    for name, skill in skills.items():
        groups[skill_source_label(skill)].append((name, skill))

    lines: list[SkillDisplayLine] = []
    for label, entries in groups.items():
        if not entries:
            continue
        if lines:
            lines.append(SkillDisplayLine(""))
        lines.append(
            SkillDisplayLine(f"=== {label} Skills ({len(entries)}) ===", header=True)
        )
        for name, skill in sorted(entries, key=lambda entry: entry[0].casefold()):
            enabled = is_skill_enabled(name, enabled_names)
            prefix = "" if enabled else "[disabled] "
            lines.append(
                SkillDisplayLine(
                    f"{prefix}{name} [{label}] - {skill.description}",
                    disabled=not enabled,
                )
            )
            if verbose:
                path = (
                    str(skill.skill_path) if skill.skill_path is not None else "(none)"
                )
                version = (
                    str(skill.registry.version)
                    if skill.registry is not None
                    else "(none)"
                )
                details = (
                    f"  path: {path}; version: {version}; "
                    f"user-invocable: {str(skill.user_invocable).lower()}; "
                    f"license: {skill.license or '(none)'}; "
                    f"compatibility: {skill.compatibility or '(none)'}"
                )
                lines.append(SkillDisplayLine(details, disabled=not enabled))
    return lines


def format_skills_json(skills: Mapping[str, SkillInfo], enabled_names: set[str]) -> str:
    ordered = sorted(
        skills.items(),
        key=lambda item: (
            ("Built-in", "Project", "Global", "Registry").index(
                skill_source_label(item[1])
            ),
            item[0].casefold(),
        ),
    )
    payload = [
        {
            "name": name,
            "description": skill.description,
            "source": skill_source_label(skill),
            "enabled": is_skill_enabled(name, enabled_names),
            "source_path": str(skill.skill_path)
            if skill.skill_path is not None
            else None,
            "version": skill.registry.version if skill.registry is not None else None,
            "user_invocable": skill.user_invocable,
            "license": skill.license,
            "compatibility": skill.compatibility,
        }
        for name, skill in ordered
    ]
    return json.dumps(payload, indent=2)


def format_skills_status(
    skills: Mapping[str, SkillInfo], enabled_names: set[str]
) -> list[SkillDisplayLine]:
    enabled = sorted(
        (name for name in skills if name in enabled_names), key=str.casefold
    )
    disabled = sorted(
        (name for name in skills if name not in enabled_names), key=str.casefold
    )
    lines = [SkillDisplayLine(f"=== Enabled Skills ({len(enabled)}) ===", header=True)]
    lines.extend(SkillDisplayLine(name) for name in enabled)
    if disabled:
        lines.append(SkillDisplayLine(""))
        lines.append(
            SkillDisplayLine(f"=== Disabled Skills ({len(disabled)}) ===", header=True)
        )
        lines.extend(
            SkillDisplayLine(f"[disabled] {name}", disabled=True) for name in disabled
        )
    return lines


def resolve_skill_patterns(
    patterns: Sequence[str], skills: Mapping[str, SkillInfo]
) -> tuple[str, ...]:
    matched: list[str] = []
    unmatched: list[str] = []
    for pattern in patterns:
        names = [name for name in skills if name_matches(name, [pattern])]
        if not names:
            unmatched.append(pattern)
            continue
        for name in sorted(names, key=str.casefold):
            if name not in matched:
                matched.append(name)
    if unmatched:
        known_names = list(skills)
        messages = []
        for pattern in unmatched:
            suggestions = get_close_matches(
                pattern.lower(), known_names, n=3, cutoff=0.5
            )
            suffix = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            messages.append(f"Skill '{pattern}' not found.{suffix}")
        raise ValueError("\n".join(messages))
    return tuple(matched)


def build_skill_state_update(
    *,
    skills: Mapping[str, SkillInfo],
    enabled_names: set[str],
    configured_enabled: Sequence[str],
    configured_disabled: Sequence[str],
    names: Sequence[str],
    target_enabled: bool,
) -> SkillStateUpdate:
    changed = tuple(name for name in names if (name in enabled_names) != target_enabled)
    if not changed:
        return SkillStateUpdate(
            enabled_skills=list(configured_enabled),
            disabled_skills=list(configured_disabled),
            changed_names=(),
            target_enabled=target_enabled,
        )

    desired_enabled = set(enabled_names)
    if target_enabled:
        desired_enabled.update(changed)
    else:
        desired_enabled.difference_update(changed)

    configurable_names = {
        name for name, skill in skills.items() if skill.source != SkillSource.BUILTIN
    }
    if configured_enabled:
        next_enabled = sorted(desired_enabled & configurable_names, key=str.casefold)
        next_disabled = sorted(configurable_names - desired_enabled, key=str.casefold)
    else:
        next_enabled = []
        next_disabled = sorted(configurable_names - desired_enabled, key=str.casefold)

    return SkillStateUpdate(
        enabled_skills=next_enabled,
        disabled_skills=next_disabled,
        changed_names=changed,
        target_enabled=target_enabled,
    )
