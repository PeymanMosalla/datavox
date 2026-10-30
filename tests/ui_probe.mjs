// بررسی سریع بالا آمدن صفحه در مرورگر بی‌صفحه: خطاهای جاوااسکریپت، درخواست‌های ناموفق و یک تصویر.
// استفاده: node tests/ui_probe.mjs <نشانی> <پوشه تصویر> [app]
//   حالت‌ها (با ویرگول): app = شبیه‌سازی پنجره اختصاصی DataVox.exe (window.chrome.webview)؛
//   old = شبیه‌سازی مرورگر قدیمی (modern.js و app.js اجرا نشوند)؛ blockjs = app.js بارگذاری نشود
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [APP = "http://127.0.0.1:8765/", OUT = tmpdir(), MODE = ""] = process.argv.slice(2);
const exe = ["C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].find((p) => existsSync(p));
const port = 9800 + Math.floor(Math.random() * 100);
const browser = spawn(exe, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "v2x-probe-"))}`, "--window-size=1366,768", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws, id = 0;
const pending = new Map(), log = [];
const send = (method, params = {}) => new Promise((resolve) => { const i = ++id; pending.set(i, resolve); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (e) => (await send("Runtime.evaluate", { expression: e, awaitPromise: true, returnByValue: true })).result?.value;
try {
  let t;
  for (let i = 0; i < 40 && !t; i++) { try { t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((x) => x.type === "page"); } catch { } if (!t) await sleep(250); }
  ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result || {}); pending.delete(m.id); }
    if (m.method === "Runtime.exceptionThrown") log.push("EXCEPTION " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) log.push("CONSOLE " + m.params.args.map((a) => a.value ?? a.description).join(" "));
    if (m.method === "Log.entryAdded") log.push("LOG " + m.params.entry.level + " " + m.params.entry.text + " " + (m.params.entry.url || ""));
    if (m.method === "Network.responseReceived" && m.params.response.status >= 400) log.push("HTTP " + m.params.response.status + " " + m.params.response.url);
    if (m.method === "Network.loadingFailed") log.push("NETFAIL " + m.params.errorText + " " + (m.params.blockedReason || ""));
  });
  for (const d of ["Runtime", "Log", "Network", "Page"]) await send(d + ".enable");
  const modes = MODE.split(",");
  if (modes.includes("app")) await send("Page.addScriptToEvaluateOnNewDocument", { source:
    "window.chrome = window.chrome || {}; window.__posted = []; window.chrome.webview = { postMessage(m){ window.__posted.push(m); }, addEventListener(){}, removeEventListener(){} };" });
  // مرورگر قدیمی: modern.js (نحو ES2020) اجرا نمی‌شود؛ app.js هم در چنین مرورگری خطای نحوی می‌دهد
  const blocked = [...(modes.includes("old") ? ["*modern.js*", "*app.js*"] : []), ...(modes.includes("blockjs") ? ["*app.js*"] : [])];
  if (blocked.length) await send("Network.setBlockedURLs", { urls: blocked });
  await send("Page.navigate", { url: APP });
  await sleep(modes.includes("blockjs") ? 18000 : 6000);
  const state = await evaluate(`(() => ({
    title: document.title, hash: location.hash, inApp: document.documentElement.classList.contains("in-app"),
    titlebarVisible: (() => { const b = document.querySelector("#titlebar"); return !!b && getComputedStyle(b).display !== "none" && b.getBoundingClientRect().height > 0; })(),
    winButtons: document.querySelectorAll("[data-win]").length,
    mainText: (document.querySelector("main") || document.body).innerText.trim().slice(0, 300),
    mainLen: (document.querySelector("main") || document.body).innerText.trim().length,
    navActive: !!document.querySelector("nav a.active, .nav a.active, [aria-current]"),
    font: getComputedStyle(document.body).fontFamily,
    ready: !!window.__v2xReady,
    bootError: (document.getElementById("v2x-boot-error") || {}).innerText?.slice(0, 400) || null,
    closeWorks: (() => { const b = document.querySelector('[data-win="close"]'); if (!b || !window.__posted) return null; b.click(); return window.__posted.includes("close"); })(),
  }))()`);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, `probe-${(MODE || "browser").replace(/,/g, "-")}.png`), Buffer.from(shot.data, "base64"));
  console.log(JSON.stringify(state, null, 1));
  console.log(log.length ? log.join("\n") : "no errors");
} finally { browser.kill(); }
