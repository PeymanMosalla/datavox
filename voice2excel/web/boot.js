// این فایل عمداً با جاوااسکریپت قدیمی (ES5) نوشته شده تا در هر مرورگری، حتی Internet Explorer، اجرا شود.
// تم انتخابی کاربر پیش از نمایش صفحه اعمال می‌شود (بدون چشمک زدن رنگ)
try { var t = localStorage.getItem("v2x.theme"); if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t); } catch (e) { }
// منوی ساده («کار امروز» و «تنظیمات»)؛ همه صفحه‌ها فقط اگر کاربر در تنظیمات خواسته باشد
try { if (localStorage.getItem("v2x.nav") === "full") document.documentElement.className += " full-nav"; } catch (e) { }
// داخل پنجره اختصاصی DataVox.exe: نوار عنوان خود برنامه (به‌جای قاب ویندوز یا مرورگر)
try { if (window.chrome && window.chrome.webview) document.documentElement.className += " in-app"; } catch (e) { }

// اگر صفحه کامل بالا نیاید (مرورگر قدیمی، فایل مسدودشده، خطای کد)، به‌جای صفحه خالی پیام روشن نشان داده می‌شود.
// app.js پس از راه‌اندازی کامل window.__v2xReady را true می‌کند.
(function () {
  var errors = [];
  window.__v2xErrors = errors;
  try {
    window.addEventListener("error", function (e) {
      var el = e && e.target;
      if (el && el !== window && (el.src || el.href)) errors.push("بارگذاری نشد: " + (el.src || el.href));
      else if (e) errors.push((e.message || "خطا") + (e.filename ? " (" + String(e.filename).split("/").pop() + ":" + e.lineno + ")" : ""));
    }, true);
    window.addEventListener("unhandledrejection", function (e) {
      var r = e && e.reason;
      errors.push("خطا: " + (r && r.message ? r.message : String(r)));
    });
  } catch (e) { }

  // modern.js (پس از همین فایل) فقط در مرورگری اجرا می‌شود که نحو app.js را بشناسد
  var modern = true;

  // دکمه‌های پنجره (کوچک، بزرگ، بستن) حتی اگر بقیه کد صفحه اجرا نشود کار کنند
  function windowButtons() {
    var wv = window.chrome && window.chrome.webview;
    if (!wv) return;
    var btns = document.querySelectorAll("[data-win]");
    for (var i = 0; i < btns.length; i++) {
      (function (b) { if (!b.onclick) b.onclick = function () { wv.postMessage(b.getAttribute("data-win")); }; })(btns[i]);
    }
  }

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function show() {
    if (window.__v2xReady || document.getElementById("v2x-boot-error")) return;
    var url = location.protocol + "//" + location.host + "/";
    var inApp = !!(window.chrome && window.chrome.webview);
    var title, body;
    if (!modern) {
      title = "این مرورگر برای DataVox قدیمی است";
      body = "برنامه در مرورگری باز شده که نمی‌تواند آن را اجرا کند (مثل Internet Explorer یا نسخه قدیمی Edge)."
        + "<br><br><b>راه حل:</b> این نشانی را در Google Chrome، Microsoft Edge جدید یا Firefox باز کنید:"
        + "<div style='direction:ltr;text-align:left;font:15px Consolas,monospace;background:#eef3f8;padding:8px 12px;border-radius:6px;margin:8px 0'>" + esc(url) + "</div>"
        + "اگر Chrome، Edge یا Firefox نصب کنید، DataVox از این به بعد خودش آن را به‌کار می‌برد."
        + " بهترین حالت: «Microsoft Edge WebView2 Runtime» را نصب کنید تا DataVox در پنجره اختصاصی خودش باز شود.";
    } else {
      title = "صفحه برنامه کامل بارگذاری نشد";
      body = "یک بار برنامه را کامل ببندید و دوباره باز کنید. اگر دوباره همین پیام آمد، متن زیر را برای پشتیبانی بفرستید."
        + "<br>اگر برنامه آنتی‌ویروس دارید، پوشه برنامه را در فهرست مجاز آن بگذارید.";
    }
    var details = "نسخه مرورگر: " + navigator.userAgent + (inApp ? " (پنجره برنامه)" : "")
      + (errors.length ? "\n" + errors.slice(0, 8).join("\n") : "");
    var box = document.createElement("div");
    box.id = "v2x-boot-error";
    box.setAttribute("dir", "rtl");
    box.style.cssText = "position:fixed;left:0;right:0;bottom:0;top:" + (inApp ? "36px" : "0") + ";z-index:2147483647;background:#f4f6fb;"
      + "color:#17202e;font:15px/1.9 Tahoma,'Segoe UI',sans-serif;overflow:auto;padding:40px 16px";
    box.innerHTML = "<div style='max-width:680px;margin:0 auto;background:#fff;border:1px solid #dfe5ee;border-radius:10px;padding:24px 28px'>"
      + "<div style='font-size:20px;font-weight:bold;color:#b3261e;margin-bottom:10px'>" + esc(title) + "</div>"
      + "<div>" + body + "</div>"
      + "<pre style='direction:ltr;text-align:left;white-space:pre-wrap;font:12px Consolas,monospace;background:#f4f6fb;border-radius:6px;padding:10px;margin-top:16px'>"
      + esc(details) + "</pre>"
      + "<button id='v2x-boot-retry' style='font:15px Tahoma,sans-serif;padding:7px 22px;margin-top:8px;cursor:pointer;"
      + "background:#138a52;color:#fff;border:0;border-radius:6px'>تلاش دوباره</button></div>";
    document.body.appendChild(box);
    document.getElementById("v2x-boot-retry").onclick = function () { location.reload(); };
  }

  function onReady() {
    windowButtons();
    modern = window.__v2xModern === true;
    if (!modern) show();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", onReady);
  else onReady();
  // راه‌اندازی صفحه معمولاً کمتر از یک ثانیه طول می‌کشد؛ ۱۵ ثانیه یعنی چیزی درست کار نکرده است
  window.addEventListener("load", function () { setTimeout(show, 15000); });
})();
