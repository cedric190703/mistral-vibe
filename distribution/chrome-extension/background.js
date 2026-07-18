// Vibe in Chrome — MV3 service worker.
//
// Connects (as a WebSocket client) to the local bridge that Mistral Vibe hosts,
// receives browser commands, executes them in the active tab via chrome.scripting
// / chrome.tabs, and returns the result. A service worker cannot listen for
// sockets, so Vibe is the server and this is the client (with a reconnect loop).

const PORT = 9223; // must match `extension_port` in the vibe-in-chrome tool config
const RECONNECT_MS = 1000;

let ws = null;

// An MV3 service worker is terminated after ~30s idle, which kills any
// setTimeout reconnect loop. A periodic alarm wakes it back up to retry, so the
// extension reconnects even after Vibe starts its bridge later. While connected,
// the live WebSocket keeps the worker alive on its own.
chrome.alarms.create("vibe-reconnect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "vibe-reconnect") ensureConnected();
});
chrome.runtime.onStartup.addListener(ensureConnected);
chrome.runtime.onInstalled.addListener(ensureConnected);

function ensureConnected() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  connect();
}

function connect() {
  try {
    ws = new WebSocket(`ws://127.0.0.1:${PORT}`);
  } catch (e) {
    setTimeout(connect, RECONNECT_MS);
    return;
  }
  ws.onopen = () => ws.send(JSON.stringify({ type: "hello", ua: navigator.userAgent }));
  ws.onmessage = async (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (!msg.id) return;
    try {
      const result = await handle(msg);
      reply({ id: msg.id, ok: true, result });
    } catch (e) {
      reply({ id: msg.id, ok: false, error: String((e && e.message) || e) });
    }
  };
  ws.onclose = () => setTimeout(connect, RECONNECT_MS);
  ws.onerror = () => {
    try {
      ws.close();
    } catch {}
  };
}

function reply(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

async function activeTab() {
  let [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) [tab] = await chrome.tabs.query({ active: true });
  if (!tab) throw new Error("No active tab to control.");
  return tab;
}

async function exec(tabId, func, args = []) {
  const [res] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  return res.result;
}

function waitComplete(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    const done = () => {
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timer);
      resolve();
    };
    const listener = (id, info) => {
      if (id === tabId && info.status === "complete") done();
    };
    const timer = setTimeout(done, timeoutMs);
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function listTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.map((t) => ({
    id: t.id,
    title: t.title || "",
    url: t.url || "",
    active: !!t.active,
  }));
}

async function snapshotOf(tabId, msg) {
  return exec(tabId, snapshotPage, [msg.maxElements ?? 150, msg.maxTextChars ?? 6000]);
}

async function handle(msg) {
  // Tab-management actions work across the whole browser, not just one tab.
  if (msg.action === "list_tabs") {
    return { tabs: await listTabs() };
  }
  if (msg.action === "open_tab") {
    const t = await chrome.tabs.create({ url: msg.url, active: true });
    await waitComplete(t.id);
    return { ...(await snapshotOf(t.id, msg)), tabs: await listTabs() };
  }
  if (msg.action === "switch_tab") {
    await chrome.tabs.update(msg.tab_id, { active: true });
    return { ...(await snapshotOf(msg.tab_id, msg)), tabs: await listTabs() };
  }
  if (msg.action === "screenshot") {
    const tab = await activeTab();
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
      format: "png",
    });
    return { ...(await snapshotOf(tab.id, msg)), screenshot_data: dataUrl };
  }

  const tab = await activeTab();
  switch (msg.action) {
    case "navigate":
      await chrome.tabs.update(tab.id, { url: msg.url });
      await waitComplete(tab.id);
      break;
    case "click":
      await exec(tab.id, clickInPage, [msg.ref]);
      break;
    case "type":
      await exec(tab.id, typeInPage, [msg.ref, msg.text ?? "", !!msg.submit]);
      if (msg.submit) await waitComplete(tab.id, 8000);
      break;
    case "scroll":
      await exec(tab.id, scrollInPage, [msg.amount ?? 600]);
      break;
    case "back":
      await chrome.tabs.goBack(tab.id);
      await waitComplete(tab.id, 8000);
      break;
    case "forward":
      await chrome.tabs.goForward(tab.id);
      await waitComplete(tab.id, 8000);
      break;
    case "snapshot":
      break;
    default:
      throw new Error(`Unsupported action in extension mode: ${msg.action}`);
  }
  // Re-read the page after the action (same shape the Playwright backend returns).
  return exec(tab.id, snapshotPage, [msg.maxElements ?? 150, msg.maxTextChars ?? 6000]);
}

// ── Functions injected into the page (must be fully self-contained) ──────────

function snapshotPage(maxElements, maxTextChars) {
  const SELECTOR = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea",
    "summary", "label", "[role=button]", "[role=link]", "[role=checkbox]",
    "[role=tab]", "[role=menuitem]", "[role=textbox]", "[onclick]",
    '[contenteditable=""]', "[contenteditable=true]",
  ].join(",");
  const visible = (el) => {
    if (el.disabled) return false;
    if (!el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none";
  };
  const name = (el) => {
    const raw =
      el.getAttribute("aria-label") || el.getAttribute("placeholder") ||
      (el.innerText || "").trim() || el.value || el.getAttribute("title") ||
      el.getAttribute("alt") || el.getAttribute("name") || "";
    return raw.replace(/\s+/g, " ").trim().slice(0, 120);
  };
  document.querySelectorAll("[data-vibe-ref]").forEach((el) =>
    el.removeAttribute("data-vibe-ref")
  );
  const elements = [];
  let i = 0;
  for (const el of document.querySelectorAll(SELECTOR)) {
    if (!visible(el)) continue;
    el.setAttribute("data-vibe-ref", String(i));
    elements.push({
      ref: i,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute("type") || el.getAttribute("role") || "",
      name: name(el),
    });
    if (++i >= maxElements) break;
  }
  let text = "";
  try {
    text = document.body.innerText || "";
  } catch {}
  if (text.length > maxTextChars) text = text.slice(0, maxTextChars) + "\n[…text truncated]";
  return { url: location.href, title: document.title, elements, text };
}

function clickInPage(ref) {
  const el = document.querySelector(`[data-vibe-ref="${ref}"]`);
  if (!el) throw new Error(`ref ${ref} not found — take a snapshot first`);
  el.click();
}

function typeInPage(ref, text, submit) {
  const el = document.querySelector(`[data-vibe-ref="${ref}"]`);
  if (!el) throw new Error(`ref ${ref} not found — take a snapshot first`);
  el.focus();
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, text);
  else el.value = text;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  if (submit) {
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    if (el.form) {
      if (el.form.requestSubmit) el.form.requestSubmit();
      else el.form.submit();
    }
  }
}

function scrollInPage(amount) {
  window.scrollBy(0, amount);
}

ensureConnected();
