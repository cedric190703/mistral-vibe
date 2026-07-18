from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibe.cli.textual_ui.skills_commands import (
    SkillsAction,
    build_skill_state_update,
    build_skills_selection_update,
    format_skills_json,
    format_skills_status,
    format_skills_text,
    parse_skills_command,
    resolve_skill_patterns,
    skill_source_label,
)
from vibe.core.skills.models import SkillInfo, SkillScope, SkillSource


def make_skill(
    name: str,
    *,
    source: SkillSource = SkillSource.LOCAL,
    scope: SkillScope = SkillScope.GLOBAL,
    path: Path | None = None,
) -> SkillInfo:
    return SkillInfo(
        name=name,
        description=f"Description for {name}",
        skill_path=path,
        prompt="Instructions",
        source=source,
        scope=scope,
    )


def test_parse_skills_list_flags() -> None:
    command = parse_skills_command("--json -v")

    assert command.action == SkillsAction.LIST
    assert command.json_output is True
    assert command.verbose is True


def test_parse_skills_management_subcommands() -> None:
    assert parse_skills_command("enable one two").names == ("one", "two")
    assert parse_skills_command("disable one").action == SkillsAction.DISABLE
    assert parse_skills_command("toggle one").action == SkillsAction.TOGGLE
    assert parse_skills_command("status").action == SkillsAction.STATUS


@pytest.mark.parametrize(
    "args", ["unknown", "toggle", "toggle one two", "status extra", "enable", "disable"]
)
def test_parse_skills_rejects_invalid_usage(args: str) -> None:
    with pytest.raises(ValueError):
        parse_skills_command(args)


def test_source_label_maps_all_display_groups() -> None:
    assert (
        skill_source_label(
            make_skill("builtin", source=SkillSource.BUILTIN, scope=SkillScope.BUILTIN)
        )
        == "Built-in"
    )
    assert (
        skill_source_label(make_skill("project", scope=SkillScope.PROJECT)) == "Project"
    )
    assert skill_source_label(make_skill("global")) == "Global"
    assert (
        skill_source_label(make_skill("registry", source=SkillSource.REGISTRY))
        == "Registry"
    )


def test_format_skills_text_groups_sorts_and_marks_disabled(tmp_path: Path) -> None:
    skills = {
        "z-global": make_skill("z-global"),
        "project": make_skill("project", scope=SkillScope.PROJECT),
        "alpha": make_skill(
            "alpha", source=SkillSource.BUILTIN, scope=SkillScope.BUILTIN
        ),
        "registry": make_skill("registry", source=SkillSource.REGISTRY),
    }

    lines = format_skills_text(skills, {"alpha", "project", "registry"}, verbose=False)
    text = [line.text for line in lines]

    assert text == [
        "=== Built-in Skills (1) ===",
        "alpha [Built-in] - Description for alpha",
        "",
        "=== Project Skills (1) ===",
        "project [Project] - Description for project",
        "",
        "=== Global Skills (1) ===",
        "[disabled] z-global [Global] - Description for z-global",
        "",
        "=== Registry Skills (1) ===",
        "registry [Registry] - Description for registry",
    ]
    assert lines[7].disabled is True


def test_format_skills_verbose_includes_optional_fields(tmp_path: Path) -> None:
    path = tmp_path / "skill" / "SKILL.md"
    skill = make_skill("skill", path=path)

    lines = format_skills_text({"skill": skill}, {"skill"}, verbose=True)

    assert str(path) in lines[2].text
    assert "version: (none)" in lines[2].text
    assert "user-invocable: true" in lines[2].text
    assert "license: (none)" in lines[2].text


def test_format_skills_json_always_includes_full_schema() -> None:
    payload = json.loads(format_skills_json({"skill": make_skill("skill")}, set()))

    assert payload == [
        {
            "name": "skill",
            "description": "Description for skill",
            "source": "Global",
            "enabled": False,
            "source_path": None,
            "version": None,
            "user_invocable": True,
            "license": None,
            "compatibility": None,
        }
    ]


def test_format_skills_status_splits_enabled_and_disabled() -> None:
    lines = format_skills_status(
        {"enabled": make_skill("enabled"), "disabled": make_skill("disabled")},
        {"enabled"},
    )

    assert [line.text for line in lines] == [
        "=== Enabled Skills (1) ===",
        "enabled",
        "",
        "=== Disabled Skills (1) ===",
        "[disabled] disabled",
    ]


def test_resolve_skill_patterns_is_case_insensitive_and_deduplicates() -> None:
    skills = {
        "search-code": make_skill("search-code"),
        "search-docs": make_skill("search-docs"),
    }

    assert resolve_skill_patterns(["SEARCH-*", "search-code"], skills) == (
        "search-code",
        "search-docs",
    )


def test_resolve_skill_patterns_suggests_close_names() -> None:
    with pytest.raises(ValueError, match="Did you mean: search-code"):
        resolve_skill_patterns(
            ["search-cod"], {"search-code": make_skill("search-code")}
        )


def test_disable_without_whitelist_writes_disabled_names_only() -> None:
    skills = {"one": make_skill("one"), "two": make_skill("two")}

    update = build_skill_state_update(
        skills=skills,
        enabled_names={"one", "two"},
        configured_enabled=[],
        configured_disabled=[],
        names=["two"],
        target_enabled=False,
    )

    assert update.enabled_skills == []
    assert update.disabled_skills == ["two"]
    assert update.changed_names == ("two",)


def test_enable_with_whitelist_preserves_other_active_names() -> None:
    skills = {
        "builtin": make_skill(
            "builtin", source=SkillSource.BUILTIN, scope=SkillScope.BUILTIN
        ),
        "one": make_skill("one"),
        "two": make_skill("two"),
        "three": make_skill("three"),
    }

    update = build_skill_state_update(
        skills=skills,
        enabled_names={"builtin", "one"},
        configured_enabled=["one"],
        configured_disabled=[],
        names=["two"],
        target_enabled=True,
    )

    assert update.enabled_skills == ["one", "two"]
    assert update.disabled_skills == ["three"]


def test_picker_selection_builds_mixed_enable_and_disable_update() -> None:
    skills = {
        "builtin": make_skill(
            "builtin", source=SkillSource.BUILTIN, scope=SkillScope.BUILTIN
        ),
        "one": make_skill("one"),
        "two": make_skill("two"),
    }

    update = build_skills_selection_update(
        skills=skills,
        enabled_names={"builtin", "one"},
        selected_enabled_names={"builtin", "two"},
        configured_enabled=[],
    )

    assert update.enabled_skills == []
    assert update.disabled_skills == ["one"]
    assert update.enabled_names == ("two",)
    assert update.disabled_names == ("one",)


def test_picker_selection_preserves_whitelist_mode() -> None:
    skills = {"one": make_skill("one"), "two": make_skill("two")}

    update = build_skills_selection_update(
        skills=skills,
        enabled_names={"one"},
        selected_enabled_names={"one", "two"},
        configured_enabled=["one"],
    )

    assert update.enabled_skills == ["one", "two"]
    assert update.disabled_skills == []
    assert update.enabled_names == ("two",)
    assert update.disabled_names == ()
