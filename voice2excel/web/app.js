/* رابط کاربری «DataVox» — بدون وابستگی خارجی، کاملاً محلی */
"use strict";

// ---------------- ابزارها ----------------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fa = (n) => String(n ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const fmtSize = (b) => (b == null ? "" : b < 1024 * 1024 ? fa((b / 1024).toFixed(0)) + " کیلوبایت" : fa((b / 1048576).toFixed(1)) + " مگابایت");
const fmtSec = (s) => (s == null ? "" : s < 60 ? fa(Math.round(s)) + " ثانیه" : fa(Math.floor(s / 60)) + ":" + fa(String(Math.round(s % 60)).padStart(2, "0")));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// کلید محرمانه همین اجرای برنامه (در صفحه گذاشته می‌شود)؛ بدون آن، فرمان‌های تغییردهنده پذیرفته نمی‌شوند
const TOKEN = document.querySelector('meta[name="v2x-token"]')?.content || "";
async function api(path, { method = "GET", body, form } = {}) {
  const opt = { method, headers: { "X-V2X-Token": TOKEN } };
  if (form) opt.body = form;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  let res;
  try { res = await fetch(path, opt); }
  catch { throw new Error("ارتباط با برنامه برقرار نشد. آیا پنجره برنامه (run.bat) باز است؟"); }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (res.status === 402 && data?.license) refreshLicense();  // دوره آزمایشی در میانه کار تمام شد: نوار وضعیت به‌روز شود
  if (!res.ok) {
    let msg = data && data.detail ? data.detail : "خطا در انجام درخواست";
    if (Array.isArray(msg)) msg = "اطلاعات ارسالی نامعتبر است.";
    throw new Error(msg);
  }
  return data;
}

/** فایلی که سرور در پاسخ یک POST می‌سازد (نمونه اکسل، پشتیبان رمزدار) دانلود می‌شود. */
async function downloadPost(path, body, filename = "") {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-V2X-Token": TOKEN }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "ساخت فایل ناموفق بود.");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob());
  a.download = filename || (res.headers.get("content-disposition") || "").match(/filename="([^"]+)"/)?.[1] || "download";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

const I = {
  play: '<svg viewBox="0 0 24 24"><path d="M7 5v14l11-7z"/></svg>',
  stop: '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
  retry: '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>',
  upload: '<svg viewBox="0 0 24 24"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5"/></svg>',
  music: '<svg viewBox="0 0 24 24"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>',
  mic: '<svg viewBox="0 0 24 24"><path d="M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3Zm-6 8a6 6 0 0 0 12 0M12 18v2.5"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
  info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
  ok: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>',
  table: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>',
  book: '<svg viewBox="0 0 24 24"><path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Z"/><path d="M5 17a3 3 0 0 1 3-3h11"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="M12 4v12M7 11l5 5 5-5M5 20h14"/></svg>',
  next: '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
  prev: '<svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  wave: '<svg viewBox="0 0 24 24"><path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 11v2"/></svg>',
  shield: '<svg viewBox="0 0 24 24"><path d="M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3Z"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16v4Z"/></svg>',
  history: '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>',
  open: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  swap: '<svg viewBox="0 0 24 24"><path d="M7 7h12l-3-3M17 17H5l3 3"/></svg>',
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>',
};

const FILE_STATUS = { queued: "در صف", processing: "در حال پردازش", done: "انجام شد", failed: "ناموفق" };
const REC_STATUS = { ready: "معتبر", review: "نیاز به بررسی", invalid: "ناقص" };
const FIELD_STATUS = { valid: "معتبر", review: "بررسی شود", missing: "گفته نشده", invalid: "نامعتبر" };
const SEG_LABEL = { name: "نام", phone: "شماره", phone_cue: "شماره", address: "آدرس", tech: "مشخصات فنی", project: "پروژه", followup: "پیگیری", note: "توضیحات" };

function chip(cls, text) { return `<span class="chip ${esc(cls)}">${esc(text)}</span>`; }
function recordChip(r) {
  if (r.exported_at) return chip("exported", "ثبت در اکسل" + (r.export_row ? ` (ردیف ${fa(r.export_row)})` : ""));
  if (r.review_state === "rejected") return chip("rejected", "ردشده");
  if (r.review_state === "approved") return chip("approved", r.approved_by === "auto" ? "آماده ثبت (خودکار)" : "تأییدشده");
  return chip(r.status, REC_STATUS[r.status] || r.status);
}

// ---------------- اعلان و مودال ----------------
/** اعلان کوتاه؛ action اختیاری: {label, onClick} مثلاً «بازگشت». */
function toast(msg, type = "", action = null) {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.setAttribute("role", type === "err" ? "alert" : "status");
  t.innerHTML = (type === "err" ? I.alert : type === "ok" ? I.ok : I.info) + `<div class="spacer">${esc(msg)}</div>`;
  if (action) {
    const b = document.createElement("button");
    b.className = "toast-action";
    b.textContent = action.label;
    b.onclick = () => { t.remove(); action.onClick(); };
    t.appendChild(b);
  }
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), action ? 8000 : type === "err" ? 7000 : 4000);
}
const toastErr = (e) => toast(e.message || String(e), "err");

let modalResolve = null;
function openModal({ title, body, actions = [], wide = false, onOpen }) {
  // پنجره قبلی که هنوز پاسخ نگرفته، بسته (انصراف) حساب می‌شود تا منتظرش برای همیشه نماند
  if (modalResolve) { const r = modalResolve; modalResolve = null; r(undefined); }
  const m = $("#modal");
  m.className = "modal" + (wide ? " wide" : "");
  m.innerHTML = `<div class="modal-h">${title}</div><div class="modal-b">${body}</div>
    <div class="modal-f">${actions.map((a, i) => `<button class="btn ${a.cls || ""}" data-mi="${i}">${a.label}</button>`).join("")}</div>`;
  $("#modal-backdrop").hidden = false;
  return new Promise((resolve) => {
    modalResolve = resolve;
    $$("[data-mi]", m).forEach((b) => b.addEventListener("click", async () => {
      const a = actions[+b.dataset.mi];
      if (a.onClick) {
        const r = await a.onClick(m);
        if (r === false) return;
        closeModal(r === undefined ? a.value : r);
      } else closeModal(a.value);
    }));
    if (onOpen) onOpen(m);
  });
}
function closeModal(v) {
  $("#modal-backdrop").hidden = true;
  if (modalResolve) { const r = modalResolve; modalResolve = null; r(v); }
}
$("#modal-backdrop").addEventListener("mousedown", (e) => { if (e.target.id === "modal-backdrop") closeModal(undefined); });
function confirmBox(title, html, okLabel = "تأیید", cls = "primary") {
  return openModal({ title, body: html, actions: [{ label: okLabel, cls, value: true }, { label: "انصراف", cls: "ghost", value: false }] });
}

// مرورگر فایل محلی (انتخاب پوشه ویس یا فایل اکسل)
async function pickPath(kind, start = "") {
  let current = start;
  let selectedFile = null;
  const render = async (m) => {
    let d;
    try { d = await api(`/api/fs?kind=${kind}&path=${encodeURIComponent(current)}`); }
    catch (e) { toastErr(e); current = ""; d = await api(`/api/fs?kind=${kind}`); }
    current = d.path;
    const items = [];
    if (d.parent !== null && d.path) items.push(`<div class="fs-item dir" data-dir="${esc(d.parent)}">${I.next}<span>.. (پوشه بالاتر)</span></div>`);
    d.dirs.forEach((x) => items.push(`<div class="fs-item dir" data-dir="${esc(x.path)}">${I.folder}<span class="ltr">${esc(x.name)}</span></div>`));
    d.files.forEach((x) => items.push(`<div class="fs-item" data-file="${esc(x.path)}">${kind === "excel" ? I.table : I.music}<span class="spacer">${esc(x.name)}</span><span class="muted small">${fmtSize(x.size)}</span></div>`));
    $(".modal-b", m).innerHTML = `<div class="stack">
      <div class="row"><span class="muted small">مسیر:</span><span class="path">${esc(d.path || "انتخاب درایو یا پوشه")}</span></div>
      <div class="fs-list">${items.join("") || '<div class="empty">پوشه خالی است</div>'}</div>
      ${kind === "audio" ? `<div class="muted small">${fa(d.files.length)} فایل صوتی در این پوشه</div>` : ""}</div>`;
    $$("[data-dir]", m).forEach((el) => el.addEventListener("click", () => { current = el.dataset.dir; selectedFile = null; render(m); }));
    $$("[data-file]", m).forEach((el) => {
      el.addEventListener("click", () => { $$(".fs-item", m).forEach((x) => x.classList.remove("sel")); el.classList.add("sel"); selectedFile = el.dataset.file; });
      el.addEventListener("dblclick", () => { selectedFile = el.dataset.file; closeModal(selectedFile); });
    });
  };
  return openModal({
    title: kind === "excel" ? "انتخاب فایل اکسل" : "انتخاب پوشه ویس‌ها",
    body: '<div class="row"><span class="spinner"></span></div>',
    wide: true,
    actions: [
      { label: kind === "excel" ? "انتخاب فایل" : "انتخاب همین پوشه", cls: "primary", onClick: () => {
        if (kind === "excel") { if (!selectedFile) { toast("یک فایل اکسل انتخاب کنید."); return false; } return selectedFile; }
        if (!current) { toast("وارد یک پوشه شوید."); return false; } return current;
      } },
      { label: "انصراف", cls: "ghost", value: null },
    ],
    onOpen: render,
  });
}

// ---------------- وضعیت سراسری ----------------
const state = { meta: null, status: null, page: "files", profile: null };

async function refreshStatus() {
  let s;
  try { s = await api("/api/status"); } catch { return; }
  const prev = state.status;
  state.status = s;
  // نسخه oldcpu: تبدیل گفتار آنلاین است (فایل اکسل و ردیف‌ها روی همین رایانه می‌مانند)
  if (s.edition === "oldcpu") $("#offline-text").textContent = "فایل‌ها و ردیف‌ها روی همین رایانه";
  const w = s.worker;
  const q = s.files.queued + s.files.processing;
  $("#nav-files").textContent = s.records.review ? fa(s.records.review) : "";
  const pill = $("#worker-pill");
  pill.className = "worker-pill" + (w.running ? " running" : w.last_error ? " error" : "");
  $("#worker-text").textContent = w.running ? (w.stopping ? "در حال توقف..." : "در حال پردازش") : w.last_error ? "متوقف (خطا)" : q ? `${fa(q)} فایل در صف` : "آماده";
  const tp = $("#top-progress");
  tp.hidden = !w.running;
  if (w.running) {
    $("#tp-name").textContent = w.current_name ? "در حال پردازش: " + w.current_name : "در حال آماده‌سازی...";
    $("#tp-pct").textContent = fa(s.progress) + "٪";
    $("#tp-bar").style.width = s.progress + "%";
  }
  renderBanners();
  const changed = !prev || prev.worker.running !== w.running || prev.files.done !== s.files.done || prev.files.failed !== s.files.failed ||
    prev.files.total !== s.files.total || prev.worker.current_id !== w.current_id || prev.records.review !== s.records.review ||
    prev.worker.model_state !== w.model_state;
  if (prev && prev.worker.running && !w.running && w.run_done > 0 && !w.last_error) notifyDone(s, w.run_done);
  if (changed) pageHooks.onStatus && pageHooks.onStatus(s, prev);
}

/** پایان پردازش صف: اعلان در برنامه، صدای کوتاه و (اگر پنجره دیده نمی‌شود) اعلان ویندوز. */
function notifyDone(s, n) {
  const msg = `پردازش ${fa(n)} ویس تمام شد${s.records.review ? `؛ ${fa(s.records.review)} ردیف منتظر بررسی است` : ""}.`;
  toast(msg, "ok", s.records.review && state.page !== "file" ? { label: "فایل‌های من", onClick: () => { location.hash = "#/files"; } } : null);
  if (localStorage.getItem("v2x.sound") !== "0") chime();
  if (document.hidden && "Notification" in window && Notification.permission === "granted") {
    try { new Notification("DataVox", { body: msg, lang: "fa", dir: "rtl" }); } catch { }
  }
}
function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [[880, 0], [1320, 0.16]].forEach(([f, t]) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
      g.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.35);
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.4);
    });
    setTimeout(() => ctx.close(), 1000);
  } catch { }
}

function renderBanners() {
  const s = state.status;
  if (!s) return;
  const out = [];
  if (!s.model.available) {
    out.push(`<div class="alert err">${I.alert}<div class="alert-body"><b>مدل تبدیل گفتار نصب نیست</b>مدل «${esc(s.model.name)}» در پوشه models پیدا نشد. یک بار با اینترنت فایل download_model.bat را اجرا کنید یا از تنظیمات دریافتش کنید.</div><a class="btn sm" href="#/settings">تنظیمات</a></div>`);
  }
  if (s.worker.last_error && !s.worker.running) {
    out.push(`<div class="alert err">${I.alert}<div class="alert-body"><b>پردازش متوقف شد</b>${esc(s.worker.last_error)}</div></div>`);
  }
  const L = state.lic;
  if (L && state.page !== "activate") {
    const T = L.trial;
    const lb = state.page === "files" ? " live-bg" : "";
    if (L.mode === "trial") out.push(`<div class="alert info${lb}">${I.info}<div class="alert-body"><b>نسخه آزمایشی</b>${fa(T.days_left)} روز و ${fa(T.voices_left)} ویس مانده است؛ هرکدام زودتر تمام شود.</div><a class="btn sm" href="#/activate">فعال‌سازی</a></div>`);
    else if (L.mode === "expired") out.push(L.lapsed
      ? `<div class="alert warn${lb}">${I.alert}<div class="alert-body"><b>اشتراک شما تمام شده است</b>برای پردازش ویس تازه، اشتراک را تمدید کنید. ردیف‌های قبلی، ثبت در اکسل و پشتیبان در دسترس‌اند.</div><a class="btn sm primary" href="#/activate">تمدید اشتراک</a></div>`
      : `<div class="alert warn${lb}">${I.alert}<div class="alert-body"><b>دوره آزمایشی تمام شد</b>برای پردازش ویس تازه، برنامه را فعال کنید. ردیف‌های قبلی، ثبت در اکسل و پشتیبان در دسترس‌اند.</div><a class="btn sm primary" href="#/activate">فعال‌سازی</a></div>`);
    else if (L.mode === "licensed" && L.days_left != null && L.days_left <= 15) out.push(`<div class="alert warn${lb}">${I.alert}<div class="alert-body"><b>اشتراک شما ${L.days_left <= 0 ? "امروز" : `تا ${fa(L.days_left)} روز دیگر`} تمام می‌شود</b>برای ادامه کار بدون وقفه، اشتراک را تمدید کنید.</div><a class="btn sm" href="#/activate">تمدید اشتراک</a></div>`);
  }
  $("#banners").innerHTML = out.join("");
}

// ---------------- مسیریابی ----------------
const PAGES = {
  files: { title: "فایل‌های من", sub: "هر فایل اکسل، ویس‌ها و ردیف‌های خودش را دارد", render: renderFiles },
  file: { title: "میز کار فایل", sub: "افزودن ویس، بررسی ردیف‌ها و ثبت در همین فایل", render: renderFile },
  history: { title: "تاریخچه ثبت‌ها", sub: "هر بار که ردیف‌ها در یک فایل اکسل ثبت شدند؛ با امکان باز کردن و برگرداندن", render: renderHistory },
  templates: { title: "تنظیمات فایل", sub: "هر ستون چه اطلاعاتی بگیرد، شکل نوشتن مقادیر و ظاهر", render: renderTemplates, parent: "files" },
  dictionary: { title: "واژه‌نامه", sub: "نام‌های تأییدشده مهندس‌ها، پروژه‌ها و خیابان‌ها", render: renderDictionary, parent: "settings" },
  settings: { title: "تنظیمات", sub: "ثبت در اکسل، واژه‌نامه، پوشه ورودی، پشتیبان‌گیری و نگهداری", render: renderSettings },
  activate: { title: "اشتراک و پشتیبانی", sub: "وضعیت اشتراک، تماس با فروشنده و وارد کردن مجوز", render: (el) => renderActivation(el) },
};
let pageHooks = {};
let routeSeq = 0;
// فقط صفحه‌ای که هنوز نمایش داده می‌شود قلاب به‌روزرسانی ثبت می‌کند (جلوگیری از تداخل صفحه قبلی)
function setHook(seq, fn) { if (seq === routeSeq) pageHooks.onStatus = fn; }

/** مسیر صفحه: [{label, href}]؛ آخرین مورد صفحه فعلی است (بدون پیوند). کمتر از دو مورد = پنهان. */
function setCrumbs(items, seq = routeSeq) {
  const nav = $("#crumbs");
  if (!nav || seq !== routeSeq) return;
  nav.hidden = items.length < 2;
  nav.innerHTML = items.map((c, i) => i === items.length - 1
    ? `<span aria-current="page">${esc(c.label)}</span>`
    : `<a href="${c.href}">${esc(c.label)}</a><span class="sep" aria-hidden="true">‹</span>`).join("");
}

function route() {
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "files";
  const p = PAGES[name] || PAGES.files;
  state.page = PAGES[name] ? name : "files";
  const navPage = state.page === "file" ? "files" : p.parent || state.page;
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === navPage));
  renderBanners();
  $("#page-title").textContent = p.title;
  $("#tb-page").textContent = p.title;
  $("#page-sub").textContent = p.sub;
  pageHooks = {};
  reviewState.reload = reviewState.updateRow = null;  // قلاب‌های صفحه بررسیِ قبلی به DOM حذف‌شده اشاره دارند
  routeSeq++;
  // صفحه‌های زیرمجموعه (واژه‌نامه ← تنظیمات)؛ مسیر صفحه‌های هر فایل را خود آن صفحه پس از خواندن نام فایل می‌سازد
  setCrumbs(p.parent && state.page !== "templates" ? [{ label: PAGES[p.parent].title, href: `#/${p.parent}` }, { label: p.title }] : []);
  closeDrawer();
  $("#page").innerHTML = '<div class="row"><span class="spinner"></span></div>';
  p.render($("#page")).catch(toastErr);
}
window.addEventListener("hashchange", route);
window.addEventListener("focus", () => pageHooks.onFocus && pageHooks.onFocus());

// ================= فایل‌های من =================
/** صفحه اول: هر فایل اکسل یک کارت. ویس‌ها در «میز کار» همان فایل اضافه می‌شوند و همیشه مال همان فایل‌اند. */
const filesState = { dests: [], orphans: [], active: "" };

async function loadDests() {
  const d = await api("/api/dests");
  Object.assign(filesState, d);
  return d;
}
const destLabel = (d) => (d ? (d.mode === "new" ? d.title : d.file || d.title) : "");
const fileHref = (name) => `#/file?f=${encodeURIComponent(name)}`;
/** «امروز»، «دیروز» یا «۳ روز پیش» از زمان ISO */
function agoText(iso) {
  if (!iso) return "";
  const day = (t) => Math.floor(new Date(t).setHours(0, 0, 0, 0) / 86400000);
  const n = day(Date.now()) - day(iso.slice(0, 10) + "T00:00:00");
  return n <= 0 ? "امروز" : n === 1 ? "دیروز" : `${fa(n)} روز پیش`;
}
/** وضعیت ویس‌ها و ردیف‌های یک فایل، هر کدام یک برچسب رنگی */
function destParts(d) {
  const p = [];
  if (d.converting) p.push(["info", `${fa(d.converting)} ویس در حال تبدیل`]);
  if (d.failed) p.push(["err", `${fa(d.failed)} ویس ناموفق`]);
  if (d.review) p.push(["warn", `${fa(d.review)} ردیف نیاز به بررسی`]);
  if (d.ready) p.push(["ok", `${fa(d.ready)} ردیف آماده ثبت`]);
  if (d.no_rows) p.push(["missing", `${fa(d.no_rows)} ویس بدون ردیف`]);
  if (d.pending_apply) p.push(["warn", `${fa(d.pending_apply)} ثبت در کپی، منتظر اعمال روی فایل`]);
  return p;
}
function fileSub(d) {
  if (d.missing) return `<span class="err-text">فایل در این مسیر پیدا نشد</span>`;
  if (!d.configured) return `<span class="warn-text">ستون‌ها هنوز تأیید نشده‌اند</span>`;
  const r = d.file_rows;
  return [r ? (r.exists ? `${fa(r.rows)} ردیف` : "هنوز ساخته نشده") : "", d.last_commit ? `آخرین ثبت: ${agoText(d.last_commit.created_at)}` : ""]
    .filter(Boolean).join(" · ");
}
function fileCard(d) {
  const parts = destParts(d);
  return `<a class="file-card ${parts.length ? "busy" : ""}" href="${fileHref(d.name)}" data-file="${esc(d.name)}">
    <div class="fc-top"><span class="fc-ico">${d.mode === "new" ? I.file : I.table}</span>
      <div class="fc-names"><b class="fc-title">${fname(destLabel(d))}</b><span class="small muted">${fileSub(d)}</span></div></div>
    <div class="fc-status">${parts.length ? parts.map(([c, t]) => chip(c, t)).join("")
      : `<span class="small muted">${d.written ? `${I.check} همه ردیف‌های ویس‌ها ثبت شده‌اند` : "هنوز ویسی به این فایل اضافه نشده"}</span>`}</div>
    ${d.auto ? `<div class="fc-auto small">${I.mic} ویس‌های گوشی و پوشه ورودی به این فایل می‌آیند</div>` : ""}
    ${d.review || d.ready ? `<div class="fc-act">${d.review ? `<span class="btn sm primary">${I.eye} بررسی ${fa(d.review)} ردیف</span>` : ""}${d.ready
      ? `<span class="btn sm ${d.review ? "" : "primary"}">${I.table} ثبت ${fa(d.ready)} ردیف</span>` : ""}</div>` : ""}</a>`;
}

async function renderFiles(el) {
  const seq = routeSeq;
  const draw = async () => {
    const d = await loadDests();
    if (seq !== routeSeq) return;
    if (!d.dests.length) return renderWelcome(el);
    el.innerHTML = `${orphansHtml(d)}<div class="file-grid">${d.dests.map(fileCard).join("")}
      <button class="file-card file-add" id="fl-add">${I.plus}<b>افزودن فایل اکسل</b><span>فایلی که دارید، یا یک فایل تازه</span></button></div>`;
    $("#fl-add").onclick = addFileFlow;
    bindOrphans(el, d);
  };
  await draw();
  setHook(seq, () => draw().catch(() => {}));
}

/** سه گام راه‌اندازی؛ done: تعداد گام‌های انجام‌شده */
function setupSteps(done) {
  const steps = ["فایل اکسل را انتخاب کنید", "ستون‌ها را تأیید کنید", "اولین ویس را اضافه کنید"];
  return `<ol class="setup-steps">${steps.map((t, i) => `<li class="${i < done ? "done" : i === done ? "now" : ""}"><span class="ss-n">${i < done ? I.check : fa(i + 1)}</span>${t}</li>`).join("")}</ol>`;
}

/** اجرای اول (هنوز هیچ فایلی در فهرست نیست): فقط یک سؤال — ردیف‌ها به کدام فایل اکسل بروند؟ */
function renderWelcome(el) {
  el.innerHTML = `<div class="card welcome live-bg"><div class="card-b stack">
      <div><h2 style="margin:0 0 4px">به DataVox خوش آمدید</h2>
        <div class="muted">در سه گام آماده کار می‌شوید. ویس‌های بازدید به متن تبدیل و به‌صورت ردیف به فایل اکسل شما اضافه می‌شوند.</div></div>
      ${setupSteps(0)}
      <div><b>گام ۱ از ۳: ردیف‌ها به کدام فایل اکسل اضافه شوند؟</b></div>
      ${destChoicesHtml()}
      ${state.meta?.samples?.excel ? `<div class="row small"><span class="muted">فایل اکسلی دم دست ندارید؟</span><button class="btn sm ghost" id="wl-sample">${I.table} امتحان با فایل اکسل نمونه</button></div>` : ""}
      <div class="small muted">${I.info} پیش از شروع، <a href="/static/recording-guide.html" target="_blank">راهنمای ضبط ویس</a> را برای بازاریاب‌ها چاپ کنید تا ویس‌ها دقیق‌تر خوانده شوند.</div></div></div>`;
  $("#wl-sample", el)?.addEventListener("click", () => addExistingFile("", "", true, state.meta.samples.excel));
  $$("[data-choice]", el).forEach((b) => b.onclick = () => {
    if (b.dataset.choice === "append") return addExistingFile("", "", true);
    if (b.dataset.choice === "new") return addNewFile();
    importTemplateFile();
  });
}

/** ویس‌هایی که فایلشان دیگر در فهرست نیست: با یک انتخاب به فایل دیگری منتقل می‌شوند */
function orphansHtml(d) {
  if (!d.orphans.length || !d.dests.length) return "";
  const n = d.orphans.reduce((a, o) => a + o.voices, 0);
  return `<div class="alert warn" style="margin-bottom:18px">${I.alert}<div class="alert-body"><b>${fa(n)} ویس به فایلی وصل‌اند که در فهرست نیست</b>
      آن‌ها را به یکی از فایل‌ها منتقل کنید تا بشود ردیف‌هایشان را ثبت کرد.</div>
    <select class="select sm" id="fl-orphan-to">${d.dests.map((x) => `<option value="${esc(x.name)}">${esc(destLabel(x))}</option>`).join("")}</select>
    <button class="btn sm primary" id="fl-orphan-go">انتقال</button></div>`;
}
function bindOrphans(el, d) {
  $("#fl-orphan-go", el)?.addEventListener("click", async () => {
    const to = $("#fl-orphan-to").value;
    try {
      let n = 0;
      for (const o of d.orphans) n += (await api(`/api/dests/${encodeURIComponent(to)}/adopt`, { method: "POST", body: { source: o.dest } })).moved;
      toast(`${fa(n)} ویس منتقل شد.`, "ok");
      refreshStatus();
    } catch (e) { toastErr(e); }
  });
}

/** افزودن فایل به فهرست: فایلی که کاربر دارد (انتخاب و تأیید ستون‌ها) یا فایل تازه */
async function addFileFlow() {
  const choice = await openModal({ title: "افزودن فایل اکسل", body: destChoicesHtml(), wide: true,
    actions: [{ label: "انصراف", cls: "ghost", value: null }],
    onOpen: (m) => $$("[data-choice]", m).forEach((b) => b.onclick = () => closeModal(b.dataset.choice)) });
  if (choice === "append") return addExistingFile();
  if (choice === "new") return addNewFile();
  if (choice === "import") return importTemplateFile();
}

/** انتخاب فایل اکسل موجود ← تأیید ستون‌ها ← باز شدن میز کار همان فایل. name: عوض کردن فایلِ یکی از فایل‌های فهرست */
async function addExistingFile(name = "", start = "", firstRun = false, given = "") {
  const path = given || await pickPath("excel", start);
  if (!path) return null;
  let res;
  try { res = await api("/api/excel/inspect", { method: "POST", body: { path, name } }); }
  catch (e) { toastErr(e); return null; }
  const block = (res.report.risks || []).filter((r) => r.level === "block");
  if (block.length || !res.profile) {
    await openModal({ title: "این فایل قابل استفاده نیست", body: `<ul class="reasons invalid">${(block.length ? block.map((r) => r.message) : ["در این فایل سرستونی پیدا نشد."]).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`,
      actions: [{ label: "متوجه شدم", cls: "primary" }] });
    return null;
  }
  if (res.profile.confirmed && !name) {
    toast(`«${res.report.name}» از قبل در فهرست هست.`, "ok");
    location.hash = fileHref(res.profile.name);
    return res.profile;
  }
  const saved = await confirmColumns(res.profile, res.report,
    firstRun ? { title: `گام ۲ از ۳: ستون‌های «${esc(res.report.name)}»`, okLabel: "تأیید و رفتن به گام آخر" } : {});
  if (saved) location.hash = fileHref(saved.name) + (firstRun ? "&first=1" : "");
  return saved;
}

/** تأیید ستون‌ها: برنامه برای هر ستون حدس زده چه اطلاعاتی بگیرد؛ کاربر فقط بررسی و تأیید می‌کند */
async function confirmColumns(profile, report, { title = "", okLabel = "تأیید ستون‌ها" } = {}) {
  const draft = JSON.parse(JSON.stringify(profile));
  const fields = state.meta.fields.concat(state.meta.computed).concat([{ key: "followup", label: "پیگیری (اقدام + تاریخ)" }]);
  const render = (m) => {
    const sheet = report.sheets.find((s) => s.name === draft.sheet) || report.sheets[0];
    const prot = new Set(draft.protected || []);
    const cur = (col) => draft.columns[col] || (prot.has(col) ? "__protect" : "");
    const entries = Object.entries(sheet.headers);
    $(".modal-b", m).innerHTML = `<div class="stack">
      <div class="small">برنامه از روی عنوان ستون‌های «${fname(report.name)}» حدس زده هر ستون چه اطلاعاتی از ویس بگیرد. بررسی کنید و هرجا لازم بود عوض کنید.</div>
      ${report.sheets.length > 1 ? `<div class="row"><div class="field"><label>شیت</label><select class="select" id="cc-sheet">${report.sheets.map((s) => `<option ${s.name === sheet.name ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></div>
        <span class="small muted">${fa(sheet.data_rows)} ردیف داده</span></div>` : ""}
      <div class="table-wrap cc-table"><table class="table"><thead><tr><th>ستون</th><th>عنوان در فایل</th><th>چه اطلاعاتی نوشته شود</th></tr></thead><tbody>
        ${entries.map(([col, h]) => `<tr class="${cur(col) ? "" : "map-empty"}"><td><b class="ltr">${esc(col)}</b></td><td>${esc(h).replace(/\n/g, " ")}</td>
          <td><select class="select map-select" data-col="${esc(col)}">
            <option value="" ${!cur(col) ? "selected" : ""}>— خالی بماند —</option>
            <option value="__protect" ${cur(col) === "__protect" ? "selected" : ""}>🔒 دست نخورد (مثلاً ستونی که همکاران پر می‌کنند)</option>
            <optgroup label="اطلاعات ویس">${fields.map((f) => `<option value="${f.key}" ${cur(col) === f.key ? "selected" : ""}>${esc(f.label)}</option>`).join("")}</optgroup></select></td></tr>`).join("")}
      </tbody></table></div>
      <div class="small muted">ردیف‌های قبلی فایل هرگز تغییر نمی‌کنند؛ ردیف‌های تازه زیر آخرین ردیف (ردیف ${fa(sheet.last_data_row)}) اضافه می‌شوند.</div></div>`;
    $$("[data-col]", m).forEach((s) => s.onchange = () => {
      const col = s.dataset.col;
      delete draft.columns[col];
      draft.protected = (draft.protected || []).filter((c) => c !== col);
      if (s.value === "__protect") draft.protected.push(col);
      else if (s.value) {
        // هر اطلاعات فقط در یک ستون: ستون قبلی همان اطلاعات خالی می‌شود
        for (const [c, f] of Object.entries(draft.columns)) if (f === s.value) delete draft.columns[c];
        draft.columns[col] = s.value;
      }
      render(m);
    });
    $("#cc-sheet", m)?.addEventListener("change", (e) => {
      const s = report.sheets.find((x) => x.name === e.target.value);
      Object.assign(draft, { sheet: s.name, header_row: s.header_row, headers: s.headers, columns: {}, protected: [] });
      render(m);
    });
  };
  return openModal({ title: title || `ستون‌های «${esc(report.name)}»`, wide: true, body: "", onOpen: render,
    actions: [{ label: `${I.check} ${okLabel}`, cls: "primary", onClick: async () => {
      if (!Object.keys(draft.columns).length) { toast("دست‌کم یک ستون باید اطلاعاتی بگیرد.", "err"); return false; }
      try {
        const saved = (await api("/api/excel/profile", { method: "PUT", body: draft })).profile;
        // واژه‌نامه از نام‌ها و خیابان‌های همین فایل پر می‌شود تا املای درست پیشنهاد شود
        api(`/api/dictionary/seed-from-excel?name=${encodeURIComponent(saved.name)}`, { method: "POST" }).then((sd) => {
          if (sd.added?.engineer || sd.added?.street) toast(`واژه‌نامه پر شد: ${fa(sd.added.engineer)} نام و ${fa(sd.added.street)} خیابان از همین فایل.`, "ok");
        }).catch(() => {});
        await refreshStatus();
        return saved;
      } catch (e) { toastErr(e); return false; }
    } }, { label: "انصراف", cls: "ghost", value: null }] });
}

async function addNewFile() {
  const title = await openModal({ title: "فایل اکسل تازه", body: `<div class="field"><label>نام فایل</label><input class="input" id="m-in" placeholder="مثلاً گزارش مدیر"></div>
      <div class="small muted" style="margin-top:8px">در گام بعد ستون‌ها، ظاهر و پوشه فایل را می‌چینید.</div>`,
    actions: [{ label: "ساخت", cls: "primary", onClick: (m) => $("#m-in", m).value.trim() || false }, { label: "انصراف", cls: "ghost", value: null }],
    onOpen: (m) => { const i = $("#m-in", m); setTimeout(() => i.focus(), 50); i.onkeydown = (e) => { if (e.key === "Enter") $('[data-mi="0"]', m).click(); }; } });
  if (!title) return;
  try {
    const { name } = await api("/api/templates", { method: "POST", body: { title } });
    toast("فایل تازه به فهرست اضافه شد؛ ستون‌ها و پوشه‌اش را بچینید و ذخیره کنید.", "ok");
    location.hash = `#/templates?dest=${encodeURIComponent(name)}&tab=columns`;
  } catch (e) { toastErr(e); }
}

function importTemplateFile() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".json";
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f, f.name);
    try {
      const { name } = await api("/api/templates/import", { method: "POST", form: fd });
      toast("تنظیمات فایل وارد شد؛ پوشه فایل را بررسی و ذخیره کنید.", "ok");
      location.hash = `#/templates?dest=${encodeURIComponent(name)}&tab=output`;
    } catch (e) { toastErr(e); }
  };
  inp.click();
}

// ================= میز کار یک فایل =================
/** همه کار یک فایل در یک صفحه: افزودن ویس، وضعیت ویس‌ها، بررسی ردیف‌ها و ثبت. */
const fileState = { name: "", info: null, lastCommit: null, filter: "all", showAll: false, check: null };
/** سرنوشت هر ویس: [کلاس رنگ، برچسب] */
const STAGE = {
  queued: ["queued", "در صف تبدیل"], processing: ["processing", "در حال تبدیل…"], failed: ["failed", "تبدیل نشد"],
  no_rows: ["missing", "ردیفی پیدا نشد"], review: ["review", "نیاز به بررسی"], ready: ["ready", "آماده ثبت"],
  written: ["exported", "ثبت شد"], rejected: ["rejected", "رد شد"],
};
/** ردیف‌هایی که کاربر توضیحشان را باز کرده (پس از به‌روز شدن فهرست باز بمانند) */
const openNotes = new Set();
const STAGE_TABS = [["all", "همه", null], ["work", "در حال تبدیل", ["queued", "processing"]], ["review", "نیاز به بررسی", ["review"]],
  ["ready", "آماده ثبت", ["ready"]], ["written", "ثبت شد", ["written"]], ["problem", "مشکل‌دار", ["failed", "no_rows"]], ["rejected", "رد شده", ["rejected"]]];

async function renderFile(el) {
  const seq = routeSeq;
  const name = new URLSearchParams(location.hash.split("?")[1] || "").get("f") || "";
  let info;
  try { info = await api(`/api/dests/${encodeURIComponent(name)}`); }
  catch (e) { toastErr(e); location.hash = "#/files"; return; }
  if (seq !== routeSeq) return;
  if (fileState.name !== name) Object.assign(fileState, { lastCommit: null, check: null });
  Object.assign(fileState, { name, info });
  $("#page-title").textContent = destLabel(info);
  $("#tb-page").textContent = destLabel(info);
  setCrumbs([{ label: PAGES.files.title, href: "#/files" }, { label: destLabel(info) }], seq);
  api("/api/model/warmup", { method: "POST" }).catch(() => {});
  const firstRun = new URLSearchParams(location.hash.split("?")[1] || "").get("first") === "1" && !info.voices;
  el.innerHTML = `<div id="fw-head" class="fw-head"></div><div class="fw">
    ${firstRun ? `<div class="card welcome"><div class="card-b stack">${setupSteps(2)}
      <div><b>گام ۳ از ۳: اولین ویس را اضافه کنید.</b> <span class="muted">ویس‌ها را در کادر «افزودن ویس» رها کنید؛ تبدیل خودکار شروع می‌شود و ردیف‌ها برای بررسی اینجا می‌آیند.</span></div></div></div>` : ""}
    <div id="fw-next"></div>
    <section class="card" id="fw-add"></section>
    <section class="card" id="fw-review"><div class="card-h"><h2>${I.eye} ردیف‌هایی که نیاز به بررسی دارند</h2><div class="row" id="fw-rv-actions"></div></div><div id="fw-rv"></div></section>
    <section class="card brief" id="fw-commit"><div class="card-h"><h2>${I.table} ثبت در فایل</h2></div><div class="card-b" id="fw-cm"></div></section>
    <section class="card" id="fw-voices"><div class="card-h"><h2>${I.music} ویس‌های این فایل</h2><div class="tabs sm" id="fw-v-tabs"></div></div><div id="fw-v"></div></section></div>`;
  drawHead();
  drawNext();
  drawAdd();
  drawCommit();
  loadCheck();
  await Promise.all([drawReview(), drawVoices()]);

  async function reloadInfo() {
    try { fileState.info = info = await api(`/api/dests/${encodeURIComponent(name)}`); } catch { }
  }
  function drawHead() {
    fileBar($("#fw-head"), info, () => reloadInfo().then(drawHead));
  }

  /** وضعیت فایل پیش از ثبت (باز بودن در Excel، تغییر ستون‌ها، …)؛ پس از هر تغییر وضعیت و برگشتن به پنجره دوباره خوانده می‌شود */
  async function loadCheck() {
    try { fileState.check = await api(`/api/dests/${encodeURIComponent(name)}/check`); } catch { return; }
    if (seq !== routeSeq) return;
    drawNext(); drawCommit();
  }
  function checkBlock() { return (fileState.check?.items || []).find((x) => x.level === "block"); }
  function fixBtn(b, cls = "btn") {
    return b?.fix === "columns" ? `<a class="${cls}" href="#/templates?dest=${encodeURIComponent(name)}">${I.edit} تأیید دوباره ستون‌ها</a>`
      : b?.fix === "file" ? `<button class="${cls}" data-refile>${I.folder} انتخاب دوباره فایل</button>` : `<button class="${cls}" data-recheck>${I.retry} دوباره بررسی کن</button>`;
  }
  function bindFix(box) {
    $$("[data-recheck]", box).forEach((b) => b.onclick = loadCheck);
    $$("[data-refile]", box).forEach((b) => b.onclick = async () => { if (await addExistingFile(name)) { await reloadInfo(); loadCheck(); drawHead(); } });
  }

  /** گام بعد: فقط یک دکمه اصلی در صفحه، بسته به اینکه کار در چه مرحله‌ای است */
  function drawNext() {
    const box = $("#fw-next");
    if (!box || seq !== routeSeq) return;
    const w = state.status?.worker || {};
    let icon = I.info, text, btn = "";
    if (!info.configured) {
      text = info.missing ? "فایل اکسل در مسیرش پیدا نشد؛ از «تنظیمات فایل» دوباره انتخابش کنید." : "اول ستون‌های این فایل را تأیید کنید تا بشود ردیف‌ها را در آن ثبت کرد.";
      btn = `<a class="btn primary lg" href="#/templates?dest=${encodeURIComponent(name)}">${I.edit} ${info.missing ? "انتخاب دوباره فایل" : "تأیید ستون‌ها"}</a>`;
    } else if (info.review) {
      icon = I.eye;
      text = `${fa(info.review)} ردیف منتظر نگاه شماست. هر ردیف را با ویس مقایسه کنید و «درست است» بزنید.`;
      btn = `<button class="btn primary lg" id="fw-next-go">${I.eye} بررسی ${fa(info.review)} ردیف</button>`;
    } else if (info.ready && checkBlock()) {
      icon = I.alert;
      text = `${fa(info.ready)} ردیف آماده است، ولی فعلاً ثبت نمی‌شود: ${esc(checkBlock().text)}`;
      btn = fixBtn(checkBlock(), "btn primary lg");
    } else if (info.ready) {
      icon = I.table;
      text = `${fa(info.ready)} ردیف آماده است.${info.converting ? ` (${fa(info.converting)} ویس دیگر هنوز در حال تبدیل است.)` : ""}`;
      btn = `<button class="btn primary lg" id="fw-next-go">${I.table} ثبت ${fa(info.ready)} ردیف در «${esc(destLabel(info))}»</button>`;
    } else if (info.converting) {
      icon = `<span class="spinner"></span>`;
      text = `${fa(info.converting)} ویس در حال تبدیل به متن است${w.running ? "" : " (تبدیل متوقف است)"}. پس از تبدیل، ردیف‌ها اینجا آماده بررسی می‌شوند.`;
      if (!w.running) btn = `<button class="btn primary lg" id="fw-next-go">${I.play} ادامه تبدیل</button>`;
    } else {
      icon = I.ok;
      text = info.voices ? "همه ویس‌های این فایل تعیین تکلیف شده‌اند. ویس‌های تازه را اضافه کنید." : "برای شروع، ویس‌های بازدید را به این فایل اضافه کنید.";
      btn = `<button class="btn primary lg" id="fw-next-go">${I.upload} افزودن ویس</button>`;
    }
    box.innerHTML = `<div class="next-step ${icon === I.alert ? "warn" : ""}"><span class="ns-ico">${icon}</span><div class="ns-text"><span class="small muted">گام بعد</span><b>${text}</b></div>${btn}</div>`;
    bindFix(box);
    arrange();
    $("#fw-next-go")?.addEventListener("click", async (e) => {
      if (info.review) {
        const { records } = await api(`/api/records?filter=review&dest=${encodeURIComponent(name)}`);
        return openFocus(records.map((r) => r.id));
      }
      if (info.ready) return doCommit(e.currentTarget);
      if (info.converting) return startQueue();
      $("#fw-files").click();
    });
  }

  /** ترتیب بخش‌ها بر اساس کار فعلی: کاری که الان باید انجام شود بالا، «افزودن ویس» در آن حالت باریک.
   *  آماده ثبت: خود بخش «ثبت در فایل» جای «گام بعد» می‌نشیند تا فقط یک دکمه اصلی در صفحه باشد. */
  function arrange() {
    const fw = $(".fw", el);
    if (!fw || seq !== routeSeq) return;
    const commitFirst = info.configured && !info.review && (info.ready > 0 || !!fileState.lastCommit);
    const order = info.review ? ["fw-next", "fw-review", "fw-add", "fw-commit", "fw-voices"]
      : commitFirst ? ["fw-next", "fw-commit", "fw-add", "fw-review", "fw-voices"]
      : ["fw-next", "fw-add", "fw-review", "fw-commit", "fw-voices"];
    order.forEach((id) => { const s = $("#" + id, fw); if (s) fw.appendChild(s); });
    $("#fw-next").hidden = info.configured && !info.review && info.ready > 0;
    $("#fw-add")?.classList.toggle("compact", !!info.review || commitFirst);
    $("#fw-commit")?.classList.toggle("focus", info.configured && !info.review && info.ready > 0);
    $("#fw-commit")?.classList.toggle("live-bg", info.configured && !info.review && info.ready > 0 && !info.converting);
  }

  function drawAdd() {
    const exts = (state.meta?.audio_extensions || []).join(",");
    $("#fw-add").innerHTML = `<div class="card-h"><h2>${I.upload} افزودن ویس</h2>
        <label class="t-date small muted">تاریخ بازدید <input class="input sm ltr" id="fw-date" value="${esc(state.status?.today || "")}"></label></div>
      <div class="card-b stack"><div class="dropzone slim" id="fw-dz"><div class="dz-ico">${I.upload}</div>
        <div><b>ویس‌ها را اینجا رها کنید</b> یا <button class="btn sm" id="fw-pick">انتخاب فایل</button> <button class="btn sm ghost" id="fw-pickdir">انتخاب پوشه</button>
          <div class="muted small">ویس‌ها فقط به «${fname(destLabel(info))}» اضافه می‌شوند و تبدیل به متن خودکار شروع می‌شود. اگر نام فایل ویس تاریخ داشته باشد (مثل ویس واتساپ)، همان تاریخ ثبت می‌شود.</div></div>
        <input type="file" id="fw-files" multiple accept="${esc(exts)},audio/*" hidden><input type="file" id="fw-dir" webkitdirectory multiple hidden></div>
        ${!info.voices && state.meta?.samples?.voices ? `<div class="row small"><span class="muted">ویسی برای امتحان ندارید؟</span><button class="btn sm ghost" id="fw-samples">${I.play} امتحان با ${fa(state.meta.samples.voices)} ویس نمونه</button></div>` : ""}
        <div id="fw-progress"></div></div>`;
    const dz = $("#fw-dz");
    $("#fw-pick").onclick = () => $("#fw-files").click();
    $("#fw-pickdir").onclick = () => $("#fw-dir").click();
    $("#fw-files").onchange = (e) => { add(e.target.files); e.target.value = ""; };
    $("#fw-dir").onchange = (e) => { add(e.target.files); e.target.value = ""; };
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("over"));
    dz.addEventListener("drop", async (e) => { e.preventDefault(); dz.classList.remove("over"); add(await droppedFiles(e)); });
    $("#fw-samples")?.addEventListener("click", async () => {
      try { reportUpload((await api(`/api/samples/import?dest=${encodeURIComponent(name)}`, { method: "POST" })).results); await startQueue(); }
      catch (e) { toastErr(e); }
      await refreshStatus();
    });
    drawProgress();
  }
  async function add(list) {
    const files = audioOnly(list);
    if (!files.length) return;
    // یک دسته در هر لحظه: دسته بعدی پس از پایان بررسی و آپلود دسته قبلی شروع می‌شود
    const prev = uploadQueue;
    let done;
    uploadQueue = new Promise((r) => { done = r; });
    await prev;
    try { await addOne(files); } finally { done(); }
  }
  async function addOne(files) {
    $("#fw-progress").innerHTML = `<div class="muted small"><span class="spinner"></span> بررسی ${fa(files.length)} ویس...</div>`;
    const plan = await planUploads(files, name);
    if (!plan) { drawProgress(); return; }  // کاربر پنجره پرسش را بست
    $("#fw-progress").innerHTML = `<div class="progress"><div class="progress-bar" id="fw-up-bar"></div></div><div class="muted small">در حال افزودن ${fa(plan.upload.length + plan.reuse.length)} ویس...</div>`;
    try {
      const results = plan.upload.length
        ? await uploadAudio(plan.upload, $("#fw-date").value.trim(), true, (p) => { const b = $("#fw-up-bar"); if (b) b.style.width = p + "%"; }, name) : [];
      for (const r of plan.reuse) {
        try { results.push(await api(`/api/files/${r.id}/reuse`, { method: "POST", body: { dest: name } })); }
        catch (e) { results.push({ name: r.name, result: "error", message: e.message }); }
      }
      plan.skipped.forEach((x) => results.push({ name: x.name, result: "skipped" }));
      reportUpload(results);
      if (results.some((r) => r.result === "added")) await startQueue();
    } catch (e) { toastErr(e); }
    await refreshStatus();
    await reloadInfo();
    drawProgress();
  }
  function drawProgress() {
    const s = state.status, box = $("#fw-progress");
    if (!s || seq !== routeSeq || !box) return;
    const w = s.worker, mine = info.converting;
    const parts = [];
    if (mine && w.running) {
      parts.push(`<div class="row between small"><span>در حال تبدیل: <b>${esc(w.current_name || "...")}</b> <span class="muted">(${fa(mine)} ویس این فایل در صف)</span></span>
          <button class="btn sm ghost" id="fw-stop">${I.stop} توقف</button></div>
        <div class="progress"><div class="progress-bar" style="width:${s.progress}%"></div></div>`);
    } else if (mine) {
      parts.push(`<div class="row between small"><span>${fa(mine)} ویس منتظر تبدیل</span><button class="btn sm" id="fw-start">${I.play} شروع تبدیل</button></div>`);
    }
    if (mine && w.model_state === "loading") parts.push(`<div class="row small">${modelChip(w.model_state, s.model.available)}</div>`);
    if (info.failed && !w.running) parts.push(`<div class="row small err-text">${I.alert} ${fa(info.failed)} ویس تبدیل نشد.
      <button class="btn sm" id="fw-retry">${I.retry} تلاش دوباره</button></div>`);
    box.innerHTML = parts.join("");
    $("#fw-stop")?.addEventListener("click", stopQueue);
    $("#fw-start")?.addEventListener("click", startQueue);
    $("#fw-retry")?.addEventListener("click", async () => {
      try { await api("/api/files/retry-failed", { method: "POST" }); await startQueue(); } catch (e) { toastErr(e); }
    });
  }

  /** جدول «ویس ← ردیف»: هر ویس یک خط با سرنوشتش؛ پس از ثبت، شماره ردیف‌ها در اکسل */
  async function drawVoices() {
    if (seq !== routeSeq) return;
    let d;
    try { d = await api(`/api/dests/${encodeURIComponent(name)}/voices`); } catch { return; }
    const box = $("#fw-v");
    if (!box || seq !== routeSeq) return;
    const all = d.voices;
    const count = (stages) => stages ? all.filter((v) => stages.includes(v.stage)).length : all.length;
    $("#fw-v-tabs").innerHTML = STAGE_TABS.filter(([k, , st]) => k === "all" || count(st)).map(([k, l, st]) =>
      `<button class="${fileState.filter === k ? "active" : ""}" data-vtab="${k}">${l}<span class="count">${fa(count(st))}</span></button>`).join("");
    $$("[data-vtab]").forEach((b) => b.onclick = () => { fileState.filter = b.dataset.vtab; fileState.showAll = false; drawVoices(); });
    const tab = STAGE_TABS.find(([k]) => k === fileState.filter) || STAGE_TABS[0];
    const list = tab[2] ? all.filter((v) => tab[2].includes(v.stage)) : all;
    if (!all.length) { box.innerHTML = `<div class="empty small">${I.music}<div>هنوز ویسی به این فایل اضافه نشده است.</div></div>`; return; }
    if (!list.length) { fileState.filter = "all"; return drawVoices(); }
    const LIMIT = 40, shown = fileState.showAll ? list : list.slice(0, LIMIT);
    const result = (v) => {
      const rs = v.records;
      if (v.stage === "written") {
        const rows = rs.filter((r) => r.exported_at);
        const files = [...new Set(rows.map((r) => r.file))];
        return `<button class="linkbtn vt-rows" data-vopen title="باز کردن فایل در Excel">${rows.length > 1 ? "ردیف‌های" : "ردیف"} ${rows.map((r) => fa(r.export_row)).join("، ")} ${I.open}</button>
          ${files.length > 1 || (files[0] && files[0] !== info.file) ? `<div class="muted small">${files.map((f) => `«${esc(f)}»`).join("، ")}</div>` : ""}`;
      }
      if (v.stage === "failed") return `<span class="err-text small">${esc((v.error || "").slice(0, 120))}</span>`;
      if (v.stage === "no_rows") return `<button class="linkbtn" data-vwhy="${v.id}">چرا؟</button>`;
      if (v.stage === "queued" || v.stage === "processing") return `<span class="muted">—</span>`;
      if (v.stage === "rejected") return `<span class="muted small">در فایل ثبت نمی‌شود</span>`;
      const live = rs.filter((r) => r.review_state !== "rejected" && !r.exported_at);
      const names = live.map((r) => r.name).filter(Boolean);
      return `${fa(live.length || rs.length)} ردیف${rs.length > 1 ? ` <span class="muted small">(${fa(rs.length)} ساختمان)</span>` : ""}
        ${names.length ? `<div class="muted small vt-names">${esc(names.join("، "))}</div>` : ""}`;
    };
    box.innerHTML = `<div class="table-wrap"><table class="table vt"><thead><tr><th>ویس</th><th>وضعیت</th><th>نتیجه</th><th></th></tr></thead><tbody>
      ${shown.map((v) => {
        const [cls, label] = STAGE[v.stage] || ["", v.stage];
        const exported = v.records.some((r) => r.exported_at);
        const first = v.records.find((r) => r.review_state === "pending" && !r.exported_at) || v.records[0];
        return `<tr data-vid="${v.id}"><td class="vt-name"><div title="${esc(v.original_name)}">${esc(v.original_name)}</div>
            <div class="muted small">تاریخ بازدید ${fa(v.visit_date)}${v.duration ? ` · ${fmtSec(v.duration)}` : ""}</div></td>
          <td>${v.stage === "processing" ? `<span class="chip processing"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> ${label}</span>` : chip(cls, label)}</td>
          <td>${result(v)}</td>
          <td class="actions">
            ${!v.audio_deleted ? `<button class="btn sm icon ghost" data-play="${v.id}" title="پخش ویس">${I.play}</button>` : ""}
            ${first ? `<button class="btn sm icon ghost" data-vrec="${first.id}" title="دیدن و اصلاح ردیف‌ها">${I.eye}</button>` : ""}
            ${v.stage === "failed" ? `<button class="btn sm icon ghost" data-vretry="${v.id}" title="تلاش دوباره">${I.retry}</button>` : ""}
            ${!exported && v.stage !== "processing" ? `<button class="btn sm icon ghost" data-vmove="${v.id}" title="انتقال به فایل دیگر">${I.swap}</button>
              <button class="btn sm icon ghost" data-vdel="${v.id}" title="حذف ویس">${I.trash}</button>` : ""}</td></tr>`;
      }).join("")}</tbody></table></div>
      ${list.length > shown.length ? `<div class="card-b small"><button class="linkbtn" id="fw-v-more">نمایش همه ${fa(list.length)} ویس</button></div>` : ""}`;
    $("#fw-v-more")?.addEventListener("click", () => { fileState.showAll = true; drawVoices(); });
    $$("[data-play]", box).forEach((b) => b.onclick = () => playAudio(+b.dataset.play, b));
    $$("[data-vrec]", box).forEach((b) => b.onclick = () => { reviewState.visible = all.flatMap((v) => v.records.map((r) => r.id)); openRecord(+b.dataset.vrec); });
    $$("[data-vopen]", box).forEach((b) => b.onclick = () => api(`/api/dests/${encodeURIComponent(name)}/open`, { method: "POST" }).catch(toastErr));
    $$("[data-vwhy]", box).forEach((b) => b.onclick = () => whyNoRows(+b.dataset.vwhy));
    $$("[data-vretry]", box).forEach((b) => b.onclick = async () => {
      try { await api(`/api/files/${b.dataset.vretry}/retry`, { method: "POST" }); await startQueue(); refreshStatus(); } catch (e) { toastErr(e); }
    });
    $$("[data-vdel]", box).forEach((b) => b.onclick = async () => {
      const v = all.find((x) => x.id === +b.dataset.vdel);
      if (!(await confirmBox("حذف ویس", `«${esc(v.original_name)}» و ردیف‌های ثبت‌نشده آن حذف می‌شوند. ادامه می‌دهید؟`, "حذف", "danger"))) return;
      try { await api(`/api/files/${v.id}`, { method: "DELETE" }); toast("ویس حذف شد.", "ok"); refreshStatus(); drawVoices(); } catch (e) { toastErr(e); }
    });
    $$("[data-vmove]", box).forEach((b) => b.onclick = () => moveVoice(all.find((x) => x.id === +b.dataset.vmove)));
  }

  async function moveVoice(v) {
    const others = (await loadDests()).dests.filter((x) => x.name !== name);
    if (!others.length) return toast("فایل دیگری در فهرست نیست؛ اول از «فایل‌های من» فایل دیگری اضافه کنید.");
    const to = await openModal({ title: "انتقال ویس به فایل دیگر", body: `<div class="stack"><div>«${esc(v.original_name)}» و ردیف‌های ثبت‌نشده‌اش به این فایل منتقل شوند:</div>
        <select class="select" id="mv-to">${others.map((x) => `<option value="${esc(x.name)}">${esc(destLabel(x))}</option>`).join("")}</select></div>`,
      actions: [{ label: "انتقال", cls: "primary", onClick: (m) => $("#mv-to", m).value }, { label: "انصراف", cls: "ghost", value: null }] });
    if (!to) return;
    try { await api(`/api/files/${v.id}`, { method: "PATCH", body: { dest: to } }); toast(`منتقل شد به «${destLabel(others.find((x) => x.name === to))}».`, "ok"); refreshStatus(); drawVoices(); }
    catch (e) { toastErr(e); }
  }

  async function drawReview() {
    if (seq !== routeSeq) return;
    const [{ records }, sheet] = await Promise.all([api(`/api/records?filter=review&dest=${encodeURIComponent(name)}`),
      api(`/api/dests/${encodeURIComponent(name)}/cells?filter=review`).catch(() => null)]);
    const box = $("#fw-rv");
    if (!box || seq !== routeSeq) return;
    $("#fw-review").hidden = !records.length;  // کارت خالی صفحه را شلوغ نکند
    reviewList(box, $("#fw-rv-actions"), records, drawReview, sheet);
  }

  function drawCommit() {
    const box = $("#fw-cm");
    if (!box || seq !== routeSeq) return;
    const n = info.ready, last = fileState.lastCommit;
    let html = "";
    if (last) {
      html += last.applied
        ? `<div class="alert ok">${I.ok}<div class="alert-body">${(last.files || []).length > 1
            ? `${fa(last.rows.length)} ردیف در ${fa(last.files.length)} فایل ثبت شد: ${last.files.map((f) => `«${esc(f)}»`).join("، ")}.`
            : `${fa(last.rows.length)} ردیف در «${esc(last.target_path.split(/[\\/]/).pop())}» ثبت شد (ردیف ${fa(last.first_row)} تا ${fa(last.last_row)}).`} پیش از ثبت از فایل پشتیبان گرفته شد.</div>
            <button class="btn sm" id="fw-open">${I.open} باز کردن فایل</button><button class="btn sm ghost" id="fw-undo">${I.history} برگرداندن</button></div>`
        : `<div class="alert warn">${I.alert}<div class="alert-body">${esc(last.message)}</div>
            ${last.export_ids?.length ? `<button class="btn sm" id="fw-open-copy">${I.open} دیدن کپی</button>` : ""}<a class="btn sm" href="#/history?f=${encodeURIComponent(name)}">تاریخچه ثبت‌ها</a></div>`;
    }
    if (!info.configured) {
      html += `<div class="dest-sentence warn">${I.alert}<span>ستون‌های این فایل هنوز تأیید نشده‌اند؛ تا تأیید نشوند چیزی ثبت نمی‌شود.</span>
        <a class="btn sm" href="#/templates?dest=${encodeURIComponent(name)}">تأیید ستون‌ها</a></div>`;
    } else if (n) {
      const items = fileState.check?.items || [];
      const ICON = { ok: I.ok, warn: I.alert, block: I.alert };
      html += `${items.length ? `<ul class="fcheck">${items.map((x) => `<li class="${x.level}">${ICON[x.level]}<span>${esc(x.text)}</span></li>`).join("")}</ul>` : ""}
        <div class="row">${checkBlock() ? fixBtn(checkBlock(), info.review ? "btn" : "btn primary lg") : ""}<button class="btn ${!info.review && !checkBlock() ? "primary lg" : ""}" id="fw-commit-go" ${checkBlock() ? "disabled" : ""}>${I.table} ثبت ${fa(n)} ردیف در «${esc(destLabel(info))}»</button></div>`;
    }
    box.innerHTML = html;
    $("#fw-commit").hidden = !html;
    bindFix(box);
    $("#fw-commit-go")?.addEventListener("click", (e) => doCommit(e.currentTarget));
    $("#fw-open")?.addEventListener("click", () => api(`/api/dests/${encodeURIComponent(name)}/open`, { method: "POST" }).catch(toastErr));
    $("#fw-open-copy")?.addEventListener("click", () => api(`/api/exports/${last.export_ids[0]}/open`, { method: "POST" }).catch(toastErr));
    $("#fw-undo")?.addEventListener("click", async () => {
      if (!(await confirmBox("برگرداندن ثبت", "ردیف‌های این ثبت از فایل اکسل برداشته می‌شوند (فایل به نسخه پیش از ثبت برمی‌گردد) و دوباره آماده ثبت می‌شوند.", "برگرداندن", "danger"))) return;
      try {
        let msg = "";
        for (const eid of [...(last.export_ids || [last.export_id])].reverse()) msg = (await api(`/api/exports/${eid}/undo`, { method: "POST" })).message;
        toast(msg, "ok"); fileState.lastCommit = null;
      } catch (er) { toastErr(er); }
      await refreshStatus();
      await reloadInfo();
      drawHead(); drawNext(); drawCommit();
    });
  }

  async function doCommit(btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> در حال ثبت...';
    try { fileState.lastCommit = await api("/api/excel/commit", { method: "POST", body: { dest: name } }); }
    catch (er) { toastErr(er); }
    await refreshStatus();
    await reloadInfo();
    drawHead(); drawNext(); drawCommit(); drawVoices().catch(() => {});
    loadCheck();
    $("#fw-commit")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  reviewState.reload = reviewState.updateRow = () => { drawReview().catch(() => {}); drawVoices().catch(() => {}); };
  pageHooks.onFocus = loadCheck;
  setHook(seq, async (s, prev) => {
    await reloadInfo();
    if (seq !== routeSeq) return;
    drawHead(); drawNext(); drawProgress(); drawCommit();
    if (prev && (prev.records.approved !== s.records.approved || prev.records.exported !== s.records.exported)) loadCheck();
    if (info.voices) $("#fw-samples")?.closest(".row").remove();
    if (!prev || prev.records.review !== s.records.review || prev.files.done !== s.files.done) drawReview().catch(() => {});
    drawVoices().catch(() => {});
  });
  const timer = setInterval(() => { if (seq !== routeSeq) return clearInterval(timer); if (state.status?.worker.running) drawProgress(); }, 1000);
}

// ================= تاریخچه ثبت‌ها =================
const histState = { dest: "" };
const EXPORT_ST = { applied: ["ok", "ثبت شد"], created: ["warn", "در یک کپی ساخته شد؛ هنوز روی فایل اصلی اعمال نشده"], undone: ["missing", "برگردانده شد"] };

async function renderHistory(el) {
  const seq = routeSeq;
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  if (q.has("f")) histState.dest = q.get("f");
  const [{ exports }, ds] = await Promise.all([api(`/api/exports?dest=${encodeURIComponent(histState.dest)}`), loadDests()]);
  if (seq !== routeSeq) return;
  const label = (e) => { const d = ds.dests.find((x) => x.name === e.profile); return d ? destLabel(d) : e.file; };
  const today = state.status?.today || "";
  const days = [];
  for (const e of exports) {
    const g = days.find((x) => x.date === e.date_jalali);
    if (g) g.items.push(e); else days.push({ date: e.date_jalali, items: [e] });
  }
  el.innerHTML = `<div class="row" style="margin-bottom:16px"><label class="small muted">فایل:</label>
      <select class="select" id="h-dest" style="width:auto;min-width:240px"><option value="">همه فایل‌ها</option>
        ${ds.dests.map((d) => `<option value="${esc(d.name)}" ${d.name === histState.dest ? "selected" : ""}>${esc(destLabel(d))}</option>`).join("")}</select></div>
    ${!exports.length ? `<div class="card"><div class="empty">${I.history}<div>هنوز ثبتی ${histState.dest ? "در این فایل " : ""}انجام نشده است.</div></div></div>`
      : days.map((g) => `<div class="h-day"><div class="h-date">${fa(g.date)}${g.date === today ? " — امروز" : ""}</div>
        <div class="card">${g.items.map((e) => {
          const [cls, st] = EXPORT_ST[e.status] || ["", e.status];
          return `<div class="h-item ${e.status}">
            <div class="h-main"><div><span class="h-time" dir="ltr">${fa(e.time)}</span> <b>${fa(e.rows_written)} ردیف</b> در «${fname(label(e))}»
                <span class="muted small">(ردیف ${fa(e.first_row)}${e.last_row !== e.first_row ? ` تا ${fa(e.last_row)}` : ""})</span></div>
              <div class="row small" style="gap:6px">${chip(cls, st)}${!e.dest_listed ? chip("missing", "این فایل دیگر در فهرست نیست") : ""}</div>
              ${e.items.length ? `<details class="small"><summary>ردیف‌ها</summary><ul class="h-rows">${e.items.map((x) =>
                `<li><b>ردیف ${fa(x.row)}</b>: ${esc(x.name || "بی‌نام")} <span class="muted">— ${esc(x.voice)}</span></li>`).join("")}</ul></details>` : ""}</div>
            <div class="h-act">
              ${e.status !== "undone" ? `<button class="btn sm" data-hopen="${e.id}">${I.open} باز کردن فایل</button>` : ""}
              ${e.status === "created" ? `<button class="btn sm primary" data-happly="${e.id}">${I.check} اعمال روی فایل اصلی</button>` : ""}
              ${e.status !== "undone" ? `<button class="btn sm ghost" data-hundo="${e.id}">${I.history} برگرداندن</button>` : ""}</div></div>`;
        }).join("")}</div></div>`).join("")}`;
  $("#h-dest").onchange = (e) => { histState.dest = e.target.value; renderHistory(el); };
  $$("[data-hopen]", el).forEach((b) => b.onclick = () => api(`/api/exports/${b.dataset.hopen}/open`, { method: "POST" }).catch(toastErr));
  $$("[data-happly]", el).forEach((b) => b.onclick = async () => {
    if (!(await confirmBox("اعمال روی فایل اصلی", "ردیف‌های این ثبت که در یک کپی ساخته شده‌اند، روی فایل اصلی نوشته می‌شوند. پیش از آن از فایل اصلی پشتیبان گرفته می‌شود. Excel باید بسته باشد.", "اعمال"))) return;
    try { await api(`/api/exports/${b.dataset.happly}/replace-original`, { method: "POST" }); toast("روی فایل اصلی اعمال شد.", "ok"); refreshStatus(); renderHistory(el); }
    catch (e) { toastErr(e); }
  });
  $$("[data-hundo]", el).forEach((b) => b.onclick = async () => {
    if (!(await confirmBox("برگرداندن ثبت", "اگر فایل اکسل پس از این ثبت دستی تغییر نکرده باشد، به حالت پیش از ثبت برمی‌گردد. ردیف‌ها دوباره «آماده ثبت» می‌شوند تا اصلاح یا دوباره ثبتشان کنید.", "برگرداندن", "danger"))) return;
    try { toast((await api(`/api/exports/${b.dataset.hundo}/undo`, { method: "POST" })).message, "ok"); refreshStatus(); renderHistory(el); }
    catch (e) { toastErr(e); }
  });
}

/** چرا از یک ویس ردیفی ساخته نشد: متن ویس، پخش و راهنمای ضبط بهتر. */
async function whyNoRows(id) {
  let w;
  try { w = await api(`/api/files/${id}/why`); } catch (e) { return toastErr(e); }
  await openModal({ title: "از این ویس ردیفی ساخته نشد", wide: true, body: `<div class="stack">
      <div>برنامه در متن این ویس <b>نام، شماره تماس یا آدرسی</b> پیدا نکرد که بشود از آن یک ردیف ساخت. معمولاً یعنی ویس دربارهٔ بازدید نبوده، خیلی کوتاه یا بی‌صدا بوده، یا صدای زمینه زیاد بوده است.</div>
      ${w.error ? `<div class="alert info">${I.info}<div class="alert-body">${esc(w.error)}</div></div>` : ""}
      <div><div class="section-title">${I.wave} متنی که از ویس شنیده شد</div><div class="transcript">${w.text ? esc(w.text) : '<span class="muted">متنی شنیده نشد (ویس بی‌صدا یا خیلی کوتاه است).</span>'}</div></div>
      ${w.audio ? `<audio controls preload="metadata" src="/api/files/${id}/audio" style="width:100%"></audio>` : ""}
      <div class="small muted">اگر ویس اطلاعات بازدید دارد، دوباره و واضح‌تر ضبط شود. <a href="/static/recording-guide.html" target="_blank">راهنمای ضبط ویس</a></div></div>`,
    actions: [{ label: "بستن", cls: "primary" }] });
}

/** نوار ثابت بالای صفحه: همیشه معلوم است کدام فایل باز است، چند ردیف دارد و آخرین بار کی ثبت شد. */
function fileBar(box, info, onChange, where = "file") {
  const r = info.file_rows, lc = info.last_commit;
  const facts = [
    info.missing ? `<span class="err-text">${I.alert} فایل در مسیرش پیدا نشد</span>` : r ? (r.exists ? `<span><b>${fa(r.rows)}</b> ردیف</span>` : `<span>هنوز ساخته نشده</span>`) : "",
    r?.exists ? `<span>آخرین ردیف: <b>${fa(r.last_row)}</b></span>` : "",
    lc ? `<a class="fb-link" href="#/history?f=${encodeURIComponent(info.name)}" title="تاریخچه ثبت‌های این فایل">آخرین ثبت: <b>${agoText(lc.created_at)}</b> (${fa(lc.rows_written)} ردیف)</a>` : `<span class="muted">هنوز ثبتی نشده</span>`,
  ].filter(Boolean);
  box.innerHTML = `<div class="file-bar">
    <span class="fb-ico">${info.mode === "new" ? I.file : I.table}</span>
    <div class="fb-main"><div class="fb-name"><span class="muted small">فایل:</span> <b>${fname(destLabel(info))}</b></div>
      <div class="fb-facts small">${facts.join('<span class="fb-dot">·</span>')}</div></div>
    <div class="fb-status">${destParts(info).map(([c, t]) => chip(c, t)).join("")}</div>
    <div class="fb-act">
      <button class="btn sm" id="fb-open" title="${info.file_rows?.exists ? "باز کردن همین فایل در Excel" : "باز کردن پوشه فایل"}">${I.open} ${info.file_rows?.exists ? "باز کردن فایل" : "پوشه فایل"}</button>
      ${where === "settings" ? `<a class="btn sm ghost" href="${fileHref(info.name)}" title="افزودن ویس، بررسی و ثبت">${I.table} میز کار فایل</a>`
        : `<a class="btn sm ghost" href="#/templates?dest=${encodeURIComponent(info.name)}" title="ستون‌ها، شکل نوشتن مقادیر و ظاهر">${I.edit} تنظیمات فایل</a>`}
      <a class="btn sm ghost" href="#/files" title="همه فایل‌های اکسل">${I.prev} همه فایل‌ها</a></div>
    <div class="fb-auto small">${info.auto ? `${I.mic} ویس‌های گوشی و پوشه ورودی هم به همین فایل می‌آیند.`
      : `<button class="linkbtn" id="fb-auto">${I.mic} ویس‌های گوشی و پوشه ورودی هم به این فایل بیایند</button>`}</div></div>`;
  $("#fb-open", box).onclick = () => api(`/api/dests/${encodeURIComponent(info.name)}/open`, { method: "POST" }).catch(toastErr);
  $("#fb-auto", box)?.addEventListener("click", async () => {
    try { await api(`/api/templates/${encodeURIComponent(info.name)}/activate`, { method: "POST" }); toast(`از این پس ویس‌های گوشی و پوشه ورودی به «${destLabel(info)}» می‌آیند.`, "ok"); onChange?.(); }
    catch (e) { toastErr(e); }
  });
}

// خانه‌ای که از چند اطلاعات ساخته می‌شود: وضعیتش بدترین وضعیت اجزای آن است
const CELL_TECH = ["floors", "structure_type", "executed", "stage", "units"];  // همان TECH_KEYS (که پایین‌تر تعریف شده)
const CELL_PARTS = {
  technical_summary: CELL_TECH, followup: ["followup_action", "followup_date"],
  notes_composed: [...CELL_TECH, "project_name", "building_type", "permit_status", "customer_need", "notes", "followup_action", "followup_date"],
};
const CELL_RANK = { invalid: 3, review: 2, missing: 1, valid: 0 };
function cellStatus(field, vf) {
  const parts = CELL_PARTS[field] || [field];
  return parts.map((k) => vf[k]?.status || "valid").reduce((a, b) => (CELL_RANK[b] > CELL_RANK[a] ? b : a), "valid");
}
/** یک ردیف به شکل خود اکسل: حرف و عنوان ستون‌های فایل و مقدار هر خانه، همان‌طور که نوشته می‌شود. */
function excelRowHtml(sheet, r) {
  const cells = sheet.rows[r.id] || {};
  const cols = sheet.columns.filter((c) => c.field);
  const vf = r.validation.fields || {};
  return `<div class="xr-wrap"><table class="xr-table"><thead><tr><th class="xr-rn"></th>${cols.map((c) =>
      `<th title="${esc(c.title)}"><span class="xr-letter">${esc(c.letter)}</span>${esc(c.title)}</th>`).join("")}</tr></thead>
    <tbody><tr><td class="xr-rn" title="ردیف تازه، زیر آخرین ردیف فایل">+</td>${cols.map((c) => {
      const st = cellStatus(c.field, vf), t = r.audio_available && !CELL_PARTS[c.field] && fieldTime(r, c.field);
      const val = cells[c.letter] || "";
      return `<td class="st-${st} ${c.field === "phone" ? "ltr-cell" : ""}" data-xcell="${r.id}" title="${esc((vf[c.field]?.reasons || []).join(" | ") || "برای اصلاح بزنید")}">
        ${val ? esc(val) : `<span class="muted">${st === "missing" ? "گفته نشده" : "—"}</span>`}${t ? `<button class="xr-play" data-tseg="${c.field}" title="پخش همین بخش از ویس">${I.play}</button>` : ""}</td>`;
    }).join("")}</tr></tbody></table></div>`;
}

/** فهرست ردیف‌های نیازمند بررسی: علت هر هشدار، پخش همان تکه از ویس، «درست است / اصلاح / رد».
 * sheet: ستون‌های فایل و مقدار خانه‌ها (از /api/dests/…/cells)؛ اگر باشد، هر ردیف به شکل خود ردیف اکسل نمایش داده می‌شود. */
function reviewList(box, actionsBox, records, reload, sheet = null) {
  const LABEL = { ...Object.fromEntries((state.meta?.fields || []).map((f) => [f.key, f.label])), tech: "مشخصات فنی" };
  const SEG_OF = { followup_date: "followup_action", followup_time_text: "followup_action" };  // فیلدی که بخش ویس خودش را ندارد
  const SHOW = 12;
  const ids = records.map((r) => r.id);
  actionsBox.innerHTML = records.length > 1 ? `<button class="btn sm" id="rl-focus" title="یک ردیف در هر صفحه، با پخش خودکار شماره و میان‌برهای صفحه‌کلید">${I.eye} بررسی سریع (${fa(records.length)})</button>` : "";
  $("#rl-focus", actionsBox)?.addEventListener("click", () => openFocus(ids));
  if (!records.length) {
    box.innerHTML = `<div class="card-b row muted">${I.ok} ردیفی برای بررسی نیست.</div>`;
    return;
  }
  box.innerHTML = `<div class="t-list">${records.slice(0, SHOW).map((r) => {
    const v = r.values, vf = r.validation.fields || {};
    const item = (k, why) => {
      const seg = SEG_OF[k] || k, t = r.audio_available && fieldTime(r, seg), words = lowWords(r, k);
      return `<li>${t ? `<button class="btn sm ghost" data-tseg="${seg}" title="پخش همین بخش از ویس">${I.play} بشنوید ${segTime(t)}</button>` : ""}
        <span class="t-why"><b>${esc(LABEL[k] || k)}:</b> ${esc(why)}</span>${words.length ? `<span class="t-words">${words.join(" ")}</span>` : ""}</li>`;
    };
    const bad = Object.entries(vf).filter(([, f]) => f.status !== "valid");
    const problems = bad.map(([k, f]) => item(k, (f.reasons || [])[0] || FIELD_STATUS[f.status]));
    for (const k of ["engineer_name", "phone", "address", "tech"]) {
      if (lowWords(r, k).length && !bad.some(([b]) => b === k)) problems.push(item(k, "بخشی با اطمینان کم شنیده شد."));
    }
    if (!problems.length) problems.push(...(r.validation.reasons || []).slice(0, 2).map((x) => `<li><span class="t-why">${esc(x)}</span></li>`));
    const play = r.audio_available ? `<button class="btn sm ghost" data-twhole title="پخش کل ویس">${I.play} کل ویس</button>` : "";
    const notes = problems.length ? `<button class="btn sm ghost t-notes-btn" data-tnotes aria-expanded="${openNotes.has(r.id)}" title="دلیل بررسی و پخش همان بخش ویس">${I.alert} ${fa(problems.length)} نکته</button>` : "";
    const acts = `<div class="t-rec-act">${notes}${play}
        <button class="btn sm pos" data-tact="approve" data-r="${r.id}">${I.check} درست است</button>
        <button class="btn sm" data-topen="${r.id}">${I.edit} اصلاح</button>
        <button class="btn sm ghost rej" data-tact="reject" data-r="${r.id}" title="رد: در فایل ثبت نشود">${I.x} رد</button></div>`;
    if (sheet?.rows[r.id]) return `<div class="t-rec xr ${openNotes.has(r.id) ? "notes-open" : ""}" data-trec="${r.id}">
      <div class="xr-head"><span class="small muted" title="${esc(r.original_name)}">${I.music} ${esc(r.original_name)}${r.building_count > 1 ? ` · ساختمان ${fa(r.building_index + 1)} از ${fa(r.building_count)}` : ""}</span>${acts}</div>
      ${excelRowHtml(sheet, r)}
      <ul class="t-problems small">${problems.join("")}</ul></div>`;
    return `<div class="t-rec" data-trec="${r.id}">
      <div class="t-rec-main"><div><b>${esc(v.engineer_name || "نام پیدا نشد")}</b>
          <span class="ltr t-phone">${esc((v.phone || "").split("\n").filter(Boolean).map(fmtPhone).join(" ، ")) || "—"}</span></div>
        <div class="small">${esc(v.address || "آدرس پیدا نشد")}${techSummary(v) ? ` <span class="muted">· ${esc(techSummary(v))}</span>` : ""}</div>
        <ul class="t-problems small">${problems.join("")}</ul></div>
      <div class="t-rec-act">${play}
        <button class="btn sm pos" data-tact="approve" data-r="${r.id}">${I.check} درست است</button>
        <button class="btn sm" data-topen="${r.id}">${I.edit} اصلاح</button>
        <button class="btn sm ghost rej" data-tact="reject" data-r="${r.id}" title="رد: در فایل ثبت نشود">${I.x} رد</button></div></div>`;
  }).join("")}</div>
  ${records.length > SHOW ? `<div class="card-b small muted">و ${fa(records.length - SHOW)} ردیف دیگر؛ با «بررسی سریع» همه را یکی‌یکی ببینید.</div>` : ""}`;
  reviewState.visible = ids;
  $$("[data-trec]", box).forEach((card) => {
    const rec = records.find((r) => r.id === +card.dataset.trec);
    $$("[data-tseg]", card).forEach((b) => b.onclick = (e) => { e.stopPropagation(); playRecordSegment(rec, b.dataset.tseg); });
    $$("[data-xcell]", card).forEach((td) => td.onclick = () => openRecord(rec.id));
    $("[data-tnotes]", card)?.addEventListener("click", (e) => {
      const open = card.classList.toggle("notes-open");
      e.currentTarget.setAttribute("aria-expanded", String(open));
      if (open) openNotes.add(rec.id); else openNotes.delete(rec.id);
    });
    $$("[data-lt]", card).forEach((b) => b.onclick = () => playRecordSegment(rec, b.dataset.lt.split(",").map(Number)));
    $("[data-twhole]", card)?.addEventListener("click", () => playRecordSegment(rec, [0, 1e6]));
  });
  $$("[data-topen]", box).forEach((b) => b.onclick = () => openRecord(+b.dataset.topen));
  $$("[data-tact]", box).forEach((b) => b.onclick = async () => {
    const id = +b.dataset.r, act = b.dataset.tact;
    try {
      await api(`/api/records/${id}/action`, { method: "POST", body: { action: act, add_to_dictionary: act === "approve" } });
      toast(act === "approve" ? "تأیید شد." : "رد شد.", "ok", { label: "بازگشت", onClick: async () => { await undoLast(id); reload(); } });
      refreshStatus();
    } catch (e) { toastErr(e); }
  });
}

async function startQueue() {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
  try { await api("/api/queue/start", { method: "POST" }); toast("پردازش شروع شد."); setTimeout(refreshStatus, 300); }
  catch (e) { toastErr(e); }
}
async function stopQueue() {
  try { await api("/api/queue/cancel", { method: "POST" }); toast("پردازش پس از فایل فعلی متوقف می‌شود؛ نتایج قبلی حفظ شده‌اند."); }
  catch (e) { toastErr(e); }
}

// ---------------- افزودن ویس (مشترک میان «کار امروز» و «ویس‌ها») ----------------
/** فقط فایل‌های صوتی پشتیبانی‌شده. */
function audioOnly(list) {
  const allowed = new Set(state.meta?.audio_extensions || []);
  const files = Array.from(list).filter((f) => allowed.has("." + (f.name.split(".").pop() || "").toLowerCase()));
  if (files.length < list.length) toast(`${fa(list.length - files.length)} فایل غیرصوتی نادیده گرفته شد.`);
  return files;
}

/** فایل‌های رهاشده روی صفحه، همراه با محتوای پوشه‌ها. */
async function droppedFiles(e) {
  const entries = Array.from(e.dataTransfer.items || []).map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.some((en) => en.isDirectory)) return Array.from(e.dataTransfer.files);
  const out = [];
  const walk = (entry) => new Promise((res) => {
    if (entry.isFile) return entry.file((f) => { out.push(f); res(); }, () => res());
    const reader = entry.createReader();
    const readAll = () => reader.readEntries(async (ents) => {
      if (!ents.length) return res();
      for (const en of ents) await walk(en);
      readAll();
    }, () => res());
    readAll();
  });
  for (const en of entries) await walk(en);
  return out;
}

/** صف افزودن ویس: دسته بعدی پس از پایان بررسی و آپلود دسته قبلی (دو پنجره پرسش هم‌زمان باز نشود) */
let uploadQueue = Promise.resolve();

/** اثر انگشت محتوای هر فایل (همان sha256 سرور)؛ null اگر مرورگر پشتیبانی نکند. فایل خیلی بزرگ بررسی نمی‌شود. */
async function fileHashes(files) {
  if (!window.crypto?.subtle) return null;
  try {
    return await Promise.all(files.map(async (f, i) => f.size > 200e6 ? `big-${i}` : [...new Uint8Array(
      await crypto.subtle.digest("SHA-256", await f.arrayBuffer()))].map((b) => b.toString(16).padStart(2, "0")).join("")));
  } catch { return null; }
}

/** پیش از آپلود از رایانه:
 *  ۱) ویس‌های تکراری همین انتخاب (محتوای یکسان): «فقط یکی استفاده شود؟» بله ← یکی، خیر ← همه.
 *  ۲) ویسی که قبلاً پردازش شده: «از همان نتیجه در این فایل استفاده شود؟» بله ← متن و ردیف‌ها بدون تبدیل دوباره
 *     (اگر همین حالا در همین فایل باشد، دوباره اضافه نمی‌شود)، خیر ← روال همیشگی: تبدیل و بررسی دوباره.
 *  خروجی null یعنی کاربر پنجره را بست (انصراف). */
async function planUploads(files, dest) {
  const hashes = await fileHashes(files);
  if (!hashes) return { upload: files, reuse: [], skipped: [] };
  let items = files.map((f, i) => ({ f, h: hashes[i] }));
  const groups = new Map();
  items.forEach((x) => groups.set(x.h, [...(groups.get(x.h) || []), x]));
  const dupGroups = [...groups.values()].filter((g) => g.length > 1);
  if (dupGroups.length) {
    const ans = await openModal({
      title: "ویس تکراری در همین انتخاب",
      body: `<div class="stack"><div>محتوای این ویس‌ها دقیقاً یکی است:</div>
        <ul class="reasons">${dupGroups.map((g) => `<li>${g.map((x) => `«${esc(x.f.name)}»`).join(" و ")}</li>`).join("")}</ul>
        <b>فقط یکی از هر کدام استفاده شود؟</b></div>`,
      actions: [{ label: "بله، فقط یکی", cls: "primary", value: "one" }, { label: "خیر، همه اضافه شوند", value: "all" }],
    });
    if (!ans) return null;
    if (ans === "one") { const seen = new Set(); items = items.filter((x) => !seen.has(x.h) && seen.add(x.h)); }
  }
  let matches = {};
  try { matches = (await api("/api/upload/check", { method: "POST", body: { hashes: [...new Set(items.map((x) => x.h))], dest } })).matches || {}; }
  catch { matches = {}; }
  const prev = items.filter((x) => matches[x.h]?.processed);
  const reuse = [], skipped = [];
  if (prev.length) {
    const where = (m) => m.same_dest ? "همین فایل" : `فایل «${esc(m.dest_label)}»`;
    const ans = await openModal({
      title: "این ویس‌ها قبلاً پردازش و بررسی شده‌اند",
      body: `<div class="stack"><ul class="reasons">${prev.map((x) => { const m = matches[x.h];
          return `<li>«${esc(x.f.name)}» — در ${where(m)}${m.rows ? `، ${fa(m.rows)} ردیف${m.written ? ` (${fa(m.written)} ردیف ثبت‌شده در اکسل)` : ""}` : ""}</li>`; }).join("")}</ul>
        <b>از همان نتیجه در این فایل استفاده شود؟</b>
        <span class="muted small">«بله»: متن و ردیف‌های قبلی بدون تبدیل دوباره به این فایل می‌آیند؛ ویسی که همین حالا در همین فایل هست دوباره اضافه نمی‌شود.
        «خیر»: ویس مثل همیشه دوباره به متن تبدیل و بررسی می‌شود.</span></div>`,
      actions: [{ label: "بله، از همان استفاده شود", cls: "primary", value: "reuse" }, { label: "خیر، دوباره پردازش شود", value: "again" }],
    });
    if (!ans) return null;
    if (ans === "reuse") {
      const taken = new Set();
      for (const x of prev) {
        const m = matches[x.h];
        if (m.same_dest) skipped.push({ name: x.f.name });
        else if (!taken.has(m.id)) { taken.add(m.id); reuse.push({ id: m.id, name: x.f.name }); }
      }
      items = items.filter((x) => !prev.includes(x));
    }
  }
  return { upload: items.map((x) => x.f), reuse, skipped };
}

/** ارسال ویس‌ها در بسته‌های ۸تایی؛ onProgress(درصد). خروجی: نتیجه هر فایل. */
async function uploadAudio(files, visitDate, useFilenameDate, onProgress = () => {}, dest = "") {
  const results = [];
  const totalBytes = files.reduce((a, f) => a + f.size, 0) || 1;
  let sent = 0;
  for (let i = 0; i < files.length; i += 8) {
    const chunk = files.slice(i, i + 8);
    const fd = new FormData();
    chunk.forEach((f) => fd.append("files", f, f.name));
    fd.append("visit_date", visitDate);
    fd.append("use_filename_date", useFilenameDate ? "true" : "false");
    fd.append("dest", dest);
    const r = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.setRequestHeader("X-V2X-Token", TOKEN);
      xhr.upload.onprogress = (e) => onProgress(Math.min(100, Math.round(100 * (sent + e.loaded) / totalBytes)));
      xhr.onload = () => {
        let d = {}; try { d = JSON.parse(xhr.responseText); } catch { }
        xhr.status < 300 ? resolve(d) : reject(new Error(d.detail || "افزودن فایل‌ها ناموفق بود."));
      };
      xhr.onerror = () => reject(new Error("ارتباط با برنامه قطع شد."));
      xhr.send(fd);
    });
    sent += chunk.reduce((a, f) => a + f.size, 0);
    results.push(...r.results);
  }
  return results;
}

// ================= ویس‌ها =================
/** وضعیت مدل گفتار: آماده (بدون انتظار)، در حال آماده‌سازی، یا در شروع پردازش آماده می‌شود. */
function modelChip(stateName, available) {
  if (!available) return chip("err", "مدل گفتار نصب نیست");
  if (stateName === "ready") return chip("ok", "مدل گفتار آماده است");
  if (stateName === "loading") return `<span class="chip info model-chip"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> در حال آماده‌سازی مدل گفتار…</span>`;
  return chip("missing", "مدل گفتار هنگام شروع پردازش آماده می‌شود");
}

function reportUpload(results) {
  const added = results.filter((r) => r.result === "added").length;
  const reused = results.filter((r) => r.result === "reused").length;
  const skipped = results.filter((r) => r.result === "skipped").length;
  const dup = results.filter((r) => r.result === "duplicate");
  const errs = results.filter((r) => r.result === "error");
  if (added) toast(`${fa(added)} فایل به صف اضافه شد.`, "ok");
  if (reused) toast(`${fa(reused)} ویس با همان نتیجه قبلی به این فایل آمد (بدون تبدیل دوباره).`, "ok");
  if (skipped) toast(`${fa(skipped)} ویس همین حالا در همین فایل بود و دوباره اضافه نشد.`, "info");
  if (dup.length || errs.length) {
    openModal({
      title: "نتیجه افزودن فایل‌ها",
      body: `<div class="stack">${added ? `<div class="alert ok">${I.ok}<div class="alert-body">${fa(added)} فایل اضافه شد.</div></div>` : ""}
        ${dup.length ? `<div><b>${fa(dup.length)} فایل تکراری (اضافه نشد):</b><ul class="reasons">${dup.map((d) => `<li>${esc(d.name)} — ${esc(d.message)}</li>`).join("")}</ul></div>` : ""}
        ${errs.length ? `<div><b>${fa(errs.length)} فایل با خطا:</b><ul class="reasons invalid">${errs.map((d) => `<li>${esc(d.name)} — ${esc(d.message)}</li>`).join("")}</ul></div>` : ""}</div>`,
      actions: [{ label: "متوجه شدم", cls: "primary" }],
    });
  }
}

let audioEl = null;
function playAudio(id, btn) {
  if (audioEl && audioEl.dataset.id == id && !audioEl.paused) { audioEl.pause(); btn.innerHTML = I.play; return; }
  if (audioEl) audioEl.pause();
  $$("[data-play]").forEach((b) => b.innerHTML = I.play);
  audioEl = new Audio(`/api/files/${id}/audio`);
  audioEl.dataset.id = id;
  audioEl.onended = () => btn.innerHTML = I.play;
  audioEl.onerror = () => { toast("پخش این فایل در مرورگر ممکن نیست."); btn.innerHTML = I.play; };
  audioEl.play().then(() => btn.innerHTML = I.stop).catch(() => {});
}

// ================= بررسی =================
let tableAudio = null;
const reviewState = { filter: "review", records: [], selected: new Set(), audioId: null };

/** پخش همان تکه از ویس که فیلد key از آن آمده (یا بازه [شروع، پایان])، بدون باز کردن جزئیات. */
function playRecordSegment(rec, keyOrSpan) {
  if (!tableAudio || tableAudio.dataset.aid !== String(rec.audio_id)) {
    if (tableAudio) tableAudio.pause();
    tableAudio = new Audio(`/api/files/${rec.audio_id}/audio`);
    tableAudio.dataset.aid = String(rec.audio_id);
  }
  playSegment(tableAudio, Array.isArray(keyOrSpan) ? keyOrSpan : fieldTime(rec, keyOrSpan));
}

function techSummary(v) {
  const p = [];
  if (v.floors) p.push(`تعداد ${v.floors} ${v.floors_unit || "سقف"}`);
  if (v.structure_type) p.push(`سازه ${v.structure_type}`);
  if (v.executed) p.push(v.executed);
  if (v.stage) p.push(v.stage);
  if (v.units) p.push(`تعداد ${v.units} واحد`);
  return p.join(" ، ");
}

// ---------- کشوی جزئیات ردیف ----------
const DRAWER_GROUPS = [
  ["اطلاعات اصلی", ["engineer_name", "phone", "project_name", "address", "visit_date"]],
  ["مشخصات فنی و مرحله ساخت", ["structure_type", "floors", "executed", "units", "stage", "building_type", "permit_status"]],
  ["توضیحات", ["customer_need", "notes"]],
  ["پیگیری", ["followup_action", "followup_time_text", "followup_date"]],
  ["اجزای آدرس", ["city", "neighborhood", "street", "alley", "plate"]],
];
const MULTILINE = new Set(["address", "notes", "phone", "followup_action", "permit_status", "customer_need", "stage"]);
const DICT_FIELDS = new Set(["engineer_name", "project_name", "street"]);

/** پخش‌کننده‌ای که دیگر لازم نیست، فایل ویس را رها کند؛ وگرنه پخش‌کننده تازهٔ همان ویس چند ثانیه منتظر می‌ماند. */
function releaseAudio(a) {
  if (!a) return;
  a.pause();
  a.removeAttribute("src");
  a.load();
}
function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer-backdrop").hidden = true;
  if (audioEl) audioEl.pause();
  releaseAudio($("#dr-audio"));
  $("#dr-audio")?.remove();
}
$("#drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { if (!$("#modal-backdrop").hidden) closeModal(undefined); else closeDrawer(); }
});

function highlightTranscript(text, clauses, block, multi) {
  let html = "", pos = 0;
  for (const c of clauses || []) {
    const i = text.indexOf(c.text, pos);
    if (i < 0) continue;
    html += esc(text.slice(pos, i));
    html += `<span class="seg seg-${esc(c.category)} ${multi && c.block !== block ? "other-block" : ""}" title="${esc(SEG_LABEL[c.category] || "")}">${esc(c.text)}</span>`;
    pos = i + c.text.length;
  }
  return html + esc(text.slice(pos));
}

// ---------- ابزارهای مشترک بررسی: پخش تکه، نمایش شماره، بازگشت ----------
const SEG_KEYS = [["engineer_name", "نام"], ["phone", "شماره"], ["address", "آدرس"], ["tech", "فنی"]];
const TECH_KEYS = ["floors", "structure_type", "executed", "stage", "units"];
const UNDOABLE = new Set(["edit", "accept", "approve", "reject", "reopen", "duplicate"]);

/** «۱:۰۵» از ثانیه؛ مثل نمایش زمان در پخش‌کننده‌ها، تا همان بخش در دستگاه دیگری هم پیدا شود. */
const fmtClock = (s) => fa(`${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
const segText = (span) => (span ? `${fmtClock(span[0])}–${fmtClock(Math.ceil(span[1]))}` : "");
const segTime = (span) => (span ? `<span class="seg-time" dir="ltr">${segText(span)}</span>` : "");

function fieldTime(r, k) {
  if (!r) return null;
  if (k === "tech") return TECH_KEYS.map((x) => r.times?.[x]).find(Boolean) || null;
  return r.times?.[k] || null;
}

/** پخش بازه [شروع، پایان] از ویس روی همان پخش‌کننده‌ای که کاربر می‌بیند. */
function playSegment(audio, span) {
  if (!audio || !span) return;
  const [t0, t1] = span;
  if (!audio.dataset.segBound) {
    audio.dataset.segBound = "1";
    audio.addEventListener("timeupdate", () => {
      const stop = parseFloat(audio.dataset.stopAt || "");
      if (stop && audio.currentTime >= stop) { audio.pause(); delete audio.dataset.stopAt; }
    });
  }
  const go = () => {
    audio.currentTime = t0;
    audio.dataset.stopAt = String(t1);
    audio.play().catch(() => {});
  };
  if (audio.readyState >= 1) go(); else audio.addEventListener("loadedmetadata", go, { once: true });
}
function playWhole(audio) {
  if (!audio) return;
  delete audio.dataset.stopAt;
  if (audio.paused) audio.play().catch(() => {}); else audio.pause();
}

/** 09151234567 ← «0915 123 4567» برای خواندن و مقایسه آسان‌تر با ویس */
function fmtPhone(p) {
  const d = String(p || "").replace(/\D/g, "");
  if (/^09\d{9}$/.test(d)) return `${d.slice(0, 4)} ${d.slice(4, 7)} ${d.slice(7)}`;
  if (/^0\d{10}$/.test(d)) return `${d.slice(0, 3)} ${d.slice(3, 7)} ${d.slice(7)}`;
  return d;
}
function phoneView(value) {
  const lines = String(value || "").split("\n").filter((x) => x.trim());
  return lines.length ? `<div class="phone-view">${lines.map((l) => `<span class="ltr">${esc(fmtPhone(l))}</span>`).join("")}</div>` : "";
}
/** واژه‌های کم‌اطمینان یک فیلد؛ اگر صدا و زمان واژه موجود باشد، هر واژه دکمه پخش همان تکه است (data-lt). */
function lowWords(r, k) {
  const keys = k === "tech" ? TECH_KEYS : [k];
  const seen = new Set();  // یک واژه ممکن است در چند فیلد فنی همان بند تکرار شده باشد
  return keys.flatMap((x) => (r.low_confidence?.[x] || []).map((w, i) => [w, r.low_times?.[x]?.[i]]))
    .filter(([w, t]) => !seen.has(w + t) && seen.add(w + t))
    .map(([w, t]) => r.audio_available && t
      ? `<button class="lc-word" data-lt="${t.join(",")}" title="پخش همین واژه از ویس">${I.play}«${esc(w)}» <span class="seg-time" dir="ltr">${fmtClock(t[0])}</span></button>` : `«${esc(w)}»`);
}
function lowConfView(r, k) {
  const w = lowWords(r, k);
  return w.length ? `<div class="lowconf">${I.alert}<span>با اطمینان کم شنیده شد: ${w.join(" ")} — ${w.some((x) => x.startsWith("<button")) ? "روی هر واژه بزنید تا همان تکه پخش شود." : "با شنیدن این بخش بررسی کنید."}</span></div>` : "";
}
/** دکمه‌های پخش واژه کم‌اطمینان درون el را به پخش‌کننده audio وصل می‌کند. */
function bindLowWords(el, audio) {
  $$("[data-lt]", el).forEach((b) => b.onclick = (e) => { e.stopPropagation(); playSegment(audio, b.dataset.lt.split(",").map(Number)); });
}
function hasUndo(r) { return (r.edits || []).some((e) => !e.undone && UNDOABLE.has(e.action)); }

async function undoLast(id) {
  try {
    const rec = await api(`/api/records/${id}/undo`, { method: "POST" });
    toast("آخرین تغییر برگشت.", "ok");
    refreshStatus();
    if (reviewState.updateRow) reviewState.updateRow(rec);
    return rec;
  } catch (e) { toastErr(e); return null; }
}

/** ذخیره یک فیلد و نمایش اعلان «ذخیره شد» با امکان بازگشت. */
async function saveField(id, field, value) {
  const rec = await api(`/api/records/${id}`, { method: "PATCH", body: { values: { [field]: value } } });
  toast("ذخیره شد.", "ok", { label: "بازگشت", onClick: async () => { if (await undoLast(id)) refreshOpenRecord(id); } });
  if (reviewState.updateRow) reviewState.updateRow(rec);
  return rec;
}
function refreshOpenRecord(id) {
  const f = $("#focus");
  if (f && !f.hidden) renderFocus(false);
  else if ($("#drawer").classList.contains("open")) openRecord(id);
}

async function openRecord(id) {
  let r;
  try { r = await api(`/api/records/${id}`); } catch (e) { return toastErr(e); }
  const d = $("#drawer");
  const labels = Object.fromEntries((state.meta?.fields || []).map((f) => [f.key, f.label]));
  const v = r.values, vf = r.validation.fields || {};
  const locked = !!r.exported_at;
  const t = r.transcript || {};
  const ids = reviewState.visible || [];
  const idx = ids.indexOf(id);
  const fieldRow = (k) => {
    const fc = vf[k];
    const val = v[k] || "";
    const multi = MULTILINE.has(k) || val.length > 40;
    const ltr = k === "phone" || k.endsWith("date");
    const input = multi
      ? `<textarea class="input ${ltr ? "ltr" : ""}" rows="${Math.min(4, Math.max(1, Math.ceil(val.length / 48), val.split("\n").length))}" data-f="${k}" ${locked ? "disabled" : ""} placeholder="گفته نشده">${esc(val)}</textarea>`
      : `<input class="input ${ltr ? "ltr" : ""}" value="${esc(val)}" data-f="${k}" ${locked ? "disabled" : ""} placeholder="گفته نشده" ${ltr ? 'style="text-align:right"' : ""}>`;
    const ev = r.evidence[k] && r.evidence[k] !== val ? `<div class="evidence">از متن: «${esc(r.evidence[k])}»</div>` : "";
    const seg = r.audio_available && r.times?.[k] ? `<button class="btn sm ghost" data-seg="${k}" title="پخش همین بخش از ویس">${I.play} ${segTime(r.times[k])}</button>` : "";
    return `<div class="frow"><label>${esc(labels[k] || k)}</label><div class="fval">
      <div class="row">${input}${seg}${fc && fc.status !== "valid" ? chip(fc.status, FIELD_STATUS[fc.status]) : ""}
        ${DICT_FIELDS.has(k) && val && !locked ? `<button class="btn sm icon ghost" data-dict="${k}" title="افزودن به واژه‌نامه">${I.book}</button>` : ""}</div>
      ${k === "phone" ? phoneView(val) : ""}${lowConfView(r, k)}
      ${fc && fc.reasons?.length ? `<ul class="reasons ${fc.status}">${fc.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${fc && fc.suggestions?.length && !locked ? `<div class="suggest"><span class="muted">پیشنهادها:</span>${fc.suggestions.map((sg) => `<button data-accept="${k}" data-val="${esc(sg)}">${esc(sg)}</button>`).join("")}</div>` : ""}
      ${ev}</div></div>`;
  };
  const words = t.words || [];
  const rawHtml = words.length
    ? words.map((w) => `<span ${w.prob < 0.5 ? `class="lowword" title="احتمال تشخیص: ${fa(Math.round(w.prob * 100))}٪"` : ""}>${esc(w.word)}</span>`).join(" ")
    : esc(t.raw_text || "");
  const ACTION_LABEL = { edit: "اصلاح", accept: "پذیرش پیشنهاد", approve: "تأیید", reject: "رد", reopen: "بازگشایی", duplicate: "تصمیم تکرار", dictionary: "واژه‌نامه" };
  // همان ویس (مثلاً پس از ذخیره یک اصلاح): پخش‌کننده قبلی با همان جای پخش نگه داشته می‌شود
  const oldAudio = $("#dr-audio", d);
  const keepAudio = oldAudio && oldAudio.dataset.aid === String(r.audio_id) && r.audio_available ? oldAudio : null;
  if (oldAudio && !keepAudio) releaseAudio(oldAudio);
  if (keepAudio) keepAudio.remove();
  d.innerHTML = `
    <div class="drawer-h">
      <div class="title"><b title="${esc(r.original_name)}">${esc(r.original_name)}</b>
        <div class="row small" style="gap:6px">${recordChip(r)}${r.building_count > 1 ? chip("info plain", `ساختمان ${fa(r.building_index + 1)} از ${fa(r.building_count)}`) : ""}</div></div>
      <button class="btn sm icon ghost" id="dr-prev" ${idx > 0 ? "" : "disabled"} title="قبلی">${I.prev}</button>
      <button class="btn sm icon ghost" id="dr-next" ${idx >= 0 && idx < ids.length - 1 ? "" : "disabled"} title="بعدی">${I.next}</button>
      <button class="btn sm icon ghost" id="dr-close" title="بستن">${I.x}</button>
    </div>
    <div class="drawer-b">
      ${r.audio_available ? `<audio id="dr-audio" controls preload="metadata" data-aid="${r.audio_id}" src="/api/files/${r.audio_id}/audio"></audio>
        <div class="seg-buttons">${SEG_KEYS.filter(([k]) => fieldTime(r, k)).map(([k, l]) => `<button class="btn sm" data-segk="${k}">${I.play} ${l} ${segTime(fieldTime(r, k))}</button>`).join("")}</div>`
        : '<div class="muted small">فایل صوتی پاک شده است.</div>'}
      ${(r.validation.reasons || []).length ? `<div class="alert ${r.status === "ready" ? "ok" : r.status === "invalid" ? "err" : "warn"}">${r.status === "ready" ? I.ok : I.alert}<div class="alert-body"><b>${REC_STATUS[r.status] || ""}</b>
        <ul class="reasons">${r.validation.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>` : ""}
      <div><div class="section-title">${I.wave} متن ویس</div>
        <div class="transcript">${t.processed_text ? highlightTranscript(t.processed_text, t.clauses, r.building_index, r.building_count > 1) : '<span class="muted">متنی موجود نیست.</span>'}</div>
        <details class="tech-details"><summary class="small">جزئیات فنی متن</summary>
          <div class="legend">${["name", "phone", "address", "tech", "project", "followup"].map((c) => `<span><i style="background:var(--c-${c})"></i>${SEG_LABEL[c]}</span>`).join("")}</div>
          <div class="small muted" style="margin-top:6px">متن خام تشخیص گفتار ${words.length ? "(واژه‌های کم‌اطمینان زیرخط‌دار)" : ""}</div>
          <div class="transcript small" style="margin-top:4px">${rawHtml}</div>
          <div class="muted small" style="margin-top:4px">مدل: <span class="ltr">${esc(t.model || "")}</span></div></details></div>
      ${r.validation.duplicates?.length ? `<div><div class="section-title">${I.swap} ردیف‌های مشابه</div><div class="stack" style="gap:8px">
        ${r.validation.duplicates.map((dp) => `<div class="dup ${dp.level}"><div class="row between"><b>${esc(dp.ref)}</b>${chip(dp.level === "strong" ? "warn" : "info", dp.level === "strong" ? "احتمال تکرار زیاد" : "شباهت جزئی")}</div>
          <div class="small">${esc(dp.engineer_name)} — <span class="ltr">${esc(dp.phone)}</span> — ${esc(dp.address)}</div>
          <div class="muted small">${esc(dp.reasons.join("، "))}</div></div>`).join("")}
        ${!locked ? `<div class="row"><span class="small muted">تصمیم:</span>
          <button class="btn sm" data-dup="keep">${r.duplicate_decision === "keep" ? I.check : ""} تکراری نیست، نگه دار</button>
          <button class="btn sm danger" data-dup="skip">تکراری است، ثبت نشود</button></div>` : ""}</div></div>` : ""}
      ${(() => {
        const groups = DRAWER_GROUPS.map(([title, keys]) => {
          const shown = keys.filter((k) => title === "اطلاعات اصلی" || v[k] || (vf[k] && vf[k].status !== "valid"));
          return [title, shown, `<div class="fgroup"><div class="fgroup-h">${title}</div>${shown.map(fieldRow).join("")}</div>`];
        });
        // گروه‌هایی که چیزی ندارند یا فقط جزئیات فنی‌اند (اجزای آدرس)، پشت «جزئیات بیشتر» می‌روند
        const main = groups.filter(([t, s]) => s.length && t !== "اجزای آدرس").map((g) => g[2]).join("");
        const more = groups.filter(([t, s]) => s.length && t === "اجزای آدرس").map((g) => g[2]).join("");
        return main + (more ? `<details class="tech-details"><summary class="small">جزئیات بیشتر (اجزای آدرس)</summary>${more}</details>` : "");
      })()}
      <details><summary class="small">افزودن فیلد دیگر</summary><div class="row" style="margin-top:8px">
        <select class="select" id="dr-addf">${(state.meta?.fields || []).filter((f) => !v[f.key]).map((f) => `<option value="${f.key}">${esc(f.label)}</option>`).join("")}</select>
        <input class="input" id="dr-addv" placeholder="مقدار" style="flex:1"><button class="btn sm" id="dr-addb" ${locked ? "disabled" : ""}>${I.plus} افزودن</button></div></details>
      ${r.edits?.length ? `<details><summary class="small">${I.history} سابقه تغییرات (${fa(r.edits.length)})</summary><ul class="reasons small" style="margin-top:6px">
        ${r.edits.map((e) => `<li class="${e.undone ? "undone" : ""}">${esc(e.at.replace("T", " "))} — ${esc(ACTION_LABEL[e.action] || e.action)}${e.field !== "*" ? ` «${esc(labels[e.field] || e.field)}»` : ""}: «${esc(e.old_value || "")}» ← «${esc(e.new_value || "")}»${e.undone ? " (برگشت داده شد)" : ""}</li>`).join("")}</ul></details>` : ""}
    </div>
    <div class="drawer-f">${locked ? `<div class="alert info" style="flex:1">${I.info}<div class="alert-body">این ردیف در ردیف ${fa(r.export_row)} فایل اکسل ثبت شده است. برای تغییر، اول آن ثبت را از <a href="#/history">تاریخچه ثبت‌ها</a> برگردانید.</div></div>`
      : `${r.review_state !== "approved" ? `<button class="btn ok lg" id="dr-approve">${I.check} تأیید برای ثبت</button>` : `<button class="btn" id="dr-reopen">بازگشت به بررسی</button>`}
        ${r.review_state !== "rejected" ? `<button class="btn danger" id="dr-reject">${I.x} رد</button>` : ""}
        ${hasUndo(r) ? `<button class="btn ghost" id="dr-undo" title="بازگشت آخرین تغییر">${I.retry} بازگشت</button>` : ""}
        <label class="check small" style="margin-inline-start:auto"><input type="checkbox" id="dr-dict" checked> نام تأییدشده به واژه‌نامه اضافه شود</label>`}</div>`;
  if (keepAudio) $("#dr-audio", d).replaceWith(keepAudio);
  d.classList.add("open");
  $("#drawer-backdrop").hidden = false;
  d.setAttribute("aria-hidden", "false");

  const reload = async (rec) => {
    if (reviewState.updateRow && rec) reviewState.updateRow(rec);
    await openRecord(id);
  };
  const audio = $("#dr-audio");
  $$("[data-seg]", d).forEach((b) => b.onclick = () => playSegment(audio, r.times[b.dataset.seg]));
  $$("[data-segk]", d).forEach((b) => b.onclick = () => playSegment(audio, fieldTime(r, b.dataset.segk)));
  bindLowWords(d, audio);
  $("#dr-close").onclick = closeDrawer;
  $("#dr-prev").onclick = () => idx > 0 && openRecord(ids[idx - 1]);
  $("#dr-next").onclick = () => idx < ids.length - 1 && openRecord(ids[idx + 1]);
  $("#dr-undo")?.addEventListener("click", async () => { if (await undoLast(id)) openRecord(id); });
  $$("[data-f]", d).forEach((inp) => inp.addEventListener("change", async () => {
    try { reload(await saveField(id, inp.dataset.f, inp.value)); } catch (e) { toastErr(e); }
  }));
  $$("[data-accept]", d).forEach((b) => b.onclick = async () => {
    try { const rec = await api(`/api/records/${id}/accept`, { method: "POST", body: { field: b.dataset.accept, value: b.dataset.val } }); toast("پیشنهاد پذیرفته شد.", "ok"); reload(rec); }
    catch (e) { toastErr(e); }
  });
  $$("[data-dict]", d).forEach((b) => b.onclick = async () => {
    try { const rec = await api(`/api/records/${id}/dictionary`, { method: "POST", body: { field: b.dataset.dict } }); toast("به واژه‌نامه اضافه شد.", "ok"); reload(rec); }
    catch (e) { toastErr(e); }
  });
  $$("[data-dup]", d).forEach((b) => b.onclick = async () => {
    try { const rec = await api(`/api/records/${id}/duplicate`, { method: "POST", body: { decision: b.dataset.dup } }); refreshStatus(); reload(rec); }
    catch (e) { toastErr(e); }
  });
  $("#dr-addb")?.addEventListener("click", async () => {
    const k = $("#dr-addf").value, val = $("#dr-addv").value.trim();
    if (!val) return;
    try { reload(await saveField(id, k, val)); } catch (e) { toastErr(e); }
  });
  const act = async (action) => {
    try {
      const rec = await api(`/api/records/${id}/action`, { method: "POST", body: { action, add_to_dictionary: $("#dr-dict")?.checked || false } });
      toast(action === "approve" ? "تأیید شد." : action === "reject" ? "رد شد." : "به بررسی برگشت.", "ok",
        { label: "بازگشت", onClick: () => undoLast(id) });
      refreshStatus();
      if (reviewState.updateRow) reviewState.updateRow(rec);
      if ((action === "approve" || action === "reject") && idx >= 0 && idx < ids.length - 1) openRecord(ids[idx + 1]);
      else { closeDrawer(); reviewState.reload && reviewState.reload(); }
    } catch (e) { toastErr(e); }
  };
  $("#dr-approve")?.addEventListener("click", async () => {
    if (r.status !== "ready" && !(await confirmBox("تأیید ردیف دارای هشدار", `این ردیف هنوز هشدار دارد:<ul class="reasons review">${(r.validation.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>آیا اطلاعات را با ویس بررسی کرده‌اید و تأیید می‌کنید؟`, "بله، تأیید می‌کنم", "ok"))) return;
    act("approve");
  });
  $("#dr-reject")?.addEventListener("click", () => act("reject"));
  $("#dr-reopen")?.addEventListener("click", () => act("reopen"));
}

// ---------- بررسی سریع (یک ردیف در هر صفحه، با صفحه‌کلید) ----------
const focusState = { ids: [], idx: 0, rec: null, saving: Promise.resolve() };
const FOCUS_FIELDS = [["engineer_name", "نام مهندس / شخص تماس", false], ["phone", "شماره تماس", true],
  ["address", "آدرس", false], ["project_name", "نام پروژه", false]];
const FOCUS_TECH = [["structure_type", "نوع سازه"], ["floors", "تعداد سقف"], ["executed", "سقف‌های اجراشده"], ["stage", "مرحله ساخت"]];

function focusEl() {
  let f = $("#focus");
  if (!f) {
    f = document.createElement("div");
    f.id = "focus";
    f.className = "focus";
    f.hidden = true;
    f.setAttribute("role", "dialog");
    f.setAttribute("aria-label", "بررسی سریع");
    document.body.appendChild(f);
  }
  return f;
}

async function openFocus(ids, startIdx = 0) {
  if (!ids.length) return toast("ردیفی برای بررسی نیست.");
  focusState.ids = ids.slice();
  focusState.idx = Math.max(0, Math.min(startIdx, ids.length - 1));
  focusEl().hidden = false;
  document.body.classList.add("no-scroll");
  await renderFocus(true);
}
function closeFocus() {
  const f = $("#focus");
  if (!f || f.hidden) return;
  $("#fm-audio")?.pause();
  f.hidden = true;
  document.body.classList.remove("no-scroll");
  if (reviewState.reload) reviewState.reload();
}

async function renderFocus(autoplay = false) {
  const f = focusEl();
  const id = focusState.ids[focusState.idx];
  let r;
  try { r = await api(`/api/records/${id}`); } catch (e) { toastErr(e); return closeFocus(); }
  focusState.rec = r;
  const vf = r.validation.fields || {}, v = r.values;
  const locked = !!r.exported_at;
  const t = r.transcript || {};
  const fieldBox = (k, label, ltr) => {
    const fc = vf[k], val = v[k] || "";
    const key = SEG_KEYS.findIndex(([x]) => x === k);
    const big = k === "phone" || k === "address";
    return `<div class="fm-field">
      <div class="row between"><label>${esc(label)}</label>
        <span class="row" style="gap:6px">${fc ? chip(fc.status, FIELD_STATUS[fc.status]) : ""}
        ${r.audio_available && fieldTime(r, k) ? `<button class="btn sm" data-fseg="${k}">${I.play} پخش ${segTime(fieldTime(r, k))}${key >= 0 ? ` <span class="kbd">Alt+${fa(key + 1)}</span>` : ""}</button>` : ""}</span></div>
      ${big
        ? `<textarea class="input big ${ltr ? "ltr" : ""}" rows="${Math.max(1, val.split("\n").length)}" data-ff="${k}" data-orig="${esc(val)}" ${locked ? "disabled" : ""} placeholder="گفته نشده">${esc(val)}</textarea>`
        : `<input class="input big" value="${esc(val)}" data-ff="${k}" data-orig="${esc(val)}" ${locked ? "disabled" : ""} placeholder="گفته نشده">`}
      ${k === "phone" ? phoneView(val) : ""}${lowConfView(r, k)}
      ${fc && fc.status !== "valid" && fc.reasons?.length ? `<ul class="reasons ${fc.status}">${fc.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${fc && fc.suggestions?.length && !locked ? `<div class="suggest"><span class="muted">پیشنهاد:</span>${fc.suggestions.map((sg) => `<button data-faccept="${k}" data-val="${esc(sg)}">${esc(sg)}</button>`).join("")}</div>` : ""}
    </div>`;
  };
  const pos = `${fa(focusState.idx + 1)} از ${fa(focusState.ids.length)}`;
  f.innerHTML = `<div class="fm-wrap">
    <div class="fm-head">
      <div><b>بررسی سریع</b> <span class="muted">— ردیف ${pos}</span>
        <div class="row small" style="gap:6px">${recordChip(r)}<span class="muted" title="${esc(r.original_name)}">${esc(r.original_name)}</span>
          ${r.building_count > 1 ? chip("info plain", `ساختمان ${fa(r.building_index + 1)} از ${fa(r.building_count)}`) : ""}</div></div>
      <div class="progress" style="flex:1; max-width:260px"><div class="progress-bar" style="width:${Math.round(100 * (focusState.idx + 1) / focusState.ids.length)}%"></div></div>
      <label class="check small"><input type="checkbox" id="fm-autoplay" ${localStorage.getItem("v2x.focus.autoplay") !== "0" ? "checked" : ""}> پخش خودکار شماره</label>
      <button class="btn ghost" id="fm-close">${I.x} خروج <span class="kbd">Esc</span></button>
    </div>
    <div class="fm-body">
      <div class="fm-side">
        ${r.audio_available ? `<audio id="fm-audio" controls preload="auto" src="/api/files/${r.audio_id}/audio"></audio>
          <div class="seg-buttons">${SEG_KEYS.filter(([k]) => fieldTime(r, k)).map(([k, l]) => `<button class="btn sm" data-fsegk="${k}">${I.play} ${l} ${segTime(fieldTime(r, k))}</button>`).join("")}
            <button class="btn sm ghost" id="fm-whole">${I.wave} کل ویس <span class="kbd">Ctrl+Space</span></button></div>`
          : '<div class="muted small">فایل صوتی پاک شده است.</div>'}
        <div class="transcript">${t.processed_text ? highlightTranscript(t.processed_text, t.clauses, r.building_index, r.building_count > 1) : '<span class="muted">متنی موجود نیست.</span>'}</div>
        ${(r.validation.reasons || []).length && r.status !== "ready" ? `<ul class="reasons review small">${r.validation.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        <div class="fm-tech">${FOCUS_TECH.map(([k, l]) => `<div class="field"><label>${l}</label><input class="input" value="${esc(v[k] || "")}" data-ff="${k}" data-orig="${esc(v[k] || "")}" ${locked ? "disabled" : ""} placeholder="—"></div>`).join("")}
          <div class="field fm-wide"><label>توضیحات</label><textarea class="input" rows="2" data-ff="notes" data-orig="${esc(v.notes || "")}" ${locked ? "disabled" : ""} placeholder="—">${esc(v.notes || "")}</textarea></div></div>
      </div>
      <div class="fm-main">${FOCUS_FIELDS.map(([k, l, ltr]) => fieldBox(k, l, ltr)).join("")}</div>
    </div>
    <div class="fm-foot">
      ${locked ? `<span class="muted">این ردیف در اکسل ثبت شده است.</span>` : `
      <button class="btn ok lg" id="fm-approve">${I.check} تأیید و بعدی <span class="kbd">Ctrl+Enter</span></button>
      <button class="btn danger" id="fm-reject">${I.x} رد <span class="kbd">Ctrl+Delete</span></button>
      <button class="btn ghost" id="fm-undo" ${hasUndo(r) ? "" : "disabled"}>${I.retry} بازگشت <span class="kbd">Ctrl+Z</span></button>`}
      <span class="spacer"></span>
      <button class="btn" id="fm-prev" ${focusState.idx > 0 ? "" : "disabled"}>${I.prev} قبلی <span class="kbd">PgUp</span></button>
      <button class="btn" id="fm-next" ${focusState.idx < focusState.ids.length - 1 ? "" : "disabled"}>بعدی ${I.next} <span class="kbd">PgDn</span></button>
    </div></div>`;
  const audio = $("#fm-audio");
  $$("[data-fseg]", f).forEach((b) => b.onclick = () => playSegment(audio, fieldTime(r, b.dataset.fseg)));
  $$("[data-fsegk]", f).forEach((b) => b.onclick = () => playSegment(audio, fieldTime(r, b.dataset.fsegk)));
  bindLowWords(f, audio);
  $("#fm-whole")?.addEventListener("click", () => playWhole(audio));
  $("#fm-autoplay").onchange = (e) => localStorage.setItem("v2x.focus.autoplay", e.target.checked ? "1" : "0");
  $("#fm-close").onclick = closeFocus;
  $("#fm-prev").onclick = () => focusGo(-1);
  $("#fm-next").onclick = () => focusGo(1);
  $("#fm-approve")?.addEventListener("click", () => focusAct("approve"));
  $("#fm-reject")?.addEventListener("click", () => focusAct("reject"));
  $("#fm-undo")?.addEventListener("click", async () => { if (await undoLast(r.id)) renderFocus(false); });
  $$("[data-ff]", f).forEach((inp) => inp.addEventListener("change", () => focusSave(inp)));
  $$("[data-faccept]", f).forEach((b) => b.onclick = async () => {
    try { await api(`/api/records/${r.id}/accept`, { method: "POST", body: { field: b.dataset.faccept, value: b.dataset.val } }); renderFocus(false); }
    catch (e) { toastErr(e); }
  });
  // پخش خودکار بخش شماره: سریع‌ترین راه تأیید رقم‌ها
  if (autoplay && audio && fieldTime(r, "phone") && localStorage.getItem("v2x.focus.autoplay") !== "0") playSegment(audio, fieldTime(r, "phone"));
}

function focusSave(inp) {
  if (inp.value === inp.dataset.orig) return focusState.saving;
  const id = focusState.rec.id, field = inp.dataset.ff, value = inp.value;
  inp.dataset.orig = value;
  focusState.saving = focusState.saving.then(() => saveField(id, field, value)).catch(toastErr);
  return focusState.saving;
}
async function focusFlush() {
  $$("#focus [data-ff]").forEach((inp) => focusSave(inp));
  await focusState.saving;
}
async function focusGo(step) {
  await focusFlush();
  const n = focusState.idx + step;
  if (n < 0 || n >= focusState.ids.length) return;
  focusState.idx = n;
  renderFocus(true);
}
async function focusAct(action) {
  await focusFlush();
  const id = focusState.rec.id;
  try {
    await api(`/api/records/${id}/action`, { method: "POST", body: { action, add_to_dictionary: action === "approve" } });
    toast(action === "approve" ? "تأیید شد." : "رد شد.", "ok", { label: "بازگشت", onClick: () => undoLast(id) });
    refreshStatus();
  } catch (e) { return toastErr(e); }
  if (focusState.idx < focusState.ids.length - 1) { focusState.idx++; renderFocus(true); }
  else { toast("همه ردیف‌های این فهرست بررسی شد.", "ok"); closeFocus(); }
}

document.addEventListener("keydown", (e) => {
  const f = $("#focus");
  if (!f || f.hidden || !$("#modal-backdrop").hidden) return;
  const inField = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
  const audio = $("#fm-audio");
  const keyIdx = { Digit1: 0, Digit2: 1, Digit3: 2, Digit4: 3, Numpad1: 0, Numpad2: 1, Numpad3: 2, Numpad4: 3 }[e.code];
  if (e.key === "Escape") { e.preventDefault(); closeFocus(); }
  else if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); focusAct("approve"); }
  else if (e.ctrlKey && e.key === "Delete") { e.preventDefault(); focusAct("reject"); }
  else if (e.ctrlKey && e.code === "Space") { e.preventDefault(); playWhole(audio); }
  else if (e.altKey && keyIdx !== undefined) { e.preventDefault(); playSegment(audio, fieldTime(focusState.rec, SEG_KEYS[keyIdx][0])); }
  else if (e.key === "PageDown") { e.preventDefault(); focusGo(1); }
  else if (e.key === "PageUp") { e.preventDefault(); focusGo(-1); }
  else if (e.ctrlKey && e.code === "KeyZ" && !inField) { e.preventDefault(); undoLast(focusState.rec.id).then((r) => r && renderFocus(false)); }
});

// ================= تنظیمات فایل =================
/** ستون‌ها، شکل نوشتن مقادیر، رنگ ردیف‌ها و ظاهر یک فایل: «فایلی که دارید» (ظاهرش دست نمی‌خورد) یا «فایل تازه» (ظاهر دلخواه). */
const COMPANY = "default";
const tplState = { name: null, tab: null, dirty: false, rows: [], colors: [], target: "" };
const VALUE_OPTS = {
  date_format: [["auto", "مثل ردیف‌های قبلی همین فایل"], ["", "1405/07/28"], ["compact", "1405/7/28"], ["persian", "۱۴۰۵/۰۷/۲۸"], ["long", "۲۸ مهر ۱۴۰۵"]],
  phone_format: [["text_leading_zero", "با صفر اول (09151234567)"], ["as_number_like_existing", "بدون صفر اول (9151234567)"]],
  multi_phone_separator: [["\n", "هر شماره در یک خط همان خانه"], [" ، ", "پشت سر هم با « ، »"], [" / ", "پشت سر هم با « / »"]],
  name_title: [["keep", "با عنوان (مهندس رجبی)"], ["drop", "بدون عنوان (رجبی)"]],
};
const NOTE_PARTS = [["technical_summary", "خلاصه فنی"], ["project_name", "نام پروژه"], ["building_type", "نوع ساختمان"], ["permit_status", "وضعیت مجوز"],
  ["customer_need", "نیاز مشتری"], ["notes", "توضیحات تکمیلی"], ["followup", "پیگیری"]];
const HELP = {
  append: "ردیف‌های تازه به انتهای یک فایل اکسل موجود (مثل فایل اصلی شرکت) اضافه می‌شوند. ستون‌ها، ترتیب و ظاهر همان فایل می‌ماند و ردیف‌های قبلی دست نمی‌خورند.",
  new: "برنامه یک فایل اکسل تازه می‌سازد و ستون‌ها، ترتیب و رنگ‌هایش را خودتان تعیین می‌کنید؛ مثلاً یک گزارش جدا برای مدیر.",
  columns_append: "برای هر ستون فایل مشخص کنید چه اطلاعاتی در آن نوشته شود. «نوشته نشود» یعنی خانه خالی می‌ماند؛ «محافظت‌شده» یعنی برنامه هرگز به آن ستون دست نمی‌زند (مثلاً ستونی که همکاران دستی پر می‌کنند).",
  columns_new: "ستون‌های فایل تازه به همین ترتیب ساخته می‌شوند؛ با کشیدن ☰ یا فلش‌ها ترتیب را عوض کنید.",
  values: "شکل نوشتن تاریخ، شماره تلفن، نام و آدرس در خانه‌های اکسل. روی خود اطلاعات استخراج‌شده اثری ندارد.",
  colors: "ردیف‌هایی که یکی از این شرایط را دارند با رنگ مشخص در اکسل ثبت می‌شوند تا زودتر به چشم بیایند.",
  header_row: "شماره ردیفی که عنوان ستون‌ها در آن نوشته شده است (معمولاً ۱).",
  split: "همه ردیف‌ها در یک فایل جمع شوند، یا برای هر ماه یا هر روز فایل یا شیت جدا ساخته شود.",
};
const help = (k) => `<span class="help" tabindex="0" role="note" aria-label="${esc(HELP[k])}" data-tip="${esc(HELP[k])}">؟</span>`;
const ART_APPEND = `<svg viewBox="0 0 120 84" aria-hidden="true"><rect x="8" y="4" width="104" height="76" rx="7" class="a-paper"/>
  <path d="M8 11a7 7 0 0 1 7-7h90a7 7 0 0 1 7 7v7H8z" class="a-head"/>${[25, 35, 45].map((y) => `<rect x="16" y="${y}" width="88" height="6" rx="3" class="a-row"/>`).join("")}
  ${[56, 66].map((y) => `<rect x="16" y="${y}" width="70" height="6" rx="3" class="a-new"/>`).join("")}<circle cx="100" cy="66" r="9" class="a-badge"/><path d="M100 61.5v9M95.5 66h9" class="a-plus"/></svg>`;
const ART_NEW = `<svg viewBox="0 0 120 84" aria-hidden="true"><rect x="8" y="4" width="104" height="76" rx="7" class="a-paper"/>
  <path d="M8 11a7 7 0 0 1 7-7h90a7 7 0 0 1 7 7v7H8z" class="a-head-new"/><path d="M42 4v76M76 4v76" class="a-grid"/>
  ${[25, 37, 49, 61].map((y, i) => `<rect x="12" y="${y}" width="96" height="9" rx="2" class="${i % 2 ? "a-zebra" : "a-row-new"}"/>`).join("")}
  <circle cx="100" cy="70" r="9" class="a-badge"/><path d="M100 65.5v9M95.5 70h9" class="a-plus"/></svg>`;

function destInfo(meta, name) {
  return meta.templates.find((t) => t.name === name)
    || (name === COMPANY ? { name: COMPANY, mode: "append", title: "فایل شرکت", target: "", active: false, confirmed: false } : null);
}
// نام فایل لاتین (مثل sample-company.xlsx) وسط جمله فارسی جدا نمایش داده شود تا جابه‌جا و شکسته نشود
const fname = (s) => `<bdi class="fname">${esc(s)}</bdi>`;
const destKind = (t) => t.mode === "new" ? "فایل تازه که برنامه می‌سازد" : "فایل اکسلی که دارید";
function destChoicesHtml() {
  return `<div class="choice-grid">
      <button class="choice" data-choice="append"><span class="choice-art">${ART_APPEND}</span><b>به فایل اکسلی که دارم اضافه شود</b>
        <span>ردیف‌های تازه به انتهای فایل موجود (مثل فایل اصلی شرکت) اضافه می‌شوند. ستون‌ها و ظاهر همان فایل می‌ماند.</span></button>
      <button class="choice" data-choice="new"><span class="choice-art">${ART_NEW}</span><b>یک فایل اکسل تازه ساخته شود</b>
        <span>ستون‌ها، ترتیب و رنگ‌ها را خودتان می‌چینید؛ مثلاً یک گزارش جدا برای مدیر.</span></button></div>
    <div class="small muted" style="margin-top:14px">تنظیمات یک فایل را از رایانه دیگر آورده‌اید؟ <button class="linkbtn" data-choice="import">وارد کردن فایل تنظیمات (.json)</button></div>`;
}

async function renderTemplates(el) {
  const seq = routeSeq;
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  if (q.get("dest")) { tplState.name = q.get("dest"); tplState.tab = q.get("tab"); tplState.dirty = false; history.replaceState(null, "", "#/templates"); }
  if (!tplState.name) { location.hash = "#/files"; return; }
  let meta, dest;
  try { [meta, dest] = await Promise.all([api("/api/templates"), api(`/api/dests/${encodeURIComponent(tplState.name)}`)]); }
  catch (e) { toastErr(e); tplState.name = null; location.hash = "#/files"; return; }
  if (seq !== routeSeq) return;
  state.tplMeta = meta;
  $("#page-title").textContent = `تنظیمات «${destLabel(dest)}»`;
  $("#tb-page").textContent = destLabel(dest);
  setCrumbs([{ label: PAGES.files.title, href: "#/files" }, { label: destLabel(dest), href: fileHref(tplState.name) }, { label: "تنظیمات فایل" }]);
  el.innerHTML = `<div id="dv-bar" class="fw-head"></div><div class="card" id="dv-editor" style="margin-top:18px"><div class="card-b"><span class="spinner"></span></div></div>`;
  fileBar($("#dv-bar"), dest, () => renderTemplates(el), "settings");

  // ---------- تنظیمات مقصد انتخاب‌شده (زبانه‌های یکسان برای هر دو نوع) ----------
  const info = destInfo(meta, tplState.name);
  const isNew = info.mode === "new";
  const savedProf = isNew ? null : (await api(`/api/excel/profile?name=${encodeURIComponent(info.name)}`)).profile;
  const draft = isNew ? (await api(`/api/templates/${info.name}`)).template
    : savedProf ? JSON.parse(JSON.stringify(savedProf)) : { name: info.name, excel_path: "", columns: {}, protected: [], policy: {} };
  if (seq !== routeSeq) return;
  draft.policy = draft.policy || {};
  let report = null;  // گزارش خواندن فایل موجود (شیت‌ها و عنوان ستون‌ها)
  const hasFile = () => isNew || !!draft.excel_path;
  const fileName = () => (draft.excel_path || "").split(/[\\/]/).pop();
  const TABS = [["columns", "ستون‌ها"], ["values", "شکل نوشتن مقادیر"], ["colors", "رنگ ردیف‌ها"], ["style", "ظاهر"], ["output", isNew ? "فایل و پوشه" : "فایل"]];
  if (!TABS.some(([k]) => k === tplState.tab)) tplState.tab = hasFile() ? "columns" : "output";
  const ed = $("#dv-editor");
  ed.innerHTML = `<div class="card-h"><div class="stack" style="gap:3px"><span class="dc-kind">${destKind(info)} ${help(isNew ? "new" : "append")}</span>
        <h2>${I.edit} ستون‌ها و شکل نوشتن</h2></div>
      <div class="row">
        <button class="btn" id="tp-show" title="جدول نمونه با ستون‌ها، ترتیب و ظاهر همین فایل">${I.eye} پیش‌نمایش</button>
        ${isNew ? `<button class="btn ghost" id="tp-like" title="ستون‌ها و ظاهر را از یک فایل اکسل دیگر بردارد">${I.table} مثل فایل دیگر…</button>
          <a class="btn ghost" href="/api/templates/${esc(info.name)}/export" title="برای استفاده در رایانه دیگر (پوشه فایل همراهش نیست)">${I.down} ذخیره تنظیمات برای رایانه دیگر</a>
          <input type="file" id="tp-like-file" accept=".xlsx,.xlsm" hidden>` : ""}
        <button class="btn ghost icon" id="tp-del" title="${dest.auto ? "ویس‌های گوشی و پوشه ورودی به این فایل می‌آیند؛ اول فایل دیگری را برای آن‌ها انتخاب کنید" : "برداشتن این فایل از فهرست (خود فایل اکسل پاک نمی‌شود)"}" ${dest.auto ? "disabled" : ""}>${I.trash}</button></div></div>
    <div class="card-b" style="padding-bottom:0"><div class="tabs" id="tp-tabs">${TABS.map(([k, l]) => `<button data-tt="${k}" class="${k === tplState.tab ? "active" : ""}">${l}</button>`).join("")}</div></div>
    <div class="card-b" id="tp-tab"></div>
    ${isNew ? `<div class="card-b" style="border-top:1px solid var(--border)"><div class="row between"><b>پیش‌نمایش زنده</b><span class="small muted">چند ردیف از ردیف‌های اخیر، با همین تنظیمات</span></div>
      <div class="tp-preview" id="tp-preview"></div></div>` : ""}
    <div class="save-bar" id="dv-savebar"><span id="dv-save-msg"></span><div class="row">
      ${isNew ? `<button class="btn ghost" id="tp-sample">${I.down} دریافت فایل نمونه</button>` : ""}
      <button class="btn ghost" id="dv-discard">لغو تغییرات</button><button class="btn primary" id="tp-save">${I.check} ذخیره</button></div></div>`;
  const setTab = (k) => { tplState.tab = k; $$("[data-tt]", ed).forEach((x) => x.classList.toggle("active", x.dataset.tt === k)); drawTab(); };
  $$("[data-tt]", ed).forEach((b) => b.onclick = () => setTab(b.dataset.tt));
  const drawSaveBar = () => {
    $("#dv-savebar").classList.toggle("dirty", tplState.dirty);
    $("#dv-save-msg").innerHTML = tplState.dirty ? `${I.alert} تغییرات ذخیره نشده` : `<span class="muted">${I.check} همه تغییرات ذخیره شده</span>`;
    $("#dv-discard").hidden = !tplState.dirty;
    $("#tp-save").disabled = !tplState.dirty;
    $("#tp-show").disabled = !hasFile();
  };
  const changed = (values = false) => { tplState.dirty = true; drawSaveBar(); if (!isNew) return; if (values) loadPreview(); else drawPreview(); };
  const loadPreview = debounce(async () => {
    if (!isNew) return;
    try { const p = await api("/api/templates/preview", { method: "POST", body: draft }); tplState.rows = p.rows; tplState.colors = p.colors || []; tplState.target = p.target;
      const tn = $("#tp-target-name"); if (tn) tn.textContent = p.target; drawPreview(); }
    catch (e) { const b = $("#tp-preview"); if (b) b.innerHTML = `<div class="err-text small">${esc(e.message)}</div>`; }
  }, 300);
  function drawPreview() {
    const box = $("#tp-preview");
    if (box) box.innerHTML = sheetHtml(draft.style, draft.columns_list, tplState.rows, tplState.colors);
  }

  // فایل موجود: خواندن شیت‌ها و عنوان ستون‌ها؛ فایل تازه = پیشنهاد ستون‌ها از روی عنوان‌ها
  async function inspect(path) {
    if (!path) return toast("مسیر فایل اکسل را وارد یا انتخاب کنید.");
    const fresh = !savedProf || savedProf.excel_path !== path;
    report = null;
    if (tplState.tab === "output") drawTab();
    try {
      const res = await api("/api/excel/inspect", { method: "POST", body: { path, name: info.name } });
      report = res.report;
      if (fresh && res.profile) {
        for (const k of Object.keys(draft)) delete draft[k];
        Object.assign(draft, JSON.parse(JSON.stringify(res.profile)));
        changed();
        toast("ستون‌های فایل خوانده شد و پیشنهاد ستون‌ها آماده است. بررسی کنید و «ذخیره» را بزنید.", "ok");
        setTab("columns");
        return;
      }
    } catch (e) { report = { error: e.message }; }
    if (["output", "columns"].includes(tplState.tab)) drawTab();
  }
  const browse = async () => {
    const cur = ($("#x-path")?.value || draft.excel_path || "").trim();
    const p = await pickPath("excel", cur ? cur.replace(/[\\/][^\\/]*$/, "") : "");
    if (p) { if ($("#x-path")) $("#x-path").value = p; inspect(p); }
  };
  const needFile = (box) => {
    box.innerHTML = `<div class="empty">${I.table}<div>اول فایل اکسل موجود را انتخاب کنید تا ستون‌هایش خوانده شود.</div>
      <button class="btn primary" id="x-go-file">${I.folder} انتخاب فایل</button></div>`;
    $("#x-go-file").onclick = () => { setTab("output"); browse(); };
  };

  function drawTab() {
    const box = $("#tp-tab"), t = tplState.tab, P = draft.policy;
    if (!box) return;
    if (!hasFile() && t !== "output") return needFile(box);
    if (t === "columns" && isNew) {
      const used = new Set(draft.columns_list.map((c) => c.field));
      box.innerHTML = `<div class="small muted" style="margin-bottom:10px">${help("columns_new")} ستون‌های فایل به همین ترتیب از راست ساخته می‌شوند.</div>
        <div class="tp-cols">${draft.columns_list.map((c, i) => `<div class="tp-col" draggable="true" data-ci="${i}">
          <span class="tp-drag" title="برای جابه‌جایی بکشید">☰</span><b class="tp-letter">${columnLetter(i)}</b>
          <select class="select sm tp-flabel" data-cf title="چه اطلاعاتی در این ستون نوشته شود">${state.tplMeta.fields.map((f) => `<option value="${f.key}" ${f.key === c.field ? "selected" : ""}>${esc(f.label)}</option>`).join("")}</select>
          <input class="input sm" data-ck="title" value="${esc(c.title)}" title="عنوان ستون">
          ${c.field === "constant" ? `<input class="input sm" data-ck="value" value="${esc(c.value || "")}" placeholder="مقدار ثابت">` : ""}
          <label class="small muted">عرض <input class="input sm" type="number" min="4" max="120" data-ck="width" value="${c.width}" style="width:64px"></label>
          <select class="select sm" data-ck="align">${Object.entries(state.tplMeta.aligns).map(([k, l]) => `<option value="${k}" ${c.align === k ? "selected" : ""}>${l}</option>`).join("")}</select>
          <button class="btn sm icon ghost" data-cmove="-1" title="بالا">${I.prev}</button><button class="btn sm icon ghost" data-cmove="1" title="پایین">${I.next}</button>
          <button class="btn sm icon ghost" data-crm title="حذف ستون">${I.x}</button></div>`).join("")}</div>
        <div class="row" style="margin-top:10px"><select class="select" id="tp-addf">${state.tplMeta.fields.filter((f) => f.key === "constant" || !used.has(f.key)).map((f) => `<option value="${f.key}">${esc(f.label)}</option>`).join("")}</select>
          <button class="btn" id="tp-add">${I.plus} افزودن ستون</button></div>`;
      $$(".tp-col", box).forEach((row) => {
        const i = +row.dataset.ci, col = draft.columns_list[i];
        $$("[data-ck]", row).forEach((inp) => inp.oninput = () => { col[inp.dataset.ck] = inp.dataset.ck === "width" ? +inp.value : inp.value; changed(inp.dataset.ck === "value"); });
        $("[data-cf]", row).onchange = (e) => {
          col.field = e.target.value;
          if (col.field === "constant") col.value = col.value || ""; else delete col.value;
          drawTab(); changed(true);
        };
        $$("[data-cmove]", row).forEach((b) => b.onclick = () => moveCol(i, i + +b.dataset.cmove));
        $("[data-crm]", row).onclick = () => { if (draft.columns_list.length > 1) { draft.columns_list.splice(i, 1); drawTab(); changed(true); } };
        row.ondragstart = (e) => e.dataTransfer.setData("text/plain", String(i));
        row.ondragover = (e) => { e.preventDefault(); row.classList.add("over"); };
        row.ondragleave = () => row.classList.remove("over");
        row.ondrop = (e) => { e.preventDefault(); moveCol(+e.dataTransfer.getData("text/plain"), i); };
      });
      $("#tp-add").onclick = () => {
        const f = $("#tp-addf").value;
        draft.columns_list.push({ field: f, title: uniqueTitle(fieldLabel(f)), width: 18, align: "right", ...(f === "constant" ? { value: "" } : {}) });
        drawTab(); changed(true);
      };
    } else if (t === "columns") {
      if (!report) { box.innerHTML = `<div class="row"><span class="spinner"></span> در حال خواندن ستون‌های «${esc(fileName())}»…</div>`; return; }
      if (report.error) { box.innerHTML = `<div class="alert err">${I.alert}<div class="alert-body"><b>فایل خوانده نشد</b>${esc(report.error)}</div><button class="btn sm" id="x-go-file">زبانه «فایل»</button></div>`; $("#x-go-file").onclick = () => setTab("output"); return; }
      const sheet = report.sheets.find((s) => s.name === draft.sheet) || report.sheets[0];
      const fields = state.meta.fields.concat(state.meta.computed).concat([{ key: "followup", label: "پیگیری (اقدام + تاریخ)" }]);
      const prot = new Set(draft.protected || []);
      const cur = (col) => draft.columns[col] || (prot.has(col) ? "__protect" : "");
      const opts = (col) => `<option value="" ${!cur(col) ? "selected" : ""}>— نوشته نشود (خالی می‌ماند) —</option>
        <option value="__protect" ${cur(col) === "__protect" ? "selected" : ""}>🔒 محافظت‌شده (برنامه هرگز دست نمی‌زند)</option>
        <optgroup label="اطلاعات ویس">${fields.map((f) => `<option value="${f.key}" ${cur(col) === f.key ? "selected" : ""}>${esc(f.label)}</option>`).join("")}</optgroup>`;
      const entries = Object.entries(sheet.headers);
      const filled = entries.filter(([c]) => draft.columns[c]).length;
      box.innerHTML = `<div class="stack">
        <div class="small muted">${help("columns_append")} برای هر ستونِ «${esc(fileName())}» مشخص کنید چه اطلاعاتی از ویس در آن نوشته شود. پیشنهاد اولیه از روی عنوان ستون‌ها ساخته شده است.</div>
        <div class="row"><div class="field"><label>شیت</label><select class="select" id="x-sheet">${report.sheets.map((s) => `<option ${s.name === sheet.name ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></div>
          <div class="field"><label>ردیف عنوان ${help("header_row")}</label><input class="input" id="x-hr" type="number" min="1" value="${draft.header_row}" style="width:100px"></div></div>
        <div class="table-wrap" style="border:1px solid var(--border); border-radius:12px"><table class="table"><thead><tr><th>ستون</th><th>عنوان در فایل</th><th>چه اطلاعاتی نوشته شود</th></tr></thead><tbody>
          ${entries.map(([col, h]) => `<tr class="${cur(col) ? "" : "map-empty"}"><td><b class="ltr">${esc(col)}</b></td><td>${esc(h).replace(/\n/g, " ")}</td>
            <td><select class="select map-select" data-col="${esc(col)}">${opts(col)}</select></td></tr>`).join("")}
        </tbody></table></div>
        <div class="small muted" id="x-map-count">${fa(filled)} ستون از ${fa(entries.length)} ستون پر می‌شود؛ بقیه خالی می‌مانند یا محافظت‌شده‌اند.</div></div>`;
      $$("[data-col]", box).forEach((s) => s.onchange = () => {
        const col = s.dataset.col;
        delete draft.columns[col];
        draft.protected = (draft.protected || []).filter((c) => c !== col);
        if (s.value === "__protect") draft.protected.push(col); else if (s.value) draft.columns[col] = s.value;
        s.closest("tr").classList.toggle("map-empty", !s.value);
        $("#x-map-count").textContent = `${fa(entries.filter(([c]) => draft.columns[c]).length)} ستون از ${fa(entries.length)} ستون پر می‌شود؛ بقیه خالی می‌مانند یا محافظت‌شده‌اند.`;
        changed();
      });
      $("#x-sheet").onchange = (e) => {
        const s = report.sheets.find((x) => x.name === e.target.value);
        Object.assign(draft, { sheet: s.name, header_row: s.header_row, headers: s.headers, columns: {}, protected: [] });
        drawTab(); changed();
      };
      $("#x-hr").oninput = (e) => { draft.header_row = +e.target.value || draft.header_row; changed(); };
    } else if (t === "values") {
      const sel = (k, def) => `<select class="select" data-pk="${k}">${VALUE_OPTS[k].filter(([v]) => !(isNew && v === "auto")).map(([v, l]) => `<option value="${esc(v)}" ${(P[k] ?? def) === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
      const ts = P.text_style || {};
      const auto = isNew ? [] : [["", "خودکار (مثل ردیف‌های همین فایل)"]];
      const tsSel = (k, opts, def) => `<select class="select" data-ts="${k}">${[...auto, ...opts].map(([v, l]) => `<option value="${esc(v)}" ${(P.text_style ? ts[k] : isNew ? def : "") === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
      box.innerHTML = `<div class="small muted" style="margin-bottom:12px">${help("values")} شکل نوشتن مقدارها در خانه‌های اکسل.</div>
        <div class="grid grid-2" style="gap:14px">
        <div class="field"><label>تاریخ</label>${sel("date_format", "")}</div>
        <div class="field"><label>نام مهندس</label>${sel("name_title", "keep")}</div>
        <div class="field"><label>شماره تلفن</label>${sel("phone_format", "text_leading_zero")}
          <label class="check small"><input type="checkbox" data-pk="phone_group" ${P.phone_group ? "checked" : ""}> گروه‌بندی رقم‌ها (0915 123 4567)</label></div>
        <div class="field"><label>چند شماره برای یک ساختمان</label>${sel("multi_phone_separator", "\n")}</div>
        <div class="field"><label>رقم‌ها در آدرس و توضیحات</label>${tsSel("digits", [["ascii", "انگلیسی (58)"], ["persian", "فارسی (۵۸)"]], "ascii")}</div>
        <div class="field"><label>جداکننده</label>${tsSel("sep", [[" ، ", "سجادیه 58 ، قطعه دوم"], ["، ", "سجادیه 58، قطعه دوم"], [" - ", "سجادیه 58 - قطعه دوم"]], " ، ")}</div>
        <div class="field" style="grid-column:1/-1"><label>چیدمان روزها</label><div class="row">
          <label class="check small"><input type="checkbox" data-pk="blank_row_between_dates" ${P.blank_row_between_dates ? "checked" : ""}> یک ردیف خالی میان روزهای بازدید</label>
          <label class="check small"><input type="checkbox" data-pk="date_first_row_only" ${P.date_first_row_only ? "checked" : ""}> تاریخ فقط در اولین ردیف هر روز</label>
          <label class="check small"><input type="checkbox" data-pk="autofit" ${P.autofit !== false ? "checked" : ""}> عرض ستون‌ها و ارتفاع ردیف‌ها خودکار به اندازه محتوا</label></div></div>
        <div class="field" style="grid-column:1/-1"><label>اجزای ستون «توضیحات ترکیبی»</label><div class="row">
          ${NOTE_PARTS.map(([k, l]) => `<label class="check small"><input type="checkbox" data-np="${k}" ${(P.notes_parts || NOTE_PARTS.map((x) => x[0])).includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div>
          <span class="hint">اگر یکی از این‌ها ستون جداگانه داشته باشد، در توضیحات تکرار نمی‌شود.</span></div></div>`;
      $$("[data-pk]", box).forEach((x) => x.onchange = () => { P[x.dataset.pk] = x.type === "checkbox" ? x.checked : x.value; changed(true); });
      $$("[data-ts]", box).forEach((x) => x.onchange = () => {
        const sep = $('[data-ts="sep"]', box).value, digits = $('[data-ts="digits"]', box).value;
        P.text_style = !isNew && !sep && !digits ? null : { sep: sep || P.text_style?.sep || " ، ", digits: digits || P.text_style?.digits || "ascii" };
        changed(true);
      });
      $$("[data-np]", box).forEach((x) => x.onchange = () => { P.notes_parts = $$("[data-np]", box).filter((c) => c.checked).map((c) => c.dataset.np); changed(true); });
    } else if (t === "colors") {
      const H = P.highlights = { ...state.tplMeta.highlight_defaults, warn: "", today: "", followup: "", ...(P.highlights || {}) };
      const row = (k, label, hint) => `<div class="tp-hl"><label class="check"><input type="checkbox" data-hk="${k}" ${H[k] ? "checked" : ""}> ${label}</label>
        <input type="color" class="tp-color" data-hc="${k}" value="${esc(H[k] || state.tplMeta.highlight_defaults[k] || "#fff3dc")}"><span class="small muted">${hint}</span></div>`;
      box.innerHTML = `<div class="stack">
        <div class="small muted">${help("colors")} ردیف‌هایی که یکی از این شرایط را دارند، با رنگ خودشان ثبت می‌شوند (اولویت به ترتیب از بالا). ${isNew ? "" : "در فایل موجود فقط ردیف‌های تازه رنگ می‌گیرند؛ ردیف‌های قبلی دست نمی‌خورند."}</div>
        ${row("followup", "پیگیری نزدیک", `تاریخ پیگیری تا <input class="input sm" type="number" min="0" max="60" id="tp-fdays" value="${H.followup_days}" style="width:60px;display:inline-block"> روز آینده`)}
        ${row("warn", "ردیف ناقص", "نام، شماره یا آدرس ندارد یا نامعتبر است")}
        ${row("today", "بازدید امروز", "تاریخ بازدید همان روز ثبت است")}</div>`;
      const set = (k) => { H[k] = $(`[data-hk="${k}"]`, box).checked ? $(`[data-hc="${k}"]`, box).value : ""; changed(true); };
      $$("[data-hk]", box).forEach((x) => x.onchange = () => set(x.dataset.hk));
      $$("[data-hc]", box).forEach((x) => x.oninput = () => { if ($(`[data-hk="${x.dataset.hc}"]`, box).checked) set(x.dataset.hc); });
      $("#tp-fdays").oninput = (e) => { H.followup_days = Math.max(0, Math.min(60, +e.target.value || 0)); changed(true); };
    } else if (t === "style" && !isNew) {
      // فایل موجود: ظاهرش دست نمی‌خورد؛ فقط ردیف‌های تازه می‌توانند مثل ردیف‌های قبلی قالب‌بندی شوند
      box.innerHTML = `<div class="stack"><div class="alert info">${I.info}<div class="alert-body"><b>ظاهر فایل موجود دست نمی‌خورد</b>
          ترتیب، عنوان، رنگ و عرض ستون‌های «${esc(fileName())}» همان‌طور که هست می‌ماند تا داده‌های قبلی به‌هم نریزند. برای ظاهر دلخواه، یک «فایل جداگانه» بسازید.</div></div>
        <label class="check"><input type="checkbox" id="pol-style" ${P.copy_style_from_last_row !== false ? "checked" : ""}> ردیف‌های تازه مثل آخرین ردیف فایل قالب‌بندی شوند (فونت، کادر و رنگ)</label></div>`;
      $("#pol-style").onchange = (e) => { P.copy_style_from_last_row = e.target.checked; changed(); };
    } else if (t === "style") {
      const S = draft.style, fonts = state.tplMeta.fonts;
      const fontSel = (part) => `<select class="select" data-sp="${part}.font">${fonts.map((f) => `<option value="${esc(f.name)}" ${S[part].font === f.name ? "selected" : ""}>${esc(f.name)}${f.installed ? "" : " (روی این رایانه نصب نیست)"}</option>`).join("")}</select>`;
      const num = (path, v, min, max) => `<input class="input" type="number" min="${min}" max="${max}" data-sp="${path}" value="${v}" style="width:80px">`;
      const color = (path, v) => `<input type="color" class="tp-color" data-sp="${path}" value="${esc(v || "#ffffff")}">`;
      box.innerHTML = `<div class="stack">
        <div class="row"><span class="small muted">رنگ‌های آماده:</span>${Object.entries(state.tplMeta.presets).map(([k, p]) => `<button class="btn sm tp-preset" data-preset="${k}"><span class="tp-swatch" style="background:${p.fill}"></span>${esc(p.label)}</button>`).join("")}</div>
        <div class="grid grid-2" style="gap:14px">
          <div class="stack"><b>سرستون</b>
            <div class="row">${fontSel("header")} ${num("header.size", S.header.size, 6, 36)}<label class="check small"><input type="checkbox" data-sp="header.bold" ${S.header.bold ? "checked" : ""}> پررنگ</label></div>
            <div class="row small"><label class="row">رنگ متن ${color("header.color", S.header.color)}</label><label class="row">پس‌زمینه ${color("header.fill", S.header.fill)}</label>
              <label class="row">ارتفاع ${num("header.height", S.header.height, 0, 120)}</label></div></div>
          <div class="stack"><b>ردیف‌ها</b>
            <div class="row">${fontSel("body")} ${num("body.size", S.body.size, 6, 36)}<label class="check small"><input type="checkbox" data-sp="body.wrap" ${S.body.wrap ? "checked" : ""}> شکستن متن بلند</label></div>
            <div class="row small"><label class="row">رنگ متن ${color("body.color", S.body.color)}</label>
              <label class="row"><input type="checkbox" id="tp-zebra-on" ${S.zebra ? "checked" : ""}> راه‌راه ${color("zebra", S.zebra || "#e8f6ef")}</label>
              <label class="row">ارتفاع ${num("body.height", S.body.height, 0, 200)}</label></div></div></div>
        <div class="row">${[["border", "کادر خانه‌ها"], ["rtl", "راست‌به‌چپ"], ["freeze", "ثابت ماندن سرستون"], ["filter", "فیلتر روی سرستون"]].map(([k, l]) => `<label class="check"><input type="checkbox" data-sp="${k}" ${S[k] ? "checked" : ""}> ${l}</label>`).join("")}</div>
        ${fonts.some((f) => f.name === S.body.font && !f.installed) || fonts.some((f) => f.name === S.header.font && !f.installed) ? `<div class="small muted">${I.info} فایل اکسل فقط نام فونت را نگه می‌دارد؛ اگر فونت روی رایانه‌ای که فایل را باز می‌کند نصب نباشد، Excel فونت دیگری نشان می‌دهد.</div>` : ""}</div>`;
      $$("[data-sp]", box).forEach((x) => x.oninput = () => {
        const [a, b] = x.dataset.sp.split(".");
        const v = x.type === "checkbox" ? x.checked : x.type === "number" ? +x.value : x.value;
        if (b) S[a][b] = v; else S[a] = a === "zebra" && !$("#tp-zebra-on").checked ? "" : v;
        changed();
      });
      $("#tp-zebra-on").onchange = (e) => { S.zebra = e.target.checked ? $('[data-sp="zebra"]', box).value : ""; changed(); };
      $$("[data-preset]", box).forEach((b) => b.onclick = () => {
        const p = state.tplMeta.presets[b.dataset.preset];
        Object.assign(S.header, { fill: p.fill, color: p.color }); S.zebra = p.zebra;
        drawTab(); changed();
      });
    } else if (!isNew) {
      box.innerHTML = `<div class="stack"><div class="field"><label>فایل اکسل موجود ${help("append")}</label><div class="row" style="flex-wrap:nowrap">
          <input class="input ltr" id="x-path" style="flex:1; text-align:right" placeholder="C:\\...\\فایل شرکت.xlsx" value="${esc(draft.excel_path || "")}">
          <button class="btn" id="x-browse">${I.folder} انتخاب فایل…</button><button class="btn ghost" id="x-inspect">${I.search} بررسی</button></div>
          <span class="hint">فایل فقط خوانده می‌شود تا ستون‌هایش شناخته شود. پیش از هر ثبت از آن پشتیبان گرفته می‌شود و هر ثبت قابل بازگشت است.</span></div>
        ${state.meta?.samples?.excel ? `<div class="row small"><span class="muted">فایل اکسل شرکت را ندارید؟</span><button class="btn sm ghost" id="x-sample">${I.table} استفاده از فایل اکسل نمونه</button></div>` : ""}
        <div id="x-report">${report ? (report.error ? `<div class="alert err">${I.alert}<div class="alert-body">${esc(report.error)}</div></div>` : excelReportHtml(report))
          : draft.excel_path ? `<div class="row"><span class="spinner"></span> در حال بررسی فایل…</div>` : ""}</div></div>`;
      $("#x-browse").onclick = browse;
      $("#x-inspect").onclick = () => inspect($("#x-path").value.trim().replace(/^"|"$/g, ""));
      $("#x-sample")?.addEventListener("click", () => { $("#x-path").value = state.meta.samples.excel; inspect(state.meta.samples.excel); });
    } else {
      const O = draft.output;
      box.innerHTML = `<div class="stack"><div class="field"><label>پوشه فایل</label><div class="row" style="flex-wrap:nowrap">
          <input class="input ltr" id="tp-folder" value="${esc(O.folder)}" style="flex:1; text-align:right"><button class="btn" id="tp-pick">${I.folder} انتخاب پوشه</button></div></div>
        <div class="field"><label>نام فایل</label><div class="row"><input class="input" id="tp-file" value="${esc(O.file)}" style="width:260px"><span class="muted">.xlsx</span></div>
          <span class="hint">اگر فایل نباشد، در اولین ثبت با ستون‌های همین فایل ساخته می‌شود؛ ثبت‌های بعدی به همان فایل اضافه می‌شوند.</span></div>
        <div class="field"><label>یک فایل یا چند فایل؟ ${help("split")}</label><select class="select" id="tp-split" style="width:300px">${Object.entries(state.tplMeta.splits).map(([k, l]) => `<option value="${k}" ${(O.split || "none") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
          <span class="hint">نام فایل امروز: <b id="tp-target-name">${esc(tplState.target || info.target || "")}</b></span></div></div>`;
      $("#tp-split").onchange = (e) => { O.split = e.target.value; changed(true); };
      $("#tp-folder").oninput = (e) => { O.folder = e.target.value.trim(); changed(); };
      $("#tp-file").oninput = (e) => { O.file = e.target.value.trim(); changed(true); };
      $("#tp-pick").onclick = async () => { const p = await pickPath("audio", O.folder); if (p) { O.folder = p; $("#tp-folder").value = p; changed(); } };
    }
  }

  function moveCol(from, to) {
    const L = draft.columns_list;
    if (to < 0 || to >= L.length || from === to) return;
    L.splice(to, 0, L.splice(from, 1)[0]);
    drawTab(); changed(true);
  }
  function uniqueTitle(t) { let n = t, i = 2; while (draft.columns_list.some((c) => c.title === n)) n = `${t} ${fa(i++)}`; return n; }

  $("#tp-save").onclick = async () => {
    const btn = $("#tp-save");
    btn.disabled = true;
    try {
      if (isNew) {
        const r = await api(`/api/templates/${info.name}`, { method: "PUT", body: draft });
        if (r.warning) toast(r.warning, "err");
      } else {
        await api("/api/excel/profile", { method: "PUT", body: draft });
        // واژه‌نامه از نام مهندس‌ها و خیابان‌های همین فایل پر می‌شود تا املای درست پیشنهاد شود
        try {
          const sd = await api(`/api/dictionary/seed-from-excel?name=${encodeURIComponent(info.name)}`, { method: "POST" });
          if (sd.added.engineer || sd.added.street) toast(`واژه‌نامه پر شد: ${fa(sd.added.engineer)} نام مهندس و ${fa(sd.added.street)} خیابان از فایل اکسل.`, "ok");
        } catch { }
      }
      tplState.dirty = false;
      toast("ذخیره شد.", "ok");
      await refreshStatus();
      renderTemplates(el);
    } catch (e) { toastErr(e); btn.disabled = false; }
  };
  $("#dv-discard").onclick = () => { tplState.dirty = false; renderTemplates(el); };
  $("#tp-show").onclick = () => showTemplatePreview(draft, isNew ? info.title : fileName());
  $("#tp-del")?.addEventListener("click", async () => {
    if (!(await confirmBox("برداشتن از فهرست", `«${esc(destLabel(dest))}» از فهرست فایل‌ها برداشته می‌شود. خود فایل اکسل و ردیف‌هایی که در آن ثبت شده‌اند دست نمی‌خورند.`, "برداشتن از فهرست", "danger"))) return;
    try { await api(`/api/templates/${info.name}`, { method: "DELETE" }); Object.assign(tplState, { name: null, dirty: false }); location.hash = "#/files"; } catch (e) { toastErr(e); }
  });
  $("#tp-like")?.addEventListener("click", () => $("#tp-like-file").click());
  $("#tp-like-file")?.addEventListener("change", async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f, f.name);
    try {
      const got = await api("/api/templates/from-file", { method: "POST", form: fd });
      draft.columns_list = got.columns_list;
      draft.style = got.style;
      const unknown = got.columns_list.filter((c) => c.field === "constant").length;
      toast(`ستون‌ها و ظاهر از «${f.name}» برداشته شد${unknown ? `؛ ${fa(unknown)} ستون شناخته نشد و خالی می‌ماند (در زبانه «ستون‌ها» می‌توانید عوضش کنید)` : ""}. ذخیره را فراموش نکنید.`, "ok");
      setTab("columns"); changed(true);
    } catch (er) { toastErr(er); }
  });
  $("#tp-sample")?.addEventListener("click", async () => {
    try { await downloadPost("/api/templates/sample", draft, `${draft.output.file || "نمونه"} (نمونه).xlsx`); }
    catch (e) { toastErr(e); }
  });
  drawSaveBar();
  drawTab();
  if (isNew) loadPreview();
  else if (draft.excel_path) inspect(draft.excel_path);
}
function fieldLabel(k) { return (state.tplMeta?.fields.find((f) => f.key === k) || {}).label || k; }
function columnLetter(i) { let s = ""; for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + (i - 1) % 26) + s; return s; }

/** گزارش بررسی فایل اکسل: ویژگی‌های پرخطر و شیت‌ها. */
function excelReportHtml(r) {
  const risks = r.risks || [];
  return `<div class="grid grid-2">
    <dl class="kv"><dt>نام فایل</dt><dd><bdi dir="ltr">${esc(r.name)}</bdi></dd><dt>نوع</dt><dd>${esc(r.type)}${r.has_macros ? " (دارای ماکرو)" : ""}</dd>
      <dt>حجم</dt><dd>${fmtSize(r.size)}</dd><dt>باز بودن در Excel</dt><dd>${r.lock?.locked ? `<span style="color:var(--warn)">${esc(r.lock.message)}</span>` : "بسته است"}</dd></dl>
    <div class="stack" style="gap:4px">${risks.length ? risks.map((x) => `<div class="risk">${x.level === "block" ? `<span style="color:var(--err)">${I.alert}</span>` : x.level === "warn" ? `<span style="color:var(--warn)">${I.alert}</span>` : `<span style="color:var(--info)">${I.info}</span>`}<span>${esc(x.message)}</span></div>`).join("")
      : `<div class="risk"><span style="color:var(--ok)">${I.ok}</span><span>ویژگی پرخطری (نمودار، Pivot، ماکرو، کنترل فرم) پیدا نشد؛ ثبت امن است.</span></div>`}</div></div>
    <div class="table-wrap" style="margin-top:12px; border:1px solid var(--border); border-radius:12px"><table class="table"><thead><tr><th>شیت</th><th>ردیف عنوان</th><th>ردیف‌های داده</th><th>آخرین ردیف داده</th><th>راست‌به‌چپ</th><th>فرمول</th><th>فیلتر</th><th>ادغام</th></tr></thead><tbody>
    ${r.sheets.map((s) => `<tr><td><b>${esc(s.name)}</b>${s.state !== "visible" ? ' <span class="muted small">(پنهان)</span>' : ""}</td><td>${fa(s.header_row)}</td><td>${fa(s.data_rows)}</td><td>${fa(s.last_data_row)}</td>
      <td>${s.right_to_left ? "بله" : "خیر"}</td><td>${fa(s.formula_count)}</td>
      <td class="small">${s.auto_filter ? `<span class="ltr">${esc(s.auto_filter)}</span>${s.auto_filter_stale ? ' <span style="color:var(--warn)" title="محدوده فیلتر همه داده‌ها را پوشش نمی‌دهد">(ناقص)</span>' : ""}` : "—"}</td><td>${fa(s.merged_cells.length)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

/** جدول شبیه برگه اکسل با ظاهر قالب. letters: سرستون حرفی و شماره ردیف مثل خود Excel. */
function sheetHtml(S, cols, rows, colors, letters = null) {
  const pt = (n) => `${Math.round(n * 1.33)}px`;
  const bd = S.border ? "border:1px solid #c9cfdb;" : "";
  const rn = (n) => letters ? `<th class="xl-rn">${n}</th>` : "";
  const filter = letters && S.filter ? `<span class="xl-filter">▾</span>` : "";
  return `<table dir="${S.rtl ? "rtl" : "ltr"}" style="font-family:'${esc(S.body.font)}',Tahoma,sans-serif"><thead>
    ${letters ? `<tr class="xl-letters"><th class="xl-h xl-rn"></th>${letters.map((l) => `<th class="xl-h">${esc(l)}</th>`).join("")}</tr>` : ""}
    <tr class="xl-titles">${rn(1)}${cols.map((c) => `<th class="${c.unmapped ? "unmapped" : ""}" ${c.unmapped ? `title="این ستون اطلاعاتی نمی‌گیرد و خالی می‌ماند"` : ""} style="width:${Math.round(c.width * 7.5)}px;min-width:${Math.round(c.width * 7.5)}px;
      font-family:'${esc(S.header.font)}',Tahoma;font-size:${pt(S.header.size)};font-weight:${S.header.bold ? 700 : 400};color:${S.header.color};background:${S.header.fill};${S.header.height ? `height:${pt(S.header.height)};` : ""}${bd}">${esc(c.title)}${filter}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r, i) => `<tr style="background:${colors?.[i] || (S.zebra && i % 2 === 1 ? S.zebra : "#fff")};${S.body.height ? `height:${pt(S.body.height)};` : ""}">${rn(i + 2)}${cols.map((c, j) => `<td class="${c.field === "phone" ? "ltr-cell" : ""}" style="font-size:${pt(S.body.size)};color:${S.body.color};text-align:${c.align};
      white-space:${S.body.wrap ? "pre-wrap" : "nowrap"};${bd}">${esc(r[j] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

// ظاهر خنثی برای فایل شرکت (ظاهر واقعی همان فایل می‌ماند)
const COMPANY_SHEET_STYLE = { header: { font: "Vazirmatn", size: 10, bold: true, color: "#10233d", fill: "#e9edf3", height: 0 },
  body: { font: "Vazirmatn", size: 10, color: "#10233d", wrap: true, height: 0 }, zebra: "", border: true, rtl: true, freeze: true, filter: false };
const HIGHLIGHT_LABELS = [["followup", "پیگیری نزدیک"], ["warn", "ردیف ناقص"], ["today", "بازدید امروز"]];

/** پیش‌نمایش بزرگ قالب (با تغییرات ذخیره‌نشده): نام و ترتیب ستون‌ها، ظاهر و چند ردیف نمونه. */
async function showTemplatePreview(template, title) {
  const isNew = template.mode === "new";
  let p;
  try { p = await api("/api/templates/preview", { method: "POST", body: isNew ? template : { name: template.name, mode: template.mode, policy: template.policy, headers: template.headers, columns: template.columns, protected: template.protected } }); }
  catch (e) { return toastErr(e); }
  const S = isNew ? template.style : COMPANY_SHEET_STYLE;
  const cols = isNew ? template.columns_list : p.headers.map((h, i) => ({ title: (p.protected?.includes(p.letters[i]) ? "🔒 " : "") + (h || `(${p.letters[i]})`), field: p.fields[i], width: 18, align: "right", unmapped: !p.fields[i] && !p.protected?.includes(p.letters[i]) }));
  const H = template.policy?.highlights || {};
  const keys = HIGHLIGHT_LABELS.filter(([k]) => H[k]);
  const notes = [
    p.demo ? "هنوز ردیفی نیست؛ مقدارها نمونه ساختگی‌اند." : `مقدارها از ${fa(p.rows.length)} ردیف اخیر، با شکل نوشتن همین فایل.`,
    isNew ? "" : "ظاهر، عرض و رنگ سرستون‌ها همان فایل موجود می‌ماند؛ اینجا نام، ترتیب و مقدار ستون‌ها را می‌بینید." + (cols.some((c) => c.unmapped) ? " ستون‌های با کادر قرمز اطلاعاتی نمی‌گیرند و خالی می‌مانند." : ""),
    tplState.dirty ? "تغییرات ذخیره‌نشده هم در این پیش‌نمایش آمده‌اند." : "",
  ].filter(Boolean);
  const actions = [{ label: "بستن", cls: "primary", value: null }];
  if (isNew) actions.unshift({ label: `${I.down} دریافت فایل نمونه`, cls: "ghost", onClick: async () => {
    try { await downloadPost("/api/templates/sample", template, `${template.output.file || "نمونه"} (نمونه).xlsx`); } catch (e) { toastErr(e); }
    return false;
  } });
  await openModal({ title: `پیش‌نمایش «${esc(title)}»`, actions, onOpen: (m) => m.classList.add("xwide"),
    body: `<div class="tpv-head"><span class="small muted">${fa(cols.length)} ستون${p.target ? ` · فایل: <b>${esc(p.target)}</b>` : ""}</span>
        ${keys.length ? `<span class="tpv-keys">${keys.map(([k, l]) => `<span class="tpv-key"><i style="background:${esc(H[k])}"></i>${l}</span>`).join("")}</span>` : ""}</div>
      <div class="tpv-order">${cols.map((c, i) => `<span class="tpv-col"><b>${esc(p.letters[i])}</b>${esc(c.title)}</span>`).join("")}</div>
      <div class="tp-preview xl ${S.freeze ? "freeze" : ""}">${sheetHtml(S, cols, p.rows, p.colors, p.letters)}</div>
      <div class="small muted" style="margin-top:10px">${notes.join(" ")}</div>` });
}

// ================= واژه‌نامه =================
async function renderDictionary(el) {
  let type = location.hash.includes("?kb") ? "__kb" : "engineer";
  const kb = { pending: [], roles: {} };  // فایل‌های بارگذاری‌شده‌ای که هنوز یاد گرفته نشده‌اند
  el.innerHTML = `<div class="card"><div class="card-h"><div class="tabs" id="dc-tabs"></div>
      <div class="row"><input class="input" id="dc-q" placeholder="جست‌وجو..." style="width:200px">
      <button class="btn" id="dc-seed">${I.table} پرکردن از فایل‌های اکسل من</button><button class="btn primary" id="dc-add">${I.plus} نام جدید</button></div></div>
    <div class="card-b row small" style="padding:10px 20px; border-bottom:1px solid var(--border)"><span class="muted">انتقال به رایانه دیگر (فقط نام‌ها و اصلاحات؛ بدون ردیف، ویس یا شماره):</span>
      <button class="btn sm" id="dc-export">${I.down} ذخیره واژه‌نامه در فایل</button><button class="btn sm" id="dc-import">${I.folder} ورود واژه‌نامه</button></div>
    <div class="card-b" id="dc-note" style="padding:12px 20px; border-bottom:1px solid var(--border)"><div class="muted small">نام‌های این فهرست به‌عنوان «املای تأییدشده» شناخته می‌شوند. نام‌های مشابه هرگز خودکار ادغام نمی‌شوند؛ فقط به‌عنوان پیشنهاد در بررسی نمایش داده می‌شوند. تغییر املا با ثبت سابقه انجام می‌شود و املای قبلی به‌عنوان «شکل دیگر» حفظ می‌شود.</div></div>
    <div class="table-wrap" id="dc-table"></div></div>`;
  const load = async () => {
    const q = $("#dc-q").value.trim();
    const isCorr = type === "__corrections", isKb = type === "__kb";
    const [d, corr, ks] = await Promise.all([
      api(`/api/dictionary?type=${isCorr || isKb ? "engineer" : type}&q=${encodeURIComponent(q)}`),
      api("/api/corrections"), api("/api/knowledge/sources")]);
    const types = state.meta.entity_types;
    $("#dc-tabs").innerHTML = Object.entries(types).map(([k, l]) => `<button class="${k === type ? "active" : ""}" data-t="${k}">${esc(l)}<span class="count">${fa(d.counts[k] || 0)}</span></button>`).join("")
      + `<button class="${isCorr ? "active" : ""}" data-t="__corrections">اصلاحات یادگرفته‌شده<span class="count">${fa(corr.corrections.length)}</span></button>`
      + `<button class="${isKb ? "active" : ""}" data-t="__kb">آموزش از اکسل<span class="count">${fa(ks.sources.length)}</span></button>`;
    $$("[data-t]").forEach((b) => b.onclick = () => { type = b.dataset.t; load(); });
    const box = $("#dc-table");
    $("#dc-note").hidden = isCorr || isKb;
    if (isCorr) return drawCorrections(box, corr, q, load);
    if (isKb) return drawKnowledge(box, kb, ks.sources, load);
    if (!d.entities.length) { box.innerHTML = `<div class="empty">${I.book}<div>موردی ثبت نشده است.</div></div>`; return; }
    box.innerHTML = `<table class="table"><thead><tr><th>نام استاندارد</th><th>شکل‌های دیگر</th><th>منبع</th><th>آخرین تأیید</th><th>دفعات استفاده</th><th></th></tr></thead><tbody>
      ${d.entities.map((e) => `<tr><td><b>${esc(e.canonical)}</b></td><td class="small">${esc(e.aliases || "")}</td><td class="small muted">${esc(e.source || "")}</td>
        <td class="small muted">${fa((e.last_confirmed_at || "").replace("T", " "))}</td><td>${fa(e.use_count)}</td>
        <td class="actions"><button class="btn sm ghost" data-alias="${e.id}" title="افزودن شکل دیگر">${I.plus}</button>
          <button class="btn sm ghost" data-ren="${e.id}" data-name="${esc(e.canonical)}" title="تغییر املا">${I.edit}</button>
          <button class="btn sm ghost" data-hist="${e.id}" title="سابقه">${I.history}</button>
          <button class="btn sm ghost" data-delent="${e.id}" title="حذف">${I.trash}</button></td></tr>`).join("")}</tbody></table>`;
    const ask = (title, label, val = "") => openModal({
      title, body: `<div class="field"><label>${label}</label><input class="input" id="m-in" value="${esc(val)}"></div>`,
      actions: [{ label: "ذخیره", cls: "primary", onClick: (m) => $("#m-in", m).value.trim() || false }, { label: "انصراف", cls: "ghost", value: null }],
      onOpen: (m) => setTimeout(() => $("#m-in", m).focus(), 50),
    });
    $$("[data-alias]", box).forEach((b) => b.onclick = async () => {
      const v = await ask("افزودن شکل دیگر", "املای دیگری که به همین نام اشاره دارد"); if (!v) return;
      try { await api(`/api/dictionary/${b.dataset.alias}/alias`, { method: "POST", body: { alias: v } }); load(); } catch (e) { toastErr(e); }
    });
    $$("[data-ren]", box).forEach((b) => b.onclick = async () => {
      const v = await ask("تغییر املای نام استاندارد", "املای جدید (املای قبلی به‌عنوان شکل دیگر حفظ می‌شود)", b.dataset.name); if (!v) return;
      try { await api(`/api/dictionary/${b.dataset.ren}`, { method: "PATCH", body: { canonical: v } }); load(); } catch (e) { toastErr(e); }
    });
    $$("[data-hist]", box).forEach((b) => b.onclick = async () => {
      const { history } = await api(`/api/dictionary/${b.dataset.hist}/history`);
      const A = { create: "ایجاد", alias: "شکل دیگر", rename: "تغییر املا", delete: "حذف" };
      openModal({ title: "سابقه تغییرات", body: `<ul class="reasons">${history.map((h) => `<li>${fa(h.at.replace("T", " "))} — ${A[h.action] || h.action}: ${esc(h.old_value || "")} ${h.old_value ? "←" : ""} ${esc(h.new_value || "")} <span class="muted">(${esc(h.source || "")})</span></li>`).join("")}</ul>`, actions: [{ label: "بستن" }] });
    });
    $$("[data-delent]", box).forEach((b) => b.onclick = async () => {
      if (!(await confirmBox("حذف از واژه‌نامه", "این نام و شکل‌های دیگرش از واژه‌نامه حذف می‌شوند (ردیف‌ها تغییر نمی‌کنند).", "حذف", "danger"))) return;
      try { await api(`/api/dictionary/${b.dataset.delent}`, { method: "DELETE" }); load(); } catch (e) { toastErr(e); }
    });
  };
  $("#dc-q").oninput = debounce(load, 250);
  $("#dc-add").onclick = async () => {
    const v = await openModal({
      title: "افزودن نام جدید",
      body: `<div class="stack"><div class="field"><label>نوع</label><select class="select" id="m-t">${Object.entries(state.meta.entity_types).map(([k, l]) => `<option value="${k}" ${k === type ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
        <div class="field"><label>نام (بدون عنوان «مهندس»)</label><input class="input" id="m-n"></div></div>`,
      actions: [{ label: "افزودن", cls: "primary", onClick: (m) => ({ type: $("#m-t", m).value, canonical: $("#m-n", m).value.trim() }) }, { label: "انصراف", cls: "ghost", value: null }],
    });
    if (!v || !v.canonical) return;
    try { await api("/api/dictionary", { method: "POST", body: v }); toast("اضافه شد.", "ok"); type = v.type; load(); } catch (e) { toastErr(e); }
  };
  $("#dc-export").onclick = async () => {
    try {
      const enc = await api("/api/backups/encryption");
      if (!enc.enabled && !(await confirmBox("ذخیره واژه‌نامه بدون رمز", "رمزگذاری در «تنظیمات ← پشتیبان‌گیری» خاموش است؛ این فایل نام مهندس‌ها را بدون قفل دارد. ادامه می‌دهید؟", "دریافت", "danger"))) return;
      await downloadPost("/api/dictionary/export", {});
    } catch (e) { toastErr(e); }
  };
  $("#dc-import").onclick = () => openModal({
    title: "ورود واژه‌نامه",
    body: `<div class="stack"><div class="muted small">نام‌ها و اصلاحات فایل به واژه‌نامه همین رایانه اضافه می‌شوند؛ چیزی پاک یا جایگزین نمی‌شود.</div>
      <label>فایل واژه‌نامه (.v2xdict یا .json)<input type="file" id="di-file" accept=".v2xdict,.json"></label>
      <label>گذرواژه <span class="muted small">(اگر فایل در رایانه دیگری قفل شده، گذرواژه پشتیبان همان رایانه)</span><input class="input ltr" type="password" id="di-pw" autocomplete="off"></label></div>`,
    actions: [{ label: "افزودن", cls: "primary", onClick: async (m) => {
      const f = $("#di-file", m).files[0];
      if (!f) { toast("فایل واژه‌نامه را انتخاب کنید.", "err"); return false; }
      const form = new FormData();
      form.append("file", f);
      form.append("password", $("#di-pw", m).value);
      try {
        const r = await api("/api/dictionary/import", { method: "POST", form });
        toast(`${fa(r.added.entities)} نام تازه، ${fa(r.added.aliases)} شکل دیگر و ${fa(r.added.corrections)} اصلاح اضافه شد`
          + (r.reextracted ? `؛ ${fa(r.reextracted)} ویس با واژه‌نامه تازه دوباره استخراج شد.` : "."), "ok");
        refreshStatus(); load(); return true;
      } catch (e) { toastErr(e); return false; }
    } }, { label: "انصراف", cls: "ghost", value: false }],
  });
  $("#dc-seed").onclick = async () => {
    if (!(await confirmBox("پرکردن واژه‌نامه از فایل‌های اکسل من", "نام مهندس‌ها (ردیف‌هایی که با «مهندس/آقای/خانم» شروع می‌شوند) و نام خیابان‌ها از ستون‌های فایل‌های اکسلِ فهرست خوانده و با منبع «اکسل» به واژه‌نامه اضافه می‌شوند. فایل‌های اکسل تغییر نمی‌کنند.", "پرکردن"))) return;
    try {
      const files = (await loadDests()).dests.filter((x) => x.mode !== "new" && x.configured);
      if (!files.length) throw new Error("هنوز فایل اکسلی با ستون‌های تأییدشده در فهرست نیست.");
      const r = { added: { engineer: 0, street: 0, project: 0 }, rows: 0, already: true, total: 0 };
      for (const f of files) {
        const x = await api(`/api/dictionary/seed-from-excel?name=${encodeURIComponent(f.name)}`, { method: "POST" });
        for (const k of Object.keys(r.added)) r.added[k] += x.added?.[k] || 0;
        Object.assign(r, { rows: r.rows + (x.rows || 0), already: r.already && x.already, total: x.total ?? r.total });
      }
      toast(`${fa(r.added.engineer)} نام مهندس و ${fa(r.added.street)} خیابان از ${fa(r.rows)} ردیف اضافه شد.`, "ok");
      load();
    } catch (e) { toastErr(e); }
  };
  await load();
}

/** آموزش از فایل اکسل: بارگذاری، تعیین نقش ستون‌ها، پیش‌نمایش آنچه یاد گرفته می‌شود و فهرست منابع یادگرفته‌شده. */
function drawKnowledge(box, kb, sources, reload) {
  const LBL = { engineer: "نام مهندس", street: "خیابان", project: "پروژه" };
  const choiceOf = (f) => ({ token: f.token, name: f.name, sheet: f.choice.sheet, header_row: f.choice.header_row, columns: f.choice.columns });
  const stats = (p) => !p || p.rows === undefined ? "" : `<div class="kb-stats">
      <div><b>${fa(p.rows)}</b><span>ردیف داده</span></div>
      ${["engineer", "street", "project"].map((k) => p[k] && p[k].total ? `<div><b>${fa(p[k].new)}</b><span>${LBL[k]} تازه از ${fa(p[k].total)}</span></div>` : "").join("")}
      ${(p.engineer?.variants || 0) + (p.street?.variants || 0) ? `<div><b>${fa((p.engineer?.variants || 0) + (p.street?.variants || 0))}</b><span>نام با چند املا (یکی می‌شوند)</span></div>` : ""}</div>
    ${["engineer", "street"].map((k) => p[k] && p[k].new_samples.length ? `<div class="kb-samples"><span class="small muted">${LBL[k]}‌های تازه:</span> ${p[k].new_samples.map((n) => `<span class="chip plain">${esc(n)}</span>`).join(" ")}${p[k].new > p[k].new_samples.length ? ` <span class="small muted">و ${fa(p[k].new - p[k].new_samples.length)} مورد دیگر</span>` : ""}</div>` : "").join("")}`;
  const card = (f, i) => {
    if (f.error) return `<div class="kb-file bad"><div class="row" style="justify-content:space-between"><b>${esc(f.name)}</b><button class="btn sm ghost" data-kbdrop="${i}">${I.x}</button></div><div class="small">${esc(f.error)}</div></div>`;
    const sh = f.sheets.find((s) => s.name === f.choice.sheet) || { headers: {} };
    const roles = Object.entries(kb.roles);
    return `<div class="kb-file" data-kbi="${i}">
      <div class="row" style="justify-content:space-between"><div><b>${esc(f.name)}</b>
        ${f.sheets.length > 1 ? `<select class="select sm" data-kbsheet="${i}">${f.sheets.map((s) => `<option ${s.name === f.choice.sheet ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select>` : `<span class="muted small"> — شیت ${esc(f.choice.sheet)}</span>`}</div>
        <button class="btn sm ghost" data-kbdrop="${i}" title="کنار گذاشتن">${I.trash}</button></div>
      ${f.already ? `<div class="small" style="color:var(--warn)">این فایل قبلاً (${fa((f.already.imported_at || "").replace("T", " "))}) یاد گرفته شده است.</div>` : ""}
      <div class="kb-cols">${Object.entries(sh.headers).map(([c, h]) => `<label class="field"><span class="small">${esc(c)} — ${esc(h.replace(/\s+/g, " "))}</span>
        <select class="select sm" data-kbcol="${i}" data-col="${c}">${roles.map(([k, l]) => `<option value="${k}" ${(f.choice.columns[c] || "") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`).join("")}</div>
      ${stats(f.preview)}
      <div class="row"><button class="btn primary" data-kblearn="${i}" ${f.already || !Object.keys(f.choice.columns).length ? "disabled" : ""}>${I.check} یادگیری از این فایل</button></div>
    </div>`;
  };
  box.innerHTML = `<div class="card-b stack">
      <div class="muted small">فایل‌های اکسل قدیمی بازدیدها (با هر ساختاری) را بدهید تا برنامه نام مهندس‌ها و خیابان‌ها را یاد بگیرد. با آن، آدرس و نام در هر جای ویس و حتی بدون گفتن «آدرس» یا «مهندس» تشخیص داده می‌شوند و املای هم‌آوا («کازمی»، «فلاهی») به املای درست برمی‌گردد. فایل‌ها فقط خوانده می‌شوند و هر فایل را می‌توانید بعداً حذف کنید.</div>
      <div class="row"><input type="file" id="kb-file" accept=".xlsx,.xlsm" multiple hidden>
        <button class="btn primary" id="kb-pick">${I.upload} انتخاب فایل اکسل</button><span class="small muted">چند فایل را می‌توانید با هم انتخاب کنید.</span></div>
      ${kb.pending.map(card).join("")}
    </div>
    ${sources.length ? `<table class="table"><thead><tr><th>فایل یادگرفته‌شده</th><th>زمان</th><th>ردیف</th><th>نام مهندس</th><th>خیابان</th><th>تازه</th><th></th></tr></thead><tbody>
      ${sources.map((s) => `<tr><td><b>${esc(s.name)}</b> <span class="small muted">${esc(s.sheet || "")}</span></td><td class="small muted">${fa((s.imported_at || "").replace("T", " "))}</td>
        <td>${fa(s.rows || 0)}</td><td>${fa(s.engineers || 0)}</td><td>${fa(s.streets || 0)}</td><td>${fa(s.new_entities || 0)}</td>
        <td class="actions"><button class="btn sm ghost" data-kbdel="${s.id}" data-name="${esc(s.name)}" title="حذف آموخته‌های این فایل">${I.trash}</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">${I.table}<div>هنوز فایلی یاد گرفته نشده است.</div></div>`}`;

  const redraw = () => drawKnowledge(box, kb, sources, reload);
  const refreshPreview = async (f) => {
    if (!Object.keys(f.choice.columns).length) { f.preview = null; return redraw(); }
    try { f.preview = (await api("/api/knowledge/preview", { method: "POST", body: choiceOf(f) })).preview; } catch (e) { toastErr(e); }
    redraw();
  };
  $("#kb-pick").onclick = () => $("#kb-file").click();
  $("#kb-file").onchange = async (e) => {
    const files = [...e.target.files];
    if (!files.length) return;
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    $("#kb-pick").disabled = true;
    try {
      const r = await api("/api/knowledge/analyze", { method: "POST", form: fd });
      kb.roles = r.roles;
      for (const f of r.files) {
        if (f.sha256 && kb.pending.some((p) => p.sha256 === f.sha256)) continue;  // همان فایل دوباره انتخاب شده
        if (!f.error) {
          const sh = f.sheets.find((s) => s.name === f.sheet) || f.sheets[0];
          f.choice = { sheet: sh.name, header_row: sh.header_row, columns: { ...sh.roles } };
        }
        kb.pending.push(f);
      }
    } catch (er) { toastErr(er); }
    e.target.value = "";
    redraw();
  };
  $$("[data-kbdrop]", box).forEach((b) => b.onclick = () => { kb.pending.splice(+b.dataset.kbdrop, 1); redraw(); });
  $$("[data-kbsheet]", box).forEach((s) => s.onchange = () => {
    const f = kb.pending[+s.dataset.kbsheet], sh = f.sheets.find((x) => x.name === s.value);
    f.choice = { sheet: sh.name, header_row: sh.header_row, columns: { ...sh.roles } };
    refreshPreview(f);
  });
  $$("[data-kbcol]", box).forEach((s) => s.onchange = () => {
    const f = kb.pending[+s.dataset.kbcol];
    // هر نقش فقط یک ستون: نقش انتخاب‌شده از ستون دیگر برداشته می‌شود
    for (const [c, r] of Object.entries(f.choice.columns)) if (r === s.value) delete f.choice.columns[c];
    if (s.value) f.choice.columns[s.dataset.col] = s.value; else delete f.choice.columns[s.dataset.col];
    refreshPreview(f);
  });
  $$("[data-kblearn]", box).forEach((b) => b.onclick = async () => {
    const i = +b.dataset.kblearn, f = kb.pending[i];
    b.disabled = true;
    try {
      const r = await api("/api/knowledge/import", { method: "POST", body: choiceOf(f) });
      kb.pending = kb.pending.filter((p, k) => k !== i && p.sha256 !== f.sha256);
      toast(`از «${f.name}» ${fa(r.added.engineer)} نام مهندس و ${fa(r.added.street)} خیابان تازه یاد گرفته شد`
        + (r.reextracted ? `؛ ${fa(r.reextracted)} ویس با واژه‌نامه تازه دوباره استخراج شد.` : "."), "ok");
      refreshStatus();
      reload();
    } catch (e) { b.disabled = false; toastErr(e); }
  });
  $$("[data-kbdel]", box).forEach((b) => b.onclick = async () => {
    if (!(await confirmBox("حذف آموخته‌های فایل", `نام‌ها و خیابان‌هایی که فقط از «${esc(b.dataset.name)}» آمده‌اند و هیچ ردیفی تأییدشان نکرده، از واژه‌نامه حذف می‌شوند. فایل اکسل و ردیف‌های ثبت‌شده تغییر نمی‌کنند.`, "حذف", "danger"))) return;
    try { const r = await api(`/api/knowledge/sources/${b.dataset.kbdel}`, { method: "DELETE" }); toast(`${fa(r.removed)} نام از واژه‌نامه حذف شد.`, "ok"); refreshStatus(); reload(); } catch (e) { toastErr(e); }
  });
}

/** فهرست اصلاحاتی که برنامه از ویرایش‌های کاربر یاد گرفته؛ با امکان غیرفعال‌کردن و حذف. */
function drawCorrections(box, corr, q, reload) {
  const list = corr.corrections.filter((c) => !q || c.wrong.includes(q) || c.right.includes(q));
  if (!list.length) {
    box.innerHTML = `<div class="empty">${I.history}<div>هنوز اصلاحی یاد گرفته نشده است.</div>
      <div class="small">وقتی در بررسی واژه‌ای را اصلاح می‌کنید (مثلاً «گلزی» ← «گلزاری»)، اینجا ثبت می‌شود؛ از ${fa(corr.threshold)} بار تکرار به بعد خودکار اعمال می‌شود.</div></div>`;
    return;
  }
  box.innerHTML = `<div class="card-b small muted" style="padding:10px 20px">اصلاحی که دست‌کم ${fa(corr.threshold)} بار تکرار شده باشد، در ویس‌های بعدی خودکار اعمال می‌شود (با یادداشت توضیحی)؛ کمتر از آن فقط پیشنهاد داده می‌شود. حد تکرار در «تنظیمات» قابل تغییر است.</div>
    <table class="table"><thead><tr><th>نوع فیلد</th><th>شنیده‌شده</th><th></th><th>اصلاح شما</th><th>تکرار</th><th>وضعیت</th><th></th></tr></thead><tbody>
    ${list.map((c) => `<tr class="${c.enabled ? "" : "muted"}"><td>${esc(corr.groups[c.field_group] || c.field_group)}</td><td>${esc(c.wrong)}</td><td>←</td><td><b>${esc(c.right)}</b></td><td>${fa(c.count)}</td>
      <td>${!c.enabled ? chip("missing", "غیرفعال") : c.count >= corr.threshold ? chip("ok", "اعمال خودکار") : chip("info", "فقط پیشنهاد")}</td>
      <td class="actions"><button class="btn sm ghost" data-ctoggle="${c.id}" data-en="${c.enabled ? 0 : 1}">${c.enabled ? "غیرفعال" : "فعال"}</button>
        <button class="btn sm ghost" data-cdel="${c.id}" title="حذف">${I.trash}</button></td></tr>`).join("")}</tbody></table>`;
  $$("[data-ctoggle]", box).forEach((b) => b.onclick = async () => {
    try { await api(`/api/corrections/${b.dataset.ctoggle}`, { method: "PATCH", body: { enabled: b.dataset.en === "1" } }); reload(); } catch (e) { toastErr(e); }
  });
  $$("[data-cdel]", box).forEach((b) => b.onclick = async () => {
    if (!(await confirmBox("حذف اصلاح", "این اصلاح دیگر پیشنهاد یا اعمال نمی‌شود. ردیف‌های قبلی تغییر نمی‌کنند.", "حذف", "danger"))) return;
    try { await api(`/api/corrections/${b.dataset.cdel}`, { method: "DELETE" }); reload(); } catch (e) { toastErr(e); }
  });
}

// ================= تنظیمات =================
/** نسخه oldcpu: انتخاب موتور (آنلاین یا روی همین رایانه) و وضعیت آن. */
function engineCard(s, eng) {
  if (!eng) return "";
  const online = s.speech_engine !== "offline";
  const last = eng.last_engine ? (eng.last_engine.startsWith("online") ? "آنلاین" : "روی همین رایانه") : "";
  let state = "";
  if (online && !eng.cloud_configured) state = `<div class="alert warn">${I.info}<div class="alert-body">موتور آنلاین در این بسته تنظیم نشده است؛ ویس‌ها روی همین رایانه تبدیل می‌شوند.</div></div>`;
  else if (online && eng.cloud_message) state = `<div class="alert warn">${I.info}<div class="alert-body">${esc(eng.cloud_message)} تا حدود ${fa(Math.max(1, eng.cloud_paused_minutes))} دقیقه دیگر ویس‌ها روی همین رایانه تبدیل می‌شوند (کندتر) و بعد دوباره آنلاین امتحان می‌شود.</div></div>`;
  if (!eng.local_available) state += `<div class="alert err">${I.info}<div class="alert-body">موتور روی همین رایانه در بسته پیدا نشد؛ بدون اینترنت ویس‌ها تبدیل نمی‌شوند. بسته را دوباره از zip باز کنید.</div></div>`;
  return `<div class="card" style="margin-bottom:18px"><div class="card-h"><h2>${I.mic} موتور تبدیل گفتار</h2></div><div class="card-b stack">
    <label class="check"><input type="radio" name="s-engine" value="online" ${online ? "checked" : ""} ${eng.cloud_configured ? "" : "disabled"}> <span><b>آنلاین</b> (پیشنهادی): هر ویس چند ثانیه. اگر اینترنت یا سرویس در دسترس نبود، خودکار روی همین رایانه تبدیل می‌شود.</span></label>
    <label class="check"><input type="radio" name="s-engine" value="offline" ${online ? "" : "checked"}> <span><b>فقط روی همین رایانه</b>: بدون اینترنت، ولی کند (هر ویس چند دقیقه).</span></label>
    <span class="hint">در حالت آنلاین، ویس برای تبدیل به متن به سرویس Cloudflare فرستاده می‌شود. فایل اکسل و ردیف‌ها همیشه روی همین رایانه می‌مانند.</span>
    ${state}${last ? `<div class="muted small">آخرین ویس: ${last}</div>` : ""}</div></div>`;
}

async function renderSettings(el) {
  const draw = async () => {
    const d = await api("/api/settings");
    const s = d.settings;
    const MODEL_INFO = {
      tiny: ["حدود ۷۵ مگابایت", "در آزمون: هیچ شماره‌ای درست نبود"],
      base: ["حدود ۱۴۵ مگابایت", "در آزمون: هیچ شماره‌ای درست نبود"],
      small: ["حدود ۴۸۰ مگابایت", "پشتیبان رایانه‌های ضعیف؛ در آزمون شماره‌ها رقم غلط داشتند"],
      medium: ["حدود ۱.۵ گیگابایت", "کند، دقیق‌تر"],
      "large-v3-turbo": ["حدود ۱.۶ گیگابایت", "پیشنهادی: در آزمون همه شماره‌ها درست؛ ~۱.۹ گیگ RAM"],
      "large-v3": ["حدود ۳ گیگابایت", "بسیار کند روی CPU؛ برای ۸ گیگ RAM توصیه نمی‌شود"],
    };
    const p = d.performance || {};
    const oldcpu = d.edition === "oldcpu";
    el.innerHTML = `${oldcpu ? engineCard(s, d.engine) : ""}
      <div class="card" style="margin-bottom:18px"><div class="card-h"><h2>${I.table} ثبت در اکسل</h2></div><div class="card-b stack">
        <div>ردیف‌ها مستقیم در خود فایل اکسل نوشته می‌شوند. پیش از هر ثبت یک پشتیبان از فایل گرفته می‌شود و هر ثبت از «تاریخچه ثبت‌ها» قابل برگرداندن است.</div>
        <label class="check"><input type="checkbox" id="s-copyfirst" ${s.review_copy_first ? "checked" : ""}> اول در یک کپی ثبت شود؛ پس از اینکه خودم کپی را دیدم، از «تاریخچه ثبت‌ها» روی فایل اصلی اعمال شود</label>
        <span class="hint">برای کسی که می‌خواهد هر بار پیش از تغییر فایل اصلی، نتیجه را ببیند. بیشتر کاربران به آن نیاز ندارند.</span></div></div>
      <div class="card" style="margin-bottom:18px"><div class="card-h"><h2>${I.book} واژه‌نامه و راهنماها</h2></div>
        <div class="card-b row">
          <a class="btn" href="#/dictionary">${I.book} واژه‌نامه</a>
          <a class="btn" href="#/dictionary?kb">${I.upload} آموزش از فایل‌های اکسل قدیمی</a>
          <a class="btn ghost" href="/static/guide.html" target="_blank">${I.info} راهنمای استفاده</a>
          <a class="btn ghost" href="/static/recording-guide.html" target="_blank">${I.info} راهنمای ضبط ویس</a>
        </div>
        <div class="card-b stack" style="border-top:1px solid var(--border)"><b>پوشه ورودی خودکار</b>
          <div class="row" style="flex-wrap:nowrap"><input class="input ltr" id="s-inbox" value="${esc(s.inbox_dir)}" placeholder="مثلاً ...\\Downloads\\Telegram Desktop" style="flex:1; text-align:right">
            <button class="btn" id="s-inbox-pick">${I.folder} انتخاب پوشه</button><button class="btn" id="s-inbox-save">${I.check} ذخیره</button></div>
          <span class="hint">ویس‌هایی که از این به بعد در این پوشه ذخیره شوند (مثلاً پوشه دانلود تلگرام یا واتساپ دسکتاپ)، خودکار برداشته و پردازش می‌شوند. ویس‌های قدیمی پوشه دست نمی‌خورند. خالی = خاموش.</span></div></div>
      <details class="tech-box"><summary>تنظیمات فنی <span class="muted small">— مدل گفتار، قواعد اعتبارسنجی، کارایی</span></summary>
      <div class="grid grid-2">
        <div class="card"><div class="card-h"><h2>${I.mic} مدل تبدیل گفتار</h2></div><div class="card-b stack">
          ${oldcpu ? `<div class="muted small">در این نسخه مدل گفتار ثابت است (<span class="ltr">large-v3-turbo</span>)؛ موتور را از کارت «موتور تبدیل گفتار» بالای همین صفحه انتخاب کنید.</div>` : `<div class="table-wrap" style="border:1px solid var(--border); border-radius:12px"><table class="table"><tbody>
            ${d.models.map((m) => { const inst = d.installed_models.includes(m); return `<tr>
              <td><label class="check"><input type="radio" name="model" value="${m}" ${s.model_name === m ? "checked" : ""} ${inst ? "" : "disabled"}> <b class="ltr">${m}</b></label></td>
              <td class="small">${MODEL_INFO[m]?.[0] || ""}<div class="muted">${MODEL_INFO[m]?.[1] || ""}</div></td>
              <td>${inst ? chip("ok", "نصب‌شده") : `<button class="btn sm" data-dl="${m}" ${d.download.status === "running" ? "disabled" : ""}>${I.down} دریافت</button>`}</td></tr>`; }).join("")}
          </tbody></table></div>
          ${d.download.status !== "idle" ? `<div class="alert ${d.download.status === "error" ? "err" : d.download.status === "done" ? "ok" : "info"}">${d.download.status === "running" ? '<span class="spinner"></span>' : I.info}<div class="alert-body"><b class="ltr">${esc(d.download.name || "")}</b> ${esc(d.download.message)}</div></div>` : ""}
          <div class="muted small">دریافت مدل تنها کاری است که به اینترنت نیاز دارد و فقط با دکمه بالا انجام می‌شود. پس از دریافت، همه پردازش‌ها آفلاین است. مدل نهایی را پس از مقایسه روی ویس‌های واقعی انتخاب کنید.</div>`}
          <div class="grid grid-2" style="gap:12px">
            <div class="field"><label>Beam size</label><input class="input" type="number" min="1" max="10" id="s-beam" value="${s.beam_size}"><span class="hint">پیشنهادی ۲؛ بیشتر کندتر می‌شود بی‌آنکه در آزمون دقیق‌تر شده باشد، ۱ دقت شماره را کم می‌کند</span></div>
            <div class="field"><label>تعداد هسته CPU</label><input class="input" type="number" min="0" max="32" id="s-threads" value="${s.cpu_threads}"><span class="hint">۰ = خودکار</span></div>
          </div>
          <label class="check"><input type="checkbox" id="s-vad" ${s.vad_filter ? "checked" : ""}> حذف بخش‌های بی‌صدا (VAD)</label>
          <label class="check"><input type="checkbox" id="s-hot" ${s.use_dictionary_hotwords ? "checked" : ""}> ارسال نام‌های واژه‌نامه به مدل گفتار (توصیه نمی‌شود)</label>
          <span class="hint muted small" style="margin-top:-6px">در آزمون روی ۸ ویس، این گزینه باعث تکرار ساختگی واژه‌ها و از دست رفتن شماره یا آدرس در ۳ ویس شد و ۲ تا ۴ برابر کندتر بود. املای درست نام‌ها از راه پیشنهادهای واژه‌نامه به دست می‌آید.</span>
          <div class="field"><label>متن راهنمای سبک نگارش برای مدل</label><textarea class="input" id="s-prompt" rows="3">${esc(s.initial_prompt)}</textarea>
            <span class="hint">فقط واژه‌های رایج را به مدل نشان می‌دهد. در آن <b>رقم یا نام شخص ننویسید</b>؛ در آزمون، رقم مدل را به حلقه رقم‌های بی‌معنی انداخت و نام شخص وارد متن تبدیل‌شده شد.</span></div>
        </div></div>
        <div class="stack" style="gap:18px">
        <div class="card"><div class="card-h"><h2>${I.shield} قواعد اعتبارسنجی</h2></div><div class="card-b stack">
          <div class="field"><label>فیلدهای الزامی برای «آماده ثبت» بودن ردیف</label>
            <div class="row">${[["engineer_name", "نام مهندس"], ["phone", "شماره تماس"], ["address", "آدرس"], ["project_name", "نام پروژه"]].map(([k, l]) => `<label class="check"><input type="checkbox" data-req="${k}" ${s.required_fields.includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div>
            <span class="hint">ردیفی که همه فیلدهای الزامی‌اش معتبر باشد، خودکار «آماده ثبت» می‌شود؛ بقیه به بررسی می‌روند.</span></div>
          <label class="check"><input type="checkbox" id="s-revphone" ${s.review_spoken_phones ? "checked" : ""}> هر شماره تلفن با شنیدن ویس تأیید شود (پیشنهادی تا سنجش دقت روی ویس‌های واقعی)</label>
          <label class="check"><input type="checkbox" id="s-kbspell" ${s.kb_auto_spelling ? "checked" : ""}> املای هم‌آوای نام و خیابان مطابق واژه‌نامه یکسان شود (مثلاً «کازمی» ← «کاظمی»؛ فقط وقتی یک گزینه باشد)</label>
          <div class="grid grid-2" style="gap:12px">
            <div class="field"><label>پیش‌شماره شهر برای تلفن ثابت</label><input class="input ltr" id="s-area" value="${esc(s.default_area_code)}" placeholder="مثلاً 051" style="text-align:right"><span class="hint">فقط به‌عنوان پیشنهاد نمایش داده می‌شود.</span></div>
            <div class="field"><label>کمینه شباهت برای پیشنهاد املا</label><input class="input" type="number" step="0.01" min="0.5" max="0.99" id="s-sim" value="${s.similarity_suggest}"></div>
            <div class="field"><label>اعمال خودکار اصلاحات یادگرفته‌شده پس از</label><div class="row"><input class="input" type="number" min="1" max="20" id="s-learn" value="${s.learn_auto_threshold}" style="width:90px"><span class="small muted">بار تکرار</span></div></div>
            <div class="field"><label>آزادسازی مدل از حافظه پس از</label><div class="row"><input class="input" type="number" min="0" max="240" id="s-idle" value="${s.model_idle_minutes}" style="width:90px"><span class="small muted">دقیقه بی‌کاری</span></div></div>
          </div>
          <div class="row"><button class="btn primary" id="s-save">${I.check} ذخیره تنظیمات</button><button class="btn" id="s-reval">${I.retry} اعتبارسنجی دوباره همه ردیف‌ها</button>
            <button class="btn" id="s-reext" title="بدون تبدیل دوباره گفتار؛ ردیف‌های اصلاح‌شده یا تأییدشده دست نمی‌خورند">${I.retry} استخراج دوباره از متن ویس‌ها</button></div>
        </div></div>
        <div class="card"><div class="card-h"><h2>${I.info} سامانه و کارایی</h2></div><div class="card-b">
          <dl class="kv"><dt>RAM کل رایانه</dt><dd>${d.system.ram_gb ? fa(d.system.ram_gb) + " گیگابایت" : "—"}</dd>
            <dt>حافظه فعلی برنامه</dt><dd>${d.system.process_mb ? fa(d.system.process_mb) + " مگابایت" : "—"}</dd>
            <dt>بیشینه حافظه در پردازش</dt><dd>${p.peak ? fa(Math.round(p.peak)) + " مگابایت" : "—"}</dd>
            <dt>میانگین زمان هر ویس</dt><dd>${p.avg_s ? fmtSec(p.avg_s) + (p.avg_d ? ` برای ویس ${fmtSec(p.avg_d)}` : "") : "—"} ${p.n ? `<span class="muted">(${fa(p.n)} ویس)</span>` : ""}</dd>
            <dt>اشتراک</dt><dd>${d.license.mode === "licensed" ? esc(d.license.customer || "فعال") + (d.license.expires_jalali ? ` — تا ${fa(d.license.expires_jalali)}` : " — نامحدود") : d.license.mode === "trial" ? "آزمایشی" : d.license.mode === "expired" ? "تمام‌شده" : "—"} <span class="muted small ltr">${esc(d.license.machine)}</span> <a class="small" href="#/activate">${d.license.mode === "licensed" ? "تمدید" : "فعال‌سازی"}</a></dd>
            <dt>هسته‌های CPU</dt><dd>${fa(d.system.cpu_count)}</dd>
            <dt>پوشه داده‌ها</dt><dd><span class="path">${esc(d.system.data_dir)}</span></dd>
            <dt>پوشه مدل‌ها</dt><dd><span class="path">${esc(d.system.models_dir)}</span></dd></dl>
        </div></div></div>
      </div></details>
      <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.down} به‌روزرسانی برنامه</h2></div>
        <div class="card-b" id="s-update"></div></div>
      <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.mic} ارسال ویس از گوشی (شبکه محلی)</h2></div>
        <div class="card-b" id="s-lan"></div></div>
      <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.shield} پشتیبان‌گیری</h2>
        <div class="row"><button class="btn" id="s-backup-import">${I.folder} افزودن از فایل</button><button class="btn" id="s-backup-now">${I.plus} پشتیبان‌گیری الان</button></div></div>
        <div class="card-b small muted" style="padding:10px 20px">هر روز یک پشتیبان خودکار از اطلاعات برنامه (ردیف‌ها، متن ویس‌ها، واژه‌نامه، اصلاحات، تنظیمات و ستون‌های فایل‌های اکسل) گرفته و ۱۴ پشتیبان آخر نگه داشته می‌شود. فایل‌های صوتی به‌خاطر حجم در پشتیبان نیستند. پیش از هر بازگردانی، از وضعیت فعلی هم پشتیبان گرفته می‌شود تا قابل برگشت باشد.</div>
        <div class="card-b" id="s-benc" style="padding:10px 20px;border-top:1px solid var(--border)"></div>
        <div class="table-wrap" id="s-backups"></div></div>
      <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.trash} نگهداری، گزارش و حریم خصوصی</h2></div><div class="card-b stack">
        <div class="row">
          <a class="btn" href="/api/report/errors.xlsx">${I.down} گزارش خطاها و هشدارها</a>
          <button class="btn" id="s-report">${I.down} گزارش کامل ردیف‌ها (با متن ویس)</button>
          <button class="btn" id="s-open-data">${I.open} باز کردن پوشه داده‌ها</button>
          <label class="check small"><input type="checkbox" id="s-sound" ${localStorage.getItem("v2x.sound") !== "0" ? "checked" : ""}> صدای پایان پردازش</label>
        </div>
        <details><summary>رخدادهای اخیر</summary><div id="s-events" class="small" style="margin-top:8px"></div></details>
      </div></div>
      <div class="card danger-zone" style="margin-top:18px"><div class="card-h"><h2>${I.alert} کارهای برگشت‌ناپذیر</h2></div><div class="card-b stack">
        <div class="muted small">این کارها قابل برگرداندن نیستند؛ پیش از آن از «پشتیبان‌گیری» یک پشتیبان بگیرید. فایل‌های صوتی برای پخش در بررسی نگه داشته می‌شوند؛ پس از ثبت در اکسل می‌توانید آن‌ها را پاک کنید و متن ویس‌ها و ردیف‌ها باقی می‌مانند.</div>
        <div class="row"><button class="btn danger" id="s-purge">${I.trash} حذف فایل‌های صوتیِ ثبت‌شده</button>
          <button class="btn danger" id="s-wipe">${I.trash} پاک‌کردن کامل اطلاعات</button></div>
      </div></div>`;
    $$("[data-dl]").forEach((b) => b.onclick = async () => {
      if (!(await confirmBox("دریافت مدل", `مدل <b class="ltr">${esc(b.dataset.dl)}</b> از اینترنت (Hugging Face) دریافت می‌شود. این تنها ارتباط اینترنتی برنامه است و هیچ ویس یا اطلاعاتی ارسال نمی‌شود. ادامه می‌دهید؟`, "دریافت"))) return;
      try { await api("/api/models/download", { method: "POST", body: { name: b.dataset.dl } }); toast("دریافت شروع شد."); poll(); } catch (e) { toastErr(e); }
    });
    $$("input[name=s-engine]").forEach((r) => r.onchange = async () => {
      try { await api("/api/settings", { method: "PUT", body: { speech_engine: r.value } });
        toast(r.value === "offline" ? "از این پس ویس‌ها فقط روی همین رایانه تبدیل می‌شوند." : "از این پس ویس‌ها آنلاین تبدیل می‌شوند.", "ok"); draw(); }
      catch (e) { toastErr(e); draw(); }
    });
    $("#s-copyfirst").onchange = async (e) => {
      try { await api("/api/settings", { method: "PUT", body: { review_copy_first: e.target.checked } }); toast(e.target.checked ? "از این پس ثبت‌ها اول در یک کپی انجام می‌شوند." : "از این پس ثبت‌ها مستقیم در فایل انجام می‌شوند.", "ok"); }
      catch (er) { toastErr(er); e.target.checked = !e.target.checked; }
    };
    $("#s-inbox-pick").onclick = async () => { const p = await pickPath("audio", $("#s-inbox").value.trim()); if (p) $("#s-inbox").value = p; };
    $("#s-inbox-save").onclick = async () => {
      const v = $("#s-inbox").value.trim();
      try { await api("/api/settings", { method: "PUT", body: { inbox_dir: v } }); toast(v ? "پوشه ورودی فعال شد." : "پوشه ورودی خاموش شد.", "ok"); refreshStatus(); }
      catch (e) { toastErr(e); }
    };
    $("#s-save").onclick = async () => {
      const body = {
        model_name: ($("input[name=model]:checked") || {}).value || s.model_name,
        beam_size: +$("#s-beam").value || 2,cpu_threads: +$("#s-threads").value || 0,
        vad_filter: $("#s-vad").checked, use_dictionary_hotwords: $("#s-hot").checked,
        initial_prompt: $("#s-prompt").value, default_area_code: $("#s-area").value.trim(),
        similarity_suggest: +$("#s-sim").value || 0.78,
        learn_auto_threshold: Math.max(1, +$("#s-learn").value || 2),
        model_idle_minutes: Math.max(0, +$("#s-idle").value || 0),
        review_spoken_phones: $("#s-revphone").checked,
        kb_auto_spelling: $("#s-kbspell").checked,
        required_fields: $$("[data-req]").filter((c) => c.checked).map((c) => c.dataset.req),
      };
      if (!body.required_fields.length) return toast("دست‌کم یک فیلد باید الزامی باشد.", "err");
      try { await api("/api/settings", { method: "PUT", body }); toast("تنظیمات ذخیره شد.", "ok"); refreshStatus(); draw(); } catch (e) { toastErr(e); }
    };
    $("#s-reval").onclick = async () => {
      try { const r = await api("/api/records/revalidate-all", { method: "POST" }); toast(`${fa(r.count)} ردیف دوباره اعتبارسنجی شد.`, "ok"); refreshStatus(); } catch (e) { toastErr(e); }
    };
    $("#s-reext").onclick = async () => {
      try {
        const r = await api("/api/records/reextract-all", { method: "POST" });
        toast(`${fa(r.reextracted)} ویس دوباره استخراج شد${r.protected ? `؛ ${fa(r.protected)} ویس به‌خاطر اصلاح یا تأیید دستی دست نخورد` : ""}.`, "ok");
        refreshStatus();
      } catch (e) { toastErr(e); }
    };
    $("#s-open-data").onclick = () => api("/api/open-folder", { method: "POST", body: { path: d.system.data_dir } }).catch(toastErr);
    $("#s-sound").onchange = (e) => localStorage.setItem("v2x.sound", e.target.checked ? "1" : "0");
    const drawBackups = async () => {
      const { backups } = await api("/api/backups");
      const box = $("#s-backups");
      if (!box) return;
      if (!backups.length) { box.innerHTML = `<div class="empty small">هنوز پشتیبانی گرفته نشده است.</div>`; return; }
      box.innerHTML = `<table class="table"><thead><tr><th>زمان</th><th>نوع</th><th>محتوا</th><th>حجم</th><th></th></tr></thead><tbody>
        ${backups.map((b) => `<tr><td class="small">${fa((b.created_at || "").replace("T", " "))}</td><td>${esc(b.reason_label || b.reason)}${b.damaged ? " " + chip("err", "خراب") : ""}</td>
          <td class="small muted">${fa(b.counts?.audio_files ?? 0)} ویس، ${fa(b.counts?.records ?? 0)} ردیف، ${fa(b.counts?.entities ?? 0)} نام</td><td class="small">${fmtSize(b.size)}</td>
          <td class="actions"><button class="btn sm ghost" data-bexport="${esc(b.name)}" title="دریافت فایل پشتیبان">${I.down}</button>
            ${b.damaged ? "" : `<button class="btn sm" data-restore="${esc(b.name)}">بازگردانی</button>`}</td></tr>`).join("")}</tbody></table>`;
      $$("[data-bexport]", box).forEach((btn) => btn.onclick = async () => {
        const enc = await api("/api/backups/encryption");
        if (!enc.enabled && !(await confirmBox("دریافت پشتیبان بدون رمز", "رمزگذاری پشتیبان خاموش است؛ این فایل همه اطلاعات مشتریان را بدون قفل دارد و هر کس آن را داشته باشد می‌تواند بخواند. ادامه می‌دهید؟", "دریافت", "danger"))) return;
        try { await downloadPost(`/api/backups/${encodeURIComponent(btn.dataset.bexport)}/export`, {}); }
        catch (e) { toastErr(e); }
      });
      $$("[data-restore]", box).forEach((btn) => btn.onclick = async () => {
        const ok = await confirmBox("بازگردانی اطلاعات", `<div class="stack"><div class="alert warn">${I.alert}<div class="alert-body">همه ردیف‌ها، واژه‌نامه، اصلاحات، تنظیمات و ستون‌های فایل‌های اکسل به وضعیت این پشتیبان برمی‌گردند.</div></div>
          <div>پیش از آن، از وضعیت فعلی یک پشتیبان «پیش از بازگردانی» گرفته می‌شود تا در صورت نیاز برگردید. فایل اکسل شرکت تغییر نمی‌کند.</div></div>`, "بازگردانی", "danger");
        if (!ok) return;
        try {
          const r = await api(`/api/backups/${encodeURIComponent(btn.dataset.restore)}/restore`, { method: "POST" });
          toast("اطلاعات بازگردانده شد. پشتیبان وضعیت قبلی: " + r.safety_backup, "ok");
          refreshStatus(); drawBackups();
        } catch (e) { toastErr(e); }
      });
    };
    const drawEnc = async () => {
      const E = await api("/api/backups/encryption");
      const box = $("#s-benc");
      if (!box) return;
      box.innerHTML = `<div class="stack">
        <label class="check"><input type="checkbox" id="benc-on" ${E.enabled ? "checked" : ""}> پشتیبانی که دریافت می‌کنید (برای فلش یا رایانه دیگر) با گذرواژه قفل شود</label>
        ${E.enabled ? `<div class="small ${E.has_password ? "muted" : ""}" ${E.has_password ? "" : 'style="color:var(--warn)"'}>${E.has_password
          ? "گذرواژه تنظیم شده است. برای بازگردانی پشتیبان روی رایانه دیگر همین گذرواژه لازم است؛ آن را جای امن یادداشت کنید."
          : "هنوز گذرواژه‌ای تنظیم نشده است؛ تا تنظیم نکنید، دریافت پشتیبان ممکن نیست."}</div>
          <div class="row"><input class="input sm ltr" type="password" id="benc-p1" placeholder="${E.has_password ? "گذرواژه جدید" : "گذرواژه"} (دست‌کم ۸ نویسه)" autocomplete="new-password" style="max-width:220px">
            <input class="input sm ltr" type="password" id="benc-p2" placeholder="تکرار گذرواژه" autocomplete="new-password" style="max-width:220px">
            <button class="btn sm" id="benc-save">${E.has_password ? "تغییر گذرواژه" : "ذخیره گذرواژه"}</button></div>
          ${E.has_password ? '<div class="muted small">با تغییر گذرواژه، پشتیبان‌هایی که قبلاً دریافت کرده‌اید همچنان با گذرواژه قبلی باز می‌شوند.</div>' : ""}`
        : '<div class="small" style="color:var(--warn)">پشتیبان‌های دریافتی بدون رمز ذخیره می‌شوند.</div>'}</div>`;
      $("#benc-on").onchange = async (e) => {
        if (!e.target.checked && !(await confirmBox("خاموش کردن رمزگذاری پشتیبان", "از این به بعد فایل پشتیبانی که دریافت می‌کنید بدون قفل است و هر کس آن را داشته باشد، اطلاعات مشتریان را می‌بیند. ادامه می‌دهید؟", "خاموش شود", "danger"))) { e.target.checked = true; return; }
        try { await api("/api/backups/encryption", { method: "PUT", body: { enabled: e.target.checked } }); drawEnc(); } catch (er) { toastErr(er); }
      };
      $("#benc-save")?.addEventListener("click", async () => {
        const p1 = $("#benc-p1").value, p2 = $("#benc-p2").value;
        if (p1 !== p2) return toast("دو گذرواژه یکی نیستند.", "err");
        try { await api("/api/backups/encryption", { method: "PUT", body: { enabled: true, password: p1 } }); toast("گذرواژه پشتیبان ذخیره شد.", "ok"); drawEnc(); } catch (er) { toastErr(er); }
      });
    };
    drawEnc().catch(() => {});
    $("#s-backup-import").onclick = () => openModal({
      title: "افزودن پشتیبان از فایل",
      body: `<div class="stack"><label>فایل پشتیبان (.v2xbak یا .zip)<input type="file" id="bi-file" accept=".v2xbak,.zip"></label>
        <label>گذرواژه <span class="muted small">(فقط اگر با گذرواژه‌ای غیر از گذرواژه فعلی این رایانه قفل شده)</span><input class="input ltr" type="password" id="bi-pw" autocomplete="off"></label></div>`,
      actions: [{ label: "افزودن", cls: "primary", onClick: async (m) => {
        const f = $("#bi-file", m).files[0];
        if (!f) { toast("فایل پشتیبان را انتخاب کنید.", "err"); return false; }
        const form = new FormData();
        form.append("file", f);
        form.append("password", $("#bi-pw", m).value);
        try { await api("/api/backups/import", { method: "POST", form }); toast("پشتیبان به فهرست اضافه شد؛ برای برگرداندن اطلاعات، «بازگردانی» را بزنید.", "ok"); drawBackups(); return true; }
        catch (e) { toastErr(e); return false; }
      } }, { label: "انصراف", cls: "ghost", value: false }],
    });
    $("#s-backup-now").onclick = async () => {
      try { const b = await api("/api/backups", { method: "POST" }); toast(`پشتیبان ساخته شد (${fmtSize(b.size)}).`, "ok"); drawBackups(); } catch (e) { toastErr(e); }
    };
    drawBackups().catch(() => {});
    const drawLan = async () => {
      const L = await api("/api/lan");
      const box = $("#s-lan");
      if (!box) return;
      box.innerHTML = `<div class="stack">
        <div class="muted small">بازاریاب‌ها در دفتر، با گوشیِ وصل به همان وای‌فای، ویس را از مرورگر گوشی مستقیم می‌فرستند. فقط صفحه ارسال ویس با رمز از گوشی باز می‌شود؛ ردیف‌ها، اکسل و تنظیمات فقط روی همین رایانه در دسترس‌اند. اطلاعات از شبکه محلی بیرون نمی‌رود.</div>
        <label class="check"><input type="checkbox" id="lan-on" ${L.enabled ? "checked" : ""}> فعال باشد</label>
        ${L.enabled ? `
          <label class="check"><input type="checkbox" id="lan-auto" ${L.auto_start ? "checked" : ""}> پردازش ویس‌های رسیده از گوشی خودکار شروع شود</label>
          ${L.restart_needed ? `<div class="alert warn">${I.alert}<div class="alert-body"><b>یک بار برنامه را ببندید و دوباره باز کنید</b>تا دسترسی از شبکه فعال شود. اگر ویندوز درباره «دیوار آتش» (Firewall) پرسید، گزینه «شبکه خصوصی» را مجاز کنید.</div></div>` : ""}
          <dl class="kv"><dt>نشانی در گوشی</dt><dd>${L.urls.length ? L.urls.map((u) => `<span class="path">${esc(u)}</span>`).join(" ") : '<span class="muted">این رایانه به شبکه محلی وصل نیست.</span>'}</dd>
            <dt>رمز</dt><dd><span class="phone-view"><span class="ltr">${esc(L.pin)}</span></span> <button class="btn sm ghost" id="lan-pin">رمز جدید</button></dd></dl>
          <div class="muted small">رمز را فقط به بازاریاب‌های خودتان بدهید. هر گوشی فقط یک بار رمز را وارد می‌کند و پس از آن در فهرست زیر است. با «رمز جدید»، همه گوشی‌ها برداشته می‌شوند.</div>
          <label class="row small">خاموش شدن خودکار اگر هیچ گوشی‌ای ویس نفرستاد:
            <select class="input sm" id="lan-idle" style="width:auto">${[[0, "هرگز"], [4, "پس از ۴ ساعت"], [8, "پس از ۸ ساعت"], [12, "پس از ۱۲ ساعت"], [24, "پس از یک روز"]]
              .map(([v, l]) => `<option value="${v}" ${L.idle_hours === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          ${L.devices.length ? `<table class="table"><thead><tr><th>گوشی وصل‌شده</th><th>آخرین ارسال</th><th></th></tr></thead><tbody>
            ${L.devices.map((d) => `<tr><td><b>${esc(d.name)}</b> <span class="muted small ltr">${esc(d.last_ip || "")}</span></td>
              <td class="small">${fa((d.last_seen || "").replace("T", " "))}</td>
              <td class="actions"><button class="btn sm danger" data-devdel="${d.id}">برداشتن</button></td></tr>`).join("")}</tbody></table>`
            : '<div class="muted small">هنوز گوشی‌ای وصل نشده است.</div>'}` : ""}
      </div>`;
      const save = async () => {
        try { await api("/api/lan", { method: "PUT", body: { enabled: $("#lan-on").checked, auto_start: $("#lan-auto") ? $("#lan-auto").checked : true, idle_hours: +($("#lan-idle")?.value ?? L.idle_hours) } }); drawLan(); }
        catch (e) { toastErr(e); }
      };
      $("#lan-on").onchange = save;
      $("#lan-auto")?.addEventListener("change", save);
      $("#lan-idle")?.addEventListener("change", save);
      $$("[data-devdel]", box).forEach((b) => b.onclick = async () => {
        try { await api(`/api/lan/devices/${b.dataset.devdel}`, { method: "DELETE" }); toast("گوشی برداشته شد؛ دیگر نمی‌تواند ویس بفرستد.", "ok"); drawLan(); } catch (e) { toastErr(e); }
      });
      $("#lan-pin")?.addEventListener("click", async () => {
        if (!(await confirmBox("رمز جدید", "همه گوشی‌های وصل‌شده برداشته می‌شوند و باید با رمز جدید دوباره وصل شوند. ادامه می‌دهید؟", "رمز جدید"))) return;
        try { await api("/api/lan/new-pin", { method: "POST" }); drawLan(); } catch (e) { toastErr(e); }
      });
    };
    drawLan().catch(() => {});
    const drawUpdate = async () => {
      const U = await api("/api/update");
      const box = $("#s-update");
      if (!box) return;
      box.innerHTML = `<div class="stack">
        <dl class="kv"><dt>نسخه فعلی</dt><dd>${fa(U.version)}</dd></dl>
        ${!U.supported ? `<div class="muted small">به‌روزرسانی سبک فقط در نسخه قابل‌حمل (DataVox.exe) در دسترس است.</div>` : U.staged
          ? `<div class="alert ok">${I.ok}<div class="alert-body"><b>نسخه ${fa(U.staged.version)} آماده نصب است</b>${U.one_click
              ? "با «نصب به‌روزرسانی»، برنامه چند ثانیه بسته و با نسخه جدید دوباره باز می‌شود؛ لازم نیست کاری بکنید."
              : "برنامه را با «خروج از برنامه» ببندید و دوباره باز کنید تا نسخه جدید جایگزین شود."} اگر نسخه جدید اجرا نشود، برنامه خودکار به نسخه فعلی برمی‌گردد.${U.staged.notes ? `<div class="small">${esc(U.staged.notes)}</div>` : ""}</div>
              ${U.one_click ? `<button class="btn sm primary" id="up-install">${I.check} نصب به‌روزرسانی</button>` : ""}<button class="btn sm ghost" id="up-cancel">لغو</button></div>`
          : `<div class="muted small">بسته به‌روزرسانی (فایل DataVox-update-….zip، حدود ۱ مگابایت) را انتخاب کنید. فقط بسته‌ای را نصب کنید که از سازنده برنامه گرفته‌اید. اطلاعات شما (پوشه data) دست نمی‌خورد.</div>
             <div class="row"><input type="file" id="up-file" accept=".zip" hidden><button class="btn" id="up-pick">${I.upload} انتخاب بسته به‌روزرسانی</button></div>`}
      </div>`;
      $("#up-pick")?.addEventListener("click", () => $("#up-file").click());
      $("#up-file")?.addEventListener("change", async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append("file", f, f.name);
        try { const r = await api("/api/update", { method: "POST", form: fd }); toast(U.one_click ? `نسخه ${fa(r.version)} آماده نصب است.` : `نسخه ${fa(r.version)} آماده شد؛ برنامه را ببندید و دوباره باز کنید.`, "ok"); drawUpdate(); }
        catch (er) { toastErr(er); }
      });
      $("#up-install")?.addEventListener("click", () => installUpdate(U.version, U.staged.version));
      $("#up-cancel")?.addEventListener("click", async () => { try { await api("/api/update", { method: "DELETE" }); drawUpdate(); } catch (er) { toastErr(er); } });
    };
    drawUpdate().catch(() => {});
    $("#s-purge").onclick = async () => {
      if (!(await confirmBox("حذف فایل‌های صوتی", "فایل‌های صوتی ویس‌هایی که همه ردیف‌هایشان در اکسل ثبت (یا رد) شده‌اند، برای همیشه از پوشه برنامه حذف می‌شوند. فایل‌های اصلی شما در جای خودشان دست نمی‌خورند.", "حذف", "danger"))) return;
      try { const r = await api("/api/maintenance/purge-audio", { method: "POST", body: { scope: "exported" } }); toast(`${fa(r.deleted)} فایل صوتی حذف شد.`, "ok"); } catch (e) { toastErr(e); }
    };
    $("#s-report").onclick = async () => {
      if (!(await confirmBox("گزارش کامل ردیف‌ها", "این فایل نام، شماره تلفن، نشانی و متن کامل همه ویس‌ها را دارد. آن را فقط در جای امن نگه دارید و برای کسی که اجازه دیدن این اطلاعات را ندارد نفرستید.", "دریافت گزارش"))) return;
      location.href = "/api/report/records.xlsx";
    };
    $("#s-wipe").onclick = async () => {
      const phrase = "پاک شود";
      const ok = await openModal({
        title: "پاک‌کردن کامل اطلاعات",
        body: `<div class="stack"><div>همه ردیف‌ها، متن و فایل ویس‌ها، واژه‌نامه آموخته، پشتیبان‌ها، نسخه‌های اکسل داخل پوشه برنامه و گزارش‌ها <b>برای همیشه</b> پاک می‌شوند و برگشت‌پذیر نیست. تنظیمات و فهرست فایل‌های اکسل می‌مانند؛ فایل اکسل اصلی و فایل‌های ساخته‌شده در پوشه‌های خودتان دست نمی‌خورند.</div>
          <label>برای تأیید، عبارت «${phrase}» را بنویسید:<input id="wipe-phrase" type="text" autocomplete="off"></label></div>`,
        actions: [{ label: "پاک‌کردن همه", cls: "danger", onClick: async (m) => {
          const v = $("#wipe-phrase", m).value.trim();
          if (v !== phrase) { toast(`عبارت «${phrase}» را دقیقاً بنویسید.`, "err"); return false; }
          try { await api("/api/maintenance/wipe", { method: "POST", body: { confirm: v } }); return true; }
          catch (e) { toastErr(e); return false; }
        } }, { label: "انصراف", cls: "ghost", value: false }],
      });
      if (ok) { toast("همه اطلاعات پاک شد.", "ok"); refreshStatus(); draw(); }
    };
    const ev = await api("/api/events");
    $("#s-events").innerHTML = ev.events.length ? `<ul class="reasons">${ev.events.map((e) => `<li>${fa(e.at.replace("T", " "))} — ${esc(e.message.split("\n")[0])}</li>`).join("")}</ul>` : '<span class="muted">رخدادی ثبت نشده است.</span>';
    return d;
  };
  const poll = async () => {
    const d = await draw();
    if (d.download.status === "running" && state.page === "settings") setTimeout(poll, 2500);
  };
  await poll();
}

// ---------------- تم ----------------
const THEMES = [["auto", "خودکار"], ["light", "روشن"], ["dark", "تیره"]];
function applyTheme(t) {
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  $("#theme-label").textContent = "تم: " + (THEMES.find(([k]) => k === t) || THEMES[0])[1];
}
applyTheme(localStorage.getItem("v2x.theme") || "auto");
$("#btn-theme").addEventListener("click", () => {
  const cur = localStorage.getItem("v2x.theme") || "auto";
  const next = THEMES[(THEMES.findIndex(([k]) => k === cur) + 1) % THEMES.length][0];
  localStorage.setItem("v2x.theme", next);
  applyTheme(next);
});

// ---------------- خروج و نمونه‌ها ----------------
$("#btn-exit").addEventListener("click", async () => {
  const running = state.status?.worker.running;
  const ok = await confirmBox("خروج از برنامه", running
    ? "پردازش در جریان است. با خروج، فایل فعلی به صف برمی‌گردد و دفعه بعد ادامه پیدا می‌کند. همه نتایج قبلی ذخیره شده‌اند."
    : "برنامه بسته می‌شود. همه اطلاعات ذخیره شده‌اند و دفعه بعد از همین‌جا ادامه می‌دهید.", "خروج", "danger");
  if (!ok) return;
  try { await api("/api/shutdown", { method: "POST" }); } catch { }
  document.body.innerHTML = `<div class="empty" style="min-height:100vh;justify-content:center">${I.ok}
    <h2 style="margin:0">برنامه بسته شد</h2><div>برای اجرای دوباره، روی «DataVox» در دسکتاپ یا DataVox.exe دوبار کلیک کنید.</div>
    <div class="muted small">می‌توانید این صفحه را ببندید.</div></div>`;
});

// ---------------- شروع ----------------
// ---------- فعال‌سازی (مجوز آفلاین) ----------
async function refreshLicense() {
  try { state.lic = await api("/api/license"); renderBanners(); } catch { }
}

/** پیام آماده درخواست اشتراک یا تمدید برای فروشنده (نام، تلفن، کد رایانه). */
/** نوع درخواست: اشتراک (آزمایشی/فعال‌نشده)، تمدید (یک‌ساله یا تمام‌شده)، پشتیبانی (نامحدود). */
function requestKind(lic) {
  if (lic.lapsed || (lic.mode === "licensed" && lic.expires)) return "renew";
  return lic.mode === "licensed" ? "support" : "subscribe";
}
const REQUEST_TITLE = { subscribe: "درخواست اشتراک", renew: "درخواست تمدید", support: "تماس با پشتیبانی" };
function requestMessage(lic, name, phone) {
  const kind = requestKind(lic);
  return [{ subscribe: "درخواست اشتراک «DataVox»", renew: "درخواست تمدید اشتراک «DataVox»", support: "درخواست پشتیبانی «DataVox»" }[kind],
    `نام: ${name || "—"}`, `تلفن: ${phone || "—"}`, `کد رایانه: ${lic.machine}`, `نسخه: ${lic.version}`].join("\n");
}
/** شماره واتس‌اپ به قالب بین‌المللی (۰۹۱۲… ← ۹۸۹۱۲…). */
function waNumber(n) {
  const d = String(n || "").replace(/[۰-۹]/g, (c) => "۰۱۲۳۴۵۶۷۸۹".indexOf(c)).replace(/\D/g, "");
  return d.startsWith("00") ? d.slice(2) : d.startsWith("0") ? "98" + d.slice(1) : d;
}

// لوگوی پیام‌رسان‌ها (فایل‌های web/brand؛ رایانه مشتری اینترنت لازم ندارد)
const MESSENGERS = {
  telegram: { label: "تلگرام", logo: "/static/brand/telegram.svg" },
  whatsapp: { label: "واتس‌اپ", logo: "/static/brand/whatsapp.svg" },
  bale: { label: "بله", logo: "/static/brand/bale.svg" },
  email: { label: "ایمیل", logo: "" },
};
const MAIL_ICON = '<svg class="logo mail" viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="M3.5 7l8.5 6 8.5-6"/></svg>';
const msgrLogo = (k) => MESSENGERS[k].logo ? `<img class="logo" src="${MESSENGERS[k].logo}" alt="">` : MAIL_ICON;

/** کارت وضعیت بالای صفحه: مهم‌ترین چیزی که کاربر باید ببیند. */
function activationHero(lic) {
  const T = lic.trial || {};
  const meter = (left, total, unit) => `<div class="act-meter"><b>${fa(left)}</b> <span>${unit} مانده</span>
    <div class="bar"><i style="width:${Math.max(0, Math.min(100, Math.round(100 * left / total)))}%"></i></div></div>`;
  if (lic.mode === "trial") return `<section class="act-hero info">
    <div class="act-hero-t">${I.info}<div><h2>نسخه آزمایشی</h2><p>هرکدام زودتر تمام شود، دوره آزمایشی پایان می‌یابد. برای ادامه، اشتراک بگیرید.</p></div></div>
    <div class="act-meters">${meter(T.days_left, 10, "روز")}${meter(T.voices_left, 10, "ویس")}</div></section>`;
  if (lic.mode === "expired") return `<section class="act-hero warn">
    <div class="act-hero-t">${I.alert}<div><h2>${lic.lapsed ? "اشتراک شما تمام شده است" : "دوره آزمایشی تمام شد"}</h2>
      <p>${lic.lapsed ? "برای پردازش ویس تازه، اشتراک را تمدید کنید." : (T.reason === "ویس" ? "۱۰ ویس آزمایشی پردازش شده است." : "۱۰ روز آزمایشی گذشته است.") + " برای ادامه، اشتراک بگیرید."}
      ردیف‌های قبلی، ثبت در اکسل و پشتیبان در دسترس‌اند.</p></div></div></section>`;
  const soon = lic.days_left != null && lic.days_left <= 15;
  const left = lic.expires_jalali ? `<div class="act-meters"><div class="act-meter"><b>${fa(Math.max(0, lic.days_left ?? 0))}</b> <span>روز مانده</span></div></div>` : "";
  return `<section class="act-hero ${soon ? "warn" : "ok"}">
    <div class="act-hero-t">${soon ? I.alert : I.ok}<div><h2>${soon ? "اشتراک به‌زودی تمام می‌شود" : "برنامه فعال است"}</h2>
      <p>${lic.customer ? `<b>${esc(lic.customer)}</b> — ` : ""}${lic.expires_jalali ? `اشتراک تا ${fa(lic.expires_jalali)}` : "اشتراک نامحدود"}</p></div></div>${left}</section>`;
}

async function renderActivation(el) {
  const lic = state.lic = await api("/api/license");
  const T = lic.trial, C = lic.contact || {};
  const kind = requestKind(lic);
  const licensed = lic.mode === "licensed" || lic.mode === "dev";
  const saved = (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } };
  const channels = ["telegram", "whatsapp", "bale", "email"].filter((k) => C[k]);
  const [mainCh, ...otherCh] = channels;
  const sendBtn = (k, main) => `<${k === "bale" ? "button" : "a"} class="btn ${main ? "primary lg" : ""}" data-send="${k}" ${k === "bale" ? "" : `target="_blank" rel="noopener"`}>
    ${msgrLogo(k)} ${main ? "ارسال در " : ""}${MESSENGERS[k].label}</${k === "bale" ? "button" : "a"}>`;
  // مسیرهای تماس مستقیم با پشتیبانی (بدون پیام آماده)
  const handle = (k) => k === "telegram" ? "@" + C.telegram.replace(/^@/, "") : C[k];
  const contactHref = (k) => k === "telegram" ? `https://t.me/${encodeURIComponent(C.telegram.replace(/^@/, ""))}`
    : k === "whatsapp" ? `https://wa.me/${waNumber(C.whatsapp)}` : k === "email" ? `mailto:${C.email}`
    : /[a-z_]/i.test(C.bale) ? `https://ble.ir/${encodeURIComponent(C.bale)}` : "";
  // مراحل گرفتن مجوز فقط وقتی لازم است: بدون اشتراک، یا اشتراکی که کمتر از ۱۵ روز مانده
  const needsLicense = !licensed || lic.lapsed || (lic.days_left != null && lic.days_left <= 15);
  const steps = kind === "support" || !needsLicense ? "" : `<ol class="act-steps">
      <li><span class="n">۱</span><div><b>کد رایانه را بفرستید</b><span>با یک کلیک در پیام‌رسان</span></div></li>
      <li><span class="n">۲</span><div><b>فایل مجوز را بگیرید</b><span>فروشنده پس از پرداخت می‌فرستد</span></div></li>
      <li><span class="n">۳</span><div><b>اینجا واردش کنید</b><span>بدون نیاز به اینترنت</span></div></li></ol>`;

  el.innerHTML = `<div class="act">
    ${activationHero(lic)}
    ${T?.clock_back ? `<div class="alert warn">${I.alert}<div class="alert-body">تاریخ رایانه عقب‌تر از تاریخ‌های قبلی است؛ تاریخ و ساعت ویندوز را درست کنید.</div></div>` : ""}
    ${lic.error && !lic.lapsed ? `<div class="alert warn">${I.alert}<div class="alert-body">${esc(lic.error)}</div></div>` : ""}
    ${steps}
    <div class="act-grid">
      <div class="act-main">
        <div class="card"><div class="card-h"><h2>${kind === "support" ? "" : `<span class="n">۱</span> `}${REQUEST_TITLE[kind]}</h2></div><div class="card-b stack">
          <div>
            <span class="act-label">کد این رایانه${kind === "support" ? " (برای پشتیبانی)" : ""}</span>
            <div class="act-code"><b id="act-code">${esc(lic.machine)}</b><button class="btn" id="act-copy">${I.file} کپی کد</button></div>
          </div>
          <div class="act-fields">
            <label><span class="act-label">نام شما یا نام شرکت <i>(اختیاری)</i></span>
              <input class="input" id="act-name" value="${esc(saved("v2x.act.name") || lic.customer || "")}"></label>
            <label><span class="act-label">شماره تماس شما <i>(اختیاری)</i></span>
              <input class="input ltr" id="act-phone" value="${esc(saved("v2x.act.phone"))}"></label>
          </div>
          ${channels.length ? `<div>
            <span class="act-label">پیام آماده (با کد رایانه) را برای ${esc(C.name || "فروشنده")} بفرستید:</span>
            <div class="act-send">${sendBtn(mainCh, true)}${otherCh.map((k) => sendBtn(k, false)).join("")}
              <button class="btn ghost" id="act-copymsg">کپی پیام</button></div>
          </div>` : `<div class="act-send"><button class="btn primary lg" id="act-copymsg">کپی پیام</button>
            <span class="muted">پیام را کپی کنید و برای فروشنده بفرستید.</span></div>`}
          <details class="act-preview"><summary>پیش‌نمایش پیام</summary>
            <textarea class="input" id="act-msg" rows="5" readonly></textarea></details>
        </div></div>

        <${licensed ? "details" : "div"} class="card act-import live-bg"><${licensed ? "summary" : "div"} class="card-h"><h2>${licensed ? "" : `<span class="n">۲</span> `}${licensed ? "وارد کردن مجوز تازه" : "وارد کردن مجوز"}</h2></${licensed ? "summary" : "div"}>
          <div class="card-b stack">
            <div class="act-drop" id="act-drop">
              ${I.upload}
              <b id="act-drop-t">فایل مجوز را اینجا بکشید</b>
              <span class="muted">فایلی که فروشنده فرستاده (با پسوند ‎.v2x)</span>
              <input type="file" id="act-file" accept=".v2x,.txt" hidden>
              <button class="btn" id="act-pick">${I.folder} انتخاب فایل مجوز</button>
            </div>
            <details class="act-paste"><summary>یا متن مجوز را بچسبانید</summary>
              <textarea class="input ltr" id="act-text" rows="3" placeholder="V2X1...."></textarea></details>
            <div class="row"><button class="btn primary lg" id="act-go" disabled>${I.check} فعال‌سازی</button>
              <span class="muted small" id="act-go-hint">اول فایل مجوز را انتخاب کنید.</span></div>
          </div></${licensed ? "details" : "div"}>
      </div>

      <aside class="card act-support"><div class="card-h"><h2>پشتیبانی</h2></div><div class="card-b stack">
        ${C.name ? `<div class="act-seller">${esc(C.name)}</div>` : ""}
        ${C.phone ? `<div class="act-phone-row"><a class="act-phone ltr" href="tel:${esc(C.phone)}">${esc(C.phone)}</a>
          <button class="btn sm" id="act-copyphone">کپی شماره</button></div>` : ""}
        ${channels.length ? `<div class="act-contact">${channels.map((k) => {
          const href = contactHref(k);
          const inner = `${msgrLogo(k)}<span>${MESSENGERS[k].label}</span><span class="handle ltr">${esc(handle(k))}</span>`;
          return href ? `<a class="act-link" href="${esc(href)}" target="_blank" rel="noopener">${inner}</a>`
            : `<button class="act-link" data-copy="${esc(C[k])}">${inner}</button>`;
        }).join("")}</div>` : ""}
        ${!C.name && !C.phone && !channels.length ? `<div class="muted">اطلاعات تماس فروشنده در این نسخه ثبت نشده است.</div>` : ""}
      </div></aside>
    </div>
  </div>`;

  const update = () => {
    const name = $("#act-name").value.trim(), phone = $("#act-phone").value.trim();
    try { localStorage.setItem("v2x.act.name", name); localStorage.setItem("v2x.act.phone", phone); } catch { }
    const msg = requestMessage(lic, name, phone);
    $("#act-msg").value = msg;
    $$("[data-send]", el).forEach((b) => {
      const k = b.dataset.send;
      if (k === "telegram") b.href = `https://t.me/${encodeURIComponent(C.telegram.replace(/^@/, ""))}?text=${encodeURIComponent(msg)}`;
      if (k === "whatsapp") b.href = `https://wa.me/${waNumber(C.whatsapp)}?text=${encodeURIComponent(msg)}`;
      if (k === "email") b.href = `mailto:${C.email}?subject=${encodeURIComponent(msg.split("\n")[0])}&body=${encodeURIComponent(msg)}`;
    });
  };
  $("#act-name").oninput = $("#act-phone").oninput = update;
  update();
  const copy = async (text, ok) => {
    try { await navigator.clipboard.writeText(text); toast(ok, "ok"); } catch { toast("متن را انتخاب و کپی کنید."); }
  };
  $("#act-copy").onclick = () => copy(lic.machine, "کد کپی شد.");
  $("#act-copymsg").onclick = () => copy($("#act-msg").value, "پیام کپی شد.");
  $("#act-copyphone")?.addEventListener("click", () => copy(C.phone, "شماره کپی شد."));
  $$("[data-copy]", el).forEach((b) => b.onclick = () => copy(b.dataset.copy, "کپی شد."));
  $('[data-send="bale"]', el)?.addEventListener("click", async () => {
    // پیوند مستقیم بله فقط با آیدی کار می‌کند و متن آماده نمی‌پذیرد؛ پس پیام کپی می‌شود
    const isId = /[a-z_]/i.test(C.bale);
    await copy($("#act-msg").value, isId ? "پیام کپی شد؛ در بله بچسبانید و بفرستید." : `پیام کپی شد؛ در بله به شماره ${C.bale} بفرستید.`);
    if (isId) window.open(`https://ble.ir/${encodeURIComponent(C.bale)}`, "_blank", "noopener");
  });

  // وارد کردن مجوز: کشیدن فایل، انتخاب فایل یا چسباندن متن؛ «فعال‌سازی» فقط وقتی چیزی وارد شده روشن است
  const drop = $("#act-drop"), text = $("#act-text");
  const ready = (fileName) => {
    const has = !!text.value.trim();
    $("#act-go").disabled = !has;
    drop.classList.toggle("has", has && !!fileName);
    if (fileName) $("#act-drop-t").textContent = `«${fileName}» آماده فعال‌سازی است`;
    $("#act-go-hint").textContent = has ? "" : "اول فایل مجوز را انتخاب کنید.";
  };
  const readFile = async (f) => { if (!f) return; text.value = (await f.text()).trim(); ready(f.name); };
  text.oninput = () => ready();
  $("#act-pick").onclick = () => $("#act-file").click();
  $("#act-file").onchange = (e) => readFile(e.target.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); readFile(e.dataTransfer.files[0]); };
  $("#act-go").onclick = async () => {
    try { await api("/api/license", { method: "POST", body: { text: text.value } }); toast("برنامه فعال شد.", "ok"); location.hash = "#/files"; setTimeout(() => location.reload(), 600); }
    catch (e) { toastErr(e); }
  };
}

// ---------- پنجره اختصاصی (DataVox.exe) ----------
const WIN = window.chrome && window.chrome.webview;
if (WIN) {
  // کشیدن و دوبار کلیک روی نوار عنوان: با «app-region: drag» خود ویندوز انجام می‌دهد و این رویدادها اصلاً به صفحه
  // نمی‌رسند؛ اگر WebView2 آن را پشتیبانی نکند، همین رویدادها می‌رسند و کار به پنجره سپرده می‌شود
  WIN.addEventListener("message", (e) => {
    const m = String(e.data);
    if (m === "state:max" || m === "state:normal") {
      document.documentElement.classList.toggle("win-max", m === "state:max");
      const b = $('[data-win="max"]');
      if (b) b.title = m === "state:max" ? "بازگرداندن" : "بزرگ کردن";
    }
  });
  $$("[data-win]").forEach((b) => b.onclick = () => WIN.postMessage(b.dataset.win));
  const bar = $("#titlebar");
  bar.addEventListener("mousedown", (e) => { if (e.button === 0 && e.detail === 1 && !e.target.closest(".tb-btn")) WIN.postMessage("drag"); });
  bar.addEventListener("dblclick", (e) => { if (!e.target.closest(".tb-btn")) WIN.postMessage("max"); });
}

/** نصب به‌روزرسانی آماده بدون بستن دستی: موتور خاموش، نسخه جدید جایگزین و روشن، صفحه خودش بارگذاری می‌شود. */
async function installUpdate(from, to) {
  try { sessionStorage.setItem("v2x.updating", JSON.stringify({ from, to })); } catch { }
  if (WIN) WIN.postMessage("updating");
  const ov = document.createElement("div");
  ov.className = "update-overlay";
  ov.innerHTML = `<div class="card"><div class="spinner"></div><b>در حال نصب نسخه ${fa(to)}…</b>
    <div class="muted small" style="margin-top:6px">برنامه چند ثانیه دیگر خودش با نسخه جدید باز می‌شود؛ پنجره را نبندید.</div></div>`;
  document.body.appendChild(ov);
  try { await api("/api/update/apply", { method: "POST" }); }
  catch (e) { ov.remove(); try { sessionStorage.removeItem("v2x.updating"); } catch { } toastErr(e); return; }
  const t0 = Date.now();
  let wentDown = false;
  while (Date.now() - t0 < 180000) {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      const r = await fetch("/api/update", { cache: "no-store" });
      if (!r.ok) throw new Error();
      const u = await r.json();
      if (wentDown || u.version !== from) { location.reload(); return; }
    } catch { wentDown = true; }
  }
  $("b", ov).textContent = "نصب بیش از حد طول کشید؛ برنامه را ببندید و دوباره باز کنید.";
}

/** پس از بارگذاری دوباره: نتیجه به‌روزرسانی یک‌کلیکی گزارش می‌شود. */
async function reportUpdate() {
  let job = null;
  try { job = JSON.parse(sessionStorage.getItem("v2x.updating") || "null"); sessionStorage.removeItem("v2x.updating"); } catch { }
  if (!job) return;
  try {
    const u = await api("/api/update");
    if (u.version === job.to) toast(`برنامه به نسخه ${fa(job.to)} به‌روز شد.`, "ok");
    else toast("نسخه جدید اجرا نشد و برنامه به نسخه قبلی برگشت؛ اطلاعات شما دست نخورده است.", "err");
  } catch { }
}

(async function init() {
  reportUpdate();
  await refreshLicense();
  try { state.meta = await api("/api/meta"); } catch (e) { toastErr(e); }
  await refreshStatus();
  route();
  setInterval(refreshStatus, 1500);
  setInterval(refreshLicense, 30000);  // شمار ویس و روز آزمایشی
  hasFallback();
  window.__v2xReady = true;  // boot.js: صفحه کامل بالا آمد؛ پیام «بارگذاری نشد» لازم نیست
})();

/** مرورگرهای بدون :has() (Firefox 115 روی ویندوز ۷): وضعیت کشو و نوار ذخیره به‌صورت کلاس روی body */
function hasFallback() {
  try { if (CSS.supports("selector(:has(*))")) return; } catch { }
  const sync = () => {
    document.body.classList.toggle("x-drawer-open", !!document.querySelector(".drawer.open"));
    document.body.classList.toggle("x-save-dirty", !!document.querySelector(".save-bar.dirty"));
  };
  new MutationObserver(sync).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
  sync();
}
