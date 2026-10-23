"""تبدیل عددهای گفتاری فارسی (رسمی و محاوره‌ای) به رقم.

مثال: «صفر نهصد و پونزده صد و بیست و سه» ← گروه‌های «0»، «915»، «123».
گروه‌ها جداگانه نگه داشته می‌شوند تا شماره تلفن از کنار هم گذاشتن آن‌ها ساخته شود،
نه از جمع‌زدنشان. اگر مرز دو گروه روشن نباشد (مثلاً «نهصد پانزده» بدون «و»)،
اجرا به‌عنوان «مبهم» علامت می‌خورد.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

UNITS = {
    "صفر": 0,
    "یک": 1, "یه": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4, "چار": 4,
    "پنج": 5,
    "شش": 6, "شیش": 6,
    "هفت": 7, "هف": 7,
    "هشت": 8,
    "نه": 9,
}
TEENS = {
    "ده": 10, "یازده": 11, "یازه": 11, "دوازده": 12, "دوازه": 12,
    "سیزده": 13, "سیزه": 13, "چهارده": 14, "چارده": 14, "چهارد": 14,
    "پانزده": 15, "پونزده": 15, "پونزه": 15, "شانزده": 16, "شونزده": 16, "شونزه": 16,
    "هفده": 17, "هیفده": 17, "هیوده": 17, "هجده": 18, "هیجده": 18, "هیژده": 18,
    "نوزده": 19, "نوزه": 19,
}
TENS = {
    "بیست": 20, "سی": 30, "چهل": 40, "چل": 40, "پنجاه": 50, "پنجا": 50,
    "شصت": 60, "شست": 60, "هفتاد": 70, "هشتاد": 80, "نود": 90,
}
HUNDREDS = {
    "صد": 100, "یکصد": 100, "دویست": 200, "دویس": 200, "سیصد": 300,
    "چهارصد": 400, "چارصد": 400, "پانصد": 500, "پونصد": 500,
    "ششصد": 600, "شیشصد": 600, "شیشصت": 600, "هفتصد": 700, "هفصد": 700,
    "هشتصد": 800, "هشصد": 800, "نهصد": 900,
}
SCALES = {"هزار": 1000, "میلیون": 1_000_000}

NUMBER_WORDS: dict[str, int] = {**UNITS, **TEENS, **TENS, **HUNDREDS}

# واژه‌هایی که تنها، معنای غیرعددی رایج دارند («نه» = خیر، «یه» = یک‌عدد نامعین)
_AMBIGUOUS_ALONE = {"نه", "یه"}
# «سه راه»، «دو راهی» و «سه شنبه» نام مکان یا روزند، نه عدد
_NOT_NUMBER_BEFORE = {"راه", "راهی", "‌راهی", "شنبه"}

_LETTERS = r"[ء-غف-يٱ-ۓ‌]+"
_TOKEN = re.compile(rf"(?P<d>\d+)|(?P<w>{_LETTERS})|(?P<p>[^\s])")


@dataclass
class Token:
    text: str
    start: int
    end: int
    kind: str  # d=رقم، w=واژه، p=نشانه
    value: int | None = None  # برای واژه عددی
    suffix: str = ""  # مانند «تا» در «هفتا»


@dataclass
class NumberRun:
    """یک توالی پیوسته از عددها در متن."""

    start: int
    end: int
    groups: list[str]
    ambiguous: bool = False
    from_words: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def digits(self) -> str:
        return "".join(self.groups)


def _word_value(word: str) -> tuple[int | None, str]:
    if word in NUMBER_WORDS or word in SCALES:
        return (NUMBER_WORDS.get(word) if word in NUMBER_WORDS else SCALES[word]), ""
    # «هفتا»، «دوتا»، «سه‌تا»
    for stem, suffix in ((word[:-2].rstrip("‌"), "تا"), (word[:-1], "تا")):
        if word.endswith("تا") and stem in NUMBER_WORDS:
            return NUMBER_WORDS[stem], suffix
    return None, ""


def tokenize(text: str) -> list[Token]:
    tokens = []
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup
        tok = Token(m.group(0), m.start(), m.end(), kind)
        if kind == "w":
            tok.value, tok.suffix = _word_value(tok.text)
        tokens.append(tok)
    return tokens


def _is_num(t: Token) -> bool:
    return t.kind == "d" or (t.kind == "w" and t.value is not None)


def _can_append(current: int, v: int) -> bool:
    if current == 0:
        return False
    if v >= 1000:
        return False
    if current >= 1000 and current % 1000 == 0:
        return v < 1000
    rem = current % 1000
    if rem % 100 == 0 and rem > 0:
        return v < 100
    if rem % 10 == 0 and rem >= 20:
        return v < 10
    return False


def _words_to_groups(words: list[tuple[int, bool]]) -> tuple[list[str], bool]:
    """words: [(مقدار، آیا قبلش «و» آمده)] ← (گروه‌ها، مبهم)."""
    groups: list[str] = []
    current = 0
    started = False
    ambiguous = False

    def flush():
        nonlocal current, started
        if started:
            groups.append(str(current))
        current, started = 0, False

    for v, joined_by_va in words:
        if v == 0 and v not in SCALES.values():
            flush()
            groups.append("0")
            continue
        if v in (1000, 1_000_000) and started:
            # «دو هزار» یا «صد و بیست هزار»
            current = current * v
            continue
        if v in (1000, 1_000_000):
            flush()
            current, started = v, True
            continue
        if started and _can_append(current, v):
            if not joined_by_va:
                ambiguous = True  # «نهصد پانزده»: 915 یا 900 و 15؟
            current += v
            continue
        if started and joined_by_va:
            ambiguous = True  # «و» میان دو عدد ناسازگار
        flush()
        current, started = v, True
    flush()
    return groups, ambiguous


def find_number_runs(text: str) -> list[NumberRun]:
    """پیدا کردن توالی‌های عددی در متن نرمال‌شده (ارقام باید ASCII باشند)."""
    tokens = tokenize(text)
    runs: list[NumberRun] = []
    i = 0
    n = len(tokens)
    while i < n:
        if not _is_num(tokens[i]):
            i += 1
            continue
        # جمع‌کردن یک اجرای پیوسته
        items: list[tuple[Token, bool]] = []  # (توکن، قبلش «و» بوده)
        j = i
        va = False
        while j < n:
            t = tokens[j]
            if _is_num(t):
                items.append((t, va))
                va = False
                j += 1
                if t.suffix:  # «هفتا» پایان اجراست
                    break
                continue
            if t.text == "و" and items and j + 1 < n and _is_num(tokens[j + 1]) and items[-1][0].kind == "w" and tokens[j + 1].kind == "w":
                va = True
                j += 1
                continue
            if t.kind == "p" and t.text in "-–" and items and j + 1 < n and tokens[j + 1].kind == "d" and items[-1][0].kind == "d":
                j += 1
                continue
            # «صفر نهصد و سی و هفت، سیصد و چهل و پنج، دوازده»: ویرگول میان گروه‌های یک شماره
            if (t.kind == "p" and t.text in "،,." and items and j + 1 < n and _is_num(tokens[j + 1])
                    and not tokens[j + 1].suffix and len(items) >= 1):
                j += 1
                continue
            break
        # واژه تنها با معنای غیرعددی
        next_tok = tokens[j] if j < n else None
        if len(items) == 1 and items[0][0].kind == "w":
            w = items[0][0].text
            if w in _AMBIGUOUS_ALONE or (next_tok is not None and next_tok.text in _NOT_NUMBER_BEFORE):
                i = j
                continue
        groups: list[str] = []
        ambiguous = False
        from_words = False
        pending: list[tuple[int, bool]] = []
        for tok, joined in items:
            if tok.kind == "d":
                if pending:
                    g, a = _words_to_groups(pending)
                    groups += g
                    ambiguous |= a
                    pending = []
                groups.append(tok.text)
            else:
                from_words = True
                pending.append((tok.value, joined))
        if pending:
            g, a = _words_to_groups(pending)
            groups += g
            ambiguous |= a
        start = items[0][0].start
        end = items[-1][0].end
        runs.append(NumberRun(start, end, groups, ambiguous, from_words))
        i = j
    return runs


def convert_number_words(text: str) -> tuple[str, list[NumberRun]]:
    """جایگزینی عددهای حروفی با رقم. خروجی: (متن جدید، اجراهای عددی با مکان در متن جدید)."""
    runs = find_number_runs(text)
    out: list[str] = []
    new_runs: list[NumberRun] = []
    pos = 0
    for r in runs:
        out.append(text[pos:r.start])
        cursor = sum(len(s) for s in out)
        original = text[r.start:r.end]
        if r.from_words:
            replacement = " ".join(r.groups)
            suffix = _suffix_of(original)
            if suffix:
                replacement += " " + suffix
        else:
            replacement = original
        out.append(replacement)
        new_runs.append(NumberRun(cursor, cursor + len(replacement), r.groups, r.ambiguous, r.from_words))
        pos = r.end
    out.append(text[pos:])
    return "".join(out), new_runs


def _suffix_of(original: str) -> str:
    last = original.split()[-1] if original.split() else ""
    _, suffix = _word_value(last)
    return suffix


def words_to_int(text: str) -> int | None:
    """تبدیل یک عدد کوتاه (مثل «هفت» یا «۱۲») به عدد صحیح؛ اگر یک گروه نباشد None."""
    runs = find_number_runs(text.strip())
    if len(runs) == 1 and len(runs[0].groups) == 1:
        return int(runs[0].groups[0])
    return None
