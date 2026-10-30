"""پیش از هر commit: هیچ شماره تلفنی از فایل اکسل شرکت نباید در فایل‌های مخزن (کد، آزمون، نمونه) باشد.

شماره‌ها از فایل(های) اکسل شرکت خوانده می‌شوند (فقط خواندن؛ چیزی ذخیره یا چاپ نمی‌شود جز سه رقم اول در صورت یافتن)
و در همه فایل‌هایی که گیت ثبت می‌کند یا ثبت خواهد کرد جست‌وجو می‌شوند.

استفاده (از پوشه voice2excel):
    .venv\\Scripts\\python.exe scripts\\phone_scan.py ..\\source\\*.xlsx
خروجی سالم: «… company phones checked; 0 hits» — اگر HIT دید، آن فایل را پیش از commit اصلاح کنید.
"""
import glob
import re
import subprocess
import sys
from pathlib import Path

import openpyxl

paths = [p for a in sys.argv[1:] for p in glob.glob(a)] or glob.glob(str(Path("..") / "source" / "*.xlsx"))
if not paths:
    raise SystemExit("فایل اکسل شرکت پیدا نشد؛ مسیر را بدهید، مثلاً: ..\\source\\*.xlsx")
phones = set()
for f in paths:
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for v in row:
                for m in re.findall(r"\d[\d\- ]{8,}\d", str(v or "")):
                    d = re.sub(r"\D", "", m)
                    if len(d) >= 10:
                        phones.add(d[-10:])
files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True).stdout.split("\n")
hits = 0
for f in filter(None, files):
    p = Path(f)
    if p.suffix in (".mp3", ".woff2", ".ico", ".png") or not p.is_file():
        continue
    t = re.sub(r"\D", "", p.read_text(encoding="utf-8", errors="ignore"))
    for ph in phones:
        if ph in t:
            hits += 1
            print("HIT", f, ph[:3] + "****")
print(len(phones), "company phones checked;", hits, "hits")
sys.exit(1 if hits else 0)
