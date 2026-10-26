"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const TOKEN = $('meta[name="x-token"]')?.content || "";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fa = (n) => String(n ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const money = (n) => new Intl.NumberFormat("fa-IR").format(n || 0) + " تومان";
const STATE = { active: ["ok", "فعال"], soon: ["warn", "نزدیک پایان"], lapsed: ["err", "تمام‌شده"], forever: ["info", "نامحدود"] };
let tab = ["issue", "customers", "due", "settings"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "issue";

async function api(path, { method = "GET", body } = {}) {
  const opt = { method, headers: { "X-Token": TOKEN } };
  if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, opt);
  const data = (res.headers.get("content-type") || "").includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(data?.detail || "خطا");
  return data;
}
function toast(msg, type = "") {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 3500);
}
const toastErr = (e) => toast(e.message || String(e), "err");
async function copy(text, ok = "کپی شد.") {
  try { await navigator.clipboard.writeText(text); toast(ok, "ok"); } catch { toast("متن را انتخاب و کپی کنید.", "err"); }
}
function waNumber(n) {
  const d = String(n || "").replace(/[۰-۹]/g, (c) => "۰۱۲۳۴۵۶۷۸۹".indexOf(c)).replace(/\D/g, "");
  return d.startsWith("00") ? d.slice(2) : d.startsWith("0") ? "98" + d.slice(1) : d;
}
const chip = (st) => `<span class="chip ${STATE[st][0]}">${STATE[st][1]}</span>`;
const validity = (l) => l.expires ? `یک‌ساله تا ${fa(l.expires_j)}` : "نامحدود";

/** پیامی که همراه مجوز برای مشتری فرستاده می‌شود. */
function customerMessage(l) {
  return [`مجوز «ثبت ویس» — ${l.customer}`, `اشتراک: ${validity(l)}`, "",
    "برای فعال‌سازی: در برنامه دکمه «فعال‌سازی» (یا تنظیمات ← اشتراک) را بزنید، متن زیر را در بخش «وارد کردن مجوز» بچسبانید و «فعال‌سازی» را بزنید:",
    "", l.text].join("\n");
}
function reminderMessage(l) {
  return l.days_left < 0
    ? `سلام ${l.customer}، اشتراک «ثبت ویس» شما از ${fa(l.expires_j)} تمام شده است. برای تمدید با من در تماس باشید.`
    : `سلام ${l.customer}، اشتراک «ثبت ویس» شما ${fa(l.days_left)} روز دیگر (${fa(l.expires_j)}) تمام می‌شود. برای تمدید با من در تماس باشید.`;
}
/** دکمه‌های ارسال یک مجوز: کپی متن، کپی پیام کامل، دانلود فایل، واتس‌اپ مشتری. */
function shareButtons(l) {
  return `<button class="btn sm" data-copytext="${l.id}">کپی متن مجوز</button>
    <button class="btn sm" data-copymsg="${l.id}">کپی پیام کامل</button>
    <a class="btn sm" href="/api/licenses/${l.id}/file">دانلود فایل</a>
    ${l.phone ? `<a class="btn sm" target="_blank" rel="noopener" href="https://wa.me/${waNumber(l.phone)}?text=${encodeURIComponent(customerMessage(l))}">ارسال در واتس‌اپ</a>` : ""}`;
}
function bindShare(box, licenses) {
  const byId = Object.fromEntries(licenses.map((l) => [l.id, l]));
  $$("[data-copytext]", box).forEach((b) => b.onclick = () => copy(byId[b.dataset.copytext].text, "متن مجوز کپی شد."));
  $$("[data-copymsg]", box).forEach((b) => b.onclick = () => copy(customerMessage(byId[b.dataset.copymsg]), "پیام کامل کپی شد."));
}

async function drawTop() {
  const o = await api("/api/overview");
  $("#sub").textContent = `نسخه برنامه ${fa(o.version)} — اطلاعات این پنل و کلیدها: ${o.keys_dir}`;
  const alerts = [];
  if (!o.key_ok) alerts.push(`<div class="alert err"><div class="alert-body"><b>کلید امضا در دسترس نیست</b>${esc(o.key_error)}</div></div>`);
  if (!o.contact.phone && !o.contact.telegram && !o.contact.whatsapp)
    alerts.push(`<div class="alert warn"><div class="alert-body"><b>راه تماس شما هنوز وارد نشده</b>در زبانه «تنظیمات» شماره تلفن، تلگرام و واتس‌اپ خود را وارد کنید تا در صفحه فعال‌سازی برنامه مشتری نمایش داده شود.</div></div>`);
  $("#alerts").innerHTML = alerts.join("");
  $("#stats").innerHTML = [["مشتری", fa(o.customers)], ["اشتراک یک‌ساله فعال", fa(o.active)], ["نامحدود", fa(o.forever)],
    ["تا ۳۰ روز تمام می‌شود", fa(o.soon)], ["تمام‌شده", fa(o.lapsed)], ["جمع دریافتی", money(o.paid)]]
    .map(([l, v]) => `<div class="card stat-box"><span class="muted small">${l}</span><b>${v}</b></div>`).join("");
  return o;
}

// ---------- صدور مجوز ----------
function parseRequest(text) {
  const t = String(text || "").toUpperCase().replace(/[۰-۹]/g, (c) => "۰۱۲۳۴۵۶۷۸۹".indexOf(c));
  const code = (t.match(/[A-Z2-7]{4}(?:-[A-Z2-7]{4}){3}/) || [""])[0];
  const line = (k) => { const m = String(text || "").match(new RegExp(k + "\\s*[:：]\\s*(.+)")); return m && m[1].trim() !== "—" ? m[1].trim() : ""; };
  return { code, name: line("نام"), phone: line("تلفن") };
}
function drawIssue(box) {
  box.innerHTML = `<div class="stack" style="max-width:720px">
    <label class="stack" style="gap:6px">پیامی که مشتری از برنامه فرستاده را اینجا بچسبانید (نام، تلفن و کد رایانه خودکار پر می‌شوند):
      <textarea class="input" id="i-msg" rows="5" placeholder="درخواست اشتراک «ثبت ویس»&#10;نام: ...&#10;تلفن: ...&#10;کد رایانه: ABCD-EFGH-IJKL-MNOP"></textarea></label>
    <div class="row"><input class="input" id="i-name" placeholder="نام مشتری یا شرکت" style="max-width:260px">
      <input class="input" dir="auto" id="i-phone" placeholder="تلفن مشتری" style="max-width:180px">
      <input class="input ltr" id="i-code" placeholder="ABCD-EFGH-IJKL-MNOP" style="max-width:240px"></div>
    <div class="row">
      <label class="check"><input type="radio" name="i-kind" value="year" checked> یک‌ساله</label>
      <label class="check"><input type="radio" name="i-kind" value="forever"> نامحدود</label>
      <input class="input" dir="auto" id="i-amount" type="number" min="0" step="1000" placeholder="مبلغ (تومان)" style="max-width:200px">
      <input class="input" id="i-note" placeholder="یادداشت (اختیاری)" style="max-width:240px"></div>
    <div class="row"><button class="btn primary" id="i-go">صدور مجوز</button></div>
    <div id="i-result"></div></div>`;
  $("#i-msg").oninput = () => {
    const r = parseRequest($("#i-msg").value);
    if (r.code) $("#i-code").value = r.code;
    if (r.name) $("#i-name").value = r.name;
    if (r.phone) $("#i-phone").value = r.phone;
  };
  $("#i-go").onclick = async () => {
    try {
      const l = await api("/api/issue", { method: "POST", body: {
        name: $("#i-name").value, phone: $("#i-phone").value, machine: $("#i-code").value,
        kind: $("input[name=i-kind]:checked").value, amount: +$("#i-amount").value || 0, note: $("#i-note").value } });
      $("#i-result").innerHTML = `<div class="alert ok"><div class="alert-body"><b>مجوز صادر شد</b>${esc(l.customer)} — ${validity(l)} — رایانه <span class="ltr">${esc(l.machine)}</span></div></div>
        <div class="stack" style="margin-top:10px"><textarea class="input ltr" rows="3" readonly>${esc(l.text)}</textarea>
        <div class="row">${shareButtons(l)}</div>
        <div class="muted small">پیام کامل را (همراه توضیح فعال‌سازی) برای مشتری بفرستید؛ یا فقط فایل مجوز را. نسخه فایل در پوشه licenses هم ذخیره شد.</div></div>`;
      bindShare($("#i-result"), [l]);
      drawTop();
    } catch (e) { toastErr(e); }
  };
}

// ---------- مشتری‌ها ----------
async function renewFlow(lid, kind) {
  const amount = prompt(kind === "forever" ? "تبدیل به نامحدود — مبلغ دریافتی (تومان، اختیاری):" : "تمدید یک‌ساله — مبلغ دریافتی (تومان، اختیاری):", "");
  if (amount === null) return null;
  const l = await api(`/api/licenses/${lid}/renew`, { method: "POST", body: { kind, amount: +String(amount).replace(/[^\d]/g, "") || 0 } });
  toast(`مجوز تازه صادر شد: ${validity(l)}`, "ok");
  return l;
}
function machineRows(c) {
  return c.machines.map((m) => `<div class="row" style="margin:6px 0">
      <span class="ltr">${esc(m.machine)}</span> ${chip(m.state)}
      <span class="small">${m.expires ? `تا ${fa(m.expires_j)}${m.days_left >= 0 ? ` (${fa(m.days_left)} روز)` : ""}` : "نامحدود"}</span>
      <button class="btn sm" data-renew="${m.id}" data-kind="year">تمدید یک‌ساله</button>
      ${m.expires ? `<button class="btn sm" data-renew="${m.id}" data-kind="forever">نامحدود کردن</button>` : ""}
      ${shareButtons(m)}</div>`).join("") || '<div class="muted small">مجوزی ندارد.</div>';
}
async function drawCustomers(box, query = "") {
  const { customers } = await api(`/api/customers?q=${encodeURIComponent(query)}`);
  const best = (c) => ["lapsed", "soon", "active", "forever"].find((s) => c.machines.some((m) => m.state === s));
  box.innerHTML = `<div class="row" style="margin-bottom:12px"><input class="input" id="c-q" placeholder="جست‌وجوی نام یا تلفن" value="${esc(query)}" style="max-width:260px"></div>
    ${customers.length ? `<div class="table-wrap"><table class="table"><thead><tr><th>مشتری</th><th>تلفن</th><th>رایانه</th><th>وضعیت</th><th>جمع دریافتی</th><th></th></tr></thead><tbody>
      ${customers.map((c) => `<tr><td><b>${esc(c.name)}</b></td><td class="ltr">${esc(c.phone)}</td><td>${fa(c.machines.length)}</td>
        <td>${best(c) ? chip(best(c)) : "—"}</td><td class="small">${money(c.paid)}</td>
        <td><button class="btn sm" data-open="${c.id}">جزئیات</button></td></tr>
        <tr class="details" data-for="${c.id}" hidden><td colspan="6"><div class="stack">
          <div class="row"><input class="input" data-f="name" value="${esc(c.name)}" style="max-width:220px">
            <input class="input ltr" data-f="phone" value="${esc(c.phone)}" placeholder="تلفن" style="max-width:160px">
            <input class="input" data-f="notes" value="${esc(c.notes)}" placeholder="یادداشت" style="max-width:280px">
            <button class="btn sm" data-save="${c.id}">ذخیره</button></div>
          <div><b class="small">رایانه‌ها (آخرین مجوز هر رایانه)</b>${machineRows(c)}</div>
          <details><summary class="small">همه مجوزهای صادرشده (${fa(c.licenses.length)})</summary><ul class="small">
            ${c.licenses.map((l) => `<li>${fa(l.issued_j)} — <span class="ltr">${esc(l.machine)}</span> — ${validity(l)} — ${money(l.amount)}${l.note ? ` — ${esc(l.note)}` : ""}</li>`).join("")}</ul></details>
        </div></td></tr>`).join("")}</tbody></table></div>`
      : '<div class="muted">هنوز مشتری‌ای ثبت نشده است.</div>'}`;
  const q = $("#c-q");
  q.onchange = () => drawCustomers(box, q.value);
  $$("[data-open]", box).forEach((b) => b.onclick = () => { const r = $(`[data-for="${b.dataset.open}"]`, box); r.hidden = !r.hidden; });
  $$("[data-save]", box).forEach((b) => b.onclick = async () => {
    const row = $(`[data-for="${b.dataset.save}"]`, box);
    const v = (f) => $(`[data-f="${f}"]`, row).value;
    try { await api(`/api/customers/${b.dataset.save}`, { method: "PUT", body: { name: v("name"), phone: v("phone"), notes: v("notes") } }); toast("ذخیره شد.", "ok"); drawCustomers(box, q.value); }
    catch (e) { toastErr(e); }
  });
  $$("[data-renew]", box).forEach((b) => b.onclick = async () => {
    try { if (await renewFlow(b.dataset.renew, b.dataset.kind)) { await drawCustomers(box, q.value); drawTop(); } } catch (e) { toastErr(e); }
  });
  bindShare(box, customers.flatMap((c) => c.machines));
}

// ---------- تمدیدهای نزدیک ----------
async function drawDue(box) {
  const { licenses } = await api("/api/due");
  box.innerHTML = licenses.length ? `<div class="muted small" style="margin-bottom:10px">اشتراک‌هایی که تا ۳۰ روز دیگر تمام می‌شوند یا تمام شده‌اند و هنوز تمدید نشده‌اند.</div>
    <div class="table-wrap"><table class="table"><thead><tr><th>مشتری</th><th>رایانه</th><th>پایان</th><th>وضعیت</th><th></th></tr></thead><tbody>
    ${licenses.map((l) => `<tr><td><b>${esc(l.customer)}</b> <span class="ltr small">${esc(l.phone)}</span></td><td class="ltr small">${esc(l.machine)}</td>
      <td>${fa(l.expires_j)} <span class="small muted">(${l.days_left < 0 ? `${fa(-l.days_left)} روز گذشته` : `${fa(l.days_left)} روز مانده`})</span></td><td>${chip(l.state)}</td>
      <td class="actions">${l.phone ? `<a class="btn sm" target="_blank" rel="noopener" href="https://wa.me/${waNumber(l.phone)}?text=${encodeURIComponent(reminderMessage(l))}">یادآوری در واتس‌اپ</a>` : ""}
        <button class="btn sm" data-remind="${l.id}">کپی یادآوری</button>
        <button class="btn sm primary" data-renew="${l.id}">تمدید یک‌ساله</button></td></tr>`).join("")}</tbody></table></div>`
    : '<div class="muted">اشتراکی نزدیک به پایان نیست.</div>';
  const byId = Object.fromEntries(licenses.map((l) => [l.id, l]));
  $$("[data-remind]", box).forEach((b) => b.onclick = () => copy(reminderMessage(byId[b.dataset.remind]), "پیام یادآوری کپی شد."));
  $$("[data-renew]", box).forEach((b) => b.onclick = async () => {
    try { const l = await renewFlow(b.dataset.renew, "year"); if (l) { drawTop(); tab = "customers"; draw(); } } catch (e) { toastErr(e); }
  });
}

// ---------- تنظیمات ----------
async function drawSettings(box) {
  const o = await api("/api/overview");
  const C = o.contact;
  box.innerHTML = `<div class="stack" style="max-width:640px">
    <b>راه‌های تماس شما (در صفحه فعال‌سازی برنامه مشتری)</b>
    <div class="muted small">هر کدام خالی بماند، در برنامه مشتری نمایش داده نمی‌شود. تغییرات در بسته کامل یا به‌روزرسانی بعدی که می‌سازید قرار می‌گیرد.</div>
    <div class="row"><input class="input" id="s-name" placeholder="نام شما یا نام فروشنده" value="${esc(C.name)}" style="max-width:240px">
      <input class="input" dir="auto" id="s-phone" placeholder="تلفن (مثلاً ۰۹۱۲…)" value="${esc(C.phone)}" style="max-width:220px"></div>
    <div class="row"><input class="input" dir="auto" id="s-tg" placeholder="آیدی تلگرام (بدون @)" value="${esc(C.telegram)}" style="max-width:240px">
      <input class="input" dir="auto" id="s-wa" placeholder="شماره واتس‌اپ" value="${esc(C.whatsapp)}" style="max-width:220px"></div>
    <div class="row"><button class="btn primary" id="s-save">ذخیره</button></div>
    <hr style="width:100%;border:0;border-top:1px solid var(--border)">
    <b>نگهداری</b>
    <div class="small">اطلاعات این پنل (مشتری‌ها و مجوزها) و کلیدهای امضا در این پوشه است: <span class="ltr">${esc(o.keys_dir)}</span><br>
      از این پوشه هر چند وقت یک نسخه روی فلش جداگانه بگیرید. بدون کلید امضا، صدور یا تمدید مجوز ممکن نیست.</div>
  </div>`;
  $("#s-save").onclick = async () => {
    try {
      await api("/api/contact", { method: "PUT", body: { name: $("#s-name").value, phone: $("#s-phone").value, telegram: $("#s-tg").value, whatsapp: $("#s-wa").value } });
      toast("ذخیره شد؛ در بسته یا به‌روزرسانی بعدی قرار می‌گیرد.", "ok"); drawTop();
    } catch (e) { toastErr(e); }
  };
}

function draw() {
  $$("#tabs [data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const box = $("#tab");
  const fn = { issue: drawIssue, customers: drawCustomers, due: drawDue, settings: drawSettings }[tab];
  Promise.resolve(fn(box)).catch(toastErr);
}
$$("#tabs [data-tab]").forEach((b) => b.onclick = () => { tab = b.dataset.tab; history.replaceState(null, "", "#" + tab); draw(); });
drawTop().catch(toastErr);
draw();
