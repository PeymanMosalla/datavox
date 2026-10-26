"""یادگیری از اصلاحات کاربر.

وقتی کاربر مقدار یک فیلد را اصلاح می‌کند، واژه‌های جایگزین‌شده (مثلاً «گلزی» ← «گلزاری» یا
«هیفته» ← «17») ثبت می‌شوند. اصلاحی که به اندازه کافی تکرار شده باشد، در ویس‌های بعدی خودکار
اعمال می‌شود؛ کمتر از آن، فقط پیشنهاد داده می‌شود.

محدودیت‌های عمدی:
- اصلاحات هر گروه فیلد جداست (نام، آدرس، پروژه، متن) تا نام شخص در آدرس اعمال نشود.
- اصلاح عددی (مثل «17» ← «19») یاد گرفته نمی‌شود؛ مختص همان ساختمان است، نه خطای تشخیص.
- شماره تلفن و تاریخ‌ها هرگز یاد گرفته نمی‌شوند.
"""
from __future__ import annotations

import difflib
import re

from .config import Settings
from .database import Database, now
from .normalizer import normalize_text

FIELD_GROUPS = {
    "engineer_name": "name",
    "project_name": "project",
    "address": "address", "street": "address", "neighborhood": "address", "alley": "address", "plate": "address",
    "notes": "text", "stage": "text", "permit_status": "text", "customer_need": "text", "followup_action": "text",
    "structure_type": "text", "building_type": "text",
}
GROUP_LABELS = {"name": "نام", "project": "پروژه", "address": "آدرس", "text": "متن"}
MAX_TOKENS = 3
_W = r"[\w‌]"
_STRIP = "،,.:؛"


def _tokens(text: str) -> list[str]:
    return [t.strip(_STRIP) for t in normalize_text(text).split() if t.strip(_STRIP)]


def correction_pairs(old: str, new: str) -> list[tuple[str, str]]:
    """واژه‌هایی از متن قدیم که در متن جدید با واژه‌های دیگری جایگزین شده‌اند."""
    a, b = _tokens(old), _tokens(new)
    pairs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "replace" or not (1 <= i2 - i1 <= MAX_TOKENS) or not (1 <= j2 - j1 <= MAX_TOKENS):
            continue
        wrong, right = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if re.search(r"\d", wrong):
            continue  # «17» ← «19»: تصمیم مخصوص همین مورد است، نه خطای تکرارشونده
        if len(wrong) > 40 or len(right) > 40 or wrong == right:
            continue
        pairs.append((wrong, right))
    return pairs


def learn_from_edit(db: Database, field: str, old: str, new: str) -> list[tuple[str, str]]:
    group = FIELD_GROUPS.get(field)
    if not group or not old or not new:
        return []
    pairs = correction_pairs(old, new)
    if not pairs:
        return []
    with db.tx() as c:
        for wrong, right in pairs:
            c.execute(
                """INSERT INTO corrections(field_group, wrong, right, count, enabled, created_at, last_at)
                   VALUES(?,?,?,1,1,?,?)
                   ON CONFLICT(field_group, wrong, right) DO UPDATE SET count=count+1, last_at=excluded.last_at""",
                (group, wrong, right, now(), now()))
    return pairs


def unlearn_edit(db: Database, field: str, old: str, new: str) -> None:
    """بازگشت یک اصلاح: شمارش همان جفت‌واژه‌ها کم (و در صفر حذف) می‌شود."""
    group = FIELD_GROUPS.get(field)
    if not group or not old or not new:
        return
    with db.tx() as c:
        for wrong, right in correction_pairs(old, new):
            c.execute("UPDATE corrections SET count=count-1 WHERE field_group=? AND wrong=? AND right=?",
                      (group, wrong, right))
        c.execute("DELETE FROM corrections WHERE count<=0")


def _replace_token(text: str, wrong: str, right: str) -> str:
    pat = re.compile(rf"(?<!{_W}){re.escape(wrong)}(?!{_W})")
    return pat.sub(right, text)


def apply_learned(db: Database, settings: Settings, values: dict, rec=None) -> dict:
    """اعمال اصلاحات یادگرفته‌شده روی مقادیر استخراج‌شده.

    اصلاحی با تکرار کافی خودکار اعمال و در یادداشت فیلد ثبت می‌شود؛ بقیه به‌عنوان پیشنهاد
    در meta رکورد («learned_suggestions») قرار می‌گیرند.
    """
    rows = db.q("SELECT field_group, wrong, right, count, enabled FROM corrections")
    own = {(r["field_group"], r["wrong"]) for r in rows}  # اصلاح خود کاربر (حتی خاموش‌شده) مقدم است
    rows = [r for r in rows if r["enabled"]]
    if settings.kb_base_pack:
        from .geo import base_corrections
        rows += [{"field_group": g, "wrong": w, "right": r, "count": n, "base": True}
                 for g, w, r, n in base_corrections() if (g, w) not in own]
    if not rows:
        return values
    by_group: dict[str, list[dict]] = {}
    for r in rows:
        by_group.setdefault(r["field_group"], []).append(r)
    out = dict(values)
    suggestions: dict[str, list[str]] = {}
    threshold = max(1, int(settings.learn_auto_threshold))
    for field, value in values.items():
        group = FIELD_GROUPS.get(field)
        if not group or not value or group not in by_group:
            continue
        current = normalize_text(value)
        # اصلاح‌های پرتکرارتر و طولانی‌تر اول
        for r in sorted(by_group[group], key=lambda r: (-r["count"], -len(r["wrong"]))):
            if not re.search(rf"(?<!{_W}){re.escape(r['wrong'])}(?!{_W})", current):
                continue
            if r["count"] >= threshold:
                current = _replace_token(current, r["wrong"], r["right"])
                if rec is not None and field in rec.fields:
                    rec.fields[field].notes.append(
                        f"اصلاح خودکار املای رایج: «{r['wrong']}» ← «{r['right']}»." if r.get("base") else
                        f"اصلاح خودکار بر اساس اصلاحات قبلی شما: «{r['wrong']}» ← «{r['right']}» ({r['count']} بار).")
            else:
                suggestions.setdefault(field, []).append(_replace_token(current, r["wrong"], r["right"]))
        out[field] = current
    if rec is not None and suggestions:
        rec.learned_suggestions = suggestions
    return out


def list_corrections(db: Database) -> list[dict]:
    return db.q("SELECT * FROM corrections ORDER BY enabled DESC, count DESC, last_at DESC")


def set_enabled(db: Database, cid: int, enabled: bool) -> None:
    with db.tx() as c:
        c.execute("UPDATE corrections SET enabled=? WHERE id=?", (1 if enabled else 0, cid))


def delete_correction(db: Database, cid: int) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM corrections WHERE id=?", (cid,))
