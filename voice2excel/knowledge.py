"""آموزش از فایل‌های اکسل: یادگیری نام مهندس‌ها، خیابان‌ها و پروژه‌ها از داده‌های گذشته.

هر فایل یک «منبع» جداگانه است: معلوم است هر نام از کدام فایل آمده و با حذف منبع،
نام‌هایی که فقط همان فایل آورده بود (و هیچ رکوردی تأییدشان نکرده) حذف می‌شوند.

قواعد:
- فایل اکسل فقط خوانده می‌شود و هرگز تغییر نمی‌کند.
- املاهای هم‌آوا («علی زاده» و «علیزاده») یک نام‌اند: پرتکرارترین املا نام استاندارد
  و بقیه «شکل دیگر» همان نام می‌شوند. نام‌های فقط مشابه هرگز ادغام نمی‌شوند.
- فقط چیزی یاد گرفته می‌شود که به‌روشنی نام شخص یا خیابان است؛ سلول‌های مبهم کنار گذاشته می‌شوند.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from .database import Database, now
from .excel_reader import detect_header_row, header_map
from .extractor import NAME_STOP, PROJECT_CUES, TECH_WORDS, TITLES
from .normalizer import match_key, normalize_text, strip_title

ROLES = {"engineer": "نام مهندس / شخص", "address": "آدرس", "project": "نام پروژه", "": "نادیده"}
MAX_ROWS = 20000

# ---------- خواندن نام از سلول ----------
_NOT_NAME = NAME_STOP | {"فامیلشو", "فامیل", "نمیدونن", "نمی‌دونن", "گروه", "ساختمانی", "شرکت", "نگهبان", "سرپرست"}
_PROJECT_RE = re.compile(rf"^(?:{'|'.join(map(re.escape, sorted(PROJECT_CUES, key=len, reverse=True)))})\s+\S")
_TRAILING_PHONE = re.compile(r"[\s:،,\-]*[\d\s\-]{7,}$")


def names_from_cell(value) -> list[tuple[str, str]]:
    """«مهندس طاهری\\nمهندس رحیمی» ← [(engineer، طاهری)، (engineer، رحیمی)].

    نام بدون عنوان فقط وقتی پذیرفته می‌شود که ۱ یا ۲ واژه و بدون واژه کلیدی باشد
    («محمودآبادی» بله، «شماره نگهبان» نه). نام پروژه («گروه ساختمانی سازمند») جدا شناخته می‌شود.
    """
    out: list[tuple[str, str]] = []
    for line in re.split(r"[\n/|]+", normalize_text(str(value or ""))):
        line = _TRAILING_PHONE.sub("", line).strip(" ،,.:-")
        if not line or re.search(r"\d", line):
            continue
        if _PROJECT_RE.match(line):
            if len(line.split()) <= 6:
                out.append(("project", line))
            continue
        title, bare = strip_title(line)
        words = bare.split()
        if not words or len(words) > (3 if title else 2):
            continue
        if any(w in _NOT_NAME or w in TITLES for w in words) or len(bare.replace(" ", "")) < 2:
            continue
        if not all(re.fullmatch(r"[؀-ۿ‌]+", w) for w in words):
            continue
        out.append(("engineer", bare))
    return out


# ---------- خواندن خیابان از آدرس ----------
# واژه‌هایی که پیش از نام خیابان می‌آیند و جزو نام نیستند
_STREET_PREFIX = {
    "نبش", "انتهای", "ابتدای", "روبروی", "روبه‌روی", "روبه", "روی", "جنب", "بین", "حاشیه", "خیابان", "خیابون",
    "بلوار", "بولوار", "میدان", "میدون", "کوی", "شهرک", "محله", "منطقه", "کوچه", "بن‌بست", "سمت", "داخل", "پشت",
}
# اگر در میان واژه‌های پیش از عدد بیایند، نام خیابان پس از آن‌ها آغاز می‌شود
_NOT_STREET = {
    "پلاک", "قطعه", "واحد", "طبقه", "فاز", "بلوک", "راست", "چپ", "اول", "دوم", "سوم", "چهارم", "پنجم", "ششم",
    "هفتم", "هشتم", "نهم", "دهم", "و", "تا", "متری", "متر", "سقف", "مرکز", "پاساژ", "روبه", "روی", "حرید", "خرید",
    "شمالی", "جنوبی", "شرقی", "غربی", "مهندس", "آقای", "خانم", "جنب", "بعد", "قبل", "از", "به", "سر", "رو",
    "تعداد", *TECH_WORDS,
}
_KEYWORD_STREET = {"بلوار", "بولوار", "خیابان", "خیابون", "میدان", "میدون", "کوی", "شهرک"}
_TOKEN = re.compile(r"\d[\d/]*|[ء-غف-يٱ-ۓ‌]+")  # بدون ویرگول عربی که در بازه حروف است
_DIRECTION = {"شمالی", "جنوبی", "شرقی", "غربی"}


@dataclass
class StreetName:
    canonical: str
    aliases: set[str] = field(default_factory=set)


def _street_from_words(words: list[str]) -> StreetName | None:
    # نام خیابان پس از آخرین واژه ناخیابانی آغاز می‌شود: «ابوطالب نبش شهید واحدی 7» ← «شهید واحدی»
    start = 0
    for i, w in enumerate(words):
        if (w in _NOT_STREET or w in _STREET_PREFIX) and w not in _DIRECTION:
            start = i + 1
    words = words[start:]
    # «طبرسی شمالی» نام کامل خیابان است، ولی «شمالی» تنها نه
    if not words or words[0] in _DIRECTION or len(words) > 4:
        return None
    name = " ".join(words)
    if len(name.replace(" ", "")) < 3:
        return None
    street = StreetName(name)
    if words[0] == "شهید" and len(words) > 1:
        street.aliases.add(" ".join(words[1:]))  # بازاریاب گاهی «شهید» را نمی‌گوید
    return street


def streets_from_address(value) -> list[StreetName]:
    """«ساجدی 7 ، فتح 8 ، پلاک 146» ← ساجدی، فتح؛ «بلوار جانباز ، مهدی 32» ← جانباز، مهدی."""
    out: list[StreetName] = []
    text = normalize_text(str(value or "")).replace("روبه روی", "روبه‌روی")
    for part in re.split(r"[،,؛\n]|\s[-–]\s", text):
        tokens = _TOKEN.findall(part)
        letters: list[str] = []
        for i, tok in enumerate(tokens):
            if tok[0].isdigit():
                st = _street_from_words(letters[-4:]) if letters else None
                if st:
                    out.append(st)
                letters = []
                continue
            if tok in _KEYWORD_STREET:
                # «بلوار جانباز» بدون عدد: نام تا پایان بخش یا تا واژه بعدی خیابان
                rest = []
                for t in tokens[i + 1:]:
                    if t[0].isdigit() or t in _STREET_PREFIX or t in _NOT_STREET:
                        break
                    rest.append(t)
                nxt = tokens[i + 1 + len(rest)] if i + 1 + len(rest) < len(tokens) else ""
                if rest and not nxt[:1].isdigit():
                    st = _street_from_words(rest[:3])
                    if st:
                        out.append(st)
                letters = []
                continue
            letters.append(tok)
    return out


# ---------- گردآوری ----------
@dataclass
class Group:
    """همه املاهای هم‌آوای یک نام در یک فایل."""

    spellings: Counter = field(default_factory=Counter)
    aliases: set[str] = field(default_factory=set)

    @property
    def canonical(self) -> str:
        return self.spellings.most_common(1)[0][0]

    @property
    def count(self) -> int:
        return sum(self.spellings.values())

    def names(self) -> set[str]:
        return set(self.spellings) | self.aliases


@dataclass
class Harvest:
    rows: int = 0
    groups: dict[str, dict[str, Group]] = field(default_factory=lambda: {"engineer": {}, "street": {}, "project": {}})

    def add(self, etype: str, name: str, aliases=()) -> None:
        g = self.groups[etype].setdefault(match_key(name), Group())
        g.spellings[name] += 1
        g.aliases.update(a for a in aliases if a != name)


def harvest(names=(), addresses=(), projects=()) -> Harvest:
    h = Harvest()
    for v in names:
        for etype, n in names_from_cell(v):
            h.add(etype, n)
    for v in addresses:
        for st in streets_from_address(v):
            h.add("street", st.canonical, st.aliases)
    for v in projects:
        p = normalize_text(str(v or "")).strip(" ،,.")
        if p and not re.search(r"\d{4,}", p) and len(p.split()) <= 6:
            h.add("project", p)
    return h


def read_columns(path: Path, sheet: str, header_row: int, roles: dict[str, str]) -> tuple[dict[str, list], int]:
    """ستون‌های نقش‌دار ← {نقش: مقادیر}، تعداد ردیف‌های دارای داده."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        idx = {openpyxl.utils.column_index_from_string(c) - 1: r for c, r in roles.items() if r}
        values: dict[str, list] = {r: [] for r in idx.values()}
        rows = 0
        for n, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True)):
            if n >= MAX_ROWS:
                break
            got = False
            for ci, role in idx.items():
                if ci < len(row) and row[ci] not in (None, ""):
                    values[role].append(row[ci])
                    got = True
            rows += got
        return values, rows
    finally:
        wb.close()


def harvest_file(path: Path, sheet: str, header_row: int, roles: dict[str, str]) -> Harvest:
    values, rows = read_columns(path, sheet, header_row, roles)
    h = harvest(values.get("engineer", []), values.get("address", []), values.get("project", []))
    h.rows = rows
    return h


# ---------- تشخیص ستون‌ها ----------
# ترتیب مهم است: «همراه کارفرما» شماره است نه نام؛ «نام پروژه» پروژه است؛ «آدرس پروژه» آدرس
_HEADER_HINTS = [
    ("", ("همراه", "تلفن", "موبایل", "شماره", "تماس", "تاریخ", "توضیح", "پیگیری", "وضعیت", "نتیجه", "ردیف")),
    ("address", ("آدرس", "نشانی", "محل", "موقعیت", "خیابان")),
    ("project", ("پروژه", "ساختمان", "مجتمع")),
    ("engineer", ("نام", "اسم", "کارفرما", "مهندس", "مالک", "مشتری")),
]


def _header_role(header: str) -> str | None:
    h = normalize_text(header)
    for role, hints in _HEADER_HINTS:
        if any(x in h for x in hints):
            return role
    return None


def _content_scores(values: list) -> dict[str, float]:
    vals = [v for v in values if str(v).strip()][:400]
    if not vals:
        return {"engineer": 0.0, "address": 0.0, "titled": 0.0, "numeric": 0.0}
    n = len(vals)
    texts = [normalize_text(str(v)) for v in vals]
    return {
        "engineer": sum(1 for t in texts if any(e == "engineer" for e, _ in names_from_cell(t))) / n,
        "titled": sum(1 for t in texts if strip_title(t)[0]) / n,
        "address": sum(1 for t in texts if streets_from_address(t)) / n,
        "numeric": sum(1 for t in texts if not re.search(r"[؀-ۿ]", t)) / n,
    }


def detect_roles(headers: dict[str, str], samples: dict[str, list]) -> dict[str, str]:
    """{حرف ستون: نقش}. از عنوان ستون و محتوای آن؛ هر نقش حداکثر یک ستون."""
    best: dict[str, tuple[float, str]] = {}
    for col, header in headers.items():
        sc = _content_scores(samples.get(col, []))
        if sc["numeric"] > 0.5:
            continue  # ستون شماره، تاریخ یا عدد
        hint = _header_role(header)
        if hint == "":
            continue
        cand: list[tuple[str, float]] = []
        if hint == "engineer" and sc["engineer"] >= 0.3:
            cand.append(("engineer", 1 + sc["engineer"]))
        elif hint == "address" and sc["address"] >= 0.3:
            cand.append(("address", 1 + sc["address"]))
        elif hint == "project":
            cand.append(("project", 1.0))
        elif hint is None:
            if sc["titled"] >= 0.5:
                cand.append(("engineer", sc["titled"]))
            elif sc["address"] >= 0.5:
                cand.append(("address", sc["address"]))
        for role, score in cand:
            if role not in best or best[role][0] < score:
                best[role] = (score, col)
    return {col: role for role, (_, col) in best.items()}


def analyze_workbook(path: Path) -> dict:
    """شیت‌ها، عنوان ستون‌ها و نقش پیشنهادی هر ستون؛ شیت اصلی، پرداده‌ترین شیتِ دارای نام یا آدرس است."""
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets:
            hr = detect_header_row(ws)
            headers = header_map(ws, hr)
            samples: dict[str, list] = {c: [] for c in headers}
            data_rows = 0
            for n, row in enumerate(ws.iter_rows(min_row=hr + 1, max_row=min(ws.max_row, hr + MAX_ROWS),
                                                 values_only=True)):
                if any(v not in (None, "") for v in row):
                    data_rows += 1
                if n >= 400:
                    continue  # نمونه برای تشخیص نقش ستون‌ها کافی است
                for c in headers:
                    ci = openpyxl.utils.column_index_from_string(c) - 1
                    if ci < len(row) and row[ci] not in (None, ""):
                        samples[c].append(row[ci])
            sheets.append({"name": ws.title, "header_row": hr, "headers": headers, "data_rows": data_rows,
                           "roles": detect_roles(headers, samples)})
    finally:
        wb.close()
    useful = [s for s in sheets if s["roles"]]
    main = max(useful or sheets, key=lambda s: s["data_rows"]) if sheets else None
    return {"sheets": sheets, "sheet": main["name"] if main else ""}


# ---------- پیش‌نمایش، ثبت و حذف ----------
def _existing_keys(db: Database) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {"engineer": set(), "street": set(), "project": set()}
    for r in db.q("SELECT e.type, a.match_key FROM aliases a JOIN entities e ON e.id=a.entity_id"):
        keys.setdefault(r["type"], set()).add(r["match_key"])
    return keys


def _keys_of(g: Group) -> set[str]:
    return {match_key(n) for n in g.names()}


def preview(db: Database, h: Harvest, sample: int = 30) -> dict:
    """چه چیزی از این فایل یاد گرفته می‌شود: تعداد کل و تازه برای هر نوع، با نمونه نام‌های تازه."""
    existing = _existing_keys(db)
    out: dict = {"rows": h.rows}
    for etype, groups in h.groups.items():
        new = [g for g in groups.values() if not (_keys_of(g) & existing.get(etype, set()))]
        new.sort(key=lambda g: -g.count)
        out[etype] = {"total": len(groups), "new": len(new), "new_samples": [g.canonical for g in new[:sample]],
                      "variants": sum(1 for g in groups.values() if len(g.spellings) > 1)}
    return out


def find_source_by_sha(db: Database, sha: str) -> dict | None:
    return db.one("SELECT * FROM knowledge_sources WHERE sha256=?", (sha,)) if sha else None


def import_harvest(db: Database, h: Harvest, name: str, sha: str = "", sheet: str = "",
                   columns: dict | None = None) -> dict:
    """ثبت یک منبع در واژه‌نامه در یک تراکنش. خروجی: شناسه منبع و تعداد نام‌های تازه هر نوع."""
    added = {"engineer": 0, "street": 0, "project": 0}
    with db.tx() as c:
        sid = c.execute(
            "INSERT INTO knowledge_sources(name, sha256, sheet, columns_json, rows, imported_at) VALUES(?,?,?,?,?,?)",
            (name, sha, sheet, json.dumps(columns or {}, ensure_ascii=False), h.rows, now())).lastrowid
        label = f"آموزش #{sid}: {name}"
        for etype, groups in h.groups.items():
            for g in groups.values():
                keys = _keys_of(g)
                row = c.execute(
                    f"SELECT e.id FROM entities e JOIN aliases a ON a.entity_id=e.id WHERE e.type=? AND a.match_key IN "
                    f"({','.join('?' * len(keys))}) ORDER BY e.use_count DESC, e.id LIMIT 1", (etype, *keys)).fetchone()
                created = 0
                if row:
                    eid = row[0]
                    c.execute("UPDATE entities SET use_count=use_count+? WHERE id=?", (g.count, eid))
                else:
                    eid = c.execute(
                        "INSERT INTO entities(canonical, type, created_at, last_confirmed_at, source, use_count) "
                        "VALUES(?,?,?,?,?,?)", (g.canonical, etype, now(), now(), label, g.count)).lastrowid
                    c.execute("INSERT INTO entity_changes(entity_id, action, old_value, new_value, source, at) "
                              "VALUES(?,?,?,?,?,?)", (eid, "create", None, g.canonical, label, now()))
                    created = 1
                    added[etype] += 1
                for n in g.names():
                    c.execute("INSERT OR IGNORE INTO aliases(entity_id, alias, match_key, source, created_at) "
                              "VALUES(?,?,?,?,?)", (eid, n, match_key(n), label, now()))
                c.execute("INSERT INTO entity_sources(entity_id, source_id, count, created) VALUES(?,?,?,?) "
                          "ON CONFLICT(entity_id, source_id) DO UPDATE SET count=count+excluded.count",
                          (eid, sid, g.count, created))
        c.execute("UPDATE knowledge_sources SET label=?, engineers=?, streets=?, projects=?, new_entities=? WHERE id=?",
                  (label, len(h.groups["engineer"]), len(h.groups["street"]), len(h.groups["project"]),
                   sum(added.values()), sid))
    return {"source_id": sid, "added": added}


def remove_source(db: Database, sid: int) -> dict:
    """حذف یک منبع: شمارش‌های آن کم می‌شود؛ نام‌هایی که فقط همین منبع آورده و هیچ تأییدی نگرفته‌اند حذف می‌شوند."""
    src = db.one("SELECT * FROM knowledge_sources WHERE id=?", (sid,))
    if not src:
        raise KeyError(sid)
    removed = 0
    with db.tx() as c:
        for link in c.execute("SELECT * FROM entity_sources WHERE source_id=?", (sid,)).fetchall():
            eid = link["entity_id"]
            c.execute("UPDATE entities SET use_count=MAX(0, use_count-?) WHERE id=?", (link["count"], eid))
            others = c.execute("SELECT COUNT(*) FROM entity_sources WHERE entity_id=? AND source_id!=?",
                               (eid, sid)).fetchone()[0]
            ent = c.execute("SELECT canonical, use_count FROM entities WHERE id=?", (eid,)).fetchone()
            if link["created"] and not others and ent and ent["use_count"] == 0:
                c.execute("DELETE FROM entities WHERE id=?", (eid,))
                c.execute("INSERT INTO entity_changes(entity_id, action, old_value, new_value, source, at) "
                          "VALUES(?,?,?,?,?,?)", (eid, "delete", ent["canonical"], None, src["label"], now()))
                removed += 1
            else:
                c.execute("DELETE FROM aliases WHERE entity_id=? AND source=? AND alias!=?",
                          (eid, src["label"], ent["canonical"] if ent else ""))
        c.execute("DELETE FROM knowledge_sources WHERE id=?", (sid,))
    return {"removed": removed}


def list_sources(db: Database) -> list[dict]:
    rows = db.q("SELECT * FROM knowledge_sources ORDER BY id DESC")
    for r in rows:
        r["columns"] = json.loads(r.pop("columns_json") or "{}")
    return rows
