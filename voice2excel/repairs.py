"""اصلاح وسط حرف: «شماره ۰۹۱۵… نه ببخشید ۰۹۱۲…» ← فقط مقدار دوم برداشته می‌شود.

نشانه اصلاح («ببخشید»، «اشتباه گفتم»، ...) فقط وقتی اصلاح حساب می‌شود که دو طرفش هم‌جنس باشند:
عدد پس از عدد، عنوان یا واژه کلیدی تکرارشده («مهندس … ببخشید مهندس …»، «خیابان … ببخشید بلوار …»)،
یا واژه تکرارشده («فاطمی ۵ ببخشید فاطمی ۷»، «۵ سقف ببخشید ۶ سقف»). «سلام ببخشید مزاحم شدم» دست نمی‌خورد.

«نه» به‌تنهایی نشانه نیست، چون همان عدد ۹ است («صفر نه یک پنج»).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .numbers_fa import NumberRun

_PUNCT = "،,.:؛;!?؟«»\"'()"
# «نه ببخشید» پیش از تبدیل عددها به «ببخشید» تبدیل می‌شود تا «نه» رقم ۹ خوانده نشود
_NO_SORRY = re.compile(r"(?<![\w‌])نه[\s،,]+ببخشید(?![\w‌])")
MARKERS = [("اشتباه", "گفتم"), ("اشتباه", "شد"), ("اشتباه", "کردم"), ("غلط", "گفتم"), ("غلط", "شد"), ("ببخشید",)]
HEAD_GROUPS = [
    {"مهندس", "مندس", "آقای", "اقای", "آقا", "اقا", "خانم", "خانوم", "دکتر", "حاج", "حاجی"},
    {"خیابان", "خیابون", "بلوار", "بولوار", "کوچه", "میدان", "میدون", "بزرگراه", "کوی", "شهرک", "پلاک", "قطعه"},
    {"شماره", "تلفن", "موبایل"},
    {"آدرس", "آدرسش", "نشانی"},
    {"اسم", "اسمشون", "اسمش", "نام"},
]
_ECHO_SKIP = {"و", "هم", "رو", "را", "که", "این", "اون", "به", "از", "با", "در"}
LOOKBACK = 8  # نشانه اصلاح فقط چند واژه پیش از خودش را می‌تواند پاک کند
PARTIAL_MAX = 4  # «… ۴۵ ۶۷ ببخشید ۶۸»: تکرار گروه آخر شماره


@dataclass
class Repair:
    pos: int        # جای مقدار درست در متن نهایی
    old: str        # آنچه اول گفته شد
    new: str        # آنچه جایش گفته شد
    applied: bool   # False: ابهام داشت و فقط برای بازبینی علامت خورد


def prepare(text: str) -> str:
    """پیش از تبدیل عددها."""
    return _NO_SORRY.sub("ببخشید", text)


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).strip(_PUNCT), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _is_digits(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:-\d+)*", tok))


def _marker_at(toks, i) -> int:
    """طول نشانه اصلاحی که از واژه i شروع می‌شود (۰ یعنی نیست)."""
    for m in MARKERS:
        if tuple(t[0] for t in toks[i:i + len(m)]) == m:
            return len(m)
    return 0


def _group_of(word: str) -> int | None:
    return next((g for g, words in enumerate(HEAD_GROUPS) if word in words), None)


def _plan(toks, i, n):
    """(شروع حذف، پایان حذف، متن جایگزین یا None، مقدار اول، مقدار دوم، قطعی؟) یا None."""
    lo = max(0, i - LOOKBACK)
    left, right = toks[lo:i], toks[i + n:]
    if not left or not right:
        return None
    # ۱) عدد پس از عدد (رقم‌های گفته‌شده تا آغاز همان عدد، بی‌محدودیت شمار واژه)
    if _is_digits(right[0][0]):
        k = i
        while k > 0 and _is_digits(toks[k - 1][0]):
            k -= 1
        rep = toks[k:i]
        if rep:
            fix = []
            for t in right:
                if not _is_digits(t[0]):
                    break
                fix.append(t)
            old = "".join(t[0] for t in rep).replace("-", "")
            new = "".join(t[0] for t in fix).replace("-", "")
            if len(new) >= len(old) or len(old) < 7 or len(new) >= 7:
                return rep[0][1], right[0][1], None, old, new, True
            groups = [len(t[0].replace("-", "")) for t in rep]
            if len(new) <= PARTIAL_MAX and (len(new) == groups[-1] or (len(groups) > 1 and len(new) == groups[-1] + groups[-2])):
                merged = old[:len(old) - len(new)] + new
                return rep[0][1], fix[-1][2], merged, old, merged, True
            # مبهم (مثلاً اصلاح گروه وسط): شماره اول می‌ماند، نشانه و عدد دوم از جریان بیرون می‌رود تا در آدرس نیفتد
            return toks[i][1], fix[-1][2], "", old, new, False
    # ۲) عنوان یا واژه کلیدی تکرارشده
    g = _group_of(right[0][0])
    if g is not None:
        for t in reversed(left):
            if _group_of(t[0]) == g:
                start = t[1]
                olds = [x[0] for x in left if x[1] >= start]
                return start, right[0][1], None, " ".join(olds), " ".join(x[0] for x in right[:len(olds)]), True
    # ۳) واژه تکرارشده (با هم‌ترازی: «۵ سقف ببخشید ۶ سقف»)
    for k, t in enumerate(right[:3]):
        if t[0] in _ECHO_SKIP or _is_digits(t[0]) or len(t[0]) < 2:
            continue
        for j in range(len(left) - 1, -1, -1):
            if left[j][0] == t[0] and j - k >= 0:
                start = left[j - k][1]
                olds = [x[0] for x in left[j - k:]]
                return start, right[0][1], None, " ".join(olds), " ".join(x[0] for x in right[:max(k + 1, len(olds))]), True
        break
    return None


def apply(text: str, runs: list[NumberRun]) -> tuple[str, list[NumberRun], list[Repair]]:
    """متن (پس از تبدیل عددها) با اصلاح‌های وسط حرف؛ عددها جابه‌جا می‌شوند و علامت «گفته‌شده با واژه» می‌ماند."""
    repairs: list[Repair] = []
    i = 0
    while True:
        toks = _tokens(text)
        found = None
        while i < len(toks):
            n = _marker_at(toks, i)
            if n:
                plan = _plan(toks, i, n)
                if plan:
                    found = plan
                    break
            i += 1
        if not found:
            return text, runs, repairs
        start, end, merged, old, new, sure = found
        insert = (merged + " ") if merged else ""
        if merged:
            touched = [r for r in runs if r.start < end and r.end > start]
            new_run = NumberRun(start=start, end=start + len(merged), groups=[merged],
                                from_words=any(r.from_words for r in touched))
        text = text[:start] + insert + text[end:]
        delta = len(insert) - (end - start)
        runs = [r if r.end <= start else replace(r, start=r.start + delta, end=r.end + delta)
                for r in runs if r.end <= start or r.start >= end]
        if merged:
            runs = sorted(runs + [new_run], key=lambda r: r.start)
        repairs.append(Repair(pos=start, old=old, new=new, applied=sure))
        i = len(_tokens(text[:start]))
