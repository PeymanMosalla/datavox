"""ساخت فایل داده پایه نشانی‌های شهر (voice2excel/assets/geo.dat).

منابع:
- نام خیابان‌های OpenStreetMap (© OpenStreetMap contributors، مجوز ODbL)؛ دریافت یک‌باره با Overpass:
    [out:csv(name,highway;false;"\\t")];area(3605725142)->.a;way(area.a)["highway"]["name"];out tags;
  (3605725142 = محدوده «شهر مشهد»)
- ستون آدرس فایل‌های اکسل شرکت (فقط نام خیابان‌ها؛ هیچ نام شخص، شماره یا آدرس کاملی وارد نمی‌شود).

استفاده:
    .venv\\Scripts\\python.exe scripts\\build_geo.py --osm packaging\\cache\\osm-mashhad.csv --excel a.xlsx b.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for s in (sys.stdout, sys.stderr):
    s.reconfigure(encoding="utf-8")

from voice2excel import geo, knowledge  # noqa: E402
from voice2excel.lexicon import _common_keys  # noqa: E402
from voice2excel.normalizer import normalize_text, sound_key, to_ascii_digits  # noqa: E402

EXCEL_WEIGHT = 3  # املای فایل شرکت بر املای نقشه مقدم است


def osm_names(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("\t")[0].strip()
        if name:
            out.append(to_ascii_digits(normalize_text(name)))
    return out


def excel_addresses(path: Path) -> list:
    info = knowledge.analyze_workbook(path)
    sheet = next(s for s in info["sheets"] if s["name"] == info["sheet"])
    roles = {c: r for c, r in sheet["roles"].items() if r == "address"}
    if not roles:
        raise SystemExit(f"ستون آدرس در «{path.name}» پیدا نشد.")
    values, _ = knowledge.read_columns(path, sheet["name"], sheet["header_row"], roles)
    return values.get("address", [])


def build(osm: Path | None, excels: list[Path], min_osm: int) -> list[list]:
    h = knowledge.Harvest()
    from_excel: set[str] = set()
    for p in excels:
        for v in excel_addresses(p):
            for st in knowledge.streets_from_address(v):
                for _ in range(EXCEL_WEIGHT):
                    h.add("street", st.canonical, st.aliases)
                from_excel.add(sound_key(st.canonical))
    if osm:
        for name in osm_names(osm):
            for st in knowledge.streets_from_address(name):
                h.add("street", st.canonical, st.aliases)
    common = _common_keys()
    out = []
    for key, g in h.groups["street"].items():
        if len(key) < 3 or key in common:
            continue
        if key not in from_excel and g.count < min_osm:
            continue  # نامی که در نقشه فقط یک بار آمده، معمولاً کوچه یا مکان جزئی است
        out.append([g.canonical, sorted(g.names() - {g.canonical}), g.count])
    out.sort(key=lambda s: -s[2])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", type=Path)
    ap.add_argument("--excel", type=Path, nargs="*", default=[])
    ap.add_argument("--min-osm", type=int, default=2, help="کمینه تکرار نام در نقشه")
    ap.add_argument("--city", default="مشهد")
    ap.add_argument("--out", type=Path, default=ROOT / "voice2excel" / "assets" / "geo.dat")
    a = ap.parse_args()
    streets = build(a.osm, a.excel, a.min_osm)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(geo.encode({"v": 1, "city": a.city, "s": streets}))
    print(f"{len(streets)} خیابان ← {a.out} ({a.out.stat().st_size // 1024} کیلوبایت)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
