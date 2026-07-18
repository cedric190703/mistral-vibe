# Vibe in Chrome — browser extension

This extension lets Mistral Vibe drive **your own Chrome** (your real profile,
logins, and open tabs) instead of launching a separate Playwright browser.

## How it works

```
Vibe (CLI)  ── local WebSocket (127.0.0.1:9223) ──►  this extension (MV3 service worker)
  vibe-in-chrome tool                                  runs the command in your active tab
        navigate / snapshot / click / type            via chrome.scripting / chrome.tabs
```

A Chrome MV3 service worker can only be a WebSocket **client**, so Vibe hosts the
server and the extension connects to it (with an automatic reconnect loop). The
`vibe-in-chrome` tool tries this extension first and **falls back to Playwright**
when no extension is connected.

## Install (load unpacked)

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode** (top-right).
3. Click **Load unpacked** and select this `distribution/chrome-extension/` folder.
4. Open the extension's **Details → Site access** and choose **"On all sites"**.
   This is required: `snapshot`/`click`/`type` (via `chrome.scripting`) and
   `screenshot` (via `captureVisibleTab`) need host access to the page.
5. That's it — the extension keeps trying to connect to Vibe in the background.

> After editing the extension's code, use **Remove + Load unpacked** if the
> reload button (↻) doesn't pick up the change.

### Limitations

Actions run against the **active tab**, and Chrome forbids scripting or capturing
its own pages (`chrome://…`, the Web Store). If the active tab is a `chrome://`
page, ask the agent to `open_tab`/`switch_tab`/`navigate` to a normal page first.

## Use it

1. Start Vibe with the browser extra: `uv run --extra browser vibe`.
2. Ask Vibe to do something in the browser (e.g. "open example.com and list the
   links"). The first browser action starts the local bridge; the extension
   connects within a second or two and subsequent actions run in **your** Chrome.
3. When no extension is connected, Vibe silently falls back to a Playwright
   browser — nothing to configure.

## Configuration

Defaults live in `~/.vibe/config.toml`:

```toml
[tools.vibe-in-chrome]
prefer_extension = true   # try this extension before Playwright
extension_port   = 9223   # must match PORT in background.js
```

To force Playwright (ignore the extension), set `prefer_extension = false`.

## Supported actions (extension mode)

All actions run against your real browser: `navigate`, `snapshot`, `click`,
`type`, `press_key`, `scroll`, `back`, `forward`, `console` (real tab's console +
errors), `screenshot` (real tab, shown to vision models), tab management
(`list_tabs`, `open_tab`, `switch_tab`), and `pause` (asks you in the CLI, then
re-reads the real tab). Nothing falls back to a separate browser while the
extension is connected.

## Security

The bridge is bound to `127.0.0.1` only, so only local processes can reach it.
Still, this extension lets a local program act in your authenticated browser —
only run it while you are using Vibe, and prefer the tool's `allowed_domains`
setting to restrict where it may navigate.
