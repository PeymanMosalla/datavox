"""تشخیص تکرار: فایل صوتی تکراری (هش محتوا) و رکورد بازاریابی احتمالاً تکراری.

رکورد مشابه فقط هشدار می‌سازد؛ هیچ رکوردی خودکار حذف یا ادغام نمی‌شود.
"""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

from .database import Database
from .normalizer import match_key, normalize_text
from .phone import compare_key


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _addr_key(addr: str) -> str:
    return normalize_text(addr).replace("،", " ").replace(",", " ").replace("  ", " ").strip()


def find_similar(values: dict, candidates: list[dict], source: str) -> list[dict]:
    """مقایسه یک رکورد با فهرستی از رکوردهای موجود.

    candidates: [{ref, engineer_name, phone, address, project_name}]
    """
    out = []
    phones = {compare_key(p) for p in str(values.get("phone", "")).split("\n") if compare_key(p)}
    name_k = match_key(values.get("engineer_name", ""))
    addr_k = _addr_key(values.get("address", ""))
    proj_k = match_key(values.get("project_name", ""))
    for c in candidates:
        reasons = []
        cphones = {compare_key(p) for p in str(c.get("phone", "")).replace("\r", "\n").split("\n") if compare_key(p)}
        same_phone = bool(phones & cphones)
        name_sim = _sim(name_k, match_key(c.get("engineer_name", "")))
        addr_sim = _sim(addr_k, _addr_key(c.get("address", "")))
        proj_sim = _sim(proj_k, match_key(c.get("project_name", ""))) if proj_k else 0.0
        if same_phone:
            reasons.append("شماره تماس یکسان")
        if name_sim >= 0.85:
            reasons.append("نام مشابه")
        if addr_sim >= 0.85:
            reasons.append("آدرس مشابه")
        if proj_sim >= 0.9:
            reasons.append("نام پروژه مشابه")
        # یک مهندس می‌تواند چند ساختمان داشته باشد: شماره یکسان به‌تنهایی «احتمال» است، نه تکرار قطعی
        strong = (same_phone and addr_sim >= 0.85) or (name_sim >= 0.85 and addr_sim >= 0.9)
        weak = same_phone or addr_sim >= 0.9
        if strong or weak:
            out.append({
                "source": source,
                "ref": c.get("ref"),
                "level": "strong" if strong else "weak",
                "reasons": reasons,
                "engineer_name": c.get("engineer_name", ""),
                "address": c.get("address", ""),
                "phone": c.get("phone", ""),
            })
    out.sort(key=lambda d: 0 if d["level"] == "strong" else 1)
    return out[:5]


def db_candidates(db: Database, exclude_record_id: int | None = None, exclude_audio_id: int | None = None) -> list[dict]:
    rows = db.list_records("r.review_state != 'rejected'")
    out = []
    for r in rows:
        if r["id"] == exclude_record_id or r["audio_id"] == exclude_audio_id:
            continue
        v = r["values"]
        out.append({
            "ref": f"رکورد #{r['id']} ({r['original_name']})",
            "record_id": r["id"],
            "engineer_name": v.get("engineer_name", ""),
            "phone": v.get("phone", ""),
            "address": v.get("address", ""),
            "project_name": v.get("project_name", ""),
        })
    return out
