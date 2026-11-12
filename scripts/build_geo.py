"""ساخت فایل داده پایه نشانی‌های شهر (voice2excel/assets/geo.dat).

منابع:
- نام خیابان‌های OpenStreetMap (© OpenStreetMap contributors، مجوز ODbL)؛ دریافت یک‌باره با Overpass:
    [out:csv(name,highway;false;"\\t")];area(3605725142)->.a;way(area.a)["highway"]["name"];out tags;
  (3605725142 = محدوده «شهر مشهد»)
- ستون آدرس فایل‌های اکسل شرکت (فقط نام خیابان‌ها؛ هیچ نام شخص، شماره یا آدرس کاملی وارد نمی‌شود).
- مختصات خیابان‌ها (--osm-geo، از همان Overpass با «out tags center;»): برای بررسی اینکه خیابان‌های یک آدرس
  روی نقشه کنار هم‌اند (address_check.py).
- محله‌ها، میدان‌ها و چهارراه‌ها (--osm-places)؛ از Overpass:
    [out:csv(name,place,highway,junction;false;"\t")];area(3605725142)->.a;(
      node(area.a)["place"~"neighbourhood|suburb|quarter|square"]["name"];way(area.a)["place"~"neighbourhood|suburb|quarter|square"]["name"];
      relation(area.a)["place"~"neighbourhood|suburb|quarter"]["name"];way(area.a)["highway"="pedestrian"]["name"];
      node(area.a)["junction"]["name"];way(area.a)["junction"="roundabout"]["name"];);out tags;
- --keep-once: نام‌هایی که در نقشه فقط یک بار آمده‌اند هم (فقط اگر نام شخص نباشند؛ وگرنه «مهندس کریمی» با کوچه «کریمی»
  اشتباه می‌شد). املای قبلی هر خیابان همیشه حفظ می‌شود تا ساخت دوباره املاها را جابه‌جا نکند.
- آموخته‌های استفاده واقعی (--learned): پایگاه داده برنامه (voice2excel.db) یا خروجی واژه‌نامه. فقط خیابان‌ها
  با شکل‌های دیگرشان و اصلاحات تأییدشده آدرس برداشته می‌شود؛ نام اشخاص، پروژه‌ها و هر رشته عددی ۴ رقمی به بالا نه.

استفاده (پیش از هر نسخه):
    .venv\\Scripts\\python.exe scripts\\build_geo.py --osm packaging\\cache\\osm-mashhad.csv --excel ..\\source\\*.xlsx ^
        --learned dist\\Voice2Excel\\data\\voice2excel.db
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for s in (sys.stdout, sys.stderr):
    s.reconfigure(encoding="utf-8")

from voice2excel import geo, knowledge  # noqa: E402
from voice2excel.lexicon import _common_keys  # noqa: E402
from voice2excel.normalizer import normalize_text, sound_key, to_ascii_digits  # noqa: E402

# واژه‌های عمومی که در نقشه به‌جای نام می‌آیند («ناحیه ۳»، «پلیس») و نام خیابان نیستند
PLACE_STOP = {"ناحیه", "منطقه", "پلیس", "محله", "کوی", "شهرک", "پارک", "پایانه", "ایستگاه", "پاسگاه"}  # «کلانتری» نه: «بلوار کلانتری» خیابان واقعی مشهد است
EXCEL_WEIGHT = 3  # املای فایل شرکت بر املای نقشه مقدم است
MIN_CORRECTION_COUNT = 2  # اصلاحی که کاربر دست‌کم دو بار تأیید کرده (نه یک اشتباه تایپی)
_LONG_NUMBER = re.compile(r"\d{4,}")


def osm_names(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("\t")[0].strip()
        if name:
            out.append(to_ascii_digits(normalize_text(name)))
    return out


def read_list(path: Path) -> list[str]:
    """فهرست یک‌نام‌در‌هر‌خط (خط‌های # توضیح‌اند)؛ تکراری‌ها حذف."""
    names = (normalize_text(ln) for ln in path.read_text(encoding="utf-8").splitlines())
    return list(dict.fromkeys(n for n in names if n and not n.startswith("#")))


def excel_addresses(path: Path) -> list:
    info = knowledge.analyze_workbook(path)
    sheet = next(s for s in info["sheets"] if s["name"] == info["sheet"])
    roles = {c: r for c, r in sheet["roles"].items() if r == "address"}
    if not roles:
        raise SystemExit(f"ستون آدرس در «{path.name}» پیدا نشد.")
    values, _ = knowledge.read_columns(path, sheet["name"], sheet["header_row"], roles)
    return values.get("address", [])


def _safe(text) -> bool:
    return isinstance(text, str) and 1 < len(text.strip()) <= 40 and not _LONG_NUMBER.search(to_ascii_digits(text))


def learned(path: Path, password: str = "") -> tuple[list[tuple[str, list[str]]], list[tuple[str, str, int]]]:
    """(خیابان‌ها با شکل‌های دیگر، اصلاحات آدرس) از پایگاه داده برنامه یا فایل خروجی واژه‌نامه."""
    if path.suffix == ".db":
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        aliases: dict[int, list[str]] = {}
        for r in con.execute("SELECT entity_id, alias FROM aliases"):
            aliases.setdefault(r["entity_id"], []).append(r["alias"])
        streets = [(r["canonical"], aliases.get(r["id"], []))
                   for r in con.execute("SELECT id, canonical FROM entities WHERE type='street'")]
        corr = [(r["wrong"], r["right"], r["count"]) for r in con.execute(
            "SELECT wrong, right, count FROM corrections WHERE field_group='address' AND enabled=1")]
        con.close()
    else:
        from voice2excel import vault
        blob = path.read_bytes()
        if vault.is_encrypted(blob):
            if not password:
                import getpass
                password = getpass.getpass(f"گذرواژه «{path.name}»: ")
            blob = vault.decrypt(blob, password)
        data = json.loads(blob.decode("utf-8"))
        streets = [(e["c"], e.get("a") or []) for e in data.get("entities", []) if e.get("t") == "street"]
        corr = [(c["w"], c["r"], int(c.get("n") or 1)) for c in data.get("corrections", [])
                if c.get("g") == "address" and c.get("e", 1)]
    streets = [(normalize_text(c), [normalize_text(a) for a in al if _safe(a)]) for c, al in streets if _safe(c)]
    corr = [(normalize_text(w), normalize_text(r), n) for w, r, n in corr if _safe(w) and _safe(r)]
    return streets, corr


def build(osm: Path | None, excels: list[Path], min_osm: int,
          learned_streets: list[tuple[str, list[str]]] = (), places: Path | None = None,
          keep_once: bool = False, person_keys: frozenset[str] = frozenset()) -> list[list]:
    h = knowledge.Harvest()
    from_excel: set[str] = set()
    for canonical, aliases in learned_streets:  # تأییدشده در استفاده واقعی؛ هم‌وزن فایل شرکت
        for _ in range(EXCEL_WEIGHT):
            h.add("street", canonical, set(aliases))
        from_excel.add(sound_key(canonical))
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
    place_keys: set[str] = set()
    if places:  # محله، میدان، چهارراه: یک بار آمدن در نقشه کافی است (هر کدام یک گره است)
        for name in osm_names(places):
            for st in knowledge.streets_from_address(name):
                h.add("street", st.canonical, st.aliases)
                place_keys.add(sound_key(st.canonical))
    common = _common_keys() | {sound_key(w) for w in PLACE_STOP}
    out = []
    for key, g in h.groups["street"].items():
        if len(key) < 3 or key in common:
            continue
        if key not in from_excel and g.count < min_osm:
            # نامی که در نقشه فقط یک بار آمده (کوچه یا مکان جزئی) یا محله/میدان: فقط اگر نام شخص نباشد
            if not ((keep_once or key in place_keys) and key not in person_keys):
                continue
        out.append([g.canonical, sorted(g.names() - {g.canonical}), g.count])
    out.sort(key=lambda s: -s[2])
    return out


def osm_points(path: Path) -> list[list]:
    """[[نام خیابان، [[عرض، طول]، ...]]]: مرکز هر تکه از هر خیابان، با دقت حدود ۱۰ متر."""
    data = json.loads(path.read_text(encoding="utf-8"))
    pts: dict[str, list] = {}
    for e in data.get("elements", []):
        c, name = e.get("center"), (e.get("tags") or {}).get("name")
        if not c or not name:
            continue
        for st in knowledge.streets_from_address(to_ascii_digits(normalize_text(name))):
            pts.setdefault(st.canonical, []).append([round(c["lat"], 4), round(c["lon"], 4)])
    return [[n, sorted({tuple(x) for x in v})] for n, v in sorted(pts.items())]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", type=Path)
    ap.add_argument("--excel", type=Path, nargs="*", default=[])
    ap.add_argument("--min-osm", type=int, default=2, help="کمینه تکرار نام در نقشه")
    ap.add_argument("--names", type=Path, default=ROOT / "packaging" / "names",
                    help="پوشه surnames.txt و firstnames.txt (نام‌های رایج عمومی)")
    ap.add_argument("--osm-geo", type=Path, default=ROOT / "packaging" / "cache" / "osm-mashhad-geo.json",
                    help="خیابان‌ها با مختصات (اگر نباشد، مختصات نسخه فعلی می‌ماند)")
    ap.add_argument("--learned", type=Path, nargs="*", default=[],
                    help="voice2excel.db یا خروجی واژه‌نامه (.v2xdict/.json) از استفاده واقعی")
    ap.add_argument("--password", default="", help="گذرواژه خروجی واژه‌نامه رمزدار (وگرنه پرسیده می‌شود)")
    ap.add_argument("--fresh", action="store_true", help="بدون داده فایل فعلی (پیش‌فرض: داده فعلی حفظ و افزوده می‌شود)")
    ap.add_argument("--city", default="مشهد")
    ap.add_argument("--osm-places", type=Path, help="محله‌ها، میدان‌ها و چهارراه‌ها از Overpass (بالا)")
    ap.add_argument("--keep-once", action="store_true", help="نام‌های یک‌باره نقشه هم (اگر نام شخص نباشند)")
    ap.add_argument("--out", type=Path, default=ROOT / "voice2excel" / "assets" / "geo.dat")
    a = ap.parse_args()
    l_streets, counts, points = [], {}, []
    if a.out.exists() and not a.fresh:  # داده پایه در هر نسخه فقط بزرگ‌تر می‌شود، چیزی از آن نمی‌افتد
        prev = geo.decode(a.out.read_bytes())
        l_streets += [(s[0], list(s[1])) for s in prev.get("s", [])]
        counts.update({(c[1], c[2]): int(c[3]) for c in prev.get("c", [])})
        points = prev.get("p", [])
    for p in a.learned:
        s, c = learned(p, a.password)
        l_streets += s
        for w, r, n in c:
            counts[(w, r)] = max(counts.get((w, r), 0), n)  # همان پایگاه داده دو بار، دو برابر شمرده نشود
    corrections = sorted(([["address", w, r, n] for (w, r), n in counts.items() if n >= MIN_CORRECTION_COUNT]),
                         key=lambda c: -c[3])
    if a.osm_geo and a.osm_geo.exists():
        points = osm_points(a.osm_geo)
    surnames, first = (read_list(a.names / f) for f in ("surnames.txt", "firstnames.txt"))
    from voice2excel.normalizer import match_key
    person_keys = frozenset({sound_key(n) for n in surnames + first} | {match_key(n) for n in surnames + first})
    streets = build(a.osm, a.excel, a.min_osm, l_streets, a.osm_places, a.keep_once, person_keys)
    if a.out.exists() and not a.fresh:  # املای قبلی هر خیابان حفظ می‌شود («سید رضی» با ساخت دوباره «سیدرضی» نشود)
        prev_canon = {sound_key(s[0]): s[0] for s in geo.decode(a.out.read_bytes()).get("s", [])}
        for s in streets:
            old = prev_canon.get(sound_key(s[0]))
            if old and old != s[0]:
                s[1] = sorted((set(s[1]) | {s[0]}) - {old})
                s[0] = old
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(geo.encode({"v": 4, "city": a.city, "s": streets, "n": surnames, "f": first, "c": corrections,
                                  "p": points}))
    print(f"{len(streets)} خیابان، {len(points)} خیابان با مختصات، {len(corrections)} اصلاح آدرس، "
          f"{len(surnames)} نام‌خانوادگی، {len(first)} نام ← {a.out} ({a.out.stat().st_size // 1024} کیلوبایت)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
