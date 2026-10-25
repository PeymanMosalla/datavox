/* رابط کاربری «ثبت ویس» — بدون وابستگی خارجی، کاملاً محلی */
"use strict";

// ---------------- ابزارها ----------------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fa = (n) => String(n ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const fmtSize = (b) => (b == null ? "" : b < 1024 * 1024 ? fa((b / 1024).toFixed(0)) + " کیلوبایت" : fa((b / 1048576).toFixed(1)) + " مگابایت");
const fmtSec = (s) => (s == null ? "" : s < 60 ? fa(Math.round(s)) + " ثانیه" : fa(Math.floor(s / 60)) + ":" + fa(String(Math.round(s % 60)).padStart(2, "0")));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

async function api(path, { method = "GET", body, form } = {}) {
  const opt = { method, headers: {} };
  if (form) opt.body = form;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  let res;
  try { res = await fetch(path, opt); }
  catch { throw new Error("ارتباط با برنامه برقرار نشد. آیا پنجره برنامه (run.bat) باز است؟"); }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    let msg = data && data.detail ? data.detail : "خطا در انجام درخواست";
    if (Array.isArray(msg)) msg = "اطلاعات ارسالی نامعتبر است.";
    throw new Error(msg);
  }
  return data;
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
const state = { meta: null, status: null, page: "today", profile: null };

async function refreshStatus() {
  let s;
  try { s = await api("/api/status"); } catch { return; }
  const prev = state.status;
  state.status = s;
  const w = s.worker;
  const q = s.files.queued + s.files.processing;
  $("#nav-queue").textContent = q ? fa(q) : "";
  $("#nav-review").textContent = s.records.review ? fa(s.records.review) : "";
  $("#nav-today").textContent = s.records.review ? fa(s.records.review) : "";
  $("#nav-approved").textContent = s.records.approved ? fa(s.records.approved) : "";
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
  const msg = `پردازش ${fa(n)} ویس تمام شد${s.records.review ? `؛ ${fa(s.records.review)} رکورد منتظر بازبینی است` : ""}.`;
  toast(msg, "ok", s.records.review && state.page !== "today" ? { label: "بازبینی", onClick: () => { location.hash = "#/today"; } } : null);
  if (localStorage.getItem("v2x.sound") !== "0") chime();
  if (document.hidden && "Notification" in window && Notification.permission === "granted") {
    try { new Notification("ثبت ویس", { body: msg, lang: "fa", dir: "rtl" }); } catch { }
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
  if (s.pending_replace && state.page === "excel") {
    out.push(`<div class="alert warn">${I.alert}<div class="alert-body"><b>خروجی اکسل هنوز جایگزین فایل اصلی نشده</b>${fa(s.pending_replace)} خروجی ساخته شده که هنوز روی فایل اصلی شرکت اعمال نشده است. پس از بررسی، از بخش «ثبت در اکسل» جایگزینش کنید.</div><a class="btn sm" href="#/excel">مشاهده</a></div>`);
  }
  $("#banners").innerHTML = out.join("");
}

// ---------------- مسیریابی ----------------
const PAGES = {
  today: { title: "کار امروز", sub: "ویس بدهید، موارد مشکوک را ببینید، در اکسل ثبت کنید", render: renderToday },
  dashboard: { title: "داشبورد", sub: "نمای کلی ویس‌ها، پردازش و رکوردها", render: renderDashboard },
  voices: { title: "ویس‌ها و پردازش", sub: "افزودن ویس، صف پردازش و وضعیت هر فایل", render: renderVoices },
  review: { title: "بازبینی اطلاعات", sub: "بررسی، اصلاح و تأیید اطلاعات استخراج‌شده پیش از ثبت", render: renderReview },
  excel: { title: "ثبت در اکسل", sub: "اتصال امن به فایل اکسل شرکت، پیش‌نمایش و ثبت روی کپی", render: renderExcel },
  dictionary: { title: "واژه‌نامه", sub: "نام‌های تأییدشده مهندس‌ها، پروژه‌ها و خیابان‌ها", render: renderDictionary },
  settings: { title: "تنظیمات", sub: "مدل گفتار، قواعد اعتبارسنجی و نگهداری", render: renderSettings },
};
let pageHooks = {};
let routeSeq = 0;
// فقط صفحه‌ای که هنوز نمایش داده می‌شود قلاب به‌روزرسانی ثبت می‌کند (جلوگیری از تداخل صفحه قبلی)
function setHook(seq, fn) { if (seq === routeSeq) pageHooks.onStatus = fn; }

function route() {
  const name = (location.hash.replace(/^#\//, "").split("?")[0]) || "today";
  const p = PAGES[name] || PAGES.today;
  state.page = PAGES[name] ? name : "today";
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === state.page));
  renderBanners();
  $("#page-title").textContent = p.title;
  $("#page-sub").textContent = p.sub;
  pageHooks = {};
  reviewState.reload = reviewState.updateRow = null;  // قلاب‌های صفحه بازبینیِ قبلی به DOM حذف‌شده اشاره دارند
  routeSeq++;
  closeDrawer();
  $("#page").innerHTML = '<div class="row"><span class="spinner"></span></div>';
  p.render($("#page")).catch(toastErr);
}
window.addEventListener("hashchange", route);

// ================= کار امروز =================
/** صفحه اصلی: سه گام کار روزانه — ویس‌ها، موارد نیازمند نگاه کاربر، ثبت در اکسل. */
const todayState = { lastCommit: null };

async function renderToday(el) {
  const seq = routeSeq;
  api("/api/model/warmup", { method: "POST" }).catch(() => {});
  const s0 = state.status || (await api("/api/status"));
  const exts = (state.meta?.audio_extensions || []).join(",");
  el.innerHTML = onboardingCard(s0) + `<div class="today">
    <section class="card"><div class="card-h"><h2><span class="t-n">${fa(1)}</span> ویس‌ها</h2>
        <label class="t-date small muted">تاریخ بازدید <input class="input sm ltr" id="t-date" value="${esc(s0.today)}"></label></div>
      <div class="card-b stack">
        <div class="dropzone slim" id="t-dz"><div class="dz-ico">${I.upload}</div>
          <div><b>ویس‌ها را اینجا رها کنید</b> یا <button class="btn sm" id="t-pick">انتخاب فایل</button>
            <div class="muted small">پردازش خودکار شروع می‌شود. اگر نام فایل تاریخ داشته باشد، همان تاریخ ثبت می‌شود.</div></div>
          <input type="file" id="t-files" multiple accept="${esc(exts)},audio/*" hidden></div>
        <div class="small muted">${s0.setup.inbox ? `${I.folder} ویس‌های تازه پوشه «${esc(s0.setup.inbox.split(/[\\/]/).filter(Boolean).pop())}» هم خودکار برداشته می‌شوند.`
          : `<a href="#/settings">${I.folder} تنظیم پوشه ورودی خودکار</a> — مثلاً پوشه دانلود تلگرام، تا ویس‌ها بدون دانلود و انتخاب دستی برسند.`}</div>
        <div id="t-progress"></div></div></section>
    <section class="card"><div class="card-h"><h2><span class="t-n">${fa(2)}</span> نیاز به نگاه شما</h2><div class="row" id="t-rv-actions"></div></div>
      <div id="t-review"></div></section>
    <section class="card"><div class="card-h"><h2><span class="t-n">${fa(3)}</span> ثبت در اکسل</h2></div>
      <div class="card-b" id="t-excel"></div></section></div>`;
  bindOnboarding();

  const dz = $("#t-dz");
  const add = async (list) => {
    const files = audioOnly(list);
    if (!files.length) return;
    $("#t-progress").innerHTML = `<div class="progress"><div class="progress-bar" id="t-up-bar"></div></div><div class="muted small">در حال افزودن ${fa(files.length)} ویس...</div>`;
    try {
      const results = await uploadAudio(files, $("#t-date").value.trim(), true, (p) => { const b = $("#t-up-bar"); if (b) b.style.width = p + "%"; });
      reportUpload(results);
      if (results.some((r) => r.result === "added")) await startQueue();
    } catch (e) { toastErr(e); }
    await refreshStatus();
    drawProgress();
  };
  $("#t-pick").onclick = () => $("#t-files").click();
  $("#t-files").onchange = (e) => { add(e.target.files); e.target.value = ""; };
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", async (e) => { e.preventDefault(); dz.classList.remove("over"); add(await droppedFiles(e)); });

  function drawProgress() {
    const s = state.status, box = $("#t-progress");
    if (!s || seq !== routeSeq || !box) return;
    const w = s.worker, q = s.files.queued + s.files.processing;
    const parts = [];
    if (w.running) {
      const total = w.run_done + q;
      parts.push(`<div class="row between small"><span>در حال پردازش: <b>${esc(w.current_name || "...")}</b></span>
          <span>${fa(w.run_done)} از ${fa(total)} <button class="btn sm ghost" id="t-stop">${I.stop} توقف</button></span></div>
        <div class="progress"><div class="progress-bar" style="width:${s.progress}%"></div></div>`);
    } else if (q) {
      parts.push(`<div class="row between small"><span>${fa(q)} ویس در صف</span><button class="btn sm primary" id="t-start">${I.play} شروع پردازش</button></div>`);
    }
    if (q && w.model_state === "loading") parts.push(`<div class="row small">${modelChip(w.model_state, s.model.available)}</div>`);
    if (s.files.failed && !w.running) parts.push(`<div class="row small err-text">${I.alert} ${fa(s.files.failed)} ویس پردازش نشد.
      <button class="btn sm" id="t-retry">${I.retry} تلاش دوباره</button><a class="btn sm ghost" href="#/voices">جزئیات</a></div>`);
    box.innerHTML = parts.join("");
    $("#t-stop")?.addEventListener("click", stopQueue);
    $("#t-start")?.addEventListener("click", startQueue);
    $("#t-retry")?.addEventListener("click", async () => {
      try { await api("/api/files/retry-failed", { method: "POST" }); await startQueue(); } catch (e) { toastErr(e); }
    });
  }

  const LABEL = Object.fromEntries((state.meta?.fields || []).map((f) => [f.key, f.label]));
  const SHOW = 12;
  async function drawReview() {
    if (seq !== routeSeq) return;
    const { records } = await api("/api/records?filter=review");
    const box = $("#t-review");
    if (!box) return;
    const ids = records.map((r) => r.id);
    $("#t-rv-actions").innerHTML = records.length > 1 ? `<button class="btn sm primary" id="t-focus" title="یک رکورد در هر صفحه، با پخش خودکار شماره و میان‌برهای صفحه‌کلید">${I.eye} بازبینی سریع (${fa(records.length)})</button>` : "";
    $("#t-focus")?.addEventListener("click", () => openFocus(ids));
    if (!records.length) {
      box.innerHTML = `<div class="card-b row muted">${I.ok} موردی برای بررسی نیست.</div>`;
      return;
    }
    box.innerHTML = `<div class="t-list">${records.slice(0, SHOW).map((r) => {
      const v = r.values, vf = r.validation.fields || {};
      const problems = Object.entries(vf).filter(([, f]) => f.status !== "valid")
        .map(([k, f]) => `<li><b>${esc(LABEL[k] || k)}:</b> ${esc((f.reasons || [])[0] || FIELD_STATUS[f.status])}</li>`);
      if (!problems.length) problems.push(...(r.validation.reasons || []).slice(0, 2).map((x) => `<li>${esc(x)}</li>`));
      const play = r.audio_available && r.times?.phone ? `<button class="btn sm ghost" data-tplay="${r.id}" title="پخش بخش شماره از ویس">${I.play} شماره</button>` : "";
      return `<div class="t-rec" data-trec="${r.id}">
        <div class="t-rec-main"><div><b>${esc(v.engineer_name || "نام پیدا نشد")}</b>
            <span class="ltr t-phone">${esc((v.phone || "").split("\n").filter(Boolean).map(fmtPhone).join(" ، ")) || "—"}</span></div>
          <div class="small">${esc(v.address || "آدرس پیدا نشد")}${techSummary(v) ? ` <span class="muted">· ${esc(techSummary(v))}</span>` : ""}</div>
          <ul class="t-problems small">${problems.join("")}</ul></div>
        <div class="t-rec-act">${play}
          <button class="btn sm ok" data-tact="approve" data-r="${r.id}">${I.check} درست است</button>
          <button class="btn sm" data-topen="${r.id}">${I.edit} اصلاح</button>
          <button class="btn sm icon ghost" data-tact="reject" data-r="${r.id}" title="رد">${I.x}</button></div></div>`;
    }).join("")}</div>
    ${records.length > SHOW ? `<div class="card-b small muted">و ${fa(records.length - SHOW)} مورد دیگر؛ با «بازبینی سریع» همه را یکی‌یکی ببینید.</div>` : ""}`;
    $$("[data-tplay]", box).forEach((b) => b.onclick = () => playRecordSegment(records.find((r) => r.id === +b.dataset.tplay), "phone"));
    $$("[data-topen]", box).forEach((b) => b.onclick = () => openRecord(+b.dataset.topen));
    $$("[data-tact]", box).forEach((b) => b.onclick = async () => {
      const id = +b.dataset.r, act = b.dataset.tact;
      try {
        await api(`/api/records/${id}/action`, { method: "POST", body: { action: act, add_to_dictionary: act === "approve" } });
        toast(act === "approve" ? "تأیید شد." : "رد شد.", "ok", { label: "بازگشت", onClick: async () => { await undoLast(id); drawReview(); } });
        refreshStatus();
      } catch (e) { toastErr(e); }
    });
  }
  // کشوی جزئیات و بازبینی سریع پس از هر تغییر همین فهرست را تازه می‌کنند
  reviewState.reload = reviewState.updateRow = () => drawReview().catch(() => {});

  function drawExcel() {
    const s = state.status, box = $("#t-excel");
    if (!s || seq !== routeSeq || !box) return;
    const n = s.records.approved, last = todayState.lastCommit;
    let html = "";
    if (last) {
      html += last.applied
        ? `<div class="alert ok">${I.ok}<div class="alert-body">${fa(last.rows.length)} ردیف در فایل شرکت ثبت شد (ردیف ${fa(last.first_row)} تا ${fa(last.last_row)}). پیش از ثبت از فایل پشتیبان گرفته شد.</div>
            <button class="btn sm" id="t-open">${I.open} نمایش فایل</button><button class="btn sm ghost" id="t-undo">${I.history} بازگشت</button></div>`
        : `<div class="alert warn">${I.alert}<div class="alert-body">${esc(last.message)}</div><a class="btn sm" href="#/excel">مشاهده</a></div>`;
    }
    if (!s.setup.excel_ready) {
      html += `<div class="row">فایل اکسل شرکت هنوز وصل نشده است. <a class="btn primary" href="#/excel">${I.table} اتصال فایل اکسل</a></div>`;
    } else if (n) {
      html += `<div class="row"><button class="btn primary lg" id="t-commit">${I.table} ثبت ${fa(n)} ردیف در اکسل</button>
        <span class="muted small">در «${esc(s.setup.excel_name)}»</span><a class="btn sm ghost" href="#/excel">پیش‌نمایش</a></div>`;
    } else if (!last) {
      html += `<div class="muted">${s.records.review ? "پس از بررسی موارد بالا، ردیف‌ها اینجا آماده ثبت می‌شوند." : "ردیفی برای ثبت نیست."}</div>`;
    }
    if (s.pending_replace) html += `<div class="small muted" style="margin-top:8px">${fa(s.pending_replace)} خروجی قدیمی هنوز روی فایل اصلی اعمال نشده است. <a href="#/excel">مشاهده</a></div>`;
    box.innerHTML = html;
    $("#t-commit")?.addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.innerHTML = '<span class="spinner"></span> در حال ثبت...';
      try { todayState.lastCommit = await api("/api/excel/commit", { method: "POST", body: {} }); }
      catch (er) { toastErr(er); }
      await refreshStatus();
      drawExcel();
    });
    $("#t-open")?.addEventListener("click", () => api("/api/open-folder", { method: "POST", body: { path: last.target_path } }).catch(toastErr));
    $("#t-undo")?.addEventListener("click", async () => {
      if (!(await confirmBox("بازگشت ثبت", "ردیف‌های این ثبت از فایل اکسل برداشته می‌شوند (فایل به نسخه پیش از ثبت برمی‌گردد) و رکوردها دوباره آماده ثبت می‌شوند.", "بازگشت", "danger"))) return;
      try { toast((await api(`/api/exports/${last.export_id}/undo`, { method: "POST" })).message, "ok"); todayState.lastCommit = null; }
      catch (er) { toastErr(er); }
      await refreshStatus();
      drawExcel();
    });
  }

  drawProgress();
  drawExcel();
  await drawReview();
  setHook(seq, (s, prev) => {
    drawProgress();
    drawExcel();
    if (!prev || prev.records.review !== s.records.review || prev.files.done !== s.files.done) drawReview().catch(() => {});
  });
  const timer = setInterval(() => { if (seq !== routeSeq) return clearInterval(timer); if (state.status?.worker.running) drawProgress(); }, 1000);
}

// ================= داشبورد =================
async function renderDashboard(el) {
  const seq = routeSeq;
  const draw = async () => {
    const s = state.status || (await api("/api/status"));
    const files = (await api("/api/files")).files.slice(0, 6);
    const pct = s.progress;
    const C = 2 * Math.PI * 40;
    const running = s.worker.running;
    const q = s.files.queued + s.files.processing;
    const stat = (label, value, icon, cls, href) => `<a class="stat" ${href ? `href="${href}"` : ""} style="color:inherit">
      <div class="stat-ico ${cls}">${icon}</div><div class="stat-label">${label}</div><div class="stat-value num">${fa(value)}</div></a>`;
    const welcome = onboardingCard(s);
    el.innerHTML = welcome + `
      <div class="grid" style="grid-template-columns: minmax(0,1.3fr) minmax(0,1fr)">
        <div class="card"><div class="card-b hero-progress">
          <svg class="ring" viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="40"/>
            <circle class="fg" cx="50" cy="50" r="40" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - (running ? pct : q ? 0 : 100) / 100)}"/>
            <text x="50" y="52">${fa(running ? pct : q ? 0 : 100)}٪</text></svg>
          <div class="stack" style="gap:6px; flex:1; min-width:0">
            <div style="font-weight:800; font-size:17px">${running ? "در حال پردازش ویس‌ها" : q ? `${fa(q)} ویس در صف پردازش` : "همه ویس‌ها پردازش شده‌اند"}</div>
            <div class="muted small" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${running ? "فایل فعلی: " + esc(s.worker.current_name || "...") : q ? "برای شروع، دکمه شروع پردازش را بزنید." : "برای افزودن ویس جدید به بخش ویس‌ها بروید."}</div>
            <div class="row" style="margin-top:6px">
              ${running ? `<button class="btn danger" id="d-stop">${I.stop} توقف پردازش</button>`
                : q ? `<button class="btn primary" id="d-start">${I.play} شروع پردازش</button>` : `<a class="btn primary" href="#/voices">${I.upload} افزودن ویس</a>`}
              ${s.records.review ? `<a class="btn" href="#/review">${I.eye} بازبینی (${fa(s.records.review)})</a>` : ""}
              ${!running && state.meta?.samples?.voices ? `<button class="btn" id="d-samples">${I.play} امتحان با ${fa(state.meta.samples.voices)} ویس نمونه</button>` : ""}
            </div>
          </div></div></div>
        <div class="card"><div class="card-b stack" style="gap:8px">
          <div class="row between"><b>وضعیت سامانه</b>${s.model.available ? chip("ok", "آماده") : chip("err", "مدل نصب نیست")}</div>
          <dl class="kv"><dt>مدل گفتار</dt><dd class="ltr">${esc(s.model.name)}</dd>
            <dt>پردازش</dt><dd>محلی روی CPU، بدون اینترنت</dd>
            <dt>تاریخ امروز</dt><dd>${fa(s.today)}</dd>
            <dt>نسخه</dt><dd>${fa(s.version)}</dd></dl>
        </div></div>
      </div>
      <div class="stats" style="margin-top:18px">
        ${stat("کل ویس‌ها", s.files.total, I.mic, "ico-primary", "#/voices")}
        ${stat("در صف", s.files.queued + s.files.processing, I.clock, "ico-info", "#/voices")}
        ${stat("پردازش موفق", s.files.done, I.ok, "ico-ok", "#/voices")}
        ${stat("ناموفق", s.files.failed, I.alert, "ico-err", "#/voices")}
        ${stat("نیازمند بازبینی", s.records.review, I.eye, "ico-warn", "#/review")}
        ${stat("آماده ثبت", s.records.approved, I.check, "ico-ok", "#/excel")}
        ${stat("ثبت‌شده در اکسل", s.records.exported, I.table, "ico-info", "#/review?exported")}
      </div>
      ${welcome ? "" : `<div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.info} مراحل کار</h2></div><div class="card-b"><div class="steps">
        <div class="step ${s.files.total ? "done" : ""}"><div class="step-n">${fa(1)}</div><h4>افزودن ویس‌ها</h4><p>فایل‌ها یا پوشه ویس‌های بازاریاب را اضافه کنید و تاریخ بازدید را مشخص کنید. <a href="/static/recording-guide.html" target="_blank">راهنمای ضبط</a> را به بازاریاب‌ها بدهید.</p><a class="btn sm" href="#/voices">ویس‌ها</a></div>
        <div class="step ${s.files.done ? "done" : ""}"><div class="step-n">${fa(2)}</div><h4>پردازش خودکار</h4><p>ویس‌ها یکی‌یکی به متن تبدیل و اطلاعات از آن استخراج می‌شود.</p><a class="btn sm" href="#/voices">صف پردازش</a></div>
        <div class="step ${s.records.approved || s.records.exported ? "done" : ""}"><div class="step-n">${fa(3)}</div><h4>بازبینی</h4><p>موارد مشکوک را با شنیدن ویس اصلاح و تأیید کنید. هیچ حدسی ثبت نمی‌شود.</p><a class="btn sm" href="#/review">بازبینی</a></div>
        <div class="step ${s.records.exported ? "done" : ""}"><div class="step-n">${fa(4)}</div><h4>ثبت در اکسل</h4><p>رکوردهای تأییدشده روی یک کپی از فایل شرکت ثبت می‌شوند؛ با پشتیبان‌گیری.</p><a class="btn sm" href="#/excel">ثبت در اکسل</a></div>
      </div></div></div>`}
      <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.music} آخرین ویس‌ها</h2><a class="btn sm ghost" href="#/voices">همه</a></div>
        ${files.length ? `<div class="table-wrap"><table class="table"><thead><tr><th>نام فایل</th><th>تاریخ بازدید</th><th>وضعیت</th><th>رکورد</th></tr></thead><tbody>
          ${files.map((f) => `<tr><td>${esc(f.original_name)}${f.error && f.status === "failed" ? `<div class="err-text">${esc(f.error)}</div>` : ""}</td><td>${fa(f.visit_date)}</td><td>${chip(f.status, FILE_STATUS[f.status])}</td><td>${fa(f.records)}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">${I.mic}<div>هنوز ویسی اضافه نشده است.</div><a class="btn primary" href="#/voices">${I.upload} افزودن ویس</a></div>`}
      </div>`;
    $("#d-start")?.addEventListener("click", startQueue);
    $("#d-stop")?.addEventListener("click", stopQueue);
    $("#d-samples")?.addEventListener("click", importSamples);
    bindOnboarding();
  };
  await draw();
  setHook(seq, () => draw().catch(() => {}));
}

/** راهنمای اجرای اول: چهار گام راه‌اندازی با وضعیت انجام‌شده/نشده؛ تا انجام همه یا بستن نمایش داده می‌شود. */
function onboardingCard(s) {
  if (localStorage.getItem("v2x.onboarding.closed") === "1") return "";
  const st = s.setup || {};
  const guideSeen = localStorage.getItem("v2x.guide.opened") === "1";
  const steps = [
    { done: st.excel_ready, title: "فایل اکسل شرکت", text: st.excel_ready ? `متصل: ${esc(st.excel_name)}` : "فایل اکسل را انتخاب و نگاشت ستون‌ها را ذخیره کنید.", btn: `<a class="btn sm" href="#/excel">ثبت در اکسل</a>` },
    { done: st.dictionary > 0, title: "واژه‌نامه", text: st.dictionary > 0 ? `${fa(st.dictionary)} نام و خیابان؛ برای تشخیص نام و آدرس و املای درست. فایل‌های اکسل قدیمی بیشتر = تشخیص بهتر.` : "با ذخیره نگاشت اکسل خودکار پر می‌شود؛ فایل‌های اکسل قدیمی را هم می‌توانید یاد بدهید.", btn: `<a class="btn sm" href="#/dictionary?kb">آموزش از اکسل</a>` },
    { done: guideSeen, title: "راهنمای ضبط ویس", text: "یک صفحه قابل چاپ برای بازاریاب‌ها تا ویس‌ها دقیق‌تر خوانده شوند.", btn: `<a class="btn sm" href="/static/recording-guide.html" target="_blank" id="ob-guide">مشاهده و چاپ</a>` },
    { done: s.files.total > 0, title: "اولین ویس", text: "ویس‌ها را اضافه کنید؛ پردازش خودکار شروع می‌شود.", btn: `<a class="btn sm" href="#/voices">افزودن ویس</a>${state.meta?.samples?.voices && !s.files.total ? ` <button class="btn sm ghost" id="ob-samples">ویس نمونه</button>` : ""}` },
  ];
  if (steps.every((x) => x.done)) return "";
  const n = steps.filter((x) => x.done).length;
  return `<div class="card" style="margin-bottom:18px"><div class="card-h"><h2>${I.info} شروع به کار — ${fa(n)} از ${fa(steps.length)} گام</h2>
      <button class="btn sm ghost" id="ob-close">${I.x} بستن راهنما</button></div>
    <div class="card-b"><div class="onboard">${steps.map((x, i) => `<div class="ob-step ${x.done ? "done" : ""}">
      <div class="ob-h"><span class="ob-n">${x.done ? I.check : fa(i + 1)}</span>${x.title}</div><p>${x.text}</p><div class="row">${x.btn}</div></div>`).join("")}</div></div></div>`;
}
function bindOnboarding() {
  $("#ob-close")?.addEventListener("click", () => { localStorage.setItem("v2x.onboarding.closed", "1"); route(); });
  $("#ob-guide")?.addEventListener("click", () => { localStorage.setItem("v2x.guide.opened", "1"); setTimeout(route, 300); });
  $("#ob-samples")?.addEventListener("click", importSamples);
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

/** ارسال ویس‌ها در بسته‌های ۸تایی؛ onProgress(درصد). خروجی: نتیجه هر فایل. */
async function uploadAudio(files, visitDate, useFilenameDate, onProgress = () => {}) {
  const results = [];
  const totalBytes = files.reduce((a, f) => a + f.size, 0) || 1;
  let sent = 0;
  for (let i = 0; i < files.length; i += 8) {
    const chunk = files.slice(i, i + 8);
    const fd = new FormData();
    chunk.forEach((f) => fd.append("files", f, f.name));
    fd.append("visit_date", visitDate);
    fd.append("use_filename_date", useFilenameDate ? "true" : "false");
    const r = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
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
const staged = [];
/** وضعیت مدل گفتار: آماده (بدون انتظار)، در حال آماده‌سازی، یا در شروع پردازش آماده می‌شود. */
function modelChip(stateName, available) {
  if (!available) return chip("err", "مدل گفتار نصب نیست");
  if (stateName === "ready") return chip("ok", "مدل گفتار آماده است");
  if (stateName === "loading") return `<span class="chip info model-chip"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> در حال آماده‌سازی مدل گفتار…</span>`;
  return chip("missing", "مدل گفتار هنگام شروع پردازش آماده می‌شود");
}

async function renderVoices(el) {
  const seq = routeSeq;
  // مدل از همین حالا در پس‌زمینه آماده می‌شود تا اولین ویس منتظر بارگذاری نماند
  api("/api/model/warmup", { method: "POST" }).then(() => setTimeout(refreshStatus, 300)).catch(() => {});
  const s = state.status || (await api("/api/status"));
  const exts = (state.meta?.audio_extensions || []).join(",");
  el.innerHTML = `
    <div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr)">
      <div class="card"><div class="card-h"><h2>${I.upload} افزودن ویس</h2></div><div class="card-b stack">
        <div class="dropzone" id="dz">
          <div class="dz-ico">${I.upload}</div>
          <h3>فایل‌ها یا پوشه ویس‌ها را اینجا رها کنید</h3>
          <div class="muted small">WAV، MP3، M4A، OGG، OPUS، AMR و قالب‌های رایج دیگر</div>
          <a class="small" href="/static/recording-guide.html" target="_blank">${I.info} راهنمای ضبط ویس برای بازاریاب‌ها (قابل چاپ)</a>
          <div class="row" style="justify-content:center; margin-top:4px">
            <button class="btn primary" id="pick-files">${I.music} انتخاب فایل‌ها</button>
            <button class="btn" id="pick-dir">${I.folder} انتخاب پوشه</button>
            <button class="btn ghost" id="pick-path">${I.search} از مسیر رایانه</button>
          </div>
          <input type="file" id="in-files" multiple accept="${esc(exts)},audio/*" hidden>
          <input type="file" id="in-dir" webkitdirectory multiple hidden>
        </div>
        <div class="grid grid-2" style="gap:12px">
          <div class="field"><label>تاریخ بازدید این ویس‌ها (شمسی)</label>
            <input class="input ltr" id="visit-date" value="${esc(s.today)}" placeholder="1405/07/28" style="text-align:right">
            <span class="hint">در ستون «تاریخ بازدید» اکسل ثبت می‌شود.</span></div>
          <div class="field"><label>&nbsp;</label>
            <label class="check"><input type="checkbox" id="use-fname-date" checked> اگر نام فایل تاریخ داشت، از آن استفاده شود</label>
            <span class="hint">مثل نام ویس‌های واتساپ: PTT-20261020-WA0001</span></div>
        </div>
        <div id="staged-box"></div>
      </div></div>
      <div class="card"><div class="card-h"><h2>${I.wave} صف پردازش</h2>
        <div class="row" id="q-actions"></div></div>
        <div class="card-b stack" id="q-summary"></div>
      </div>
    </div>
    <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.music} فایل‌ها</h2>
      <div class="row"><input class="input" id="f-search" placeholder="جست‌وجوی نام فایل..." style="width:220px">
      <select class="select" id="f-filter"><option value="">همه وضعیت‌ها</option>${Object.entries(FILE_STATUS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div></div>
      <div class="table-wrap" id="files-table"></div></div>`;

  const dz = $("#dz");
  const addFiles = (list) => {
    for (const f of audioOnly(list)) if (!staged.some((x) => x.name === f.name && x.size === f.size)) staged.push(f);
    drawStaged();
  };
  $("#pick-files").onclick = () => $("#in-files").click();
  $("#pick-dir").onclick = () => $("#in-dir").click();
  $("#in-files").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
  $("#in-dir").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", async (e) => {
    e.preventDefault(); dz.classList.remove("over");
    addFiles(await droppedFiles(e));
  });
  $("#pick-path").onclick = async () => {
    const p = await pickPath("audio");
    if (!p) return;
    try {
      const r = await api("/api/import-folder", { method: "POST", body: { path: p, visit_date: $("#visit-date").value.trim(), use_filename_date: $("#use-fname-date").checked } });
      reportUpload(r.results);
      refreshStatus(); drawFiles();
    } catch (e) { toastErr(e); }
  };
  $("#f-search").oninput = debounce(drawFiles, 200);
  $("#f-filter").onchange = drawFiles;

  function drawStaged() {
    const box = $("#staged-box");
    if (!staged.length) { box.innerHTML = ""; return; }
    const total = staged.reduce((a, f) => a + f.size, 0);
    box.innerHTML = `<div class="stack" style="gap:8px">
      <div class="row between"><b>${fa(staged.length)} فایل انتخاب‌شده <span class="muted small">(${fmtSize(total)})</span></b>
        <button class="btn sm ghost" id="st-clear">پاک کردن فهرست</button></div>
      <div class="staged">${staged.map((f, i) => `<div class="staged-item"><div class="file-ico">${I.music}</div>
        <span class="name">${esc(f.name)}</span><span class="muted small">${fmtSize(f.size)}</span>
        <button class="btn sm icon ghost" data-rm="${i}" title="حذف از فهرست">${I.x}</button></div>`).join("")}</div>
      <div id="up-progress" hidden><div class="progress"><div class="progress-bar" id="up-bar"></div></div><div class="muted small" id="up-text"></div></div>
      <div class="row"><button class="btn primary lg" id="st-upload">${I.plus} افزودن به صف (${fa(staged.length)} فایل)</button>
        <label class="check small"><input type="checkbox" id="auto-start" checked> شروع خودکار پردازش</label></div></div>`;
    $$("[data-rm]", box).forEach((b) => b.onclick = () => { staged.splice(+b.dataset.rm, 1); drawStaged(); });
    $("#st-clear").onclick = () => { staged.length = 0; drawStaged(); };
    $("#st-upload").onclick = uploadStaged;
  }

  async function uploadStaged() {
    const vd = $("#visit-date").value.trim();
    const useFn = $("#use-fname-date").checked;
    const autoStart = $("#auto-start").checked;
    $("#st-upload").disabled = true;
    $("#up-progress").hidden = false;
    try {
      const results = await uploadAudio(staged.slice(), vd, useFn, (p) => {
        $("#up-bar").style.width = p + "%";
        $("#up-text").textContent = `در حال افزودن... ${fa(p)}٪`;
      });
      staged.length = 0;
      drawStaged();
      reportUpload(results);
      await refreshStatus();
      drawFiles();
      if (autoStart && results.some((r) => r.result === "added")) startQueue();
    } catch (e) {
      toastErr(e);
      $("#st-upload").disabled = false;
    }
  }

  function drawSummary() {
    const s = state.status;
    if (!s || seq !== routeSeq || !$("#q-actions")) return;
    const w = s.worker;
    const q = s.files.queued + s.files.processing;
    $("#q-actions").innerHTML = w.running
      ? `<button class="btn danger" id="q-stop">${I.stop} توقف</button>`
      : `<button class="btn primary" id="q-start" ${q ? "" : "disabled"}>${I.play} شروع پردازش</button>
         ${s.files.failed ? `<button class="btn" id="q-retry">${I.retry} تلاش دوباره ناموفق‌ها</button>` : ""}`;
    $("#q-stop")?.addEventListener("click", stopQueue);
    $("#q-start")?.addEventListener("click", startQueue);
    $("#q-retry")?.addEventListener("click", async () => {
      try { const r = await api("/api/files/retry-failed", { method: "POST" }); toast(`${fa(r.requeued)} فایل دوباره در صف قرار گرفت.`); refreshStatus(); drawFiles(); }
      catch (e) { toastErr(e); }
    });
    const tot = s.files.total;
    $("#q-summary").innerHTML = `
      <div class="stats" style="grid-template-columns:repeat(4,1fr)">
        <div class="stat"><div class="stat-label">کل</div><div class="stat-value num">${fa(tot)}</div></div>
        <div class="stat"><div class="stat-label">موفق</div><div class="stat-value num" style="color:var(--ok)">${fa(s.files.done)}</div></div>
        <div class="stat"><div class="stat-label">ناموفق</div><div class="stat-value num" style="color:var(--err)">${fa(s.files.failed)}</div></div>
        <div class="stat"><div class="stat-label">باقی‌مانده</div><div class="stat-value num" style="color:var(--info)">${fa(q)}</div></div>
      </div>
      <div><div class="row between small" style="margin-bottom:5px"><span>${w.running ? "در حال پردازش: <b>" + esc(w.current_name || "...") + "</b>" + (w.current_elapsed ? ` <span class="muted">(${fmtSec(w.current_elapsed)})</span>` : "") : q ? "آماده شروع" : "صف خالی است"}</span>
        <b>${fa(w.running ? s.progress : q ? 0 : 100)}٪</b></div>
        <div class="progress lg"><div class="progress-bar" style="width:${w.running ? s.progress : q ? 0 : 100}%"></div></div></div>
      <div class="row small">${modelChip(w.model_state, s.model.available)}</div>
      ${s.records.review ? `<div class="alert info">${I.info}<div class="alert-body">${fa(s.records.review)} رکورد نیازمند بازبینی است.</div><a class="btn sm" href="#/review">بازبینی</a></div>` : ""}`;
  }

  async function drawFiles() {
    const box = $("#files-table");
    if (!box) return;
    const { files } = await api("/api/files");
    const term = ($("#f-search")?.value || "").trim();
    const filt = $("#f-filter")?.value || "";
    const list = files.filter((f) => (!term || f.original_name.includes(term)) && (!filt || f.status === filt));
    if (!files.length) { box.innerHTML = `<div class="empty">${I.music}<div>هنوز فایلی اضافه نشده است.</div></div>`; return; }
    box.innerHTML = `<table class="table"><thead><tr><th>#</th><th>نام فایل</th><th>حجم</th><th>مدت</th><th>تاریخ بازدید</th><th>وضعیت</th><th>رکوردها</th><th>زمان پردازش</th><th></th></tr></thead><tbody>
      ${list.map((f) => `<tr>
        <td class="muted num">${fa(f.id)}</td>
        <td style="max-width:320px"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(f.original_name)}">${esc(f.original_name)}</div>
          ${f.error ? `<div class="${f.status === "failed" ? "err-text" : "muted small"}">${esc(f.error)}</div>` : ""}</td>
        <td class="small muted">${fmtSize(f.size)}</td>
        <td class="small">${fmtSec(f.duration)}</td>
        <td class="small">${fa(f.visit_date)}${f.date_source === "filename" ? ' <span class="muted" title="از نام فایل">•</span>' : ""}</td>
        <td>${f.status === "processing" ? '<span class="chip processing"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> در حال پردازش</span>' : chip(f.status, FILE_STATUS[f.status])}</td>
        <td>${f.records ? `<a href="#/review" data-goto-audio="${f.id}">${fa(f.records)} رکورد</a>${f.pending ? ` <span class="chip warn plain">${fa(f.pending)} بازبینی</span>` : ""}` : '<span class="muted">—</span>'}</td>
        <td class="small muted">${f.processing_seconds ? fmtSec(f.processing_seconds) : ""}</td>
        <td class="actions">
          ${!f.audio_deleted ? `<button class="btn sm icon ghost" data-play="${f.id}" title="پخش">${I.play}</button>` : ""}
          ${["failed", "done"].includes(f.status) ? `<button class="btn sm icon ghost" data-retry="${f.id}" title="پردازش دوباره">${I.retry}</button>` : ""}
          ${f.status !== "processing" && !f.exported ? `<button class="btn sm icon ghost" data-del="${f.id}" title="حذف">${I.trash}</button>` : ""}
        </td></tr>`).join("") || `<tr><td colspan="9"><div class="empty">موردی با این فیلتر نیست.</div></td></tr>`}
      </tbody></table>`;
    $$("[data-play]", box).forEach((b) => b.onclick = () => playAudio(+b.dataset.play, b));
    $$("[data-retry]", box).forEach((b) => b.onclick = async () => {
      try { await api(`/api/files/${b.dataset.retry}/retry`, { method: "POST" }); toast("فایل دوباره در صف قرار گرفت."); refreshStatus(); drawFiles(); }
      catch (e) { toastErr(e); }
    });
    $$("[data-del]", box).forEach((b) => b.onclick = async () => {
      if (!(await confirmBox("حذف فایل", "این فایل و رکوردهای استخراج‌شده آن حذف می‌شوند. ادامه می‌دهید؟", "حذف", "danger"))) return;
      try { await api(`/api/files/${b.dataset.del}`, { method: "DELETE" }); refreshStatus(); drawFiles(); }
      catch (e) { toastErr(e); }
    });
    $$("[data-goto-audio]", box).forEach((a) => a.onclick = () => { reviewState.audioId = +a.dataset.gotoAudio; reviewState.filter = "all"; });
  }

  drawStaged();
  drawSummary();
  await drawFiles();
  setHook(seq, () => { drawSummary(); drawFiles().catch(() => {}); });
  const timer = setInterval(() => { if (seq !== routeSeq) return clearInterval(timer); if (state.status?.worker.running) drawSummary(); }, 1000);
}

function reportUpload(results) {
  const added = results.filter((r) => r.result === "added").length;
  const dup = results.filter((r) => r.result === "duplicate");
  const errs = results.filter((r) => r.result === "error");
  if (added) toast(`${fa(added)} فایل به صف اضافه شد.`, "ok");
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

// ================= بازبینی =================
let tableAudio = null;
const reviewState = { filter: "review", records: [], selected: new Set(), audioId: null };
const TABLE_FIELDS = [["engineer_name", "نام مهندس / شخص تماس"], ["phone", "شماره تماس"], ["address", "آدرس"]];

/** پخش همان تکه از ویس که فیلد key از آن آمده (بدون باز کردن جزئیات). */
function playRecordSegment(rec, key) {
  if (!tableAudio || tableAudio.dataset.aid !== String(rec.audio_id)) {
    if (tableAudio) tableAudio.pause();
    tableAudio = new Audio(`/api/files/${rec.audio_id}/audio`);
    tableAudio.dataset.aid = String(rec.audio_id);
  }
  playSegment(tableAudio, rec.times[key]);
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

async function renderReview(el) {
  const seq = routeSeq;
  if (location.hash.includes("?exported")) reviewState.filter = "exported";
  if (location.hash.includes("open=") || location.hash.includes("filter=all")) reviewState.filter = "all";
  const s = state.status || (await api("/api/status"));
  let dictTip = "";
  try {
    const dc = await api("/api/dictionary?type=engineer&q=__none__");
    const total = Object.values(dc.counts || {}).reduce((a, b) => a + b, 0);
    if (!total) dictTip = `<div class="alert info" style="margin-bottom:16px">${I.book}<div class="alert-body">
      <b>واژه‌نامه خالی است</b>برای اینکه برنامه املای درست نام مهندس‌ها و خیابان‌ها را پیشنهاد دهد (مثلاً «کازمی» ← «کاظمی»)،
      در بخش «ثبت در اکسل» فایل اکسل شرکت را انتخاب و نگاشت را ذخیره کنید؛ واژه‌نامه خودکار از همان فایل پر می‌شود.</div>
      <a class="btn sm" href="#/excel">ثبت در اکسل</a></div>`;
  } catch { }
  el.innerHTML = dictTip + `
    <div class="card"><div class="card-h">
      <div class="tabs" id="rv-tabs"></div>
      <div class="row"><input class="input" id="rv-search" placeholder="جست‌وجو در نام، شماره، آدرس..." style="width:240px"></div>
    </div>
    <div class="card-b row between" id="rv-bulk" style="padding:10px 20px; border-bottom:1px solid var(--border)"></div>
    <div class="table-wrap" id="rv-table"></div></div>`;
  $("#rv-search").oninput = debounce(drawTable, 200);
  await load();
  const openId = (location.hash.match(/[?&]open=(\d+)/) || [])[1];
  if (openId) openRecord(+openId);
  setHook(seq, () => { drawTabs(); if (!$("#drawer").classList.contains("open")) load(); });

  function drawTabs() {
    const r = state.status?.records || s.records;
    const tabs = [["review", "نیازمند بازبینی", r.review], ["approved", "آماده ثبت", r.approved], ["exported", "ثبت‌شده", r.exported], ["rejected", "ردشده", r.rejected], ["all", "همه", r.review + r.approved + r.exported + r.rejected]];
    $("#rv-tabs").innerHTML = tabs.map(([k, l, n]) => `<button class="${reviewState.filter === k ? "active" : ""}" data-tab="${k}">${l}<span class="count">${fa(n)}</span></button>`).join("");
    $$("[data-tab]").forEach((b) => b.onclick = () => { reviewState.filter = b.dataset.tab; reviewState.audioId = null; reviewState.selected.clear(); load(); });
  }

  async function load() {
    drawTabs();
    const q = reviewState.audioId ? `filter=all&audio_id=${reviewState.audioId}` : `filter=${reviewState.filter}`;
    const { records } = await api(`/api/records?${q}`);
    reviewState.records = records;
    drawTable();
  }

  function drawTable() {
    const term = ($("#rv-search")?.value || "").trim();
    const list = reviewState.records.filter((r) => !term || Object.values(r.values).join(" ").includes(term) || (r.original_name || "").includes(term));
    reviewState.visible = list.map((r) => r.id);
    const bulk = $("#rv-bulk");
    const editable = reviewState.filter !== "exported";
    const pendingIds = list.filter((r) => !r.exported_at && r.review_state === "pending").map((r) => r.id);
    bulk.innerHTML = `<div class="row small">
        ${reviewState.audioId ? `<span class="chip info plain">فقط فایل #${fa(reviewState.audioId)}</span><button class="btn sm ghost" id="rv-clear-audio">نمایش همه</button>` : ""}
        <span class="muted">${fa(list.length)} رکورد</span>
        ${reviewState.selected.size ? `<b>${fa(reviewState.selected.size)} انتخاب‌شده</b>` : ""}</div>
      <div class="row">${editable && reviewState.selected.size ? `
        <button class="btn sm ok" id="bulk-approve">${I.check} تأیید انتخاب‌شده‌ها</button>
        <button class="btn sm danger" id="bulk-reject">${I.x} رد انتخاب‌شده‌ها</button>` : ""}
        ${editable && pendingIds.length ? `<button class="btn sm primary" id="rv-focus" title="یک رکورد در هر صفحه، با پخش خودکار شماره و میان‌برهای صفحه‌کلید">${I.eye} بازبینی سریع (${fa(pendingIds.length)})</button>` : ""}
        <span class="muted small">روی هر ردیف بزنید تا جزئیات، متن ویس و پخش صدا باز شود.</span></div>`;
    $("#rv-focus")?.addEventListener("click", () => openFocus(pendingIds));
    $("#rv-clear-audio")?.addEventListener("click", () => { reviewState.audioId = null; load(); });
    $("#bulk-approve")?.addEventListener("click", () => bulkAction("approve"));
    $("#bulk-reject")?.addEventListener("click", () => bulkAction("reject"));
    const box = $("#rv-table");
    if (!list.length) {
      box.innerHTML = `<div class="empty">${I.ok}<div>${reviewState.filter === "review" ? "هیچ رکوردی منتظر بازبینی نیست." : "رکوردی وجود ندارد."}</div></div>`;
      return;
    }
    box.innerHTML = `<table class="table"><thead><tr>
      <th style="width:34px"><input type="checkbox" id="rv-all" ${editable ? "" : "disabled"}></th>
      <th>وضعیت</th><th>فایل</th>${TABLE_FIELDS.map(([, l]) => `<th>${l}</th>`).join("")}<th>مشخصات و توضیحات</th><th></th></tr></thead><tbody>
      ${list.map((r) => {
        const v = r.values, vf = r.validation.fields || {};
        const locked = !!r.exported_at;
        const warn = Object.values(vf).filter((f) => f.status !== "valid").length;
        return `<tr class="clickable" data-rid="${r.id}">
          <td><input type="checkbox" data-sel="${r.id}" ${reviewState.selected.has(r.id) ? "checked" : ""} ${locked ? "disabled" : ""}></td>
          <td>${recordChip(r)}${warn && !r.exported_at && r.review_state === "pending" ? `<div class="muted small" style="margin-top:3px">${fa(warn)} هشدار</div>` : ""}</td>
          <td class="small" style="max-width:170px"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.original_name)}">${esc(r.original_name)}</div>
            ${r.building_count > 1 ? `<span class="chip info plain">ساختمان ${fa(r.building_index + 1)} از ${fa(r.building_count)}</span>` : ""}</td>
          ${TABLE_FIELDS.map(([k]) => {
            const st = vf[k]?.status || (v[k] ? "valid" : "missing");
            const tag = k === "phone" ? "textarea" : "input";
            const val = v[k] || "";
            const seg = r.audio_available && r.times?.[k] ? `<button class="btn sm icon ghost cell-play" data-tseg="${k}" data-r="${r.id}" title="پخش همین بخش از ویس">${I.play}</button>` : "";
            return `<td style="min-width:${k === "address" ? 230 : 160}px"><div class="cell-wrap">${tag === "textarea"
              ? `<textarea class="cell-input st-${st} ltr" rows="${Math.max(1, val.split("\n").length)}" data-edit="${k}" data-r="${r.id}" ${locked ? "disabled" : ""} title="${esc((vf[k]?.reasons || []).join(" | "))}" placeholder="—">${esc(val)}</textarea>`
              : `<input class="cell-input st-${st}" value="${esc(val)}" data-edit="${k}" data-r="${r.id}" ${locked ? "disabled" : ""} title="${esc((vf[k]?.reasons || []).join(" | "))}" placeholder="—">`}${seg}</div>${k === "phone" ? phoneView(val) : ""}</td>`;
          }).join("")}
          <td class="small" style="max-width:280px; color:var(--text-2)">${esc([techSummary(v), v.notes].filter(Boolean).join(" ، ")) || '<span class="muted">—</span>'}</td>
          <td class="actions">${locked ? "" : r.review_state === "approved" ? `<button class="btn sm ghost" data-act="reopen" data-r="${r.id}">بازگشایی</button>`
            : `<button class="btn sm icon ok" data-act="approve" data-r="${r.id}" title="تأیید">${I.check}</button>
               <button class="btn sm icon danger" data-act="reject" data-r="${r.id}" title="رد">${I.x}</button>`}
            <button class="btn sm icon ghost" data-open="${r.id}" title="جزئیات">${I.eye}</button></td></tr>`;
      }).join("")}</tbody></table>`;
    $$("[data-tseg]", box).forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      const rec = reviewState.records.find((x) => x.id === +b.dataset.r);
      if (rec) playRecordSegment(rec, b.dataset.tseg);
    }));
    $("#rv-all")?.addEventListener("change", (e) => {
      list.filter((r) => !r.exported_at).forEach((r) => e.target.checked ? reviewState.selected.add(r.id) : reviewState.selected.delete(r.id));
      drawTable();
    });
    $$("[data-sel]", box).forEach((c) => c.addEventListener("change", (e) => {
      e.stopPropagation();
      c.checked ? reviewState.selected.add(+c.dataset.sel) : reviewState.selected.delete(+c.dataset.sel);
      drawTable();
    }));
    $$("[data-edit]", box).forEach((inp) => {
      inp.addEventListener("click", (e) => e.stopPropagation());
      inp.addEventListener("change", async () => {
        try {
          const rec = await api(`/api/records/${inp.dataset.r}`, { method: "PATCH", body: { values: { [inp.dataset.edit]: inp.value } } });
          updateRow(rec);
          toast("ذخیره شد.", "ok");
        } catch (e) { toastErr(e); }
      });
    });
    $$("[data-act]", box).forEach((b) => b.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        await api(`/api/records/${b.dataset.r}/action`, { method: "POST", body: { action: b.dataset.act, add_to_dictionary: b.dataset.act === "approve" } });
        toast(b.dataset.act === "approve" ? "تأیید شد و برای ثبت در اکسل آماده است." : b.dataset.act === "reject" ? "رد شد." : "به بازبینی برگشت.", "ok");
        refreshStatus(); load();
      } catch (er) { toastErr(er); }
    }));
    $$("tr[data-rid]", box).forEach((tr) => tr.addEventListener("click", (e) => {
      if (e.target.closest("input,textarea,button,a")) return;
      openRecord(+tr.dataset.rid);
    }));
    $$("[data-open]", box).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); openRecord(+b.dataset.open); }));
  }

  function updateRow(rec) {
    const i = reviewState.records.findIndex((r) => r.id === rec.id);
    if (i >= 0) reviewState.records[i] = rec;
    drawTable();
  }
  reviewState.reload = load;
  reviewState.updateRow = updateRow;

  async function bulkAction(action) {
    const ids = [...reviewState.selected];
    if (action === "approve") {
      const notValid = reviewState.records.filter((r) => ids.includes(r.id) && r.status !== "ready").length;
      if (notValid && !(await confirmBox("تأیید گروهی", `${fa(notValid)} مورد از رکوردهای انتخاب‌شده هنوز هشدار دارند. با تأیید، مسئولیت درستی آن‌ها با شماست. ادامه می‌دهید؟`, "تأیید همه"))) return;
    }
    let ok = 0;
    for (const id of ids) {
      try { await api(`/api/records/${id}/action`, { method: "POST", body: { action, add_to_dictionary: action === "approve" } }); ok++; }
      catch (e) { toastErr(e); }
    }
    reviewState.selected.clear();
    toast(`${fa(ok)} رکورد ${action === "approve" ? "تأیید" : "رد"} شد.`, "ok");
    refreshStatus(); load();
  }
}

// ---------- کشوی جزئیات رکورد ----------
const DRAWER_GROUPS = [
  ["اطلاعات اصلی", ["engineer_name", "phone", "project_name", "address", "visit_date"]],
  ["مشخصات فنی و مرحله ساخت", ["structure_type", "floors", "executed", "units", "stage", "building_type", "permit_status"]],
  ["توضیحات", ["customer_need", "notes"]],
  ["پیگیری", ["followup_action", "followup_time_text", "followup_date"]],
  ["اجزای آدرس", ["city", "neighborhood", "street", "alley", "plate"]],
];
const MULTILINE = new Set(["address", "notes", "phone", "followup_action", "permit_status", "customer_need", "stage"]);
const DICT_FIELDS = new Set(["engineer_name", "project_name", "street"]);

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer-backdrop").hidden = true;
  if (audioEl) audioEl.pause();
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

// ---------- ابزارهای مشترک بازبینی: پخش تکه، نمایش شماره، بازگشت ----------
const SEG_KEYS = [["engineer_name", "نام"], ["phone", "شماره"], ["address", "آدرس"], ["tech", "فنی"]];
const TECH_KEYS = ["floors", "structure_type", "executed", "stage", "units"];
const UNDOABLE = new Set(["edit", "accept", "approve", "reject", "reopen", "duplicate"]);

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
function lowConfView(r, k) {
  const w = k === "tech" ? TECH_KEYS.flatMap((x) => r.low_confidence?.[x] || []) : (r.low_confidence?.[k] || []);
  return w.length ? `<div class="lowconf">${I.alert}<span>با اطمینان کم شنیده شد: ${w.map((x) => `«${esc(x)}»`).join("، ")} — با شنیدن این بخش بررسی کنید.</span></div>` : "";
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
    const seg = r.audio_available && r.times?.[k] ? `<button class="btn sm icon ghost" data-seg="${k}" title="پخش همین بخش از ویس">${I.play}</button>` : "";
    return `<div class="frow"><label>${esc(labels[k] || k)}</label><div class="fval">
      <div class="row">${input}${seg}${fc ? chip(fc.status, FIELD_STATUS[fc.status]) : ""}
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
  d.innerHTML = `
    <div class="drawer-h">
      <div class="title"><b title="${esc(r.original_name)}">${esc(r.original_name)}</b>
        <div class="row small" style="gap:6px">${recordChip(r)}${r.building_count > 1 ? chip("info plain", `ساختمان ${fa(r.building_index + 1)} از ${fa(r.building_count)}`) : ""}<span class="muted">رکورد #${fa(r.id)}</span></div></div>
      <button class="btn sm icon ghost" id="dr-prev" ${idx > 0 ? "" : "disabled"} title="قبلی">${I.prev}</button>
      <button class="btn sm icon ghost" id="dr-next" ${idx >= 0 && idx < ids.length - 1 ? "" : "disabled"} title="بعدی">${I.next}</button>
      <button class="btn sm icon ghost" id="dr-close" title="بستن">${I.x}</button>
    </div>
    <div class="drawer-b">
      ${r.audio_available ? `<audio id="dr-audio" controls preload="metadata" src="/api/files/${r.audio_id}/audio"></audio>
        <div class="seg-buttons">${SEG_KEYS.filter(([k]) => fieldTime(r, k)).map(([k, l]) => `<button class="btn sm" data-segk="${k}">${I.play} ${l}</button>`).join("")}</div>`
        : '<div class="muted small">فایل صوتی پاک شده است.</div>'}
      ${(r.validation.reasons || []).length ? `<div class="alert ${r.status === "ready" ? "ok" : r.status === "invalid" ? "err" : "warn"}">${r.status === "ready" ? I.ok : I.alert}<div class="alert-body"><b>${REC_STATUS[r.status] || ""}</b>
        <ul class="reasons">${r.validation.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>` : ""}
      <div><div class="section-title">${I.wave} متن ویس</div>
        <div class="transcript">${t.processed_text ? highlightTranscript(t.processed_text, t.clauses, r.building_index, r.building_count > 1) : '<span class="muted">متنی موجود نیست.</span>'}</div>
        <div class="legend">${["name", "phone", "address", "tech", "project", "followup"].map((c) => `<span><i style="background:var(--c-${c})"></i>${SEG_LABEL[c]}</span>`).join("")}</div>
        <details style="margin-top:8px"><summary class="small">متن خام تشخیص گفتار ${words.length ? "(واژه‌های کم‌اطمینان زیرخط‌دار)" : ""}</summary>
          <div class="transcript small" style="margin-top:6px">${rawHtml}</div>
          <div class="muted small" style="margin-top:4px">مدل: <span class="ltr">${esc(t.model || "")}</span></div></details></div>
      ${r.validation.duplicates?.length ? `<div><div class="section-title">${I.swap} رکوردهای مشابه</div><div class="stack" style="gap:8px">
        ${r.validation.duplicates.map((dp) => `<div class="dup ${dp.level}"><div class="row between"><b>${esc(dp.ref)}</b>${chip(dp.level === "strong" ? "warn" : "info", dp.level === "strong" ? "احتمال تکرار زیاد" : "شباهت جزئی")}</div>
          <div class="small">${esc(dp.engineer_name)} — <span class="ltr">${esc(dp.phone)}</span> — ${esc(dp.address)}</div>
          <div class="muted small">${esc(dp.reasons.join("، "))}</div></div>`).join("")}
        ${!locked ? `<div class="row"><span class="small muted">تصمیم:</span>
          <button class="btn sm" data-dup="keep">${r.duplicate_decision === "keep" ? I.check : ""} تکراری نیست، نگه دار</button>
          <button class="btn sm danger" data-dup="skip">تکراری است، ثبت نشود</button></div>` : ""}</div></div>` : ""}
      ${DRAWER_GROUPS.map(([title, keys]) => {
        const shown = keys.filter((k) => title === "اطلاعات اصلی" || v[k] || vf[k]);
        if (!shown.length && title !== "مشخصات فنی و مرحله ساخت" && title !== "توضیحات") return "";
        const keysToShow = title === "اطلاعات اصلی" ? keys : (shown.length ? shown : keys.slice(0, 2));
        return `<div class="fgroup"><div class="fgroup-h">${title}</div>${keysToShow.map(fieldRow).join("")}</div>`;
      }).join("")}
      <details><summary class="small">افزودن فیلد دیگر</summary><div class="row" style="margin-top:8px">
        <select class="select" id="dr-addf">${(state.meta?.fields || []).filter((f) => !v[f.key]).map((f) => `<option value="${f.key}">${esc(f.label)}</option>`).join("")}</select>
        <input class="input" id="dr-addv" placeholder="مقدار" style="flex:1"><button class="btn sm" id="dr-addb" ${locked ? "disabled" : ""}>${I.plus} افزودن</button></div></details>
      ${r.edits?.length ? `<details><summary class="small">${I.history} سابقه تغییرات (${fa(r.edits.length)})</summary><ul class="reasons small" style="margin-top:6px">
        ${r.edits.map((e) => `<li class="${e.undone ? "undone" : ""}">${esc(e.at.replace("T", " "))} — ${esc(ACTION_LABEL[e.action] || e.action)}${e.field !== "*" ? ` «${esc(labels[e.field] || e.field)}»` : ""}: «${esc(e.old_value || "")}» ← «${esc(e.new_value || "")}»${e.undone ? " (برگشت داده شد)" : ""}</li>`).join("")}</ul></details>` : ""}
    </div>
    <div class="drawer-f">${locked ? `<div class="alert info" style="flex:1">${I.info}<div class="alert-body">این رکورد در ردیف ${fa(r.export_row)} اکسل ثبت شده است. برای تغییر، ابتدا آن خروجی را در بخش «ثبت در اکسل» بازگردانید.</div></div>`
      : `${r.review_state !== "approved" ? `<button class="btn ok lg" id="dr-approve">${I.check} تأیید برای ثبت</button>` : `<button class="btn" id="dr-reopen">بازگشت به بازبینی</button>`}
        ${r.review_state !== "rejected" ? `<button class="btn danger" id="dr-reject">${I.x} رد</button>` : ""}
        ${hasUndo(r) ? `<button class="btn ghost" id="dr-undo" title="بازگشت آخرین تغییر">${I.retry} بازگشت</button>` : ""}
        <label class="check small" style="margin-inline-start:auto"><input type="checkbox" id="dr-dict" checked> نام تأییدشده به واژه‌نامه اضافه شود</label>`}</div>`;
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
      toast(action === "approve" ? "تأیید شد." : action === "reject" ? "رد شد." : "به بازبینی برگشت.", "ok",
        { label: "بازگشت", onClick: () => undoLast(id) });
      refreshStatus();
      if (reviewState.updateRow) reviewState.updateRow(rec);
      if ((action === "approve" || action === "reject") && idx >= 0 && idx < ids.length - 1) openRecord(ids[idx + 1]);
      else { closeDrawer(); reviewState.reload && reviewState.reload(); }
    } catch (e) { toastErr(e); }
  };
  $("#dr-approve")?.addEventListener("click", async () => {
    if (r.status !== "ready" && !(await confirmBox("تأیید رکورد دارای هشدار", `این رکورد هنوز هشدار دارد:<ul class="reasons review">${(r.validation.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>آیا اطلاعات را با ویس بررسی کرده‌اید و تأیید می‌کنید؟`, "بله، تأیید می‌کنم", "ok"))) return;
    act("approve");
  });
  $("#dr-reject")?.addEventListener("click", () => act("reject"));
  $("#dr-reopen")?.addEventListener("click", () => act("reopen"));
}

// ---------- بازبینی سریع (یک رکورد در هر صفحه، با صفحه‌کلید) ----------
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
    f.setAttribute("aria-label", "بازبینی سریع");
    document.body.appendChild(f);
  }
  return f;
}

async function openFocus(ids, startIdx = 0) {
  if (!ids.length) return toast("رکوردی برای بازبینی نیست.");
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
        ${r.audio_available && fieldTime(r, k) ? `<button class="btn sm" data-fseg="${k}">${I.play} پخش${key >= 0 ? ` <span class="kbd">Alt+${fa(key + 1)}</span>` : ""}</button>` : ""}</span></div>
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
      <div><b>بازبینی سریع</b> <span class="muted">— رکورد ${pos}</span>
        <div class="row small" style="gap:6px">${recordChip(r)}<span class="muted" title="${esc(r.original_name)}">${esc(r.original_name)}</span>
          ${r.building_count > 1 ? chip("info plain", `ساختمان ${fa(r.building_index + 1)} از ${fa(r.building_count)}`) : ""}</div></div>
      <div class="progress" style="flex:1; max-width:260px"><div class="progress-bar" style="width:${Math.round(100 * (focusState.idx + 1) / focusState.ids.length)}%"></div></div>
      <label class="check small"><input type="checkbox" id="fm-autoplay" ${localStorage.getItem("v2x.focus.autoplay") !== "0" ? "checked" : ""}> پخش خودکار شماره</label>
      <button class="btn ghost" id="fm-close">${I.x} خروج <span class="kbd">Esc</span></button>
    </div>
    <div class="fm-body">
      <div class="fm-side">
        ${r.audio_available ? `<audio id="fm-audio" controls preload="auto" src="/api/files/${r.audio_id}/audio"></audio>
          <div class="seg-buttons">${SEG_KEYS.filter(([k]) => fieldTime(r, k)).map(([k, l]) => `<button class="btn sm" data-fsegk="${k}">${I.play} ${l}</button>`).join("")}
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
      ${locked ? `<span class="muted">این رکورد در اکسل ثبت شده است.</span>` : `
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
  else { toast("همه رکوردهای این فهرست بازبینی شد.", "ok"); closeFocus(); }
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

// ================= اکسل =================
const excelState = { report: null, profile: null, lastExport: null };

async function renderExcel(el) {
  const { profile } = await api("/api/excel/profile");
  excelState.profile = profile;
  el.innerHTML = `
    <div class="card"><div class="card-h"><h2>${I.table} ۱. فایل اکسل مقصد</h2>${profile?.confirmed ? chip("ok", "نگاشت ذخیره شده") : ""}</div>
      <div class="card-b stack">
        <div class="row" style="flex-wrap:nowrap">
          <input class="input ltr" id="x-path" style="flex:1; text-align:right" placeholder="C:\\...\\فایل شرکت.xlsx" value="${esc(profile?.excel_path || "")}">
          <button class="btn" id="x-browse">${I.folder} انتخاب...</button>
          <button class="btn primary" id="x-inspect">${I.search} بررسی فایل</button>
        </div>
        ${state.meta?.samples?.excel ? `<div class="row small"><span class="muted">فایل اکسل شرکت را ندارید؟</span>
          <button class="btn sm ghost" id="x-sample">${I.table} استفاده از فایل اکسل نمونه (ساختار مشابه فایل شرکت، داده ساختگی)</button></div>` : ""}
        <div class="muted small">فایل اصلی شرکت فقط خوانده می‌شود. ثبت همیشه روی یک کپی انجام می‌شود و جایگزینی فایل اصلی فقط با تأیید جداگانه شما انجام می‌شود.</div>
        <div id="x-report"></div>
      </div></div>
    <div class="card" id="x-map-card" hidden><div class="card-h"><h2>${I.swap} ۲. نگاشت ستون‌ها</h2><div class="row" id="x-map-actions"></div></div><div class="card-b" id="x-map"></div></div>
    <div class="card" id="x-prev-card" hidden><div class="card-h"><h2>${I.eye} ۳. پیش‌نمایش و ثبت</h2><div class="row" id="x-prev-actions"></div></div><div class="card-b stack" id="x-prev"></div></div>
    <div class="card"><div class="card-h"><h2>${I.history} خروجی‌های ساخته‌شده</h2></div><div class="table-wrap" id="x-exports"></div></div>`;
  $("#x-browse").onclick = async () => {
    const cur = $("#x-path").value.trim();
    const p = await pickPath("excel", cur ? cur.replace(/[\\/][^\\/]*$/, "") : "");
    if (p) { $("#x-path").value = p; inspect(); }
  };
  $("#x-inspect").onclick = inspect;
  $("#x-sample")?.addEventListener("click", () => { $("#x-path").value = state.meta.samples.excel; inspect(); });
  if (profile?.excel_path) inspect();
  drawExports();

  async function inspect() {
    const path = $("#x-path").value.trim();
    if (!path) return toast("مسیر فایل اکسل را وارد یا انتخاب کنید.");
    $("#x-report").innerHTML = '<div class="row"><span class="spinner"></span> در حال بررسی فایل...</div>';
    let res;
    try { res = await api("/api/excel/inspect", { method: "POST", body: { path } }); }
    catch (e) { $("#x-report").innerHTML = ""; return toastErr(e); }
    excelState.report = res.report;
    excelState.draft = JSON.parse(JSON.stringify(res.profile));
    drawReport();
    drawMapping();
    if (excelState.profile?.confirmed && excelState.profile.excel_path === res.report.path) drawPreview();
    else $("#x-prev-card").hidden = true;
  }

  function drawReport() {
    const r = excelState.report;
    const risks = r.risks || [];
    $("#x-report").innerHTML = `<div class="grid grid-2">
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

  function drawMapping() {
    const p = excelState.draft;
    const card = $("#x-map-card");
    if (!p) { card.hidden = true; return; }
    card.hidden = false;
    const sheet = excelState.report.sheets.find((s) => s.name === p.sheet) || excelState.report.sheets[0];
    const fields = state.meta.fields.concat(state.meta.computed).concat([{ key: "followup", label: "پیگیری (اقدام + تاریخ)" }]);
    const protectedSet = new Set(p.protected || []);
    const opts = (col) => {
      const cur = p.columns[col] || (protectedSet.has(col) ? "__protect" : "");
      return `<option value="" ${!cur ? "selected" : ""}>— نوشته نشود —</option>
        <option value="__protect" ${cur === "__protect" ? "selected" : ""}>🔒 محافظت‌شده (هرگز دست نخورد)</option>
        <optgroup label="فیلدها">${fields.map((f) => `<option value="${f.key}" ${cur === f.key ? "selected" : ""}>${esc(f.label)}</option>`).join("")}</optgroup>`;
    };
    const pol = p.policy;
    $("#x-map-actions").innerHTML = `<button class="btn primary" id="x-save">${I.check} ذخیره نگاشت</button>`;
    $("#x-map").innerHTML = `<div class="stack">
      <div class="row"><div class="field"><label>شیت مقصد</label><select class="select" id="x-sheet">${excelState.report.sheets.map((s) => `<option ${s.name === p.sheet ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></div>
        <div class="field"><label>ردیف عنوان</label><input class="input" id="x-hr" type="number" min="1" value="${p.header_row}" style="width:100px"></div>
        <div class="alert info" style="flex:1">${I.info}<div class="alert-body">نگاشت پیشنهادی از روی عنوان ستون‌ها ساخته شده است. آن را بررسی کنید. ستون‌های پیگیری فروش به‌صورت محافظت‌شده علامت خورده‌اند تا سامانه هرگز در آن‌ها ننویسد.</div></div></div>
      <div class="table-wrap" style="border:1px solid var(--border); border-radius:12px"><table class="table"><thead><tr><th>ستون</th><th>عنوان ستون در فایل شرکت</th><th>چه چیزی نوشته شود</th></tr></thead><tbody>
        ${Object.entries(sheet.headers).map(([col, h]) => `<tr><td><b class="ltr">${esc(col)}</b></td><td>${esc(h).replace(/\n/g, " ")}</td>
          <td><select class="select map-select" data-col="${esc(col)}">${opts(col)}</select></td></tr>`).join("")}
      </tbody></table></div>
      <div class="grid grid-2">
        <div class="stack" style="gap:8px"><b>قواعد ثبت</b>
          <label class="check"><input type="radio" name="pf" value="text_leading_zero" ${pol.phone_format !== "as_number_like_existing" ? "checked" : ""}> شماره تلفن به‌صورت متن و با صفر اول (09151234567)</label>
          <label class="check"><input type="radio" name="pf" value="as_number_like_existing" ${pol.phone_format === "as_number_like_existing" ? "checked" : ""}> شماره بدون صفر اول، مثل ردیف‌های فعلی فایل (9151234567)</label>
          <label class="check"><input type="checkbox" id="pol-blank" ${pol.blank_row_between_dates ? "checked" : ""}> یک ردیف خالی میان روزهای بازدید</label>
          <label class="check"><input type="checkbox" id="pol-date1" ${pol.date_first_row_only ? "checked" : ""}> تاریخ فقط در اولین ردیف هر روز</label>
          <label class="check"><input type="checkbox" id="pol-style" ${pol.copy_style_from_last_row ? "checked" : ""}> قالب‌بندی ردیف‌های جدید مثل آخرین ردیف فایل</label>
          <div class="field"><label>سبک نوشتن آدرس و توضیحات</label><div class="row">
            <select class="select" id="pol-sep">${[["", "خودکار (مثل ردیف‌های همین فایل)"], [" ، ", "سجادیه 58 ، قطعه دوم"], ["، ", "سجادیه 58، قطعه دوم"], ["،", "سجادیه 58،قطعه دوم"]]
              .map(([k, l]) => `<option value="${esc(k)}" ${(pol.text_style?.sep ?? "") === k && (k || !pol.text_style) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
            <select class="select" id="pol-digits">${[["", "رقم: خودکار"], ["ascii", "رقم انگلیسی (58)"], ["persian", "رقم فارسی (۵۸)"]]
              .map(([k, l]) => `<option value="${k}" ${(pol.text_style?.digits ?? "") === k && (k || !pol.text_style) ? "selected" : ""}>${l}</option>`).join("")}</select></div>
            <span class="hint">«خودکار» یعنی از روی ردیف‌های موجود فایل شرکت تشخیص داده می‌شود${pol.text_style ? `؛ فعلاً: «${esc(pol.text_style.sep)}» و رقم ${pol.text_style.digits === "persian" ? "فارسی" : "انگلیسی"}` : ""}.</span></div></div>
        <div class="stack" style="gap:8px"><b>اجزای ستون «توضیحات ترکیبی»</b>
          ${[["technical_summary", "خلاصه فنی (تعداد سقف، سازه، مرحله)"], ["project_name", "نام پروژه"], ["building_type", "نوع ساختمان"], ["permit_status", "وضعیت نقشه/مجوز"], ["customer_need", "نیاز مشتری"], ["notes", "توضیحات تکمیلی"], ["followup", "پیگیری و تاریخ پیشنهادی"]]
            .map(([k, l]) => `<label class="check"><input type="checkbox" data-np="${k}" ${pol.notes_parts.includes(k) ? "checked" : ""}> ${l}</label>`).join("")}
          <span class="hint muted small">اگر یکی از این‌ها ستون جداگانه داشته باشد، در توضیحات تکرار نمی‌شود.</span></div></div></div>`;
    $("#x-sheet").onchange = (e) => {
      const s = excelState.report.sheets.find((x) => x.name === e.target.value);
      p.sheet = s.name; p.header_row = s.header_row; p.headers = s.headers; p.columns = {}; p.protected = [];
      drawMapping();
    };
    $("#x-save").onclick = saveMapping;
  }

  async function saveMapping() {
    const p = excelState.draft;
    const columns = {}, prot = [];
    $$("[data-col]").forEach((s) => { if (s.value === "__protect") prot.push(s.dataset.col); else if (s.value) columns[s.dataset.col] = s.value; });
    const body = {
      ...p, header_row: +$("#x-hr").value || p.header_row, columns, protected: prot,
      policy: {
        ...p.policy,
        phone_format: $("input[name=pf]:checked").value,
        blank_row_between_dates: $("#pol-blank").checked,
        date_first_row_only: $("#pol-date1").checked,
        copy_style_from_last_row: $("#pol-style").checked,
        text_style: $("#pol-sep").value || $("#pol-digits").value
          ? { sep: $("#pol-sep").value || p.policy.text_style?.sep || " ، ", digits: $("#pol-digits").value || p.policy.text_style?.digits || "ascii" }
          : null,
        notes_parts: $$("[data-np]").filter((c) => c.checked).map((c) => c.dataset.np),
      },
    };
    try {
      const r = await api("/api/excel/profile", { method: "PUT", body });
      excelState.profile = r.profile;
      excelState.draft = JSON.parse(JSON.stringify(r.profile));
      toast("نگاشت ذخیره شد.", "ok");
      // واژه‌نامه از نام مهندس‌ها و خیابان‌های همین فایل پر می‌شود تا املای درست پیشنهاد شود
      try {
        const sd = await api("/api/dictionary/seed-from-excel", { method: "POST" });
        if (sd.added.engineer || sd.added.street)
          toast(`واژه‌نامه پر شد: ${fa(sd.added.engineer)} نام مهندس و ${fa(sd.added.street)} خیابان از فایل اکسل.`, "ok");
      } catch { }
      drawMapping();
      drawPreview();
      refreshStatus();
    } catch (e) { toastErr(e); }
  }

  async function drawPreview() {
    const card = $("#x-prev-card");
    card.hidden = false;
    $("#x-prev").innerHTML = '<div class="row"><span class="spinner"></span> در حال آماده‌سازی پیش‌نمایش...</div>';
    $("#x-prev-actions").innerHTML = "";
    let pv;
    try { pv = await api("/api/excel/preview", { method: "POST" }); }
    catch (e) { $("#x-prev").innerHTML = `<div class="alert err">${I.alert}<div class="alert-body">${esc(e.message)}</div></div>`; return; }
    const prof = pv.profile;
    const cols = Object.keys(prof.headers);
    const rows = pv.rows || [];
    const lockMsg = pv.lock?.locked ? `<div class="alert warn">${I.alert}<div class="alert-body"><b>فایل اصلی ظاهراً در Excel باز است</b>تغییرات ذخیره‌نشده آن در خروجی دیده نمی‌شود. بهتر است فایل را ذخیره کنید و ببندید.</div></div>` : "";
    if (!rows.length) {
      $("#x-prev").innerHTML = `${lockMsg}<div class="empty">${I.check}<div>رکورد تأییدشده‌ای برای ثبت وجود ندارد.</div>
        ${pv.pending ? `<div>${fa(pv.pending)} رکورد هنوز منتظر بازبینی است.</div><a class="btn" href="#/review">رفتن به بازبینی</a>` : ""}</div>`;
      return;
    }
    $("#x-prev-actions").innerHTML = `<button class="btn" id="x-refresh">${I.retry} به‌روزرسانی</button><button class="btn primary lg" id="x-export">${I.table} ساخت فایل خروجی (${fa(rows.length)} ردیف)</button>`;
    let html = "";
    let prevRow = pv.last_existing_row;
    for (const r of rows) {
      if (r.row > prevRow + 1) html += `<tr class="blank"><td colspan="${cols.length + 2}"></td></tr>`;
      html += `<tr><td class="rownum">${fa(r.row)}</td><td class="small muted" style="max-width:140px">${esc(r.original_name)}</td>${cols.map((c) => `<td ${prof.protected.includes(c) ? 'class="muted"' : ""}>${prof.protected.includes(c) ? "🔒" : esc(r.cells[c] || "")}</td>`).join("")}</tr>`;
      prevRow = r.row;
    }
    $("#x-prev").innerHTML = `${lockMsg}
      ${pv.header_mismatches?.length ? `<div class="alert err">${I.alert}<div class="alert-body"><b>عنوان ستون‌ها تغییر کرده است</b>${pv.header_mismatches.map(esc).join("<br>")}</div></div>` : ""}
      <div class="row small"><span>آخرین ردیف داده فعلی: <b>${fa(pv.last_existing_row)}</b></span><span class="muted">|</span><span>${fa(rows.length)} ردیف جدید از ردیف ${fa(rows[0].row)} تا ${fa(rows[rows.length - 1].row)}</span>
        ${pv.pending ? `<span class="muted">|</span><a href="#/review">${fa(pv.pending)} رکورد هنوز منتظر بازبینی است و ثبت نمی‌شود</a>` : ""}</div>
      <div class="table-wrap" style="border:1px solid var(--border); border-radius:12px; max-height:460px"><table class="table preview-table"><thead><tr><th>ردیف</th><th>ویس</th>${cols.map((c) => `<th title="${esc(prof.headers[c])}">${esc(c)} — ${esc(prof.headers[c]).replace(/\n/g, " ")}</th>`).join("")}</tr></thead><tbody>${html}</tbody></table></div>`;
    $("#x-refresh").onclick = drawPreview;
    $("#x-export").onclick = doExport;
  }

  async function doExport() {
    const ok = await confirmBox("ساخت فایل خروجی", `<div class="stack"><div>این کارها انجام می‌شود:</div><ul class="reasons">
      <li>یک نسخه پشتیبان از فایل اصلی در پوشه backups ساخته می‌شود.</li>
      <li>ردیف‌های تأییدشده در <b>یک کپی جدید</b> از فایل نوشته می‌شوند؛ فایل اصلی تغییر نمی‌کند.</li>
      <li>پس از ذخیره، کپی دوباره خوانده و بررسی می‌شود که داده‌های قبلی دست نخورده باشند.</li></ul></div>`, "ساخت خروجی");
    if (!ok) return;
    const btn = $("#x-export");
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> در حال ثبت...';
    try {
      const rep = await api("/api/excel/export", { method: "POST", body: {} });
      excelState.lastExport = rep;
      refreshStatus();
      showExportResult(rep);
      drawPreview();
      drawExports();
    } catch (e) { toastErr(e); btn.disabled = false; btn.innerHTML = "ساخت فایل خروجی"; }
  }

  function showExportResult(rep) {
    openModal({
      title: `${I.ok} فایل خروجی ساخته شد`,
      wide: true,
      body: `<div class="stack"><dl class="kv">
        <dt>ردیف‌های ثبت‌شده</dt><dd>${fa(rep.rows.length)} ردیف (${fa(rep.first_row)} تا ${fa(rep.last_row)})</dd>
        <dt>فایل خروجی</dt><dd><span class="path">${esc(rep.output_path)}</span></dd>
        <dt>نسخه پشتیبان</dt><dd><span class="path">${esc(rep.backup_path)}</span></dd>
        <dt>فایل اصلی</dt><dd>بدون تغییر <span class="path">${esc(rep.target_path)}</span></dd></dl>
        ${rep.warnings?.length ? `<div class="alert warn">${I.alert}<div class="alert-body"><ul class="reasons">${rep.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div></div>` : ""}
        ${rep.dropped_parts?.length ? `<div class="alert info">${I.info}<div class="alert-body">این بخش‌های داخلی فایل در خروجی حذف شدند (معمولاً بی‌اثرند): <span class="ltr small">${rep.dropped_parts.map(esc).join(", ")}</span></div></div>` : ""}
        <div class="alert info">${I.info}<div class="alert-body">فایل خروجی را در Excel باز و بررسی کنید. اگر درست بود، دکمه «جایگزینی فایل اصلی» را بزنید.</div></div></div>`,
      actions: [
        { label: `${I.open} باز کردن پوشه خروجی`, cls: "", onClick: async () => { await api("/api/open-folder", { method: "POST", body: { path: rep.output_path } }).catch(toastErr); return false; } },
        { label: `${I.down} دانلود`, onClick: () => { location.href = `/api/exports/${rep.export_id}/download`; return false; } },
        { label: `${I.swap} جایگزینی فایل اصلی`, cls: "primary", onClick: async () => { await replaceOriginal(rep.export_id); } },
        { label: "بستن", cls: "ghost" },
      ],
    });
  }

  async function drawExports() {
    const { exports } = await api("/api/exports");
    const box = $("#x-exports");
    if (!exports.length) { box.innerHTML = `<div class="empty">${I.table}<div>هنوز خروجی‌ای ساخته نشده است.</div></div>`; return; }
    const ST = { created: ["warn", "ساخته شده، هنوز اعمال نشده"], applied: ["ok", "جایگزین فایل اصلی شد"], undone: ["missing", "بازگردانده شد"] };
    box.innerHTML = `<table class="table"><thead><tr><th>#</th><th>زمان</th><th>ردیف‌ها</th><th>وضعیت</th><th>فایل خروجی</th><th></th></tr></thead><tbody>
      ${exports.map((x) => `<tr><td class="muted">${fa(x.id)}</td><td class="small">${fa(x.created_at.replace("T", " "))}</td>
        <td>${fa(x.rows_written)} <span class="muted small">(${fa(x.first_row)}–${fa(x.last_row)})</span></td><td>${chip(...ST[x.status] || ["", x.status])}</td>
        <td class="small" style="max-width:320px"><span class="path">${esc(x.output_path.split(/[\\/]/).pop())}</span></td>
        <td class="actions">
          <button class="btn sm ghost" data-xdl="${x.id}" title="دانلود">${I.down}</button>
          <button class="btn sm ghost" data-xopen="${esc(x.output_path)}" title="باز کردن پوشه">${I.open}</button>
          ${x.status === "created" ? `<button class="btn sm primary" data-xrep="${x.id}">جایگزینی فایل اصلی</button>` : ""}
          ${x.status !== "undone" ? `<button class="btn sm danger" data-xundo="${x.id}">بازگردانی</button>` : ""}</td></tr>`).join("")}</tbody></table>`;
    $$("[data-xdl]", box).forEach((b) => b.onclick = () => location.href = `/api/exports/${b.dataset.xdl}/download`);
    $$("[data-xopen]", box).forEach((b) => b.onclick = () => api("/api/open-folder", { method: "POST", body: { path: b.dataset.xopen } }).catch(toastErr));
    $$("[data-xrep]", box).forEach((b) => b.onclick = () => replaceOriginal(+b.dataset.xrep));
    $$("[data-xundo]", box).forEach((b) => b.onclick = async () => {
      if (!(await confirmBox("بازگردانی خروجی", "رکوردهای این خروجی دوباره به حالت «آماده ثبت» برمی‌گردند تا بتوانید اصلاح یا دوباره ثبتشان کنید. فایل‌ها حذف نمی‌شوند. ادامه می‌دهید؟", "بازگردانی", "danger"))) return;
      try { const r = await api(`/api/exports/${b.dataset.xundo}/undo`, { method: "POST" }); toast(r.message, "ok"); refreshStatus(); drawExports(); drawPreview(); }
      catch (e) { toastErr(e); }
    });
  }

  async function replaceOriginal(eid) {
    const ok = await confirmBox("جایگزینی فایل اصلی شرکت", `<div class="stack"><div class="alert warn">${I.alert}<div class="alert-body">فایل اصلی با فایل خروجی جایگزین می‌شود. پیش از آن یک نسخه پشتیبان دیگر از فایل اصلی گرفته می‌شود.</div></div>
      <ul class="reasons"><li>Excel باید بسته باشد.</li><li>اگر فایل اصلی پس از ساخت خروجی تغییر کرده باشد، جایگزینی انجام نمی‌شود تا آن تغییرات از بین نروند.</li></ul>
      <div>آیا فایل خروجی را بررسی کرده‌اید و از جایگزینی مطمئنید؟</div></div>`, "بله، جایگزین کن", "primary");
    if (!ok) return false;
    try {
      const r = await api(`/api/exports/${eid}/replace-original`, { method: "POST" });
      toast("فایل اصلی به‌روزرسانی شد. پشتیبان: " + r.backup_path.split(/[\\/]/).pop(), "ok");
      refreshStatus(); drawExports();
    } catch (e) { toastErr(e); return false; }
  }
}

// ================= واژه‌نامه =================
async function renderDictionary(el) {
  let type = location.hash.includes("?kb") ? "__kb" : "engineer";
  const kb = { pending: [], roles: {} };  // فایل‌های بارگذاری‌شده‌ای که هنوز یاد گرفته نشده‌اند
  el.innerHTML = `<div class="card"><div class="card-h"><div class="tabs" id="dc-tabs"></div>
      <div class="row"><input class="input" id="dc-q" placeholder="جست‌وجو..." style="width:200px">
      <button class="btn" id="dc-seed">${I.table} پرکردن از اکسل شرکت</button><button class="btn primary" id="dc-add">${I.plus} نام جدید</button></div></div>
    <div class="card-b" id="dc-note" style="padding:12px 20px; border-bottom:1px solid var(--border)"><div class="muted small">نام‌های این فهرست به‌عنوان «املای تأییدشده» شناخته می‌شوند. نام‌های مشابه هرگز خودکار ادغام نمی‌شوند؛ فقط به‌عنوان پیشنهاد در بازبینی نمایش داده می‌شوند. تغییر املا با ثبت سابقه انجام می‌شود و املای قبلی به‌عنوان «شکل دیگر» حفظ می‌شود.</div></div>
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
      if (!(await confirmBox("حذف از واژه‌نامه", "این نام و شکل‌های دیگرش از واژه‌نامه حذف می‌شوند (رکوردها تغییر نمی‌کنند).", "حذف", "danger"))) return;
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
  $("#dc-seed").onclick = async () => {
    if (!(await confirmBox("پرکردن واژه‌نامه از اکسل شرکت", "نام مهندس‌ها (ردیف‌هایی که با «مهندس/آقای/خانم» شروع می‌شوند) و نام خیابان‌ها از ستون‌های نگاشت‌شده فایل شرکت خوانده و با منبع «اکسل» به واژه‌نامه اضافه می‌شوند. فایل اکسل تغییر نمی‌کند.", "پرکردن"))) return;
    try {
      const r = await api("/api/dictionary/seed-from-excel", { method: "POST" });
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
    if (!(await confirmBox("حذف آموخته‌های فایل", `نام‌ها و خیابان‌هایی که فقط از «${esc(b.dataset.name)}» آمده‌اند و هیچ رکوردی تأییدشان نکرده، از واژه‌نامه حذف می‌شوند. فایل اکسل و رکوردهای ثبت‌شده تغییر نمی‌کنند.`, "حذف", "danger"))) return;
    try { const r = await api(`/api/knowledge/sources/${b.dataset.kbdel}`, { method: "DELETE" }); toast(`${fa(r.removed)} نام از واژه‌نامه حذف شد.`, "ok"); refreshStatus(); reload(); } catch (e) { toastErr(e); }
  });
}

/** فهرست اصلاحاتی که برنامه از ویرایش‌های کاربر یاد گرفته؛ با امکان غیرفعال‌کردن و حذف. */
function drawCorrections(box, corr, q, reload) {
  const list = corr.corrections.filter((c) => !q || c.wrong.includes(q) || c.right.includes(q));
  if (!list.length) {
    box.innerHTML = `<div class="empty">${I.history}<div>هنوز اصلاحی یاد گرفته نشده است.</div>
      <div class="small">وقتی در بازبینی واژه‌ای را اصلاح می‌کنید (مثلاً «گلزی» ← «گلزاری»)، اینجا ثبت می‌شود؛ از ${fa(corr.threshold)} بار تکرار به بعد خودکار اعمال می‌شود.</div></div>`;
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
    if (!(await confirmBox("حذف اصلاح", "این اصلاح دیگر پیشنهاد یا اعمال نمی‌شود. رکوردهای قبلی تغییر نمی‌کنند.", "حذف", "danger"))) return;
    try { await api(`/api/corrections/${b.dataset.cdel}`, { method: "DELETE" }); reload(); } catch (e) { toastErr(e); }
  });
}

// ================= تنظیمات =================
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
    const fullNav = document.documentElement.classList.contains("full-nav");
    el.innerHTML = `
      <div class="card" style="margin-bottom:18px"><div class="card-h"><h2>${I.table} ابزارها</h2>
        <label class="check small"><input type="checkbox" id="s-fullnav" ${fullNav ? "checked" : ""}> نمایش همه صفحه‌ها در منو</label></div>
        <div class="card-b row">
          <a class="btn" href="#/excel">${I.table} اتصال و نگاشت فایل اکسل</a>
          <a class="btn" href="#/dictionary">${I.book} واژه‌نامه</a>
          <a class="btn" href="#/dictionary?kb">${I.upload} آموزش از اکسل</a>
          <a class="btn" href="#/voices">${I.music} همه ویس‌ها</a>
          <a class="btn" href="#/review?filter=all">${I.eye} همه رکوردها</a>
          <a class="btn ghost" href="/static/recording-guide.html" target="_blank">${I.info} راهنمای ضبط ویس</a>
        </div>
        <div class="card-b stack" style="border-top:1px solid var(--border)"><b>پوشه ورودی خودکار</b>
          <div class="row" style="flex-wrap:nowrap"><input class="input ltr" id="s-inbox" value="${esc(s.inbox_dir)}" placeholder="مثلاً ...\\Downloads\\Telegram Desktop" style="flex:1; text-align:right">
            <button class="btn" id="s-inbox-pick">${I.folder} انتخاب پوشه</button><button class="btn primary" id="s-inbox-save">${I.check} ذخیره</button></div>
          <span class="hint">ویس‌هایی که از این به بعد در این پوشه ذخیره شوند (مثلاً پوشه دانلود تلگرام یا واتساپ دسکتاپ)، خودکار برداشته و پردازش می‌شوند. ویس‌های قدیمی پوشه دست نمی‌خورند. خالی = خاموش.</span></div></div>
      <details class="tech-box"><summary>تنظیمات فنی <span class="muted small">— مدل گفتار، قواعد اعتبارسنجی، کارایی</span></summary>
      <div class="grid grid-2">
        <div class="card"><div class="card-h"><h2>${I.mic} مدل تبدیل گفتار</h2></div><div class="card-b stack">
          <div class="table-wrap" style="border:1px solid var(--border); border-radius:12px"><table class="table"><tbody>
            ${d.models.map((m) => { const inst = d.installed_models.includes(m); return `<tr>
              <td><label class="check"><input type="radio" name="model" value="${m}" ${s.model_name === m ? "checked" : ""} ${inst ? "" : "disabled"}> <b class="ltr">${m}</b></label></td>
              <td class="small">${MODEL_INFO[m]?.[0] || ""}<div class="muted">${MODEL_INFO[m]?.[1] || ""}</div></td>
              <td>${inst ? chip("ok", "نصب‌شده") : `<button class="btn sm" data-dl="${m}" ${d.download.status === "running" ? "disabled" : ""}>${I.down} دریافت</button>`}</td></tr>`; }).join("")}
          </tbody></table></div>
          ${d.download.status !== "idle" ? `<div class="alert ${d.download.status === "error" ? "err" : d.download.status === "done" ? "ok" : "info"}">${d.download.status === "running" ? '<span class="spinner"></span>' : I.info}<div class="alert-body"><b class="ltr">${esc(d.download.name || "")}</b> ${esc(d.download.message)}</div></div>` : ""}
          <div class="muted small">دریافت مدل تنها کاری است که به اینترنت نیاز دارد و فقط با دکمه بالا انجام می‌شود. پس از دریافت، همه پردازش‌ها آفلاین است. مدل نهایی را پس از مقایسه روی ویس‌های واقعی انتخاب کنید.</div>
          <div class="grid grid-2" style="gap:12px">
            <div class="field"><label>Beam size</label><input class="input" type="number" min="1" max="10" id="s-beam" value="${s.beam_size}"><span class="hint">پیشنهادی ۲؛ بیشتر کندتر می‌شود بی‌آنکه در آزمون دقیق‌تر شده باشد، ۱ دقت شماره را کم می‌کند</span></div>
            <div class="field"><label>تعداد هسته CPU</label><input class="input" type="number" min="0" max="32" id="s-threads" value="${s.cpu_threads}"><span class="hint">۰ = خودکار</span></div>
          </div>
          <label class="check"><input type="checkbox" id="s-vad" ${s.vad_filter ? "checked" : ""}> حذف بخش‌های بی‌صدا (VAD)</label>
          <label class="check"><input type="checkbox" id="s-hot" ${s.use_dictionary_hotwords ? "checked" : ""}> ارسال نام‌های واژه‌نامه به مدل گفتار (توصیه نمی‌شود)</label>
          <span class="hint muted small" style="margin-top:-6px">در آزمون روی ۸ ویس، این گزینه باعث تکرار ساختگی واژه‌ها و از دست رفتن شماره یا آدرس در ۳ ویس شد و ۲ تا ۴ برابر کندتر بود. املای درست نام‌ها از راه پیشنهادهای واژه‌نامه به دست می‌آید.</span>
          <div class="field"><label>متن راهنمای سبک نگارش برای مدل</label><textarea class="input" id="s-prompt" rows="3">${esc(s.initial_prompt)}</textarea>
            <span class="hint">فقط واژه‌های رایج را به مدل نشان می‌دهد. در آن <b>رقم یا نام شخص ننویسید</b>؛ در آزمون، رقم مدل را به حلقه رقم‌های بی‌معنی انداخت و نام شخص به خروجی نشت کرد.</span></div>
        </div></div>
        <div class="stack" style="gap:18px">
        <div class="card"><div class="card-h"><h2>${I.shield} قواعد اعتبارسنجی</h2></div><div class="card-b stack">
          <div class="field"><label>فیلدهای الزامی برای «آماده ثبت» بودن رکورد</label>
            <div class="row">${[["engineer_name", "نام مهندس"], ["phone", "شماره تماس"], ["address", "آدرس"], ["project_name", "نام پروژه"]].map(([k, l]) => `<label class="check"><input type="checkbox" data-req="${k}" ${s.required_fields.includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div>
            <span class="hint">رکوردی که همه فیلدهای الزامی‌اش معتبر باشد، خودکار «آماده ثبت» می‌شود؛ بقیه به بازبینی می‌روند.</span></div>
          <label class="check"><input type="checkbox" id="s-revphone" ${s.review_spoken_phones ? "checked" : ""}> هر شماره تلفن با شنیدن ویس تأیید شود (پیشنهادی تا سنجش دقت روی ویس‌های واقعی)</label>
          <label class="check"><input type="checkbox" id="s-kbspell" ${s.kb_auto_spelling ? "checked" : ""}> املای هم‌آوای نام و خیابان مطابق واژه‌نامه یکسان شود (مثلاً «کازمی» ← «کاظمی»؛ فقط وقتی یک گزینه باشد)</label>
          <div class="grid grid-2" style="gap:12px">
            <div class="field"><label>پیش‌شماره شهر برای تلفن ثابت</label><input class="input ltr" id="s-area" value="${esc(s.default_area_code)}" placeholder="مثلاً 051" style="text-align:right"><span class="hint">فقط به‌عنوان پیشنهاد نمایش داده می‌شود.</span></div>
            <div class="field"><label>کمینه شباهت برای پیشنهاد املا</label><input class="input" type="number" step="0.01" min="0.5" max="0.99" id="s-sim" value="${s.similarity_suggest}"></div>
            <div class="field"><label>اعمال خودکار اصلاحات یادگرفته‌شده پس از</label><div class="row"><input class="input" type="number" min="1" max="20" id="s-learn" value="${s.learn_auto_threshold}" style="width:90px"><span class="small muted">بار تکرار</span></div></div>
            <div class="field"><label>آزادسازی مدل از حافظه پس از</label><div class="row"><input class="input" type="number" min="0" max="240" id="s-idle" value="${s.model_idle_minutes}" style="width:90px"><span class="small muted">دقیقه بی‌کاری</span></div></div>
          </div>
          <div class="row"><button class="btn primary" id="s-save">${I.check} ذخیره تنظیمات</button><button class="btn" id="s-reval">${I.retry} اعتبارسنجی دوباره همه رکوردها</button>
            <button class="btn" id="s-reext" title="بدون تبدیل دوباره گفتار؛ رکوردهای اصلاح‌شده یا تأییدشده دست نمی‌خورند">${I.retry} استخراج دوباره از متن ویس‌ها</button></div>
        </div></div>
        <div class="card"><div class="card-h"><h2>${I.info} سامانه و کارایی</h2></div><div class="card-b">
          <dl class="kv"><dt>RAM کل رایانه</dt><dd>${d.system.ram_gb ? fa(d.system.ram_gb) + " گیگابایت" : "—"}</dd>
            <dt>حافظه فعلی برنامه</dt><dd>${d.system.process_mb ? fa(d.system.process_mb) + " مگابایت" : "—"}</dd>
            <dt>بیشینه حافظه در پردازش</dt><dd>${p.peak ? fa(Math.round(p.peak)) + " مگابایت" : "—"}</dd>
            <dt>میانگین زمان هر ویس</dt><dd>${p.avg_s ? fmtSec(p.avg_s) + (p.avg_d ? ` برای ویس ${fmtSec(p.avg_d)}` : "") : "—"} ${p.n ? `<span class="muted">(${fa(p.n)} ویس)</span>` : ""}</dd>
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
        <div class="row"><button class="btn primary" id="s-backup-now">${I.plus} پشتیبان‌گیری الان</button></div></div>
        <div class="card-b small muted" style="padding:10px 20px">هر روز یک پشتیبان خودکار از اطلاعات برنامه (رکوردها، متن ویس‌ها، واژه‌نامه، اصلاحات، تنظیمات و نگاشت اکسل) گرفته و ۱۴ پشتیبان آخر نگه داشته می‌شود. فایل‌های صوتی به‌خاطر حجم در پشتیبان نیستند. پیش از هر بازگردانی، از وضعیت فعلی هم پشتیبان گرفته می‌شود تا قابل برگشت باشد.</div>
        <div class="table-wrap" id="s-backups"></div></div>
      <div class="card" style="margin-top:18px"><div class="card-h"><h2>${I.trash} نگهداری، گزارش و حریم خصوصی</h2></div><div class="card-b stack">
        <div class="row">
          <a class="btn" href="/api/report/errors.xlsx">${I.down} گزارش خطاها و هشدارها</a>
          <a class="btn" href="/api/report/records.xlsx">${I.down} گزارش کامل رکوردها (با متن ویس)</a>
          <button class="btn" id="s-open-data">${I.open} باز کردن پوشه داده‌ها</button>
          <button class="btn danger" id="s-purge">${I.trash} حذف فایل‌های صوتیِ ثبت‌شده</button>
          <label class="check small"><input type="checkbox" id="s-sound" ${localStorage.getItem("v2x.sound") !== "0" ? "checked" : ""}> صدای پایان پردازش</label>
        </div>
        <div class="muted small">فایل‌های صوتی برای پخش در بازبینی نگه داشته می‌شوند. پس از ثبت در اکسل می‌توانید آن‌ها را پاک کنید؛ متن ویس‌ها و رکوردها باقی می‌مانند.</div>
        <details><summary>رخدادهای اخیر</summary><div id="s-events" class="small" style="margin-top:8px"></div></details>
      </div></div>`;
    $$("[data-dl]").forEach((b) => b.onclick = async () => {
      if (!(await confirmBox("دریافت مدل", `مدل <b class="ltr">${esc(b.dataset.dl)}</b> از اینترنت (Hugging Face) دریافت می‌شود. این تنها ارتباط اینترنتی برنامه است و هیچ ویس یا اطلاعاتی ارسال نمی‌شود. ادامه می‌دهید؟`, "دریافت"))) return;
      try { await api("/api/models/download", { method: "POST", body: { name: b.dataset.dl } }); toast("دریافت شروع شد."); poll(); } catch (e) { toastErr(e); }
    });
    $("#s-inbox-pick").onclick = async () => { const p = await pickPath("audio", $("#s-inbox").value.trim()); if (p) $("#s-inbox").value = p; };
    $("#s-inbox-save").onclick = async () => {
      const v = $("#s-inbox").value.trim();
      try { await api("/api/settings", { method: "PUT", body: { inbox_dir: v } }); toast(v ? "پوشه ورودی فعال شد." : "پوشه ورودی خاموش شد.", "ok"); refreshStatus(); }
      catch (e) { toastErr(e); }
    };
    $("#s-fullnav").onchange = (e) => {
      try { localStorage.setItem("v2x.nav", e.target.checked ? "full" : "simple"); } catch { }
      document.documentElement.classList.toggle("full-nav", e.target.checked);
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
      try { const r = await api("/api/records/revalidate-all", { method: "POST" }); toast(`${fa(r.count)} رکورد دوباره اعتبارسنجی شد.`, "ok"); refreshStatus(); } catch (e) { toastErr(e); }
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
          <td class="small muted">${fa(b.counts?.audio_files ?? 0)} ویس، ${fa(b.counts?.records ?? 0)} رکورد، ${fa(b.counts?.entities ?? 0)} نام</td><td class="small">${fmtSize(b.size)}</td>
          <td class="actions"><a class="btn sm ghost" href="/api/backups/${encodeURIComponent(b.name)}/download" title="دانلود">${I.down}</a>
            ${b.damaged ? "" : `<button class="btn sm" data-restore="${esc(b.name)}">بازگردانی</button>`}</td></tr>`).join("")}</tbody></table>`;
      $$("[data-restore]", box).forEach((btn) => btn.onclick = async () => {
        const ok = await confirmBox("بازگردانی اطلاعات", `<div class="stack"><div class="alert warn">${I.alert}<div class="alert-body">همه رکوردها، واژه‌نامه، اصلاحات، تنظیمات و نگاشت اکسل به وضعیت این پشتیبان برمی‌گردند.</div></div>
          <div>پیش از آن، از وضعیت فعلی یک پشتیبان «پیش از بازگردانی» گرفته می‌شود تا در صورت نیاز برگردید. فایل اکسل شرکت تغییر نمی‌کند.</div></div>`, "بازگردانی", "danger");
        if (!ok) return;
        try {
          const r = await api(`/api/backups/${encodeURIComponent(btn.dataset.restore)}/restore`, { method: "POST" });
          toast("اطلاعات بازگردانده شد. پشتیبان وضعیت قبلی: " + r.safety_backup, "ok");
          refreshStatus(); drawBackups();
        } catch (e) { toastErr(e); }
      });
    };
    $("#s-backup-now").onclick = async () => {
      try { const b = await api("/api/backups", { method: "POST" }); toast(`پشتیبان ساخته شد (${fmtSize(b.size)}).`, "ok"); drawBackups(); } catch (e) { toastErr(e); }
    };
    drawBackups().catch(() => {});
    const drawLan = async () => {
      const L = await api("/api/lan");
      const box = $("#s-lan");
      if (!box) return;
      box.innerHTML = `<div class="stack">
        <div class="muted small">بازاریاب‌ها در دفتر، با گوشیِ وصل به همان وای‌فای، ویس را از مرورگر گوشی مستقیم می‌فرستند. فقط صفحه ارسال ویس با رمز از گوشی باز می‌شود؛ رکوردها، اکسل و تنظیمات فقط روی همین رایانه در دسترس‌اند. اطلاعات از شبکه محلی بیرون نمی‌رود.</div>
        <label class="check"><input type="checkbox" id="lan-on" ${L.enabled ? "checked" : ""}> فعال باشد</label>
        ${L.enabled ? `
          <label class="check"><input type="checkbox" id="lan-auto" ${L.auto_start ? "checked" : ""}> پردازش ویس‌های رسیده از گوشی خودکار شروع شود</label>
          ${L.restart_needed ? `<div class="alert warn">${I.alert}<div class="alert-body"><b>یک بار برنامه را ببندید و دوباره باز کنید</b>تا دسترسی از شبکه فعال شود. اگر ویندوز درباره «دیوار آتش» (Firewall) پرسید، گزینه «شبکه خصوصی» را مجاز کنید.</div></div>` : ""}
          <dl class="kv"><dt>نشانی در گوشی</dt><dd>${L.urls.length ? L.urls.map((u) => `<span class="path">${esc(u)}</span>`).join(" ") : '<span class="muted">این رایانه به شبکه محلی وصل نیست.</span>'}</dd>
            <dt>رمز</dt><dd><span class="phone-view"><span class="ltr">${esc(L.pin)}</span></span> <button class="btn sm ghost" id="lan-pin">رمز جدید</button></dd></dl>
          <div class="muted small">رمز را فقط به بازاریاب‌های خودتان بدهید. با «رمز جدید»، گوشی‌هایی که رمز قبلی را داشتند دیگر نمی‌توانند ویس بفرستند.</div>` : ""}
      </div>`;
      const save = async () => {
        try { await api("/api/lan", { method: "PUT", body: { enabled: $("#lan-on").checked, auto_start: $("#lan-auto") ? $("#lan-auto").checked : true } }); drawLan(); }
        catch (e) { toastErr(e); }
      };
      $("#lan-on").onchange = save;
      $("#lan-auto")?.addEventListener("change", save);
      $("#lan-pin")?.addEventListener("click", async () => {
        if (!(await confirmBox("رمز جدید", "گوشی‌هایی که رمز قبلی را دارند باید رمز جدید را وارد کنند. ادامه می‌دهید؟", "رمز جدید"))) return;
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
        ${!U.supported ? `<div class="muted small">به‌روزرسانی سبک فقط در نسخه قابل‌حمل (Voice2Excel.exe) در دسترس است.</div>` : U.staged
          ? `<div class="alert ok">${I.ok}<div class="alert-body"><b>نسخه ${fa(U.staged.version)} آماده نصب است</b>برنامه را با «خروج از برنامه» ببندید و دوباره باز کنید تا نسخه جدید جایگزین شود. اگر نسخه جدید اجرا نشود، برنامه خودکار به نسخه فعلی برمی‌گردد.${U.staged.notes ? `<div class="small">${esc(U.staged.notes)}</div>` : ""}</div>
              <button class="btn sm ghost" id="up-cancel">لغو</button></div>`
          : `<div class="muted small">بسته به‌روزرسانی (فایل Voice2Excel-update-….zip، حدود ۱ مگابایت) را انتخاب کنید. فقط بسته‌ای را نصب کنید که از سازنده برنامه گرفته‌اید. اطلاعات شما (پوشه data) دست نمی‌خورد.</div>
             <div class="row"><input type="file" id="up-file" accept=".zip" hidden><button class="btn" id="up-pick">${I.upload} انتخاب بسته به‌روزرسانی</button></div>`}
      </div>`;
      $("#up-pick")?.addEventListener("click", () => $("#up-file").click());
      $("#up-file")?.addEventListener("change", async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append("file", f, f.name);
        try { const r = await api("/api/update", { method: "POST", form: fd }); toast(`نسخه ${fa(r.version)} آماده شد؛ برنامه را ببندید و دوباره باز کنید.`, "ok"); drawUpdate(); }
        catch (er) { toastErr(er); }
      });
      $("#up-cancel")?.addEventListener("click", async () => { try { await api("/api/update", { method: "DELETE" }); drawUpdate(); } catch (er) { toastErr(er); } });
    };
    drawUpdate().catch(() => {});
    $("#s-purge").onclick = async () => {
      if (!(await confirmBox("حذف فایل‌های صوتی", "فایل‌های صوتی ویس‌هایی که همه رکوردهایشان در اکسل ثبت (یا رد) شده‌اند، برای همیشه از پوشه برنامه حذف می‌شوند. فایل‌های اصلی شما در جای خودشان دست نمی‌خورند.", "حذف", "danger"))) return;
      try { const r = await api("/api/maintenance/purge-audio", { method: "POST", body: { scope: "exported" } }); toast(`${fa(r.deleted)} فایل صوتی حذف شد.`, "ok"); } catch (e) { toastErr(e); }
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
    <h2 style="margin:0">برنامه بسته شد</h2><div>برای اجرای دوباره، روی «ثبت ویس» در دسکتاپ یا Voice2Excel.exe دوبار کلیک کنید.</div>
    <div class="muted small">می‌توانید این صفحه را ببندید.</div></div>`;
});

async function importSamples() {
  try {
    const r = await api("/api/samples/import", { method: "POST" });
    reportUpload(r.results);
    await refreshStatus();
    if (r.results.some((x) => x.result === "added")) startQueue();
    location.hash = "#/today";
  } catch (e) { toastErr(e); }
}

// ---------------- شروع ----------------
(async function init() {
  try { state.meta = await api("/api/meta"); } catch (e) { toastErr(e); }
  await refreshStatus();
  route();
  setInterval(refreshStatus, 1500);
})();
