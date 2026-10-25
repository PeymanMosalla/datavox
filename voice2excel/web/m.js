"use strict";
const $ = (s) => document.querySelector(s);
const fa = (n) => String(n ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = { get: (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { } }, del: (k) => { try { localStorage.removeItem(k); } catch { } } };
const STATUS = { queued: ["info", "در صف"], processing: ["warn", "در حال پردازش"], done: ["ok", "پردازش شد"], failed: ["err", "ناموفق"] };
let picked = [];

store.del("v2x.m.pin");  // نسخه‌های قبلی خود رمز را روی گوشی نگه می‌داشتند
const LOST = "این گوشی دیگر وصل نیست (رمز عوض شده یا از فهرست برداشته شده)؛ دوباره رمز را وارد کنید.";
async function call(path, opt = {}) {
  const res = await fetch(path, { ...opt, headers: { ...(opt.headers || {}), "X-Device": store.get("v2x.m.dev") } });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { store.del("v2x.m.dev"); showLogin(LOST); throw new Error("401"); }
  if (!res.ok) throw new Error(data.detail || "خطا در ارتباط با برنامه.");
  return data;
}
function showLogin(err) {
  $("#app").hidden = true; $("#login").hidden = false;
  $("#sender-l").value = store.get("v2x.m.sender");
  $("#login-err").hidden = !err; $("#login-err").textContent = err || "";
}
async function showApp() {
  const info = await call("/api/m/check", { method: "POST" });
  $("#login").hidden = true; $("#app").hidden = false;
  $("#sender").value = info.name;
  $("#sender").readOnly = true;  // نام همین گوشی که هنگام ورود ثبت شد
  $("#date").value = info.today;
  loadRecent();
}
$("#login-btn").onclick = async () => {
  const pin = $("#pin").value.replace(/\D/g, "");
  if (pin.length !== 6) return showLogin("رمز باید شش رقم باشد.");
  const name = $("#sender-l").value.trim();
  if (!name) return showLogin("نام خود را بنویسید.");
  store.set("v2x.m.sender", name);
  try {
    const res = await fetch("/api/m/login", { method: "POST", headers: { "X-PIN": pin, "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) return showLogin(res.status === 401 ? "رمز نادرست است." : d.detail || "ورود ناموفق بود.");
    store.set("v2x.m.dev", d.token);
    $("#pin").value = "";
    await showApp();
  } catch (e) { if (e.message !== "401") showLogin(e.message || "ارتباط با رایانه دفتر برقرار نشد."); }
};
$("#logout").onclick = (e) => { e.preventDefault(); store.del("v2x.m.dev"); showLogin(); };
$("#pick-btn").onclick = () => $("#pick").click();
$("#pick").onchange = (e) => {
  picked = picked.concat(Array.from(e.target.files));
  e.target.value = "";
  drawPicked();
};
function drawPicked() {
  $("#picked").innerHTML = picked.map((f, i) => `<li><span class="n">${esc(f.name)}</span><span class="muted">${fa(Math.round(f.size / 1024))} KB</span>
    <button class="chip err" data-rm="${i}" style="border:none">حذف</button></li>`).join("");
  document.querySelectorAll("[data-rm]").forEach((b) => b.onclick = () => { picked.splice(+b.dataset.rm, 1); drawPicked(); });
  $("#send").disabled = !picked.length;
  $("#send").textContent = picked.length ? `ارسال ${fa(picked.length)} ویس` : "ارسال";
}
$("#send").onclick = () => {
  if (!picked.length) return;
  const fd = new FormData();
  picked.forEach((f) => fd.append("files", f, f.name));
  fd.append("visit_date", $("#date").value.trim());
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/m/upload");
  xhr.setRequestHeader("X-Device", store.get("v2x.m.dev"));
  $("#prog").hidden = false; $("#send").disabled = true; $("#send-msg").hidden = true;
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) { const p = Math.round(100 * e.loaded / e.total); $("#bar").style.width = p + "%"; $("#prog-t").textContent = `در حال ارسال… ${fa(p)}٪`; } };
  xhr.onload = () => {
    $("#prog").hidden = true;
    let d = {}; try { d = JSON.parse(xhr.responseText); } catch { }
    if (xhr.status === 401) { store.del("v2x.m.dev"); return showLogin(LOST); }
    const box = $("#send-msg");
    box.hidden = false;
    if (xhr.status >= 300) { box.className = "msg err"; box.textContent = d.detail || "ارسال ناموفق بود."; $("#send").disabled = false; return; }
    const added = d.results.filter((r) => r.result === "added").length;
    const others = d.results.filter((r) => r.result !== "added");
    box.className = "msg " + (others.length ? "warn" : "ok");
    box.innerHTML = `${fa(added)} ویس رسید و در صف پردازش قرار گرفت.` + others.map((r) => `<div>${esc(r.name)}: ${esc(r.message)}</div>`).join("");
    picked = []; drawPicked(); loadRecent();
  };
  xhr.onerror = () => { $("#prog").hidden = true; $("#send").disabled = false; const b = $("#send-msg"); b.hidden = false; b.className = "msg err"; b.textContent = "ارتباط با رایانه دفتر برقرار نشد. آیا به همان شبکه وای‌فای وصل هستید؟"; };
  xhr.send(fd);
};
async function loadRecent() {
  try {
    const d = await call("/api/m/recent");
    $("#recent").innerHTML = d.files.length ? d.files.map((f) => { const [c, l] = STATUS[f.status] || ["info", f.status];
      return `<li><span class="n">${esc(f.original_name)}</span><span class="chip ${c}">${l}</span></li>`; }).join("") : '<li class="muted">هنوز ویسی نفرستاده‌اید.</li>';
  } catch { }
}
setInterval(() => { if (!$("#app").hidden && !document.hidden) loadRecent(); }, 5000);
if (store.get("v2x.m.dev")) showApp().catch((e) => { if (e.message !== "401") showLogin(e.message); }); else showLogin();
