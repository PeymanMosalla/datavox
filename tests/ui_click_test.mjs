// آزمون کلیک واقعی در مرورگر (Edge/Chrome بدون رابط) از طریق DevTools Protocol.
// استفاده: node tests/ui_click_test.mjs [http://127.0.0.1:8765/]
// بررسی می‌کند که لایه‌ای روی صفحه کلیک‌ها را نبلعد و دکمه‌ها و منوها واقعاً کار کنند.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const APP = process.argv[2] || "http://127.0.0.1:8765/";
const BROWSERS = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// دریافت وضعیت با چند بار تلاش (اتصال لحظه‌ای ممکن است زیر بار پردازش قطع شود)
async function getJSON(url) { for (let i = 0; i < 5; i++) { try { return await (await fetch(url)).json(); } catch { await sleep(1000); } } throw new Error("fetch failed: " + url); }

const profile = mkdtempSync(join(tmpdir(), "v2x-ui-"));
const port = 9300 + Math.floor(Math.random() * 500);
const exe = BROWSERS.find((p) => existsSync(p)) || BROWSERS[0];
const browser = spawn(exe, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
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

  check("صفحه بارگذاری شد", (await evaluate("document.title")) === "ثبت ویس");
  const overlay = await evaluate(`(() => { const e = document.elementFromPoint(700, 450); return e ? (e.id || e.className || e.tagName) : ""; })()`);
  check("لایه‌ای روی صفحه نیست", !/backdrop/.test(overlay), "عنصر بالایی وسط صفحه: " + overlay);

  // منوی ساده: فقط «کار امروز» و «تنظیمات»؛ بقیه صفحه‌ها از کارت «ابزارها» در تنظیمات
  const navShown = await evaluate(`[...document.querySelectorAll("#nav a")].filter((a) => a.offsetParent && a.dataset.page).map((a) => a.dataset.page).join(",")`);
  check("منوی ساده فقط «کار امروز»، «قالب اکسل» و «تنظیمات» دارد", navShown === "today,templates,settings", navShown);
  check("صفحه پیش‌فرض «کار امروز»", (await evaluate("document.querySelector('#page-title').textContent")) === "کار امروز");
  await click(`#nav a[data-page="settings"]`);
  await sleep(1200);
  const rt = await click(`#page a[href="#/excel"]`);
  await sleep(900);
  check("پیوند «اتصال فایل اکسل» در تنظیمات", rt.hit && (await evaluate("document.querySelector('#page-title').textContent")) === "ثبت در اکسل");
  // ادامه آزمون با منوی کامل (همان تنظیم «نمایش همه صفحه‌ها»)
  await evaluate("localStorage.setItem('v2x.nav', 'full'); document.documentElement.classList.add('full-nav')");
  for (const [page, title] of [["voices", "ویس‌ها و پردازش"], ["review", "بازبینی اطلاعات"], ["excel", "ثبت در اکسل"], ["dictionary", "واژه‌نامه"], ["settings", "تنظیمات"], ["dashboard", "داشبورد"], ["templates", "قالب اکسل"], ["today", "کار امروز"]]) {
    const r = await click(`#nav a[data-page="${page}"]`);
    await sleep(900);
    const t = await evaluate("document.querySelector('#page-title').textContent");
    check(`منو «${title}»`, r.hit && t === title, `کلیک به ${r.top} خورد؛ عنوان: ${t}`);
  }
  await click(`#nav a[data-page="voices"]`);
  await sleep(900);
  await evaluate("document.querySelector('#in-files').addEventListener('click', () => window.__fileDialog = true, { once: true })");
  const r1 = await click("#pick-files");
  await sleep(300);
  check("دکمه «انتخاب فایل‌ها»", r1.hit && (await evaluate("!!window.__fileDialog")), "کلیک به " + r1.top);

  const r2 = await click("#btn-exit");
  await sleep(500);
  const modalOpen = await evaluate("!document.querySelector('#modal-backdrop').hidden && getComputedStyle(document.querySelector('#modal-backdrop')).display !== 'none'");
  check("دکمه «خروج» پنجره تأیید را باز می‌کند", r2.hit && modalOpen, "کلیک به " + r2.top);
  const r3 = await click("#modal .modal-f .btn.ghost");
  await sleep(400);
  const modalClosed = await evaluate("getComputedStyle(document.querySelector('#modal-backdrop')).display === 'none'");
  check("«انصراف» پنجره را می‌بندد و صفحه دوباره قابل کلیک است", r3.hit && modalClosed);
  if (process.argv.includes("--full")) {
    // مسیر کامل: ویس نمونه ← پردازش ← بازبینی ← تأیید ← اکسل نمونه ← خروجی
    await click(`#nav a[data-page="dashboard"]`);
    await sleep(1200);
    const fresh = (await getJSON(APP + "api/status")).files.total === 0;
    if (fresh) check("راهنمای اجرای اول نمایش داده می‌شود", (await evaluate("document.querySelectorAll('.ob-step').length")) === 4);
    await shot("01-dashboard-onboarding");
    const t1 = await click("#btn-theme"); await sleep(200);
    const th1 = await evaluate("document.documentElement.dataset.theme || 'auto'");
    await click("#btn-theme"); await sleep(200);
    const th2 = await evaluate("document.documentElement.dataset.theme || 'auto'");
    await click("#btn-theme"); await sleep(200);
    const th3 = await evaluate("document.documentElement.dataset.theme || 'auto'");
    check("دکمه تم: خودکار ← روشن ← تیره ← خودکار", t1.hit && th1 === "light" && th2 === "dark" && th3 === "auto", `${th1}, ${th2}, ${th3}`);
    const rs = await click("#d-samples");
    check("دکمه «امتحان با ویس نمونه»", rs.hit, "کلیک به " + rs.top);
    let done = false;
    for (let i = 0; i < 200 && !done; i++) {
      await sleep(2000);
      const st = await getJSON(APP + "api/status");
      done = !st.worker.running && st.files.queued === 0 && st.files.done > 0;
    }
    check("پردازش ویس‌های نمونه تمام شد", done);
    // اگر پنجره «نتیجه افزودن فایل‌ها» (مثلاً فایل تکراری) باز است، بسته شود
    if (await evaluate("!document.querySelector('#modal-backdrop').hidden")) await click("#modal .modal-f .btn");
    await sleep(500);
    await click(`#nav a[data-page="review"]`);
    await sleep(1500);
    const rows = await evaluate("document.querySelectorAll('tr[data-rid]').length");
    check("جدول بازبینی ردیف دارد", rows > 0, `${rows} ردیف`);
    const ro = await click("tr[data-rid] td:nth-child(3)");
    await sleep(1500);
    check("کلیک روی ردیف، پنجره جزئیات را باز می‌کند", ro.hit && (await evaluate("document.querySelector('#drawer').classList.contains('open')")));
    check("پخش‌کننده صدا در پنجره جزئیات", await evaluate("!!document.querySelector('#drawer audio')"));
    await evaluate(`(() => { const i = document.querySelector('#drawer [data-f="address"]'); i.value = i.value + ' (اصلاح آزمایشی)';
      i.dispatchEvent(new Event('change')); })()`);
    await sleep(1500);
    check("اصلاح دستی فیلد ذخیره شد", (await evaluate("document.querySelector('#drawer [data-f=\"address\"]').value")).includes("اصلاح آزمایشی"));
    // پخش همان بخشِ شماره از ویس
    const hasSeg = await evaluate("!!document.querySelector('#drawer [data-segk=\"phone\"]')");
    check("دکمه پخش بخش شماره", hasSeg);
    if (hasSeg) {
      await click('#drawer [data-segk="phone"]');
      await sleep(1200);
      const played = await evaluate("(() => { const a = document.querySelector('#dr-audio'); return a.currentTime > 0.2; })()");
      check("پخش بخش شماره از ویس", played, "زمان: " + (await evaluate("document.querySelector('#dr-audio').currentTime.toFixed(2)")));
      await evaluate("document.querySelector('#dr-audio').pause()");
    }
    check("نمایش گروه‌بندی‌شده شماره", /^0\d{3} \d{3} \d{4}$/.test(await evaluate("document.querySelector('#drawer .phone-view span')?.textContent || ''")),
      await evaluate("document.querySelector('#drawer .phone-view span')?.textContent || ''"));
    await shot("02-drawer");
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
    await click("#dr-close");
    await sleep(500);
    // بازبینی سریع با صفحه‌کلید
    const approvedBefore = (await getJSON(APP + "api/status")).records.approved;
    const rf = await click("#rv-focus");
    await sleep(1800);
    await shot("03-focus");
    check("دکمه «بازبینی سریع» حالت تمام‌صفحه را باز می‌کند", rf.hit && (await evaluate("!document.querySelector('#focus').hidden")));
    await evaluate(`(() => { const i = document.querySelector('#focus [data-ff="engineer_name"]'); i.value = i.value + 'پور'; i.dispatchEvent(new Event('change')); })()`);
    await sleep(1200);
    await evaluate("document.activeElement && document.activeElement.blur()");
    await key("Enter", "Enter", 13, 2);  // Ctrl+Enter
    await sleep(2500);
    const approvedAfter = (await getJSON(APP + "api/status")).records.approved;
    check("Ctrl+Enter در بازبینی سریع تأیید می‌کند و به رکورد بعدی می‌رود", approvedAfter === approvedBefore + 1,
      `آماده ثبت: ${approvedBefore} ← ${approvedAfter}؛ ${await evaluate("document.querySelector('.fm-head')?.innerText.split(String.fromCharCode(10))[0] || ''")}`);
    await key("Escape", "Escape", 27);
    await sleep(800);
    check("Esc بازبینی سریع را می‌بندد", await evaluate("document.querySelector('#focus').hidden"));
    // یادگیری از اصلاح: «… → …پور» در زبانه اصلاحات دیده می‌شود
    await click(`#nav a[data-page="dictionary"]`);
    await sleep(1200);
    await click('[data-t="__corrections"]');
    await sleep(1200);
    await shot("04-corrections");
    check("اصلاح انجام‌شده در «اصلاحات یادگرفته‌شده» ثبت شد", (await evaluate("document.querySelectorAll('#dc-table tbody tr').length")) >= 1);
    // پشتیبان‌گیری دستی
    await click(`#nav a[data-page="settings"]`);
    await sleep(1500);
    await evaluate("document.querySelector('#s-backup-now').scrollIntoView({block:'center'})");
    await sleep(300);
    await click("#s-backup-now");
    await sleep(2000);
    await shot("05-settings-backups");
    check("پشتیبان‌گیری الان", (await evaluate("document.querySelectorAll('#s-backups tbody tr').length")) >= 1);
    await click(`#nav a[data-page="review"]`);
    await sleep(800);
    await click(`#nav a[data-page="excel"]`);
    await sleep(1200);
    const hasSample = await evaluate("!!document.querySelector('#x-sample')");
    if (hasSample) {
      await click("#x-sample");
      await sleep(3000);
      check("بررسی فایل اکسل نمونه", await evaluate("!!document.querySelector('#x-save')"));
      await click("#x-save");
      const waitFor = async (sel, ms = 15000) => {
        for (let t = 0; t < ms; t += 300) { if (await evaluate(`!!document.querySelector(${JSON.stringify(sel)})`)) return true; await sleep(300); }
        return false;
      };
      check("پیش‌نمایش ثبت و دکمه «ساخت فایل خروجی» نمایش داده شد", await waitFor("#x-export"),
        await evaluate("(document.querySelector('#x-prev') || {}).innerText?.slice(0, 200) || ''"));
      await evaluate("document.querySelector('#x-export')?.scrollIntoView({block: 'center'})");
      await sleep(400);
      const rx = await click("#x-export");
      check("کلیک روی «ساخت فایل خروجی»", rx.hit, "کلیک به " + rx.top);
      check("پنجره تأیید ثبت باز شد", await waitFor("#modal-backdrop:not([hidden]) .modal-f .btn.primary", 5000));
      await click("#modal .modal-f .btn.primary");
      let exported = false;
      for (let i = 0; i < 20 && !exported; i++) { await sleep(1000); exported = (await getJSON(APP + "api/status")).records.exported >= 1; }
      check("ساخت فایل خروجی اکسل از رابط", rx.hit && exported);
      await evaluate("document.querySelector('#modal-backdrop').hidden || (document.querySelector('#modal .modal-f .btn.ghost') || {}).click?.()");
    } else {
      check("فایل اکسل نمونه (فقط در نسخه قابل‌حمل)", true, "رد شد؛ فایل نمونه در این اجرا نیست");
    }
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
