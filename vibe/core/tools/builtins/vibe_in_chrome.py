"""The vibe-in-chrome tool: browser automation via Playwright.

Drives a real Chromium browser so the agent can close the feedback loop on the
web app it is building: open the local dev server, walk through a flow, fill a
form, read console/network errors to reproduce a bug, and verify a fix — all
from the CLI. It also handles pages with no API or connector (admin panels,
dashboards) as a secondary use case.

The tool operates in *text mode*: instead of sending screenshots to the model,
``snapshot`` extracts the page's interactable elements as an indexed list
(``[3] button "Sign in"``). The model then acts on elements by their index
(``click`` / ``type``), exactly like reading and editing code. This keeps the
tool usable with any model, vision-capable or not.

The live browser is held in a module-level singleton (mirroring the managed
bash session manager) so the page — and its cookies, login state, and scroll
position — survives across separate tool calls within a session. It is closed
when the agent session ends (see ``close_browser``).

Safety: page content is untrusted and enters the model's context, so treat this
as a prompt-injection surface. Every mutating action requires approval by
default, and ``allowed_domains`` can restrict where the tool may navigate.

Playwright is an optional dependency: install with ``pip install mistral-vibe[browser]``
followed by ``playwright install chromium``. When the package is absent the tool
hides itself; when the browser binary is missing, launching raises an actionable
error.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from vibe.core.tools.base import (
    BaseTool,
    BaseToolConfig,
    BaseToolState,
    InvokeContext,
    ToolError,
    ToolPermission,
)
from vibe.core.tools.permissions import (
    PermissionContext,
    PermissionScope,
    RequiredPermission,
)
from vibe.core.tools.ui import ToolCallDisplay, ToolResultDisplay, ToolUIData
from vibe.core.types import ToolStreamEvent

if TYPE_CHECKING:
    from vibe.core.config import AnyVibeConfig
    from vibe.core.types import ToolCallEvent, ToolResultEvent


VibeInChromeAction = Literal[
    "navigate",
    "snapshot",
    "click",
    "type",
    "press_key",
    "scroll",
    "back",
    "forward",
    "list_tabs",
    "open_tab",
    "switch_tab",
    "console",
    "screenshot",
    "pause",
    "close",
]

# Hard cap on the in-memory console buffer, independent of how many lines a
# single `console` action returns (``max_console_messages``).
_MAX_CONSOLE_BUFFER = 500

# Actions that only observe the page (or hand off to the human) — auto-approved.
_READ_ONLY_ACTIONS: frozenset[str] = frozenset({
    "snapshot",
    "scroll",
    "back",
    "forward",
    "console",
    "screenshot",
    "pause",
    "list_tabs",
    "switch_tab",
})

# Actions that may trigger navigation or client-side rendering; wait for the
# network to settle before reading the page. `pause` is included because the
# human typically logs in or clears a captcha, changing the page.
_SETTLE_ACTIONS: frozenset[str] = frozenset({
    "navigate",
    "click",
    "type",
    "back",
    "forward",
    "pause",
    "open_tab",
    "switch_tab",
})

# Actions the Chrome extension backend can perform on the user's real browser.
# Others (console, screenshot) stay on the Playwright backend for now.
_EXTENSION_ACTIONS: frozenset[str] = frozenset({
    "navigate",
    "snapshot",
    "click",
    "type",
    "scroll",
    "back",
    "forward",
    "list_tabs",
    "open_tab",
    "switch_tab",
    "screenshot",
})

# Browser-wide tab management (distinct from acting on the current page).
_TAB_ACTIONS: frozenset[str] = frozenset({"list_tabs", "open_tab", "switch_tab"})

# JS that tags every visible, interactable element with a stable ``data-vibe-ref``
# attribute and returns a compact description the model can act on.
_SNAPSHOT_JS = r"""
() => {
  const SELECTOR = [
    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',
    'summary', 'label', '[role=button]', '[role=link]', '[role=checkbox]',
    '[role=tab]', '[role=menuitem]', '[role=textbox]', '[onclick]',
    '[contenteditable=""]', '[contenteditable=true]',
  ].join(',');
  const isVisible = (el) => {
    if (el.disabled) return false;
    const rects = el.getClientRects();
    if (!rects.length) return false;
    const style = window.getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  };
  const name = (el) => {
    const raw = el.getAttribute('aria-label') || el.getAttribute('placeholder')
      || (el.innerText || '').trim() || el.value || el.getAttribute('title')
      || el.getAttribute('alt') || el.getAttribute('name') || '';
    return raw.replace(/\s+/g, ' ').trim().slice(0, 120);
  };
  document.querySelectorAll('[data-vibe-ref]').forEach(
    (el) => el.removeAttribute('data-vibe-ref')
  );
  const out = [];
  let i = 0;
  for (const el of document.querySelectorAll(SELECTOR)) {
    if (!isVisible(el)) continue;
    el.setAttribute('data-vibe-ref', String(i));
    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute('type') || el.getAttribute('role') || '';
    out.push({ ref: i, tag, type, name: name(el) });
    i += 1;
  }
  return out;
}
"""


class VibeInChromeArgs(BaseModel):
    action: VibeInChromeAction = Field(
        description=(
            "The browser action to perform: navigate, snapshot, click, type, "
            "press_key, scroll, back, forward, close."
        )
    )
    url: str | None = Field(
        default=None, description="Target URL. Required for `navigate`."
    )
    ref: int | None = Field(
        default=None,
        description=(
            "Element index from the most recent `snapshot`. Required for "
            "`click` and `type`."
        ),
    )
    text: str | None = Field(
        default=None, description="Text to type. Required for `type`."
    )
    submit: bool = Field(
        default=False,
        description="For `type`: press Enter after typing (submit the field).",
    )
    key: str | None = Field(
        default=None,
        description="Key to press for `press_key` (e.g. 'Enter', 'Escape', 'Tab').",
    )
    amount: int = Field(
        default=600, description="For `scroll`: vertical pixels (negative scrolls up)."
    )
    message: str | None = Field(
        default=None,
        description=(
            "For `pause`: the instruction shown to the human before handing over "
            "control (e.g. 'Log in and solve the captcha, then continue')."
        ),
    )
    path: str | None = Field(
        default=None,
        description=(
            "For `screenshot`: where to save the PNG. Defaults to a file in the "
            "session's scratchpad directory."
        ),
    )
    full_page: bool = Field(
        default=False,
        description="For `screenshot`: capture the full scrollable page, not just the viewport.",
    )
    tab_id: int | None = Field(
        default=None,
        description="For `switch_tab`: the id of the tab to activate (from `list_tabs`).",
    )


class VibeInChromeElement(BaseModel):
    ref: int
    tag: str
    type: str = ""
    name: str = ""


class VibeInChromeTab(BaseModel):
    id: int
    title: str = ""
    url: str = ""
    active: bool = False


class VibeInChromeResult(BaseModel):
    action: VibeInChromeAction
    url: str = ""
    title: str = ""
    elements: list[VibeInChromeElement] = Field(default_factory=list)
    text: str = ""
    console: list[str] = Field(default_factory=list)
    tabs: list[VibeInChromeTab] = Field(default_factory=list)
    screenshot_path: str = ""
    message: str = ""


class VibeInChromeConfig(BaseToolConfig):
    permission: ToolPermission = ToolPermission.ASK

    prefer_extension: bool = Field(
        default=True,
        description=(
            "Try to control the user's own Chrome through the Vibe-in-Chrome "
            "extension first, and fall back to launching a Playwright browser "
            "when no extension is connected."
        ),
    )
    extension_port: int = Field(
        default=9223,
        description="Local port the extension connects to (must match the extension).",
    )
    extension_connect_grace: float = Field(
        default=2.5,
        description=(
            "Seconds to wait for the extension to connect the first time before "
            "falling back to Playwright."
        ),
    )
    persist_session: bool = Field(
        default=False,
        description=(
            "Reuse a persistent Chrome profile so logins and cookies survive "
            "across runs. The tool launches the browser itself (your installed "
            "Chrome when available) — no manual startup, no flags. Log in once and "
            "you stay logged in. The simplest way to use your own sessions."
        ),
    )
    chrome_profile_dir: str | None = Field(
        default=None,
        description=(
            "Where to store the persistent profile (defaults to "
            "'~/.vibe/chrome-profile'). Only used when `persist_session` is true."
        ),
    )
    cdp_url: str | None = Field(
        default=None,
        description=(
            "Advanced: attach to an already-running Chrome over the DevTools "
            "Protocol (e.g. 'http://127.0.0.1:9222') instead of launching a "
            "browser. Reuses that browser's open tabs and leaves it running on "
            "exit. Requires starting Chrome with `--remote-debugging-port=9222`. "
            "Prefer `persist_session` unless you need the already-open window."
        ),
    )
    headless: bool = Field(
        default=False,
        description="Run Chromium without a visible window. Default shows the browser.",
    )
    viewport_width: int = Field(default=1280)
    viewport_height: int = Field(default=800)
    nav_timeout_ms: int = Field(
        default=30_000, description="Navigation/action timeout in milliseconds."
    )
    settle_ms: int = Field(
        default=5_000,
        description=(
            "Best-effort wait (ms) for the network to go idle after navigation or "
            "a click, so client-rendered (JS/AJAX) content has time to appear."
        ),
    )
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        description="User agent for the browser (avoids the default headless UA).",
    )
    allowed_domains: list[str] = Field(
        default_factory=list,
        description=(
            "If non-empty, navigation is restricted to these domains and their "
            "subdomains (e.g. ['localhost', 'example.com']); anything else is "
            "refused. Empty means any domain, still subject to per-domain approval."
        ),
    )
    max_elements: int = Field(
        default=150, description="Maximum interactable elements returned by snapshot."
    )
    max_text_chars: int = Field(
        default=6_000, description="Maximum characters of page text returned."
    )
    max_console_messages: int = Field(
        default=50,
        description="Maximum console/network log lines returned by the `console` action.",
    )


class _VibeInChromeManager:
    """Owns the single live Playwright browser for the session.

    Playwright's async objects are bound to the event loop that created them; the
    agent loop runs every tool call on the same loop, so the page persists across
    calls without any cross-thread handling.
    """

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        # True when attached to a user-owned browser over CDP: teardown must not
        # close their Chrome, only detach the local driver.
        self._connected: bool = False
        # Rolling buffer of console messages, page errors, and failed requests.
        self._console: list[str] = []

    async def ensure_page(self, config: VibeInChromeConfig) -> Any:
        if self._page is not None:
            return self._page

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        page: Any
        if config.cdp_url:
            page = await self._attach_over_cdp(config.cdp_url)
        elif config.persist_session:
            page = await self._launch_persistent(config)
        else:
            page = await self._launch_fresh(config)
        page.set_default_timeout(config.nav_timeout_ms)
        self._attach_console_listeners(page)
        self._page = page
        return page

    def _attach_console_listeners(self, page: Any) -> None:
        """Record console output, uncaught errors, and failed requests.

        These are the signals a developer uses to debug the web app under test,
        surfaced to the model via the ``console`` action.
        """
        page.on("console", lambda m: self._record(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: self._record(f"[pageerror] {e}"))
        page.on(
            "requestfailed",
            lambda r: self._record(
                f"[requestfailed] {r.method} {r.url} — {(r.failure or 'failed')}"
            ),
        )

    def _record(self, line: str) -> None:
        self._console.append(line)
        if len(self._console) > _MAX_CONSOLE_BUFFER:
            del self._console[:-_MAX_CONSOLE_BUFFER]

    def console_messages(self, limit: int) -> list[str]:
        return self._console[-limit:] if limit > 0 else []

    async def _launch_persistent(self, config: VibeInChromeConfig) -> Any:
        """Launch Chrome with a persistent profile so logins survive across runs.

        Uses the user's installed Google Chrome when available (via the "chrome"
        channel) and falls back to the bundled Chromium otherwise. This is the
        low-friction alternative to CDP: no manual startup, log in once.
        """
        profile = Path(config.chrome_profile_dir or "~/.vibe/chrome-profile")
        profile = profile.expanduser()
        profile.mkdir(parents=True, exist_ok=True)
        launch = self._playwright.chromium.launch_persistent_context
        try:
            self._context = await launch(
                str(profile), channel="chrome", headless=config.headless
            )
        except Exception:
            # Google Chrome not installed — fall back to bundled Chromium.
            try:
                self._context = await launch(str(profile), headless=config.headless)
            except Exception as exc:
                raise _launch_error(exc) from exc
        self._browser = self._context.browser
        pages = self._context.pages
        return pages[0] if pages else await self._context.new_page()

    async def _attach_over_cdp(self, cdp_url: str) -> Any:
        """Attach to the user's own Chrome, reusing its logged-in session."""
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            raise ToolError(
                f"Could not connect to Chrome at {cdp_url}: {exc}. Start Chrome with "
                "`--remote-debugging-port=9222` first (see the tool docs)."
            ) from exc
        self._connected = True
        # contexts[0] is the user's real profile (cookies, logins, open tabs).
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else await self._browser.new_context()
        pages = self._context.pages
        return pages[0] if pages else await self._context.new_page()

    async def _launch_fresh(self, config: VibeInChromeConfig) -> Any:
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=config.headless
            )
        except Exception as exc:
            raise _launch_error(exc) from exc
        self._context = await self._browser.new_context(
            viewport={"width": config.viewport_width, "height": config.viewport_height},
            user_agent=config.user_agent,
        )
        return await self._context.new_page()

    @property
    def page(self) -> Any:
        if self._page is None:
            raise ToolError("No page is open. Use action='navigate' first.")
        return self._page

    async def open_tab(self, url: str, config: VibeInChromeConfig) -> Any:
        page = await self._context.new_page()
        page.set_default_timeout(config.nav_timeout_ms)
        self._attach_console_listeners(page)
        self._page = page
        await page.goto(url, wait_until="domcontentloaded")
        return page

    async def switch_tab(self, tab_id: int) -> Any:
        pages = self._context.pages if self._context else []
        if tab_id < 0 or tab_id >= len(pages):
            raise ToolError(f"No tab with id {tab_id}. Use `list_tabs` first.")
        self._page = pages[tab_id]
        await self._page.bring_to_front()
        return self._page

    async def list_tabs(self) -> list[VibeInChromeTab]:
        pages = self._context.pages if self._context else []
        tabs: list[VibeInChromeTab] = []
        for i, p in enumerate(pages):
            try:
                title = await p.title()
            except Exception:
                title = ""
            tabs.append(
                VibeInChromeTab(id=i, title=title, url=p.url, active=p is self._page)
            )
        return tabs

    async def close(self) -> None:
        # When attached to the user's own Chrome, leave the browser and its tabs
        # running — only detach the local driver.
        if not self._connected:
            for closer in (self._context, self._browser):
                if closer is not None:
                    try:
                        await closer.close()
                    except Exception:
                        pass
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright = self._browser = self._context = self._page = None
        self._connected = False


def _launch_error(exc: Exception) -> ToolError:
    """Turn a Playwright launch failure into an actionable message."""
    text = str(exc).lower()
    if "install" in text or "executable doesn't exist" in text or "not found" in text:
        return ToolError(
            "Chromium is not installed. Run `playwright install chromium` "
            "(or `uv run playwright install chromium`) and try again."
        )
    return ToolError(f"Failed to launch the browser: {exc}")


_MANAGER: _VibeInChromeManager | None = None


def _manager() -> _VibeInChromeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = _VibeInChromeManager()
    return _MANAGER


async def close_browser() -> None:
    """Close the shared browser, if any. Called on agent-session teardown."""
    global _MANAGER
    if _MANAGER is not None:
        await _MANAGER.close()
        _MANAGER = None


class VibeInChrome(
    BaseTool[VibeInChromeArgs, VibeInChromeResult, VibeInChromeConfig, BaseToolState],
    ToolUIData[VibeInChromeArgs, VibeInChromeResult],
):
    description: ClassVar[str] = (
        "Drive a real browser to test and debug web apps, or use sites with no API."
    )

    @classmethod
    def get_name(cls) -> str:
        return "vibe-in-chrome"

    @classmethod
    def is_available(cls, config: AnyVibeConfig | None = None) -> bool:
        _ = config
        return importlib.util.find_spec("playwright") is not None

    def resolve_permission(self, args: VibeInChromeArgs) -> PermissionContext | None:
        if self.config.permission is ToolPermission.NEVER:
            return PermissionContext(permission=ToolPermission.NEVER)

        if args.action == "navigate" and args.url:
            domain = urlparse(self._normalize_url(args.url)).netloc
            if not self._domain_allowed(domain):
                return PermissionContext(
                    permission=ToolPermission.NEVER,
                    reason=(
                        f"'{domain}' is not in allowed_domains "
                        f"({', '.join(self.config.allowed_domains)})"
                    ),
                )

        if self.config.permission is ToolPermission.ALWAYS:
            return PermissionContext(permission=ToolPermission.ALWAYS)

        if args.action in _READ_ONLY_ACTIONS or args.action == "close":
            return PermissionContext(permission=ToolPermission.ALWAYS)

        if args.action == "navigate" and args.url:
            domain = urlparse(self._normalize_url(args.url)).netloc
            if domain:
                return PermissionContext(
                    permission=ToolPermission.ASK,
                    required_permissions=[
                        RequiredPermission(
                            scope=PermissionScope.URL_PATTERN,
                            invocation_pattern=domain,
                            session_pattern=domain,
                            label=f"browsing {domain}",
                        )
                    ],
                )
        return PermissionContext(permission=ToolPermission.ASK)

    def _domain_allowed(self, domain: str) -> bool:
        allowed = self.config.allowed_domains
        if not allowed:
            return True
        host = domain.split(":", 1)[0]  # strip any port
        return any(host == d or host.endswith(f".{d}") for d in allowed)

    @staticmethod
    def _normalize_url(url: str) -> str:
        raw = url.strip()
        known_schemes = ("http://", "https://", "file://", "about:", "data:")
        return raw if raw.startswith(known_schemes) else "https://" + raw

    def _build_extension_payload(self, args: VibeInChromeArgs) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": args.action,
            "maxElements": self.config.max_elements,
            "maxTextChars": self.config.max_text_chars,
        }
        if args.action in {"navigate", "open_tab"}:
            if not args.url:
                raise ToolError(f"`{args.action}` requires `url`.")
            target = self._normalize_url(args.url)
            if not self._domain_allowed(urlparse(target).netloc):
                raise ToolError(
                    f"Navigation to '{target}' is blocked by allowed_domains "
                    f"({', '.join(self.config.allowed_domains)})."
                )
            payload["url"] = target
        elif args.action in {"click", "type"}:
            if args.ref is None:
                raise ToolError(f"`{args.action}` requires `ref` from a snapshot.")
            payload["ref"] = args.ref
            if args.action == "type":
                if args.text is None:
                    raise ToolError("`type` requires `text`.")
                payload["text"] = args.text
                payload["submit"] = args.submit
        elif args.action == "scroll":
            payload["amount"] = args.amount
        elif args.action == "switch_tab":
            if args.tab_id is None:
                raise ToolError("`switch_tab` requires `tab_id` (from `list_tabs`).")
            payload["tab_id"] = args.tab_id
        return payload

    async def _try_extension(
        self, args: VibeInChromeArgs, ctx: InvokeContext | None
    ) -> VibeInChromeResult | None:
        """Run an action against the user's Chrome via the extension.

        Returns None when no extension is connected, so the caller falls back to
        the Playwright backend.
        """
        from vibe.core.tools.builtins.vibe_in_chrome_bridge import bridge

        br = bridge()
        await br.ensure_started(
            self.config.extension_port, grace=self.config.extension_connect_grace
        )
        if not br.is_connected():
            return None

        payload = self._build_extension_payload(args)

        timeout = max(self.config.nav_timeout_ms, self.config.settle_ms) / 1000 + 5
        try:
            resp = await br.send(payload, timeout=timeout)
        except (ConnectionError, TimeoutError) as exc:
            raise ToolError(f"Extension command failed: {exc}") from exc
        if not resp.get("ok"):
            raise ToolError(resp.get("error") or "Extension returned an error.")

        data = resp.get("result") or {}
        elements = [
            VibeInChromeElement(
                ref=int(e["ref"]),
                tag=str(e.get("tag", "")),
                type=str(e.get("type", "")),
                name=str(e.get("name", "")),
            )
            for e in (data.get("elements") or [])
        ]
        tabs = [
            VibeInChromeTab(
                id=int(t["id"]),
                title=str(t.get("title", "")),
                url=str(t.get("url", "")),
                active=bool(t.get("active", False)),
            )
            for t in (data.get("tabs") or [])
        ]
        text = str(data.get("text", ""))
        if len(text) > self.config.max_text_chars:
            text = text[: self.config.max_text_chars] + "\n[…text truncated]"
        result = VibeInChromeResult(
            action=args.action,
            url=str(data.get("url", "")),
            title=str(data.get("title", "")),
            elements=elements,
            tabs=tabs,
            text=text,
        )
        if args.action == "screenshot":
            data_url = str(data.get("screenshot_data") or "")
            if data_url:
                result.screenshot_path = self._save_screenshot_data(data_url, args, ctx)
        return result

    def _save_screenshot_data(
        self, data_url: str, args: VibeInChromeArgs, ctx: InvokeContext | None
    ) -> str:
        """Save a base64 PNG from the extension and show it to a vision model."""
        import base64

        b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
        raw = base64.b64decode(b64)
        if args.path:
            dest = Path(args.path).expanduser()
        else:
            base = ctx.scratchpad_dir if ctx and ctx.scratchpad_dir else Path.cwd()
            name = f"vibe-in-chrome-{ctx.tool_call_id if ctx else 'shot'}.png"
            dest = Path(base) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        if ctx is not None and ctx.emit_image_callback is not None:
            try:
                from vibe.core.session.image_snapshot import snapshot_image_bytes

                attachment = snapshot_image_bytes(
                    raw,
                    alias=dest.name,
                    mime_type="image/png",
                    session_dir=ctx.session_dir,
                )
                ctx.emit_image_callback(
                    [attachment],
                    f"Screenshot captured by vibe-in-chrome ({dest.name}):",
                )
            except Exception:
                pass
        return str(dest)

    async def run(
        self, args: VibeInChromeArgs, ctx: InvokeContext | None = None
    ) -> AsyncGenerator[ToolStreamEvent | VibeInChromeResult, None]:
        if args.action == "close":
            await _manager().close()
            from vibe.core.tools.builtins.vibe_in_chrome_bridge import close_bridge

            await close_bridge()
            yield VibeInChromeResult(action="close", message="VibeInChrome closed.")
            return

        # Fail fast (before launching a browser) if a human handoff is impossible.
        if args.action == "pause" and (ctx is None or ctx.user_input_callback is None):
            raise ToolError(
                "Cannot pause for human input in this mode. Run interactively, "
                "with a visible browser, to hand off logins or captchas."
            )

        # Prefer the user's own Chrome via the extension when one is connected;
        # otherwise fall through to a Playwright-launched browser.
        if self.config.prefer_extension and args.action in _EXTENSION_ACTIONS:
            extension_result = await self._try_extension(args, ctx)
            if extension_result is not None:
                yield extension_result
                return

        await _manager().ensure_page(self.config)
        if args.action in _TAB_ACTIONS:
            await self._perform_tab(args)
        else:
            await self._perform(_manager().page, args, ctx)
        # open_tab / switch_tab change the active page, so re-read it here.
        page = _manager().page

        if args.action in _SETTLE_ACTIONS:
            await self._settle(page)

        result = await self._describe(page, args.action)
        if args.action == "console":
            result.console = _manager().console_messages(
                self.config.max_console_messages
            )
        elif args.action == "screenshot":
            result.screenshot_path = await self._capture(page, args, ctx)
        elif args.action in _TAB_ACTIONS:
            result.tabs = await _manager().list_tabs()
        yield result

    async def _perform_tab(self, args: VibeInChromeArgs) -> None:
        """Browser-wide tab management on the Playwright backend."""
        if args.action == "open_tab":
            if not args.url:
                raise ToolError("`open_tab` requires `url`.")
            target = self._normalize_url(args.url)
            if not self._domain_allowed(urlparse(target).netloc):
                raise ToolError(
                    f"Navigation to '{target}' is blocked by allowed_domains "
                    f"({', '.join(self.config.allowed_domains)})."
                )
            await _manager().open_tab(target, self.config)
        elif args.action == "switch_tab":
            if args.tab_id is None:
                raise ToolError("`switch_tab` requires `tab_id` (from `list_tabs`).")
            await _manager().switch_tab(args.tab_id)
        # list_tabs needs no page action; the tab list is attached by run().

    async def _perform(
        self, page: Any, args: VibeInChromeArgs, ctx: InvokeContext | None
    ) -> None:
        """Execute a single browser action against the live page."""
        match args.action:
            case "navigate":
                if not args.url:
                    raise ToolError("`navigate` requires `url`.")
                target = self._normalize_url(args.url)
                if not self._domain_allowed(urlparse(target).netloc):
                    raise ToolError(
                        f"Navigation to '{target}' is blocked by allowed_domains "
                        f"({', '.join(self.config.allowed_domains)})."
                    )
                await page.goto(target, wait_until="domcontentloaded")
            case "click":
                await self._locator(page, args).click()
            case "type":
                if args.text is None:
                    raise ToolError("`type` requires `text`.")
                locator = self._locator(page, args)
                await locator.fill(args.text)
                if args.submit:
                    await locator.press("Enter")
            case "press_key":
                if not args.key:
                    raise ToolError("`press_key` requires `key`.")
                await page.keyboard.press(args.key)
            case "scroll":
                await page.mouse.wheel(0, args.amount)
            case "back":
                await page.go_back()
            case "forward":
                await page.go_forward()
            case "pause":
                await self._await_human(ctx, args)
            case "snapshot" | "console" | "screenshot":
                pass

    async def _capture(
        self, page: Any, args: VibeInChromeArgs, ctx: InvokeContext | None
    ) -> str:
        """Save a PNG of the current page, show it to the model, and return its path.

        The image is injected into the conversation so a vision-capable model can
        see it on its next turn (and is stripped for models without vision). It is
        also a file artifact for the human (demos, bug reports).
        """
        if args.path:
            dest = Path(args.path).expanduser()
        else:
            base = ctx.scratchpad_dir if ctx and ctx.scratchpad_dir else Path.cwd()
            name = f"vibe-in-chrome-{ctx.tool_call_id if ctx else 'shot'}.png"
            dest = Path(base) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(dest), full_page=args.full_page)
        self._show_to_model(dest, ctx)
        return str(dest)

    @staticmethod
    def _show_to_model(dest: Path, ctx: InvokeContext | None) -> None:
        """Emit the screenshot as an image the model sees on its next turn."""
        if ctx is None or ctx.emit_image_callback is None:
            return
        try:
            from vibe.core.session.image_snapshot import snapshot_image

            attachment = snapshot_image(
                dest, alias=dest.name, session_dir=ctx.session_dir
            )
        except Exception:
            return  # too large or unreadable — the file is still saved on disk
        ctx.emit_image_callback(
            [attachment], f"Screenshot captured by vibe-in-chrome ({dest.name}):"
        )

    async def _await_human(
        self, ctx: InvokeContext | None, args: VibeInChromeArgs
    ) -> None:
        """Hand control to the human for a login, captcha, or 2FA step.

        Shows the instruction through the standard question UI and blocks until
        the human confirms (or aborts). The caller re-snapshots afterwards, so
        the agent sees the page as it stands once the human is done.
        """
        if ctx is None or ctx.user_input_callback is None:
            raise ToolError("No way to reach the human for a pause in this mode.")

        from vibe.core.tools.builtins.ask_user_question import (
            AskUserQuestionArgs,
            AskUserQuestionResult,
            Choice,
            Question,
        )

        prompt = args.message or (
            "This page needs you: complete the login, captcha, or 2FA in the "
            "browser window, then choose Continue."
        )
        note = (
            "The browser is running headless — you may not be able to interact."
            if self.config.headless
            else None
        )
        question = Question(
            question=prompt,
            header="Browser",
            options=[
                Choice(label="Continue", description="I've finished in the browser"),
                Choice(label="Abort", description="Stop this browser task"),
            ],
            hide_other=True,
        )
        raw = await ctx.user_input_callback(
            AskUserQuestionArgs(questions=[question], footer_note=note)
        )
        result = cast(AskUserQuestionResult, raw)
        if getattr(result, "cancelled", False):
            raise ToolError("Human handoff was cancelled.")
        answer = result.answers[0].answer if result.answers else ""
        if answer.strip().lower().startswith("abort"):
            raise ToolError("Human aborted the browser task.")

    async def _settle(self, page: Any) -> None:
        """Best-effort wait for client-rendered content to finish loading.

        ``networkidle`` may never fire on pages with analytics beacons or
        long-poll/websocket connections, so the wait is bounded and its timeout
        is swallowed — the snapshot proceeds with whatever has rendered.
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=self.config.settle_ms)
        except Exception:
            pass

    def _locator(self, page: Any, args: VibeInChromeArgs) -> Any:
        if args.ref is None:
            raise ToolError(f"`{args.action}` requires `ref` from a snapshot.")
        locator = page.locator(f'[data-vibe-ref="{args.ref}"]')
        return locator

    async def _describe(
        self, page: Any, action: VibeInChromeAction
    ) -> VibeInChromeResult:
        """Re-tag the page and return the current interactable elements + text."""
        try:
            raw = await page.evaluate(_SNAPSHOT_JS)
        except Exception as exc:
            raise ToolError(f"Failed to read page: {exc}") from exc

        elements = [
            VibeInChromeElement(
                ref=int(item["ref"]),
                tag=str(item.get("tag", "")),
                type=str(item.get("type", "")),
                name=str(item.get("name", "")),
            )
            for item in raw[: self.config.max_elements]
        ]

        text = ""
        try:
            text = await page.inner_text("body")
        except Exception:
            text = ""
        if len(text) > self.config.max_text_chars:
            text = text[: self.config.max_text_chars] + "\n[…text truncated]"

        return VibeInChromeResult(
            action=action,
            url=page.url,
            title=await page.title(),
            elements=elements,
            text=text,
        )

    @classmethod
    def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
        if not isinstance(event.args, VibeInChromeArgs):
            return ToolCallDisplay(summary="vibe-in-chrome")
        args = event.args
        detail = args.url or (f"ref {args.ref}" if args.ref is not None else "")
        summary = f"vibe-in-chrome: {args.action}"
        if detail:
            summary += f" — {detail}"
        return ToolCallDisplay(summary=summary)

    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        if not isinstance(event.result, VibeInChromeResult):
            return ToolResultDisplay(
                success=False, message=event.error or event.skip_reason or "No result"
            )
        result = event.result
        if result.message:
            message = result.message
        elif result.screenshot_path:
            message = f"screenshot → {result.screenshot_path}"
        else:
            message = f"{result.action} → {result.title or result.url}"
            if result.elements:
                message += f" ({len(result.elements)} elements)"
        return ToolResultDisplay(success=event.error is None, message=message)

    @classmethod
    def get_status_text(cls) -> str:
        return "Controlling browser"
