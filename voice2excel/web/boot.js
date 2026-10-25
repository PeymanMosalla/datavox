// تم انتخابی کاربر پیش از نمایش صفحه اعمال می‌شود (بدون چشمک زدن رنگ)
try { const t = localStorage.getItem("v2x.theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) { }
// منوی ساده («کار امروز» و «تنظیمات»)؛ همه صفحه‌ها فقط اگر کاربر در تنظیمات خواسته باشد
try { if (localStorage.getItem("v2x.nav") === "full") document.documentElement.classList.add("full-nav"); } catch (e) { }
