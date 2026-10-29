# شاخه windows7-only — فقط نسخه ویندوز ۷

این شاخه **فقط** برای ساخت و نگهداری بسته DataVox ویژه ویندوز ۷ (۶۴ بیتی، SP1) است.
بسته ویندوز ۱۰ و ۱۱ همیشه از شاخه `main` ساخته می‌شود و این شاخه هرگز در `main` ادغام نمی‌شود.

## نام‌گذاری
- شماره نسخه همان نسخه `main` است که این شاخه بر پایه آن ساخته شده (مثلاً 2.6.0).
- بسته کامل: `dist/DataVox-<نسخه>-win7.zip` — به‌روزرسانی: `dist/DataVox-update-<نسخه>-win7.zip`
- برچسب گیت و انتشار: `v<نسخه>-win7` (هرگز به‌عنوان «آخرین انتشار» علامت نمی‌خورد)

## تفاوت با main
- Python 3.12 وصله‌شده برای ویندوز ۷ (PythonVista، با چکیده sha256 ثابت)
- `requirements-win7.txt`: pydantic 2.10.6، tokenizers 0.19.1، av 18.0.0؛ بدون onnxruntime و hf_xet
- VAD با numpy (`voice2excel/vad_numpy.py`) با خروجی یکسان با onnxruntime
- Visual C++ 14.44 (نسخه 14.5x به ویندوز ۸ به بعد نیاز دارد)
- اجراکننده روی ویندوز ۷ به‌جای WebView2، پنجره Edge/Chrome (یا Firefox) باز می‌کند و پیش‌نیازها را بررسی می‌کند
- پوشه `Windows7` در بسته: به‌روزرسانی‌های رسمی KB3063858 و KB2999226، ‎.NET 4.8، Firefox ESR 115 فارسی،
  `Install-Prerequisites.bat` و راهنمای فارسی

## ساخت
```
.venv\Scripts\python.exe scripts\build_portable.py     # همیشه بسته ویندوز ۷
.venv\Scripts\python.exe scripts\build_update.py       # همیشه به‌روزرسانی ویندوز ۷
```
هر DLL بسته با `scripts/win7_check.py` بررسی می‌شود؛ هر ناسازگاری ساخت را متوقف می‌کند.
آزمون‌ها با کتابخانه‌های ویندوز ۷: محیط `.venv-win7` (بدون onnxruntime).

## آوردن تغییرات تازه از main
```
git checkout windows7-only
git merge main
```
سپس `requirements-win7.txt` را با `requirements.txt` مقایسه کنید؛ هر کتابخانه تازه باید پیش از ساخت با
`scripts/win7_check.py` بررسی شود.
