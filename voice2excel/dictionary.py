"""واژه‌نامه پویا: نام مهندس‌ها، پروژه‌ها، خیابان‌ها و ...

قواعد:
- نام جدید رد نمی‌شود؛ فقط پس از تأیید کاربر ذخیره می‌شود.
- نام‌های مشابه فقط پیشنهاد می‌شوند و هرگز خودکار ادغام نمی‌شوند.
- تغییر نام استاندارد با ثبت سابقه انجام می‌شود و شکل قبلی به‌عنوان شکل جایگزین می‌ماند.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .database import Database, now
from .normalizer import match_key, normalize_text, strip_title

ENTITY_TYPES = {
    "engineer": "مهندس / شخص تماس",
    "project": "پروژه / ساختمان",
    "street": "خیابان",
    "neighborhood": "محله",
    "company": "شرکت",
    "city": "شهر",
}


@dataclass
class Match:
    entity_id: int
    canonical: str
    alias: str
    score: float
    exact: bool
    use_count: int = 0


def _clean(name: str, etype: str) -> str:
    name = normalize_text(name)
    if etype == "engineer":
        _, name = strip_title(name)
    return name.strip()


def add_entity(db: Database, canonical: str, etype: str, source: str = "user", notes: str = "") -> int:
    canonical = _clean(canonical, etype)
    if not canonical:
        raise ValueError("نام خالی است.")
    if etype not in ENTITY_TYPES:
        raise ValueError("نوع موجودیت نامعتبر است.")
    with db.tx() as c:
        row = c.execute("SELECT id FROM entities WHERE type=? AND canonical=?", (etype, canonical)).fetchone()
        if row:
            c.execute("UPDATE entities SET last_confirmed_at=? WHERE id=?", (now(), row[0]))
            return row[0]
        cur = c.execute(
            "INSERT INTO entities(canonical, type, created_at, last_confirmed_at, source, notes) VALUES(?,?,?,?,?,?)",
            (canonical, etype, now(), now(), source, notes))
        eid = cur.lastrowid
        c.execute("INSERT OR IGNORE INTO aliases(entity_id, alias, match_key, source, created_at) VALUES(?,?,?,?,?)",
                  (eid, canonical, match_key(canonical), source, now()))
        c.execute("INSERT INTO entity_changes(entity_id, action, old_value, new_value, source, at) VALUES(?,?,?,?,?,?)",
                  (eid, "create", None, canonical, source, now()))
        return eid


def add_alias(db: Database, entity_id: int, alias: str, source: str = "user") -> None:
    etype = db.one("SELECT type FROM entities WHERE id=?", (entity_id,))
    if not etype:
        raise ValueError("موجودیت پیدا نشد.")
    alias = _clean(alias, etype["type"])
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO aliases(entity_id, alias, match_key, source, created_at) VALUES(?,?,?,?,?)",
                  (entity_id, alias, match_key(alias), source, now()))
        c.execute("UPDATE entities SET last_confirmed_at=? WHERE id=?", (now(), entity_id))
        c.execute("INSERT INTO entity_changes(entity_id, action, old_value, new_value, source, at) VALUES(?,?,?,?,?,?)",
                  (entity_id, "alias", None, alias, source, now()))


def rename_entity(db: Database, entity_id: int, new_canonical: str, source: str = "user") -> None:
    """تغییر املای نام استاندارد؛ نام قبلی به‌عنوان شکل جایگزین حفظ می‌شود."""
    row = db.one("SELECT * FROM entities WHERE id=?", (entity_id,))
    if not row:
        raise ValueError("موجودیت پیدا نشد.")
    new_canonical = _clean(new_canonical, row["type"])
    with db.tx() as c:
        c.execute("UPDATE entities SET canonical=?, last_confirmed_at=? WHERE id=?", (new_canonical, now(), entity_id))
        c.execute("INSERT OR IGNORE INTO aliases(entity_id, alias, match_key, source, created_at) VALUES(?,?,?,?,?)",
                  (entity_id, new_canonical, match_key(new_canonical), source, now()))
        c.execute("INSERT INTO entity_changes(entity_id, action, old_value, new_value, source, at) VALUES(?,?,?,?,?,?)",
                  (entity_id, "rename", row["canonical"], new_canonical, source, now()))


def delete_entity(db: Database, entity_id: int) -> None:
    row = db.one("SELECT * FROM entities WHERE id=?", (entity_id,))
    with db.tx() as c:
        c.execute("DELETE FROM entities WHERE id=?", (entity_id,))
        if row:
            c.execute("INSERT INTO entity_changes(entity_id, action, old_value, new_value, source, at) VALUES(?,?,?,?,?,?)",
                      (entity_id, "delete", row["canonical"], None, "user", now()))


def lookup(db: Database, name: str, etype: str, min_score: float = 0.78, limit: int = 5) -> list[Match]:
    """جست‌وجوی نام در واژه‌نامه: تطابق دقیق یا املاهای مشابه (فقط برای پیشنهاد)."""
    bare = _clean(name, etype)
    if not bare:
        return []
    key = match_key(bare)
    rows = db.q(
        "SELECT a.entity_id, a.alias, a.match_key, e.canonical, e.use_count FROM aliases a JOIN entities e ON e.id=a.entity_id "
        "WHERE e.type=?", (etype,))
    best: dict[int, Match] = {}
    for r in rows:
        exact = r["alias"] == bare
        if exact:
            score = 1.0
        elif r["match_key"] == key:
            score = 0.97  # فقط تفاوت در حروف هم‌آوا یا فاصله
        else:
            score = difflib.SequenceMatcher(None, key, r["match_key"]).ratio()
        if score >= min_score:
            m = Match(r["entity_id"], r["canonical"], r["alias"], round(score, 3), exact, r["use_count"])
            if r["entity_id"] not in best or best[r["entity_id"]].score < score:
                best[r["entity_id"]] = m
    # هم‌امتیازها: نام پرکاربردتر (پرتکرار در فایل شرکت یا تأییدشده بیشتر) اول
    return sorted(best.values(), key=lambda m: (-m.score, -m.use_count))[:limit]


def list_entities(db: Database, etype: str | None = None, query: str = "", limit: int = 300) -> list[dict]:
    sql = ("SELECT e.*, (SELECT GROUP_CONCAT(alias, ' | ') FROM aliases a WHERE a.entity_id=e.id AND a.alias!=e.canonical) "
           "AS aliases FROM entities e WHERE 1=1")
    args: list = []
    if etype:
        sql += " AND e.type=?"
        args.append(etype)
    if query:
        sql += " AND (e.canonical LIKE ? OR e.id IN (SELECT entity_id FROM aliases WHERE alias LIKE ?))"
        args += [f"%{normalize_text(query)}%"] * 2
    sql += " ORDER BY e.last_confirmed_at DESC LIMIT ?"
    args.append(limit)
    return db.q(sql, args)


def hotwords(db: Database, limit: int = 40) -> str:
    """پرکاربردترین نام‌های مهندس و خیابان برای راهنمایی مدل گفتار.

    ترتیب بر اساس تعداد استفاده است (تکرار در فایل شرکت + هر بار تأیید رکورد)، تا مدل نام‌هایی را
    که بیشتر شنیده می‌شوند بهتر بنویسد. نیمی از سهم برای مهندس‌ها و نیمی برای خیابان‌هاست.
    """
    half = max(1, limit // 2)
    rows = []
    for etype in ("engineer", "street"):
        rows += db.q("SELECT canonical FROM entities WHERE type=? ORDER BY use_count DESC, last_confirmed_at DESC "
                     "LIMIT ?", (etype, half))
    return "، ".join(r["canonical"] for r in rows)


def touch(db: Database, entity_id: int) -> None:
    with db.tx() as c:
        c.execute("UPDATE entities SET use_count=use_count+1, last_confirmed_at=? WHERE id=?", (now(), entity_id))


def touch_by_name(db: Database, name: str, etype: str) -> None:
    """افزایش شمارش استفاده نامی که در رکورد تأییدشده آمده (اگر در واژه‌نامه باشد)."""
    bare = _clean(name, etype)
    row = db.one("SELECT entity_id FROM aliases a JOIN entities e ON e.id=a.entity_id WHERE e.type=? AND a.alias=?",
                 (etype, bare))
    if row:
        touch(db, row["entity_id"])


def _set_use_count_at_least(db: Database, etype: str, canonical: str, count: int) -> None:
    with db.tx() as c:
        c.execute("UPDATE entities SET use_count=MAX(use_count, ?) WHERE type=? AND canonical=?", (count, etype, canonical))


_STREET_FROM_ADDRESS = re.compile(r"^(?:بلوار|خیابان|خیابون)?\s*([؀-ۿ‌ ]{2,25}?)\s*\d")


def seed_from_rows(db: Database, names: list[str], addresses: list[str], source: str) -> dict[str, int]:
    """پرکردن واژه‌نامه از ستون‌های فایل اکسل شرکت.

    تعداد تکرار هر نام در فایل به‌عنوان «تعداد استفاده» ثبت می‌شود تا پرتکرارترها در اولویت
    پیشنهاد و راهنمایی مدل گفتار باشند.
    """
    from collections import Counter

    engineers: Counter = Counter()
    for n in names:
        title, bare = strip_title(str(n or ""))
        if not title or not bare or len(bare) < 2 or re.search(r"\d", bare) or len(bare.split()) > 3:
            continue  # فقط ردیف‌هایی که به‌روشنی نام شخص‌اند
        engineers[bare] += 1
    streets: Counter = Counter()
    for a in addresses:
        for part in re.split(r"[،,]", normalize_text(str(a or ""))):
            m = _STREET_FROM_ADDRESS.match(part.strip())
            if not m:
                continue
            street = m.group(1).strip()
            if len(street) < 3 or street.startswith(("پلاک", "قطعه", "کوچه", "نبش")):
                continue
            streets[street] += 1
    added = {"engineer": 0, "street": 0}
    for etype, counter in (("engineer", engineers), ("street", streets)):
        for name, count in counter.items():
            before = db.one("SELECT id FROM entities WHERE type=? AND canonical=?", (etype, name))
            add_entity(db, name, etype, source=source)
            _set_use_count_at_least(db, etype, name, count)
            added[etype] += 0 if before else 1
    return added
