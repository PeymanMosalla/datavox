"""واژه‌نامه پویا: نام مهندس‌ها، پروژه‌ها، خیابان‌ها و ...

قواعد:
- نام جدید رد نمی‌شود؛ فقط پس از تأیید کاربر ذخیره می‌شود.
- نام‌های مشابه فقط پیشنهاد می‌شوند و هرگز خودکار ادغام نمی‌شوند.
- تغییر نام استاندارد با ثبت سابقه انجام می‌شود و شکل قبلی به‌عنوان شکل جایگزین می‌ماند.
"""
from __future__ import annotations

import difflib
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




# ---------- انتقال واژه‌نامه به رایانه دیگر (بدون هیچ رکورد یا ویسی) ----------
MAX_TRANSFER_ITEMS = 200_000
_MAX_TEXT = 200


def export_data(db: Database) -> dict:
    """نام‌ها با همه شکل‌هایشان و اصلاحات یادگرفته‌شده؛ رکورد، متن ویس و شماره تلفن در آن نیست."""
    from . import __version__

    aliases: dict[int, list[str]] = {}
    for r in db.q("SELECT entity_id, alias FROM aliases ORDER BY id"):
        aliases.setdefault(r["entity_id"], []).append(r["alias"])
    entities = [{"t": e["type"], "c": e["canonical"], "a": [a for a in aliases.get(e["id"], []) if a != e["canonical"]],
                 "u": e["use_count"]} for e in db.q("SELECT id, type, canonical, use_count FROM entities ORDER BY id")]
    corrections = [{"g": c["field_group"], "w": c["wrong"], "r": c["right"], "n": c["count"], "e": c["enabled"]}
                   for c in db.q("SELECT * FROM corrections ORDER BY id")]
    return {"app": "voice2excel", "type": "dictionary", "version": __version__, "created_at": now(),
            "entities": entities, "corrections": corrections}


def import_data(db: Database, data: dict) -> dict:
    """افزودن به واژه‌نامه فعلی؛ چیزی پاک یا جایگزین نمی‌شود و نام تکراری دوباره اضافه نمی‌شود."""
    from .learning import GROUP_LABELS

    if not isinstance(data, dict) or data.get("app") != "voice2excel" or data.get("type") != "dictionary":
        raise ValueError("این فایل، واژه‌نامه «DataVox» نیست.")
    entities, corrections = data.get("entities") or [], data.get("corrections") or []
    if not isinstance(entities, list) or not isinstance(corrections, list) \
            or len(entities) + len(corrections) > MAX_TRANSFER_ITEMS:
        raise ValueError("فایل واژه‌نامه نامعتبر یا بیش از حد بزرگ است.")
    ok = lambda s: isinstance(s, str) and 0 < len(s.strip()) <= _MAX_TEXT  # noqa: E731
    before_e = db.one("SELECT COUNT(*) n FROM entities")["n"]
    before_a = db.one("SELECT COUNT(*) n FROM aliases")["n"]
    for e in entities:
        if not isinstance(e, dict) or e.get("t") not in ENTITY_TYPES or not ok(e.get("c")):
            continue
        try:
            eid = add_entity(db, e["c"], e["t"], source="import")
        except ValueError:
            continue
        have = {r["alias"] for r in db.q("SELECT alias FROM aliases WHERE entity_id=?", (eid,))}
        for a in (e.get("a") or [])[:50]:
            if ok(a) and _clean(a, e["t"]) not in have:  # دوباره وارد کردن همان فایل، سابقه را شلوغ نکند
                add_alias(db, eid, a, source="import")
    added_c = 0
    with db.tx() as c:
        for x in corrections:
            if not isinstance(x, dict) or x.get("g") not in GROUP_LABELS or not ok(x.get("w")) or not ok(x.get("r")):
                continue
            added_c += c.execute(
                "INSERT OR IGNORE INTO corrections(field_group, wrong, right, count, enabled, created_at, last_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (x["g"], x["w"], x["r"], max(1, int(x.get("n") or 1)), 1 if x.get("e", 1) else 0, now(), now())).rowcount
    new_e = db.one("SELECT COUNT(*) n FROM entities")["n"] - before_e
    new_a = db.one("SELECT COUNT(*) n FROM aliases")["n"] - before_a - new_e  # بدون خود نام اصلی هر مورد تازه
    return {"entities": new_e, "aliases": new_a, "corrections": added_c}
