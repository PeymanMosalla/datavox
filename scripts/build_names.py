"""ساخت فهرست نام‌ها و نام‌خانوادگی‌های رایج (packaging/names) از داده‌های باز؛ سپس scripts/build_geo.py آن‌ها را در
voice2excel/assets/geo.dat می‌گذارد. واژه‌نامه پایه برای یکسان کردن املای هم‌آوا («کازمی» ← «کاظمی») به کار می‌رود.

منابع (یک بار دریافت و در packaging/cache/names نگه داشته می‌شوند؛ در مخزن نیستند):
- نام‌خانوادگی: farbodbj/iranian-surname-frequencies (Apache-2.0)، بیش از ۱۰۰ هزار نام با بسامد از ۱۰ میلیون رکورد
    https://raw.githubusercontent.com/farbodbj/iranian-surname-frequencies/github-master/iranian-surname-frequencies.csv
- نام کوچک: nabidam/persian-names (MIT)، ۸۸۱۶ نام به ترتیب رواج
    https://raw.githubusercontent.com/nabidam/persian-names/master/names.json

چرا ۵۰۰۰ نام‌خانوادگی (سنجش ۱۴۰۵/۰۸/۲۱ روی فامیل مهندس‌های فایل‌های اکسل شرکت، ۲۹۲ فامیل متفاوت):
۴۶۴ نام قبلی ۴۸٪ را پوشش می‌داد، ۵۰۰۰ نام ۷۸٪ و ۱۰۰۰۰ نام ۸۲٪؛ ولی کلیدهای هم‌آوای چندگزینه‌ای (که یکسان‌سازی
خودکار ندارند) از ۱۳۹ به ۳۱۵ می‌رسید. پس از ۵۰۰۰، سود کم و ابهام زیاد است.

    python scripts/build_names.py [--surnames 5000] [--first 2000]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from voice2excel.normalizer import normalize_text, strip_title  # noqa: E402

CACHE = ROOT / "packaging" / "cache" / "names"
OUT = ROOT / "packaging" / "names"
PERSIAN = re.compile(r"[آ-ی‌ ]+")


def clean(name: str) -> str | None:
    n = normalize_text(str(name or "")).strip().replace("ك", "ک").replace("ي", "ی")
    n = re.sub(r"\s+", " ", n)
    if len(n.replace(" ", "").replace("‌", "")) < 3 or not PERSIAN.fullmatch(n):
        return None
    # «حاجی پور»: برنامه «حاجی/حاج» را عنوان می‌داند؛ با فاصله، کلید آن «پور» می‌شد و هر «…پور» را می‌گرفت
    if strip_title(n)[0]:
        n = re.sub(r"^(\S+)\s+", r"\1‌", n, count=1)
        if strip_title(n)[0]:
            return None
    return n


def read_current(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surnames", type=int, default=5000)
    ap.add_argument("--first", type=int, default=2000)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    rows = []
    with open(CACHE / "iranian-surname-frequencies.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["name"], float(r["frequency"])))
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda x: -x[1])
    surnames: list[str] = []
    seen: set[str] = set()
    for n in read_current(OUT / "surnames.txt"):  # فهرست قبلی (دست‌چین) همیشه می‌ماند
        if n not in seen:
            seen.add(n); surnames.append(n)
    taken = 0
    for raw, _ in rows:
        if taken >= a.surnames:
            break
        n = clean(raw)
        if n and n not in seen:
            seen.add(n); surnames.append(n)
        if n:
            taken += 1

    given = json.loads((CACHE / "names.json").read_text(encoding="utf-8"))
    first: list[str] = []
    seen = set()
    for n in read_current(OUT / "firstnames.txt"):
        if n not in seen:
            seen.add(n); first.append(n)
    taken = 0
    for raw in given:  # ترتیب فایل = ترتیب رواج
        if taken >= a.first:
            break
        n = clean(raw)
        if n and n not in seen:
            seen.add(n); first.append(n)
        if n:
            taken += 1

    (OUT / "surnames.txt").write_text(
        "# نام‌خانوادگی‌های رایج ایرانی (دانش عمومی و داده باز farbodbj/iranian-surname-frequencies، Apache-2.0؛"
        " بدون هیچ داده مشتری). هر خط یک نام. ساخته‌شده با scripts/build_names.py\n" + "\n".join(surnames) + "\n",
        encoding="utf-8")
    (OUT / "firstnames.txt").write_text(
        "# نام‌های کوچک رایج ایرانی (دانش عمومی و داده باز nabidam/persian-names، MIT؛ بدون هیچ داده مشتری)."
        " هر خط یک نام. ساخته‌شده با scripts/build_names.py\n" + "\n".join(first) + "\n", encoding="utf-8")
    print(f"{len(surnames)} نام‌خانوادگی، {len(first)} نام کوچک ← {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
