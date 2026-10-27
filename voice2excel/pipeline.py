"""اتصال مراحل: متن ← استخراج ← اعتبارسنجی ← تشخیص تکرار ← رکورد قابل ذخیره."""
from __future__ import annotations

from .config import Settings
from .database import Database
from .dates_fa import parse_jalali
from .deduplicator import db_candidates, find_similar
from .extractor import extract
from .learning import apply_learned
from .lexicon import get_lexicon, unify_spelling
from .normalizer import normalize_text
from .schema import ExtractedRecord
from .timing import field_times
from .validator import validate

# منبع رکوردهای موجود در فایل اکسل مقصد برای تشخیص تکرار (توسط ماژول اکسل تنظیم می‌شود)
_excel_candidates_provider = None


def set_excel_candidates_provider(fn) -> None:
    global _excel_candidates_provider
    _excel_candidates_provider = fn


def excel_candidates() -> list[dict]:
    if _excel_candidates_provider is None:
        return []
    try:
        return _excel_candidates_provider() or []
    except Exception:
        return []


def record_meta(rec: ExtractedRecord) -> dict:
    return {
        "phones": [p.model_dump() for p in rec.phones],
        "inherited": [k for k, fv in rec.fields.items() if fv.inherited],
        "field_notes": {k: fv.notes for k, fv in rec.fields.items() if fv.notes},
        "evidence": {k: fv.evidence for k, fv in rec.fields.items() if fv.evidence},
        "ambiguities": list(rec.ambiguities),
        "title": rec.title,
        "learned_suggestions": dict(rec.learned_suggestions),
    }


def find_duplicates(db: Database, values: dict, record_id: int | None = None, audio_id: int | None = None) -> list[dict]:
    dups = find_similar(values, db_candidates(db, exclude_record_id=record_id, exclude_audio_id=audio_id), "db")
    dups += find_similar(values, excel_candidates(), "excel")
    dups.sort(key=lambda d: 0 if d["level"] == "strong" else 1)
    return dups[:6]


def build_records(db: Database, settings: Settings, text: str, visit_date: str, audio_id: int | None = None,
                  words: list[dict] | None = None):
    """متن ویس ← (متن پردازش‌شده، بندها، رکوردهای آماده ذخیره).

    words: واژه‌های زمان‌دار ویس؛ برای یافتن زمان هر فیلد (پخش همان تکه) و واژه‌های کم‌اطمینان.
    """
    lex = get_lexicon(db, base=settings.kb_base_pack)
    result = extract(text, parse_jalali(visit_date), lexicon=lex)
    out = []
    for rec in result.records:
        values = {k: fv.value for k, fv in rec.fields.items() if fv.value}
        values["visit_date"] = visit_date
        values = apply_learned(db, settings, values, rec)
        if lex and settings.kb_auto_spelling:
            values = unify_spelling(values, lex, rec)
        meta = record_meta(rec)
        if settings.kb_base_pack and values.get("address"):
            values, meta["map_fix"] = map_fix(values)
        if words:
            spans = {k: fv.span for k, fv in rec.fields.items() if fv.span and fv.value}
            meta["times"], meta["low_confidence"], meta["low_times"] = field_times(result.text, words, spans)
        dups = find_duplicates(db, values, audio_id=audio_id)
        v = validate(db, values, meta, settings, duplicates=dups)
        out.append({
            "building_index": rec.building_index,
            "building_count": rec.building_count,
            "extracted": {"values": dict(values), "meta": meta},
            "values": values,
            "validation": v.model_dump(),
            "status": v.status,
            "review_state": "approved" if v.status == "ready" else "pending",
            "approved_by": "auto" if v.status == "ready" else None,
        })
    clauses = [s.model_dump() for s in result.segments]
    return result.text, clauses, out


def map_fix(values: dict) -> tuple[dict, dict | None]:
    """خیابان فرعیِ دور با هم‌آوای نزدیک خیابان اصلی جایگزین می‌شود (حدس محتمل‌تر در ردیف؛ گزینه اصلی برای
    بازگشت با یک کلیک در بازبینی). در آزمون، حدس در ۹۵٪ موارد علامت‌خورده همان خیابان درست بود."""
    from .address_check import check
    found = check(values["address"])
    if not found:
        return values, None
    f = found[0]
    fixed = values["address"].replace(f["heard"], f["suggestion"], 1)
    if fixed == values["address"]:
        return values, None
    return {**values, "address": fixed}, {**f, "from": values["address"], "to": fixed}


def edited_fields(db: Database, record_id: int) -> set[str]:
    return {r["field"] for r in db.q("SELECT DISTINCT field FROM record_edits WHERE record_id=? AND undone=0 AND action IN ('edit','accept')",
                                     (record_id,))}


def revalidate(db: Database, settings: Settings, record_id: int) -> dict:
    r = db.get_record(record_id)
    if r is None:
        raise KeyError(record_id)
    meta = r["extracted"].get("meta", {})
    dups = find_duplicates(db, r["values"], record_id=record_id, audio_id=r["audio_id"])
    v = validate(db, r["values"], meta, settings, edited=edited_fields(db, record_id), duplicates=dups)
    db.update_record(record_id, validation_json=v.model_dump(), status=v.status)
    return v.model_dump()


def normalized(text: str) -> str:
    return normalize_text(text)


def reextract_all(db: Database, settings: Settings) -> dict:
    """استخراج دوباره از متن‌های ذخیره‌شده (بدون تبدیل دوباره گفتار به متن).

    رکوردهایی که دستی اصلاح، توسط کاربر تأیید یا در اکسل ثبت شده‌اند دست نمی‌خورند
    (save_results آن‌ها را محافظت می‌کند).
    """
    done = skipped = 0
    rows = db.q("SELECT a.id, a.visit_date, t.normalized_text, t.raw_text FROM audio_files a "
                "JOIN transcripts t ON t.audio_id=a.id WHERE a.status='done'")
    for r in rows:
        text = r["normalized_text"] or normalize_text(r["raw_text"] or "")
        t = db.transcript(r["id"])
        processed, clauses, records = build_records(db, settings, text, r["visit_date"], r["id"],
                                                    words=t.get("words") or [])
        ids = db.save_results(r["id"], {
            "raw_text": t["raw_text"], "normalized_text": t["normalized_text"], "processed_text": processed,
            "segments": t.get("segments", []), "words": t.get("words", []), "clauses": clauses,
            "language": t.get("language"), "language_prob": t.get("language_prob"),
            "avg_logprob": t.get("avg_logprob"), "model": t.get("model"),
        }, records)
        if ids:
            done += 1
        else:
            skipped += 1
    return {"reextracted": done, "protected": skipped}
