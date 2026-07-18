from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from rich.text import Text
from textual.widgets import OptionList

from tests.conftest import build_test_vibe_app, build_test_vibe_config
from vibe.cli.textual_ui.app import BottomApp
from vibe.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic
from vibe.cli.textual_ui.widgets.skills_picker import SkillsPickerApp
from vibe.core.skills.models import SkillInfo, SkillScope, SkillSource
from vibe.core.trusted_folders import trusted_folders_manager


def _skill(
    name: str,
    *,
    source: SkillSource = SkillSource.LOCAL,
    scope: SkillScope = SkillScope.GLOBAL,
) -> SkillInfo:
    return SkillInfo(
        name=name,
        description=f"Description for {name}",
        prompt="Instructions",
        source=source,
        scope=scope,
    )


def _app_with_skills():
    config = build_test_vibe_config(disabled_skills=["beta"])
    app = build_test_vibe_app(config=config)
    skills = {
        "builtin": _skill(
            "builtin", source=SkillSource.BUILTIN, scope=SkillScope.BUILTIN
        ),
        "alpha": _skill("alpha", scope=SkillScope.PROJECT),
        "beta": _skill("beta"),
    }
    app.agent_loop.skill_manager.discovered_skills = skills
    app.agent_loop.skill_manager.available_skills = {
        "builtin": skills["builtin"],
        "alpha": skills["alpha"],
    }
    return app


def _checked_options(option_list: OptionList) -> list[bool]:
    return [
        isinstance(option.prompt, Text) and option.prompt.plain.startswith("[✓]")
        for option in option_list.options
    ]


@pytest.mark.asyncio
async def test_skills_without_arguments_opens_picker() -> None:
    app = _app_with_skills()

    async with app.run_test() as pilot:
        await app._show_skills()
        await pilot.pause()

        assert app._current_bottom_app == BottomApp.SkillsPicker
        assert len(app.query(SkillsPickerApp)) == 1
        assert _checked_options(app.query_one(OptionList)) == [True, True, False]


@pytest.mark.asyncio
async def test_skills_picker_explains_hidden_project_skills(
    tmp_working_directory,
) -> None:
    skills_dir = tmp_working_directory / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    trusted_folders_manager.add_untrusted(tmp_working_directory)
    app = _app_with_skills()

    async with app.run_test() as pilot:
        await app._show_skills()
        await pilot.pause()

        warning = app.query_one("#skillspicker-trust-warning", NoMarkupStatic)
        assert "PROJECT SKILLS HIDDEN" in str(warning.content)
        assert "vibe --trust" in str(warning.content)


@pytest.mark.asyncio
async def test_skills_picker_space_toggles_multiple_choices() -> None:
    app = _app_with_skills()

    async with app.run_test() as pilot:
        await app._show_skills()
        await pilot.press("down", "space", "down", "space")
        await pilot.pause()

        assert _checked_options(app.query_one(OptionList)) == [True, False, True]


@pytest.mark.asyncio
async def test_skills_picker_builtin_choice_stays_checked() -> None:
    app = _app_with_skills()

    async with app.run_test() as pilot:
        await app._show_skills()
        await pilot.press("space")
        await pilot.pause()

        assert _checked_options(app.query_one(OptionList)) == [True, True, False]


@pytest.mark.asyncio
async def test_skills_picker_enter_applies_and_closes() -> None:
    app = _app_with_skills()

    async with app.run_test() as pilot:
        orchestrator = app.agent_loop.config_orchestrator
        with (
            patch.object(app, "_reload_config", new=AsyncMock()),
            patch.object(
                orchestrator, "set_field", new=AsyncMock(return_value=[])
            ) as set_field,
        ):
            await app._show_skills()
            await pilot.press("down", "space", "down", "space", "enter")
            await pilot.pause()

        assert set_field.await_count == 2
        assert set_field.await_args_list[0].args == ("/enabled_skills", [])
        assert set_field.await_args_list[1].args == ("/disabled_skills", ["alpha"])
        assert app._current_bottom_app == BottomApp.Input
        assert len(app.query(SkillsPickerApp)) == 0


@pytest.mark.asyncio
async def test_skills_picker_escape_cancels_without_writing() -> None:
    app = _app_with_skills()

    async with app.run_test() as pilot:
        orchestrator = app.agent_loop.config_orchestrator
        with patch.object(
            orchestrator, "set_field", new=AsyncMock(return_value=[])
        ) as set_field:
            await app._show_skills()
            await pilot.press("down", "space", "escape")
            await pilot.pause()

        set_field.assert_not_awaited()
        assert app._current_bottom_app == BottomApp.Input
        assert len(app.query(SkillsPickerApp)) == 0
