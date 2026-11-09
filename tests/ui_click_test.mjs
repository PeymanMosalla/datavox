// آزمون کلیک واقعی در مرورگر (Edge/Chrome بدون رابط) از طریق DevTools Protocol.
// استفاده: node tests/ui_click_test.mjs [http://127.0.0.1:8765/]
// بررسی می‌کند که لایه‌ای روی صفحه کلیک‌ها را نبلعد و دکمه‌ها و منوها واقعاً کار کنند.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const APP = process.argv[2] || "http://127.0.0.1:8765/";
// Chrome اول: Edge بی‌پنجره (صرفه‌جویی انرژی) پس از چند ثانیه صفحه را «پنهان» حساب می‌کند و بارگذاری صدا عقب می‌افتد
const BROWSERS = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// دریافت وضعیت با چند بار تلاش (اتصال لحظه‌ای ممکن است زیر بار پردازش قطع شود)
async function getJSON(url) { for (let i = 0; i < 5; i++) { try { return await (await fetch(url)).json(); } catch { await sleep(1000); } } throw new Error("fetch failed: " + url); }

const profile = mkdtempSync(join(tmpdir(), "v2x-ui-"));
const port = 9300 + Math.floor(Math.random() * 500);
const exe = BROWSERS.find((p) => existsSync(p)) || BROWSERS[0];
// صفحه حتی وقتی صفحه‌نمایش ویندوز خاموش یا قفل است «پنهان» حساب نشود (مرورگر بارگذاری صدا را در صفحه پنهان عقب می‌اندازد)
const browser = spawn(exe, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--disable-features=CalculateNativeWinOcclusion", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
  "--window-size=1400,900", "about:blank"], { stdio: "ignore" });

let ws, id = 0;
const pending = new Map();
const errors = [];
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const i = ++id;
    pending.set(i, { resolve, reject });
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); reject(new Error("مهلت پاسخ مرورگر تمام شد: " + method)); } }, 30000);
  });
}
async function evaluate(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + JSON.stringify(r.exceptionDetails.exception?.description));
  return r.result.value;
}
async function click(selector) {
  const box = await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return null;
    const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!box) throw new Error("پیدا نشد: " + selector);
  const top = await evaluate(`(() => { const e = document.elementFromPoint(${box.x}, ${box.y});
    return e ? (e.id ? "#" + e.id : e.className || e.tagName) : null; })()`);
  const hit = await evaluate(`(() => { const t = document.elementFromPoint(${box.x}, ${box.y});
    const e = document.querySelector(${JSON.stringify(selector)}); return !!t && (t === e || e.contains(t)); })()`);
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
  return { hit, top };
}

async function key(keyName, code, vk, modifiers = 0) {
  for (const type of ["keyDown", "keyUp"])
    await send("Input.dispatchKeyEvent", { type, key: keyName, code, windowsVirtualKeyCode: vk, modifiers });
}

// UI_SHOTS=پوشه: در نقاط کلیدی از صفحه تصویر گرفته می‌شود (برای بررسی چشمی چیدمان)
async function shot(name) {
  if (!process.env.UI_SHOTS) return;
  const r = await send("Page.captureScreenshot", { format: "png" });
  if (r.data) writeFileSync(join(process.env.UI_SHOTS, name + ".png"), Buffer.from(r.data, "base64"));
}

const results = [];
function check(name, ok, detail = "") { results.push({ name, ok, detail }); console.log((ok ? "PASS " : "FAIL ") + name + (detail ? "  — " + detail : "")); }

try {
  let target;
  for (let i = 0; i < 40 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page"); } catch { }
    if (!target) await sleep(250);
  }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id).resolve(m.result || {}); pending.delete(m.id); }
    if (m.method === "Runtime.exceptionThrown") errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  });
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Page.navigate", { url: APP });
  await sleep(3000);

  check("صفحه بارگذاری شد", (await evaluate("document.title")) === "DataVox");
  const overlay = await evaluate(`(() => { const e = document.elementFromPoint(700, 450); return e ? (e.id || e.className || e.tagName) : ""; })()`);
  check("لایه‌ای روی صفحه نیست", !/backdrop/.test(overlay), "عنصر بالایی وسط صفحه: " + overlay);
  const title = () => evaluate("document.querySelector('#page-title').textContent");
  const waitFor = async (sel, ms = 15000) => {
    for (let t = 0; t < ms; t += 300) { if (await evaluate(`!!document.querySelector(${JSON.stringify(sel)})`)) return true; await sleep(300); }
    return false;
  };
  const clickIn = async (sel) => {
    await evaluate(`document.querySelector(${JSON.stringify(sel)})?.scrollIntoView({block: "center"})`);
    await sleep(250);
    return click(sel);
  };
  const toastErrors = () => evaluate(`[...document.querySelectorAll("#toasts .toast.err")].map((x) => x.innerText).join(" | ")`);

  // منو: فقط چهار بخش؛ صفحه اول «فایل‌های من»
  const navShown = await evaluate(`[...document.querySelectorAll("#nav a")].filter((a) => a.offsetParent && a.dataset.page).map((a) => a.dataset.page).join(",")`);
  check("منو: «فایل‌های من»، «تاریخچه ثبت‌ها»، «تنظیمات»، «اشتراک و پشتیبانی»", navShown === "files,history,settings,activate", navShown);
  check("صفحه پیش‌فرض «فایل‌های من»", (await title()) === "فایل‌های من");
  for (const [page, t] of [["history", "تاریخچه ثبت‌ها"], ["settings", "تنظیمات"], ["files", "فایل‌های من"]]) {
    const r = await click(`#nav a[data-page="${page}"]`);
    await sleep(1000);
    const got = await title();
    check(`منو «${t}»`, r.hit && got === t, `کلیک به ${r.top} خورد؛ عنوان: ${got}`);
  }
  await click(`#nav a[data-page="settings"]`);
  await sleep(1200);
  const rd = await click(`#page a[href="#/dictionary"]`);
  await sleep(1000);
  check("واژه‌نامه از داخل تنظیمات", rd.hit && (await title()) === "واژه‌نامه" &&
    (await evaluate(`document.querySelector('#nav a[data-page="settings"]').classList.contains("active")`)));
  await evaluate(`location.hash = "#/today"`);
  await sleep(900);
  check("پیوند قدیمی «کار امروز» به «فایل‌های من» می‌رود", (await title()) === "فایل‌های من");

  const r2 = await click("#btn-exit");
  await sleep(500);
  const modalOpen = await evaluate("!document.querySelector('#modal-backdrop').hidden && getComputedStyle(document.querySelector('#modal-backdrop')).display !== 'none'");
  check("دکمه «خروج» پنجره تأیید را باز می‌کند", r2.hit && modalOpen, "کلیک به " + r2.top);
  const r3 = await click("#modal .modal-f .btn.ghost");
  await sleep(400);
  const modalClosed = await evaluate("getComputedStyle(document.querySelector('#modal-backdrop')).display === 'none'");
  check("«انصراف» پنجره را می‌بندد و صفحه دوباره قابل کلیک است", r3.hit && modalClosed);
  // صفحه «اشتراک و پشتیبانی»: وضعیت بالای صفحه، کد رایانه، پیوند پیام‌رسان‌ها و فعال‌سازی فقط با مجوز واردشده
  await click(`#nav a[data-page="activate"]`);
  await sleep(1500);
  const act = await evaluate(`(() => ({ hero: !!document.querySelector(".act-hero h2"), code: document.querySelector("#act-code")?.textContent.trim() || "",
    goOff: document.querySelector("#act-go")?.disabled, links: document.querySelectorAll(".act-link").length,
    logos: [...document.querySelectorAll("img.logo")].every((i) => i.complete && i.naturalWidth > 0) }))()`);
  check("اشتراک و پشتیبانی: کارت وضعیت و کد رایانه", act.hero && /^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$/.test(act.code), act.code);
  check("لوگوی پیام‌رسان‌ها بارگذاری شد", act.logos);
  await evaluate(`(() => { const t = document.querySelector("#act-text"); t.value = "V2X1.x"; t.dispatchEvent(new Event("input")); })()`);
  const goOn = await evaluate(`!document.querySelector("#act-go").disabled`);
  check("«فعال‌سازی» فقط پس از وارد کردن مجوز روشن می‌شود", act.goOff === true && goOn);
  await evaluate(`(() => { const t = document.querySelector("#act-text"); t.value = ""; t.dispatchEvent(new Event("input")); })()`);
  if (process.argv.includes("--full")) {
    // مسیر کامل: فایل اکسل نمونه ← تأیید ستون‌ها ← ویس نمونه ← تبدیل ← بررسی ← تأیید ← ثبت ← تاریخچه ← برگرداندن
    await click(`#nav a[data-page="files"]`);
    await sleep(1500);
    const t1 = await click("#btn-theme"); await sleep(200);
    const th1 = await evaluate("document.documentElement.dataset.theme || 'auto'");
    await click("#btn-theme"); await sleep(200);
    const th2 = await evaluate("document.documentElement.dataset.theme || 'auto'");
    await click("#btn-theme"); await sleep(200);
    const th3 = await evaluate("document.documentElement.dataset.theme || 'auto'");
    check("دکمه تم: خودکار ← روشن ← تیره ← خودکار", t1.hit && th1 === "light" && th2 === "dark" && th3 === "auto", `${th1}, ${th2}, ${th3}`);
    const fresh = (await getJSON(APP + "api/dests")).dests.length === 0;
    const hasSample = await evaluate("!!state.meta?.samples?.excel");
    if (fresh && hasSample) {
      check("اجرای اول: صفحه خوش‌آمد با سه گام", (await evaluate("document.querySelectorAll('.welcome .setup-steps li').length")) === 3);
      await shot("01-welcome");
      await clickIn("#wl-sample");
      check("گام ۲: پنجره تأیید ستون‌ها", await waitFor("#modal-backdrop:not([hidden]) .map-select", 8000) &&
        (await evaluate("document.querySelector('#modal .modal-h').innerText")).includes("گام ۲"));
      await shot("02-columns");
      await clickIn('#modal [data-mi="0"]');
      await waitFor("#fw-next .next-step", 10000);
      check("گام ۳: میز کار فایل با نوار فایل و «گام بعد»", (await evaluate("location.hash")).includes("first=1") &&
        await waitFor(".file-bar") && await waitFor(".welcome .setup-steps li.now"), await toastErrors());
    } else {
      const first = (await getJSON(APP + "api/dests")).dests[0];
      check("فایلی در فهرست هست", !!first, fresh ? "فایل اکسل نمونه در این اجرا نیست" : "");
      if (!first) throw new Error("فایلی برای ادامه آزمون نیست");
      await evaluate(`location.hash = "#/file?f=${encodeURIComponent(first.name)}"`);
      await waitFor(".file-bar");
    }
    const dest = decodeURIComponent((await evaluate("location.hash")).match(/f=([^&]+)/)[1]);
    // ویس نمونه
    if (await evaluate("!!document.querySelector('#fw-samples')")) {
      const rs = await clickIn("#fw-samples");
      check("دکمه «امتحان با ویس نمونه»", rs.hit, "کلیک به " + rs.top);
    } else {
      await evaluate(`api("/api/samples/import?dest=${encodeURIComponent(dest)}", { method: "POST" }).then(() => startQueue())`);
    }
    let done = false;
    for (let i = 0; i < 200 && !done; i++) {
      await sleep(2000);
      const st = await getJSON(APP + "api/status");
      done = !st.worker.running && st.files.queued === 0 && st.files.done > 0;
    }
    check("تبدیل ویس‌های نمونه تمام شد", done);
    if (await evaluate("!document.querySelector('#modal-backdrop').hidden")) await click("#modal .modal-f .btn");
    await sleep(1500);
    const info = await getJSON(APP + `api/dests/${encodeURIComponent(dest)}`);
    check("ویس‌ها مال همین فایل‌اند", info.voices >= 1 && info.converting === 0, JSON.stringify({ v: info.voices, r: info.review, ok: info.ready }));
    check("جدول «ویس‌های این فایل» برای هر ویس یک خط دارد", (await evaluate("document.querySelectorAll('#fw-v tr[data-vid]').length")) === info.voices);
    check("ردیف‌های نیازمند بررسی به شکل ردیف اکسل", await waitFor("#fw-rv .xr-table td[data-xcell]", 8000));
    await shot("03-workspace");
    const ro = await clickIn("#fw-rv [data-xcell]");
    await sleep(1500);
    check("کلیک روی خانه، پنجره اصلاح را باز می‌کند", ro.hit && (await evaluate("document.querySelector('#drawer').classList.contains('open')")));
    check("پخش‌کننده صدا در پنجره اصلاح", await evaluate("!!document.querySelector('#drawer audio')"));
    await evaluate(`(() => { const i = document.querySelector('#drawer [data-f="address"]'); i.value = i.value + ' (اصلاح آزمایشی)';
      i.dispatchEvent(new Event('change')); })()`);
    await sleep(1500);
    check("اصلاح دستی فیلد ذخیره شد", (await evaluate("document.querySelector('#drawer [data-f=\"address\"]').value")).includes("اصلاح آزمایشی"));
    const hasSeg = await evaluate("!!document.querySelector('#drawer [data-segk=\"phone\"]')");
    check("دکمه پخش بخش شماره", hasSeg);
    if (hasSeg) {
      await click('#drawer [data-segk="phone"]');
      let played = false;
      for (let i = 0; i < 8 && !played; i++) {
        await sleep(500);
        played = await evaluate("(() => { const a = document.querySelector('#dr-audio'); return a.currentTime > 0.2; })()");
      }
      check("پخش بخش شماره از ویس", played, "زمان: " + (await evaluate(`(() => { const a = document.querySelector('#dr-audio');
        return a.currentTime.toFixed(2) + (a.currentTime > 0.2 ? "" : " | ready=" + a.readyState + " net=" + a.networkState + " paused=" + a.paused
          + " err=" + (a.error && a.error.code) + " stopAt=" + a.dataset.stopAt + " bound=" + a.dataset.segBound + " src=" + a.src.split("/api/")[1] + " vis=" + document.visibilityState + " focus=" + document.hasFocus()); })()`)));
      await evaluate("document.querySelector('#dr-audio').pause()");
    }
    check("نمایش گروه‌بندی‌شده شماره", /^0\d{3} \d{3} \d{4}$/.test(await evaluate("document.querySelector('#drawer .phone-view span')?.textContent || ''")));
    await shot("04-drawer");
    const ru = await click("#dr-undo");
    check("اعلان روی دکمه «بازگشت» قرار نمی‌گیرد", ru.hit, "کلیک به " + ru.top);
    await sleep(1500);
    check("دکمه «بازگشت» اصلاح را برمی‌گرداند", ru.hit && !(await evaluate("document.querySelector('#drawer [data-f=\"address\"]').value")).includes("اصلاح آزمایشی"));
    const ra = await click("#dr-approve");
    await sleep(800);
    if (await evaluate("!document.querySelector('#modal-backdrop').hidden")) await click("#modal .modal-f .btn.ok");
    await sleep(1500);
    const st2 = await getJSON(APP + "api/status");
    check("دکمه «تأیید برای ثبت»", ra.hit && st2.records.approved >= 1, `آماده ثبت: ${st2.records.approved}`);
    if (await evaluate("document.querySelector('#drawer').classList.contains('open')")) await click("#dr-close");
    await sleep(800);
    // «گام بعد» فقط یک دکمه اصلی دارد و بررسی سریع را باز می‌کند
    check("فقط یک دکمه اصلی در میز کار", (await evaluate("document.querySelectorAll('#page .btn.primary').length")) === 1);
    const approvedBefore = (await getJSON(APP + "api/status")).records.approved;
    if ((await getJSON(APP + `api/dests/${encodeURIComponent(dest)}`)).review) {
      const rf = await clickIn("#fw-next-go");
      await sleep(1800);
      await shot("05-focus");
      check("«گام بعد» بررسی سریع را باز می‌کند", rf.hit && (await evaluate("!document.querySelector('#focus').hidden")));
      await evaluate(`(() => { const i = document.querySelector('#focus [data-ff="engineer_name"]'); i.value = i.value + 'پور'; i.dispatchEvent(new Event('change')); })()`);
      await sleep(1200);
      await evaluate("document.activeElement && document.activeElement.blur()");
      await key("Enter", "Enter", 13, 2);  // Ctrl+Enter
      await sleep(2500);
      const approvedAfter = (await getJSON(APP + "api/status")).records.approved;
      check("Ctrl+Enter در بررسی سریع تأیید می‌کند", approvedAfter === approvedBefore + 1, `آماده ثبت: ${approvedBefore} ← ${approvedAfter}`);
      await key("Escape", "Escape", 27);
      await sleep(800);
      check("Esc بررسی سریع را می‌بندد", await evaluate("document.querySelector('#focus').hidden"));
    }
    // ثبت در فایل، با بررسی وضعیت فایل
    check("وضعیت فایل پیش از ثبت با جمله ساده", await waitFor("#fw-cm .fcheck li.ok", 8000), await evaluate("document.querySelector('#fw-cm')?.innerText.slice(0, 200) || ''"));
    const rc = await clickIn("#fw-commit-go");
    let exported = false;
    for (let i = 0; i < 20 && !exported; i++) { await sleep(1000); exported = (await getJSON(APP + "api/status")).records.exported >= 1; }
    check("ثبت مستقیم در فایل از میز کار", rc.hit && exported, await toastErrors());
    check("پس از ثبت، شماره ردیف در جدول ویس‌ها", await waitFor("#fw-v .vt-rows", 8000));
    await shot("06-after-commit");
    // تاریخچه ثبت‌ها و برگرداندن
    await click(`#nav a[data-page="history"]`);
    check("تاریخچه ثبت‌ها ثبت را نشان می‌دهد", await waitFor(".h-item [data-hundo]", 8000));
    await shot("07-history");
    await clickIn(".h-item [data-hundo]");
    await waitFor("#modal-backdrop:not([hidden]) .modal-f .btn.danger", 5000);
    await click("#modal .modal-f .btn.danger");
    let undone = false;
    for (let i = 0; i < 20 && !undone; i++) { await sleep(700); undone = await evaluate("!!document.querySelector('.h-item.undone')"); }
    check("«برگرداندن» ثبت را لغو می‌کند", undone && (await getJSON(APP + "api/status")).records.exported === 0, await toastErrors());
    // یادگیری از اصلاح: «… → …پور» در زبانه اصلاحات
    await evaluate(`location.hash = "#/dictionary"`);
    await sleep(1200);
    await click('[data-t="__corrections"]');
    await sleep(1200);
    check("اصلاح انجام‌شده در «اصلاحات یادگرفته‌شده» ثبت شد", (await evaluate("document.querySelectorAll('#dc-table tbody tr').length")) >= 1);
    // تنظیمات فایل و پیش‌نمایش
    await evaluate(`location.hash = "#/templates?dest=${encodeURIComponent(dest)}"`);
    check("تنظیمات فایل با نوار فایل و زبانه‌ها", await waitFor("#dv-bar .file-bar") && await waitFor("#tp-tabs [data-tt='columns'].active"));
    await clickIn("#tp-show");
    check("پیش‌نمایش جدول شبیه اکسل", await waitFor(".modal.xwide .xl-letters"));
    await clickIn("#modal .modal-f .btn.primary");
    await sleep(400);
    // پشتیبان‌گیری دستی
    await click(`#nav a[data-page="settings"]`);
    for (let i = 0; i < 40 && !(await evaluate("!!document.querySelector('#s-backup-now')")); i++) await sleep(300);
    await clickIn("#s-backup-now");
    await sleep(2000);
    check("پشتیبان‌گیری الان", (await evaluate("document.querySelectorAll('#s-backups tbody tr').length")) >= 1);
  }
  check("بدون خطای جاوااسکریپت", errors.length === 0, errors.join(" | "));
} catch (e) {
  check("اجرای آزمون", false, String(e));
} finally {
  try { ws?.close(); } catch { }
  browser.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { }
}
const failed = results.filter((r) => !r.ok).length;
console.log(failed ? `\n${failed} مورد ناموفق` : "\nهمه موارد موفق");
process.exit(failed ? 1 : 0);
