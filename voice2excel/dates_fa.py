"""تاریخ شمسی و تفسیر عبارت‌های زمانی پیگیری.

تاریخ پیشنهادی فقط وقتی محاسبه می‌شود که تاریخ مبنا (تاریخ بازدید/ضبط) معلوم باشد
و عبارت به‌روشنی قابل تفسیر باشد. هفته ایرانی از شنبه شروع می‌شود.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

import jdatetime

from .normalizer import normalize_text, to_ascii_digits
from .numbers_fa import words_to_int

# شنبه=0 ... جمعه=6 (ترتیب هفته ایرانی)
WEEKDAYS = {
    "شنبه": 0, "یکشنبه": 1, "یک‌شنبه": 1, "دوشنبه": 2, "دو‌شنبه": 2, "سه‌شنبه": 3, "سشنبه": 3,
    "سه شنبه": 3, "چهارشنبه": 4, "چهار‌شنبه": 4, "چارشنبه": 4, "پنجشنبه": 5, "پنج‌شنبه": 5,
    "پنج شنبه": 5, "جمعه": 6,
}
_WEEKDAY_RE = "|".join(sorted(map(re.escape, WEEKDAYS), key=len, reverse=True))
_NEXT_WEEK = r"(?:هفته\s*(?:ی\s*)?(?:بعد|دیگه|دیگر|آینده|آتی))"


@dataclass
class FollowUpTime:
    text: str  # همان عبارتی که گفته شد
    date: jdatetime.date | None
    reason: str  # توضیح نحوه محاسبه یا علت عدم محاسبه


def today_jalali() -> jdatetime.date:
    return jdatetime.date.today()


def parse_jalali(text: str) -> jdatetime.date | None:
    """«1405/7/28» یا «۱۴۰۵-۰۷-۲۸» ← تاریخ شمسی."""
    if not text:
        return None
    m = re.match(r"^\s*(1[34]\d\d)\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*$", to_ascii_digits(str(text)))
    if not m:
        return None
    try:
        return jdatetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def format_jalali(d: jdatetime.date | None) -> str:
    return "" if d is None else f"{d.year:04d}/{d.month:02d}/{d.day:02d}"


def from_gregorian(d: dt.date) -> jdatetime.date:
    return jdatetime.date.fromgregorian(date=d)


def _iran_weekday(d: jdatetime.date) -> int:
    return d.weekday()  # jdatetime: شنبه=0


def _start_of_week(d: jdatetime.date) -> jdatetime.date:
    return d - jdatetime.timedelta(days=_iran_weekday(d))


def find_followup_time(text: str, base: jdatetime.date | None) -> FollowUpTime | None:
    """پیدا کردن اولین عبارت زمانی پیگیری در متن و محاسبه تاریخ در صورت امکان."""
    t = normalize_text(text)
    patterns: list[tuple[str, callable]] = [
        (rf"(?:روز\s+)?({_WEEKDAY_RE})\s*(?:ی\s*)?{_NEXT_WEEK}", "weekday_next_week"),
        (rf"{_NEXT_WEEK}\s*(?:روز\s+)?({_WEEKDAY_RE})", "weekday_next_week"),
        (r"پس\s*‌?\s*فردا", "after_tomorrow"),
        (r"فردا", "tomorrow"),
        (r"امروز|همین\s+امروز", "today"),
        (r"(\S+(?:\s+و\s+\S+)?)\s+روز\s+(?:دیگه|دیگر|بعد)", "n_days"),
        (rf"{_NEXT_WEEK}", "next_week"),
        (r"(\S+)\s+هفته\s+(?:دیگه|دیگر|بعد)", "n_weeks"),
        (r"(?:ماه|ماهِ)\s+(?:بعد|دیگه|دیگر|آینده)", "next_month"),
        (r"آخر\s+هفته|اوایل\s+هفته|چند\s+روز\s+(?:دیگه|دیگر|بعد)|بعد\s+از\s+\S+", "vague"),
        (rf"({_WEEKDAY_RE})", "weekday"),
    ]
    for pat, kind in patterns:
        m = re.search(pat, t)
        if not m:
            continue
        phrase = m.group(0)
        if base is None:
            return FollowUpTime(phrase, None, "تاریخ بازدید مشخص نیست؛ تاریخ پیگیری محاسبه نشد.")
        return _resolve(kind, m, phrase, base)
    return None


def _resolve(kind: str, m: re.Match, phrase: str, base: jdatetime.date) -> FollowUpTime:
    td = jdatetime.timedelta
    if kind == "today":
        return FollowUpTime(phrase, base, "همان روز بازدید.")
    if kind == "tomorrow":
        return FollowUpTime(phrase, base + td(days=1), "یک روز پس از تاریخ بازدید.")
    if kind == "after_tomorrow":
        return FollowUpTime(phrase, base + td(days=2), "دو روز پس از تاریخ بازدید.")
    if kind == "n_days":
        n = words_to_int(m.group(1))
        if n is None or not 0 < n <= 90:
            return FollowUpTime(phrase, None, "تعداد روز قابل تفسیر نبود.")
        return FollowUpTime(phrase, base + td(days=n), f"{n} روز پس از تاریخ بازدید.")
    if kind == "n_weeks":
        n = words_to_int(m.group(1))
        if n is None or not 0 < n <= 12:
            return FollowUpTime(phrase, None, "تعداد هفته قابل تفسیر نبود.")
        return FollowUpTime(phrase, base + td(days=7 * n), f"{n} هفته پس از تاریخ بازدید.")
    if kind == "weekday_next_week":
        wd = WEEKDAYS[m.group(1)]
        target = _start_of_week(base) + td(days=7 + wd)
        return FollowUpTime(phrase, target, "روز گفته‌شده در هفته بعد (هفته از شنبه شروع می‌شود).")
    if kind == "weekday":
        wd = WEEKDAYS[m.group(1)]
        delta = (wd - _iran_weekday(base)) % 7
        if delta == 0:
            return FollowUpTime(phrase, None, "روز گفته‌شده همان روز بازدید است؛ معلوم نیست همین هفته یا هفته بعد.")
        return FollowUpTime(phrase, base + td(days=delta), "نزدیک‌ترین روز هم‌نام پس از بازدید.")
    if kind == "next_week":
        return FollowUpTime(phrase, None, "«هفته بعد» روز مشخصی ندارد؛ تاریخ دقیق محاسبه نشد.")
    if kind == "next_month":
        return FollowUpTime(phrase, None, "«ماه بعد» روز مشخصی ندارد؛ تاریخ دقیق محاسبه نشد.")
    return FollowUpTime(phrase, None, "عبارت زمانی کلی است؛ تاریخ دقیق محاسبه نشد.")


_FILENAME_DATE_PATTERNS = [
    # WhatsApp Audio 2026-10-20 at 19.02.11 / audio_2026-10-20_19-02-11
    re.compile(r"(20\d\d)[-_.](\d\d)[-_.](\d\d)"),
    # PTT-20261020-WA0001 / AUD-20261020-WA0001 / Recording_20261020_...
    re.compile(r"(?<!\d)(20\d\d)(\d\d)(\d\d)(?!\d)"),
]
_FILENAME_JALALI = re.compile(r"(?<!\d)(14\d\d)[-_.]?(\d\d)[-_.]?(\d\d)(?!\d)")


def date_from_filename(name: str) -> jdatetime.date | None:
    """استخراج تاریخ از نام فایل‌های رایج پیام‌رسان‌ها و ضبط صدا."""
    name = to_ascii_digits(name)
    m = _FILENAME_JALALI.search(name)
    if m:
        try:
            return jdatetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    for pat in _FILENAME_DATE_PATTERNS:
        m = pat.search(name)
        if m:
            try:
                return from_gregorian(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except ValueError:
                continue
    return None
