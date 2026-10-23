"""تشخیص و استانداردسازی شماره تلفن ایران.

قاعده‌ها محافظه‌کارانه‌اند: هیچ رقمی ساخته نمی‌شود؛ فقط پیش‌شماره کشور (‎+98/0098)
به صفر تبدیل می‌شود و برای موبایل ده‌رقمیِ بدون صفر، صفرِ استاندارد افزوده و دلیلش ثبت می‌شود.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalizer import to_ascii_digits
from .numbers_fa import NumberRun

MOBILE = re.compile(r"^09\d{9}$")
LANDLINE = re.compile(r"^0[1-8]\d{9}$")
LOCAL = re.compile(r"^[2-9]\d{7}$")

PHONE_CUES = ("شماره", "تلفن", "موبایل", "همراه", "تماس", "شمارش", "شمارشون", "شماره‌اش", "شماره‌شون", "تلفنش")


@dataclass
class PhoneCandidate:
    heard: str  # رقم‌ها به همان ترتیبی که شنیده شد
    normalized: str  # شکل استاندارد (با صفر ابتدایی)
    kind: str  # mobile / landline / local / incomplete
    explicit: bool  # آیا پیش از آن واژه‌ای مثل «شماره» آمده بود
    ambiguous: bool  # مرز گروه‌های عددی مبهم بود
    start: int
    end: int
    notes: list[str] = field(default_factory=list)
    from_words: bool = False  # از عددهای حروفیِ گفتار ساخته شده (نه رقم‌های نوشته‌شده توسط مدل)

    @property
    def complete(self) -> bool:
        return self.kind in ("mobile", "landline")


def classify(digits: str) -> tuple[str, str, list[str]]:
    """رشته رقمی ← (نوع، شکل استاندارد، توضیحات)."""
    d = to_ascii_digits(re.sub(r"[^\d۰-۹+]", "", digits))
    notes: list[str] = []
    if d.startswith("+98"):
        d = "0" + d[3:]
        notes.append("پیش‌شماره کشور (+98) به صفر تبدیل شد.")
    elif d.startswith("0098"):
        d = "0" + d[4:]
        notes.append("پیش‌شماره کشور (0098) به صفر تبدیل شد.")
    elif d.startswith("98") and len(d) == 12 and d[2] == "9":
        d = "0" + d[2:]
        notes.append("پیش‌شماره کشور (98) به صفر تبدیل شد.")
    d = d.replace("+", "")
    if MOBILE.match(d):
        return "mobile", d, notes
    if len(d) == 10 and d.startswith("9"):
        notes.append("شماره موبایل بدون صفر ابتدایی گفته شده بود؛ صفر استاندارد افزوده شد.")
        return "mobile", "0" + d, notes
    if LANDLINE.match(d):
        return "landline", d, notes
    if LOCAL.match(d):
        notes.append("شماره ثابت هشت‌رقمی بدون کد شهر است.")
        return "local", d, notes
    return "incomplete", d, notes


def _valid_kind(digits: str) -> bool:
    return classify(digits)[0] in ("mobile", "landline", "local")


def phones_from_runs(text: str, runs: list[NumberRun]) -> list[PhoneCandidate]:
    """استخراج شماره‌های تلفن از اجراهای عددی.

    هر اجرا ممکن است چند شماره یا عدد دیگری (مثل پلاک) را هم در بر داشته باشد،
    پس زیربازه‌های پیوسته‌ای از گروه‌ها که شماره معتبر می‌سازند جست‌وجو می‌شوند.
    """
    found: list[PhoneCandidate] = []
    for run in runs:
        groups = run.groups
        total_digits = len(run.digits)
        if total_digits < 7:
            continue
        explicit = _has_cue_before(text, run.start)
        i = 0
        used_any = False
        leftover: list[str] = []
        while i < len(groups):
            best = None
            acc = ""
            for j in range(i, len(groups)):
                acc += groups[j]
                if len(acc) > 14:
                    break
                if _valid_kind(acc) and classify(acc)[0] != "local":
                    best = (j, acc)
                elif _valid_kind(acc) and best is None and j == len(groups) - 1 and i == 0:
                    best = (j, acc)
            if best:
                j, acc = best
                kind, norm, notes = classify(acc)
                found.append(PhoneCandidate(acc, norm, kind, explicit, run.ambiguous, run.start, run.end, notes, run.from_words))
                used_any = True
                i = j + 1
            else:
                leftover.append(groups[i])
                i += 1
        rest = "".join(leftover)
        if not used_any and len(rest) >= 7:
            kind, norm, notes = classify(rest)
            found.append(PhoneCandidate(rest, norm, "incomplete", explicit, run.ambiguous, run.start, run.end, notes, run.from_words))
        elif used_any and len(rest) >= 4 and explicit:
            # بخشی از اجرا شماره نشد؛ ممکن است رقم اضافه یا بخش دیگری از شماره باشد
            for c in found:
                if c.start == run.start:
                    c.notes.append("بخشی از رقم‌های گفته‌شده در کنار شماره، جزو شماره قرار نگرفت.")
                    c.ambiguous = True
    return found


def _has_cue_before(text: str, pos: int, window: int = 40) -> bool:
    before = text[max(0, pos - window):pos]
    return any(cue in before for cue in PHONE_CUES)


def format_for_excel(normalized_phones: list[str]) -> str:
    return "\n".join(normalized_phones)


def compare_key(phone: str) -> str:
    """کلید مقایسه برای تشخیص تکرار: بدون صفر ابتدایی، فقط رقم."""
    d = re.sub(r"\D", "", to_ascii_digits(str(phone)))
    if d.startswith("98") and len(d) == 12:
        d = d[2:]
    return d.lstrip("0")
