from __future__ import annotations

import pytest

from tests.mock.utils import collect_result
from vibe.core.tools.base import BaseToolState, InvokeContext, ToolError, ToolPermission
from vibe.core.tools.builtins.ask_user_question import Answer, AskUserQuestionResult
from vibe.core.tools.builtins.vibe_in_chrome import (
    VibeInChrome,
    VibeInChromeArgs,
    VibeInChromeConfig,
)


def _ctx_answering(label: str) -> InvokeContext:
    """An InvokeContext whose user_input_callback always returns `label`."""

    async def _cb(_args: object) -> AskUserQuestionResult:
        return AskUserQuestionResult(answers=[Answer(question="?", answer=label)])

    return InvokeContext(tool_call_id="t", user_input_callback=_cb)


# The browser tool needs Playwright + a Chromium build. Skip the whole module
# when either is missing so the suite stays green without the optional extra.
pytest.importorskip("playwright")

# These tests launch a real Chromium (and, in persist mode, probe for the system
# Chrome before falling back to the bundled build). Under CI's parallel load that
# can exceed the repo-wide 10s pytest-timeout, so give this module more headroom.
pytestmark = pytest.mark.timeout(60)

_FORM_PAGE = (
    "data:text/html,"
    "<title>Login</title>"
    "<h1>Sign in</h1>"
    "<input type='text' placeholder='Email'>"
    "<button onclick=\"document.title='clicked'\">Submit</button>"
)


def _make_browser() -> VibeInChrome:
    config = VibeInChromeConfig(headless=True)
    return VibeInChrome(config_getter=lambda: config, state=BaseToolState())


async def _open_or_skip(tool: VibeInChrome) -> None:
    """Open the fixture page, skipping the test if Chromium is not installed."""
    try:
        await collect_result(
            tool.run(VibeInChromeArgs(action="navigate", url=_FORM_PAGE))
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "playwright install" in msg or "executable" in msg:
            pytest.skip(f"Chromium not installed: {exc}")
        raise


def test_is_available_when_playwright_installed() -> None:
    assert VibeInChrome.is_available() is True


def test_read_only_actions_auto_approved() -> None:
    tool = _make_browser()
    ctx = tool.resolve_permission(VibeInChromeArgs(action="snapshot"))
    assert ctx is not None
    assert ctx.permission is ToolPermission.ALWAYS


def test_click_requires_ask_permission() -> None:
    tool = _make_browser()
    ctx = tool.resolve_permission(VibeInChromeArgs(action="click"))
    assert ctx is not None
    assert ctx.permission is ToolPermission.ASK


@pytest.mark.asyncio
async def test_navigate_indexes_interactable_elements() -> None:
    tool = _make_browser()
    await _open_or_skip(tool)
    try:
        result = await collect_result(tool.run(VibeInChromeArgs(action="snapshot")))
        assert result.title == "Login"
        names = {e.name for e in result.elements}
        assert any("Email" in n for n in names)
        assert any("Submit" in n for n in names)
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


@pytest.mark.asyncio
async def test_type_fills_and_click_mutates_page() -> None:
    tool = _make_browser()
    await _open_or_skip(tool)
    try:
        snap = await collect_result(tool.run(VibeInChromeArgs(action="snapshot")))
        email = next(e for e in snap.elements if "Email" in e.name)
        button = next(e for e in snap.elements if "Submit" in e.name)

        await collect_result(
            tool.run(VibeInChromeArgs(action="type", ref=email.ref, text="user@x.com"))
        )
        clicked = await collect_result(
            tool.run(VibeInChromeArgs(action="click", ref=button.ref))
        )
        # The button's onclick sets document.title to "clicked".
        assert clicked.title == "clicked"
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


@pytest.mark.asyncio
async def test_javascript_rendered_content_is_read() -> None:
    """The tool runs a real browser: JS-injected DOM must appear in the snapshot."""
    tool = _make_browser()
    js_page = (
        "data:text/html,<div id=app></div>"
        "<script>document.getElementById('app').innerHTML="
        "'<button>Injected by JS</button>'</script>"
    )
    try:
        result = await collect_result(
            tool.run(VibeInChromeArgs(action="navigate", url=js_page))
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "playwright install" in msg or "executable" in msg:
            pytest.skip(f"Chromium not installed: {exc}")
        raise
    try:
        assert any("Injected by JS" in e.name for e in result.elements)
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


@pytest.mark.asyncio
async def test_persist_session_launches_and_populates_profile(tmp_path) -> None:
    """persist_session launches a persistent profile and reuses it across runs."""
    profile = tmp_path / "chrome-profile"
    config = VibeInChromeConfig(
        headless=True, persist_session=True, chrome_profile_dir=str(profile)
    )
    tool = VibeInChrome(config_getter=lambda: config, state=BaseToolState())
    try:
        result = await collect_result(
            tool.run(VibeInChromeArgs(action="navigate", url=_FORM_PAGE))
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "playwright install" in msg or "executable" in msg:
            pytest.skip(f"Chromium not installed: {exc}")
        raise
    try:
        assert result.title == "Login"
        # The profile directory is created and written to, so a later run reuses it.
        assert profile.exists()
        assert any(profile.iterdir())
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


def test_allowed_domains_blocks_navigation() -> None:
    """An allowlist refuses off-list domains even under auto-approve."""
    config = VibeInChromeConfig(
        permission=ToolPermission.ALWAYS, allowed_domains=["example.com"]
    )
    tool = VibeInChrome(config_getter=lambda: config, state=BaseToolState())

    blocked = tool.resolve_permission(
        VibeInChromeArgs(action="navigate", url="https://evil.test")
    )
    assert blocked is not None
    assert blocked.permission is ToolPermission.NEVER

    # Subdomains of an allowed domain are permitted.
    ok = tool.resolve_permission(
        VibeInChromeArgs(action="navigate", url="https://app.example.com")
    )
    assert ok is not None
    assert ok.permission is not ToolPermission.NEVER


@pytest.mark.asyncio
async def test_console_action_captures_page_errors() -> None:
    """The console action surfaces JS console output and page errors."""
    tool = _make_browser()
    error_page = "data:text/html,<script>console.error('boom-xyz')</script><h1>App</h1>"
    try:
        await collect_result(
            tool.run(VibeInChromeArgs(action="navigate", url=error_page))
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "playwright install" in msg or "executable" in msg:
            pytest.skip(f"Chromium not installed: {exc}")
        raise
    try:
        result = await collect_result(tool.run(VibeInChromeArgs(action="console")))
        assert any("boom-xyz" in line for line in result.console)
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


@pytest.mark.asyncio
async def test_screenshot_saves_file_and_emits_image_to_model(tmp_path) -> None:
    """screenshot writes a PNG and injects it for a vision-capable model to see."""
    tool = _make_browser()
    emitted: list[tuple[list, str]] = []
    ctx = InvokeContext(
        tool_call_id="t",
        session_dir=tmp_path,
        emit_image_callback=lambda imgs, caption: emitted.append((imgs, caption)),
    )
    dest = tmp_path / "shot.png"
    try:
        await collect_result(
            tool.run(VibeInChromeArgs(action="navigate", url=_FORM_PAGE), ctx)
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "playwright install" in msg or "executable" in msg:
            pytest.skip(f"Chromium not installed: {exc}")
        raise
    try:
        result = await collect_result(
            tool.run(VibeInChromeArgs(action="screenshot", path=str(dest)), ctx)
        )
        assert result.screenshot_path == str(dest)
        assert dest.exists() and dest.stat().st_size > 0
        # The image was emitted to the model (one attachment, with a caption).
        assert len(emitted) == 1
        images, caption = emitted[0]
        assert len(images) == 1
        assert "creenshot" in caption
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


@pytest.mark.asyncio
async def test_pause_requires_user_input_callback() -> None:
    """Without a way to reach the human, `pause` fails fast (no browser launched)."""
    tool = _make_browser()
    with pytest.raises(ToolError, match="pause for human input"):
        await collect_result(tool.run(VibeInChromeArgs(action="pause")))


@pytest.mark.asyncio
async def test_pause_continue_then_abort() -> None:
    """`pause` hands off to the human, re-reads on Continue, raises on Abort."""
    tool = _make_browser()
    cont = _ctx_answering("Continue")
    try:
        await collect_result(
            tool.run(VibeInChromeArgs(action="navigate", url=_FORM_PAGE), cont)
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "playwright install" in msg or "executable" in msg:
            pytest.skip(f"Chromium not installed: {exc}")
        raise
    try:
        # Continue -> the page is re-read and returned.
        resumed = await collect_result(
            tool.run(VibeInChromeArgs(action="pause", message="log in"), cont)
        )
        assert resumed.title == "Login"

        # Abort -> the tool raises so the agent stops.
        with pytest.raises(ToolError, match="aborted"):
            await collect_result(
                tool.run(VibeInChromeArgs(action="pause"), _ctx_answering("Abort"))
            )
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))


@pytest.mark.asyncio
async def test_type_requires_text() -> None:
    tool = _make_browser()
    await _open_or_skip(tool)
    try:
        snap = await collect_result(tool.run(VibeInChromeArgs(action="snapshot")))
        ref = snap.elements[0].ref
        with pytest.raises(ToolError, match="requires `text`"):
            await collect_result(tool.run(VibeInChromeArgs(action="type", ref=ref)))
    finally:
        await collect_result(tool.run(VibeInChromeArgs(action="close")))
