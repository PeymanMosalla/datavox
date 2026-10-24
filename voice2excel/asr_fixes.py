"""اصلاح خطاهای رایج و آوایی خروجی تشخیص گفتار فارسی.

Whisper عددهای گفتاری و برخی واژه‌های پرتکرار را آوایی و غلط می‌نویسد
(مثلاً «سفر ناسد سیو هفد» به‌جای «صفر نهصد و سی و هفت»). این اصلاح‌ها:
- فقط روی متن پردازش‌شده اعمال می‌شوند؛ متن خام ویس همیشه دست‌نخورده می‌ماند.
- فقط واژه‌های عمومی (عدد، سقف، آدرس، ...) را اصلاح می‌کنند، هرگز نام اشخاص یا خیابان‌ها را.
- واژه‌هایی که خودشان معنای دیگری دارند (مثل «سفر» یا «سد») فقط در کنار عددهای دیگر عدد حساب می‌شوند
  (این قاعده در numbers_fa اعمال می‌شود).
"""
from __future__ import annotations

import re

W = r"[\w‌]"

# شکل‌های آوایی عددها ← شکل درست
NUMBER_VARIANTS = {
    "سفر": "صفر", "صیفر": "صفر", "صف": "صفر",
    "ناسد": "نهصد", "نسد": "نهصد", "نحسد": "نهصد", "نهسد": "نهصد", "نوصد": "نهصد",
    "سیسد": "سیصد", "سی‌سد": "سیصد", "چارسد": "چارصد", "چهارسد": "چهارصد", "پانسد": "پانصد", "پونسد": "پونصد",
    "ششسد": "ششصد", "شیشسد": "شیشصد", "هفسد": "هفصد", "هفتسد": "هفتصد", "هشسد": "هشصد", "هشتسد": "هشتصد",
    "دویس": "دویست", "سد": "صد",
    "چیل": "چهل", "چهیل": "چهل",
    "پینج": "پنج", "پنش": "پنج", "پنچ": "پنج",
    "هفد": "هفت", "حفت": "هفت", "حفد": "هفت",
    "حشت": "هشت", "حشد": "هشت", "هشد": "هشت",
    "پنجا": "پنجاه", "شست": "شصت", "حفتاد": "هفتاد", "حشتاد": "هشتاد",
    "اجده": "هجده", "حجده": "هجده", "هیژده": "هجده",
    "دوزده": "دوازده", "پنزده": "پانزده", "پونزه": "پونزده",
}
# «چیلو»، «سیو»، «پنجو»: عدد + «و» چسبیده
_GLUED_VA_STEMS = (
    "صفر یک دو سه چهار چار پنج پینج شش شیش هفت هشت نه ده بیست سی چهل چیل پنجاه پنجا شصت شست هفتاد هشتاد نود "
    "صد سد دویست سیصد سیسد چهارصد پانصد پونصد ششصد هفتصد هفصد هشتصد هشصد نهصد ناسد نسد هزار"
).split()
# «سی سد»، «پنز ده»
_SPLIT_NUMBERS = [
    (r"(?:سی|سه)\s+(?:سد|صد)", "سیصد"), (r"(?:هف|هفت)\s+(?:سد|صد)", "هفتصد"), (r"(?:هش|هشت)\s+(?:سد|صد)", "هشتصد"),
    (r"نه\s+(?:سد|صد)", "نهصد"), (r"(?:چهار|چار)\s+(?:سد|صد)", "چهارصد"), (r"(?:پان|پون|پن)\s+(?:سد|صد)", "پانصد"),
    (r"(?:شش|شیش)\s+(?:سد|صد)", "ششصد"),
    (r"(?:پنز|پانز|پونز)\s+ده", "پانزده"), (r"(?:دواز|دوازد)\s+ده", "دوازده"), (r"یاز\s+ده", "یازده"),
    (r"سیز\s+ده", "سیزده"), (r"(?:چهار|چار)\s+ده(?=\s|$|[،,.])", "چهارده"), (r"(?:شانز|شونز)\s+ده", "شانزده"),
    (r"(?:هیف|هف)\s+ده", "هفده"), (r"(?:هیج|هج)\s+ده", "هجده"), (r"نوز\s+ده", "نوزده"),
]
# واژه‌های عمومی پرتکرار در ویس بازاریاب
WORD_FIXES = {
    "سخف": "سقف", "سقب": "سقف", "سفش": "سقفش", "سخفش": "سقفش", "سقفا": "سقف‌ها", "سفا": "سقف‌ها",
    "ادرس": "آدرس", "عدرس": "آدرس", "عدرز": "آدرس", "ادریز": "آدرس", "آدرز": "آدرس", "ادرسی": "آدرس",
    "محندس": "مهندس", "مهندسر": "مهندس", "مندس": "مهندس", "مهنس": "مهندس",
    "تیداد": "تعداد", "تهداد": "تعداد", "تداد": "تعداد",
    "بطن": "بتن", "بیتون": "بتون", "بتم": "بتن", "بیتن": "بتن", "بوتون": "بتون", "بوتن": "بتن", "بتونی": "بتنی",
    "فلضی": "فلزی", "فلض": "فلز",
    "فلزیت": "فلزی", "شماری": "شماره", "شمارهی": "شماره", "پلا": "پلاک",
    "ترار": "قرار", "غرار": "قرار",
    "سوام": "سوم", "سویم": "سوم",
    "قتعه": "قطعه","قتعی": "قطعه", "قطعی": "قطعه", "غطعه": "قطعه",
    "فندسیون": "فونداسیون", "فنداسیون": "فونداسیون", "فونداسیونش": "فونداسیون",
    "دیوارچینی‌شده": "دیوارچینی شده", "اجرا‌شده": "اجرا شده",
}
NUMBER_VARIANTS.update({
    "شهل": "چهل", "سیوزه": "سیزده", "دیویست": "دویست", "دوویست": "دویست", "نهسد": "نهصد", "پنسد": "پانصد",
    "هفتسد": "هفتصد", "شیشسد": "ششصد", "یاسده": "یازده",
    # شکل‌های دیده‌شده در ویس‌های واقعی و هم‌خانواده‌هایشان (هیچ‌کدام واژه معنادار فارسی نیستند)
    "هیفته": "هفده", "هیفتح": "هفده", "هیفدح": "هفده", "هفدح": "هفده", "هیفدا": "هفده", "هیوده": "هفده",
    "هیجته": "هجده", "هیژته": "هجده", "هژده": "هجده", "هیجدح": "هجده",
    "شونزته": "شانزده", "شونزدح": "شانزده", "شانزدح": "شانزده",
    "پونزته": "پانزده", "پانزدح": "پانزده", "پونزدح": "پانزده",
    "دوازدح": "دوازده", "دوازته": "دوازده", "سیزدح": "سیزده", "سیزته": "سیزده",
    "چاردح": "چهارده", "چارته": "چهارده", "یازدح": "یازده", "یازته": "یازده",
    "نوزدح": "نوزده", "نوزته": "نوزده",
    "نوود": "نود", "ناود": "نود", "نوت": "نود",
    "هفتات": "هفتاد", "هشتات": "هشتاد", "حفتات": "هفتاد", "حشتات": "هشتاد",
    "بیس": "بیست", "چیهل": "چهل",
    "پونسد": "پونصد", "پانسد": "پانصد", "شیشصد": "ششصد", "هشصد": "هشتصد",
    "نخصد": "نهصد", "نخسد": "نهصد",
})
# «نوت» در متن عادی معنای دیگری دارد؛ فقط کنار عدد
_CONTEXT_EXTRA = {"نوت", "بیس"}


def _segment_glued(word: str) -> list[str] | None:
    """«نهسدسی» ← [«نهصد»، «سی»]؛ «بیستوسی» ← [«بیست»، «و»، «سی»]. فقط اگر کل واژه به عددها شکسته شود."""
    from .numbers_fa import NUMBER_WORDS

    vocab = {**{w: w for w in NUMBER_WORDS}, **NUMBER_VARIANTS, "و": "و"}
    vocab = {k: v for k, v in vocab.items() if len(k) >= 2 or k == "و"}
    n = len(word)
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        if best[i] is None:
            continue
        for k, v in vocab.items():
            if word.startswith(k, i):
                cand = best[i] + [v]
                if best[i + len(k)] is None or len(cand) < len(best[i + len(k)]):
                    best[i + len(k)] = cand
    seg = best[n]
    if not seg or len(seg) < 2 or seg[0] == "و" or seg[-1] == "و":
        return None
    return seg


def _fix_glued_numbers(text: str) -> str:
    from .numbers_fa import NUMBER_WORDS

    def rep(m: re.Match) -> str:
        w = m.group(0)
        if w in NUMBER_WORDS or w in NUMBER_VARIANTS or len(w) < 5:
            return w
        seg = _segment_glued(w)
        return " ".join(seg) if seg else w

    return re.sub(r"[؀-ۿ]{5,}", rep, text)


def _word_sub(text: str, mapping: dict[str, str]) -> str:
    pat = re.compile(rf"(?<!{W})(" + "|".join(map(re.escape, sorted(mapping, key=len, reverse=True))) + rf")(?!{W})")
    return pat.sub(lambda m: mapping[m.group(1)], text)


_GLUED_RE = re.compile(rf"(?<!{W})(" + "|".join(sorted(_GLUED_VA_STEMS, key=len, reverse=True)) + rf")و(?!{W})")


# این شکل‌ها خودشان واژه معنادارند («سفر»، «صف»، «سد»، «شست») و فقط کنار عدد دیگر عدد حساب می‌شوند
CONTEXT_ONLY = {"سفر", "صف", "سد", "شست"} | _CONTEXT_EXTRA

# --- تطبیق شباهت برای واژه‌های ناشناخته‌ای که کنار عدد آمده‌اند ---
_PH = str.maketrans({"ص": "س", "ث": "س", "ح": "ه", "ط": "ت", "ذ": "ز", "ض": "ز", "ظ": "ز", "غ": "ق", "ع": "ا", "آ": "ا", "ی": "ی"})


def _num_key(w: str) -> str:
    """کلید آوایی: حروف هم‌صدا یکی و حروف تکراری فشرده («نوود» ← «نود»)."""
    w = w.translate(_PH)
    w = re.sub(r"(.)\1+", r"\1", w)
    return w.replace("ته", "ده") if w.endswith("ته") else w


# واژه‌های واقعی که کنار عدد می‌آیند و شبیه عددند؛ هرگز به عدد تبدیل نمی‌شوند («هفته» ≈ «هفده»، «دوم» ≈ «دو»)
_REAL_WORDS = set(
    """هفته هفتم هشتم دوم سوم چهارم پنجم ششم نهم دهم اول اولی دومی بیستم سقف سقفه سقفش طبقه طبقش واحد پلاک قطعه کوچه
    متر متری تعداد روز روزه ماه ماهه سال ساله دقیقه ساعت تومن تومان شماره نبش خیابان بلوار فرعی سمت راست چپ بعد قبل دیگه
    دیگر بعدی هستن هست شده اجرا سازه فلز بتن بتون نیم ربع""".split()
)


def _fuzzy_number(word: str) -> str | None:
    """اگر واژه‌ای بسیار شبیه یک عدد باشد (و یک گزینه به‌روشنی بهتر از بقیه)، همان عدد برگردانده می‌شود."""
    import difflib

    from .numbers_fa import NUMBER_WORDS

    if len(word) < 4 or word in _REAL_WORDS:
        return None
    key = _num_key(word)
    scored = sorted(((difflib.SequenceMatcher(None, key, _num_key(n)).ratio(), n) for n in NUMBER_WORDS), reverse=True)
    best, second = scored[0], scored[1]
    if best[0] >= 0.8 and best[0] - second[0] >= 0.08 and abs(len(best[1]) - len(word)) <= 2:
        return best[1]
    return None


def _fix_context_numbers(text: str) -> str:
    from .numbers_fa import NUMBER_WORDS, SCALES, TENS, HUNDREDS

    parts = re.split(r"(\s+)", text)
    words = [i for i, p in enumerate(parts) if p.strip()]

    def is_num(i: int) -> bool:
        w = parts[i].strip("،,.:؛")
        return bool(re.fullmatch(r"\d[\d\-]*", w)) or w in NUMBER_WORDS or w in NUMBER_VARIANTS or w == "و"

    def num_neighbor(k: int) -> bool:
        """آیا در یک یا دو واژه قبل/بعد (بدون احتساب «و») عددی هست؟"""
        for j in (k - 1, k + 1, k - 2, k + 2):
            if 0 <= j < len(words):
                w = parts[words[j]].strip("،,.:؛")
                if w == "و":
                    continue
                if is_num(words[j]) and w not in CONTEXT_ONLY:
                    return True
        return False

    tens_hundreds = set(TENS) | set(HUNDREDS)
    for k, i in enumerate(words):
        w = parts[i].rstrip("،,.:؛")
        tail = parts[i][len(w):]
        # «چلا هشت» = «چهل و هشت»: دهگان/صدگان + «ا» چسبیده، پیش از عدد دیگر
        if (w.endswith("ا") and w[:-1] in tens_hundreds and w not in NUMBER_WORDS and w not in NUMBER_VARIANTS
                and k + 1 < len(words) and is_num(words[k + 1])):
            parts[i] = w[:-1] + " و" + tail
            continue
        # واژه ناشناخته‌ای شبیه عدد، کنار عددهای دیگر («نوود»، «هیفدح»)
        if (re.fullmatch(r"[؀-ۿ]+", w or "-") and w not in NUMBER_WORDS and w not in NUMBER_VARIANTS
                and w not in SCALES and w not in ("سف", "صف") and w not in CONTEXT_ONLY and num_neighbor(k)):
            guess = _fuzzy_number(w)
            if guess:
                parts[i] = guess + tail
                continue
        if w in ("سف", "صف"):
            # «سف/صف» پس از عدد یعنی «سقف» (هفت سف)، پیش از عدد یعنی «صفر» (شماره سف نهصد)
            prev_num = k > 0 and is_num(words[k - 1])
            next_num = k + 1 < len(words) and is_num(words[k + 1])
            if next_num and not prev_num:
                parts[i] = "صفر" + tail
            elif prev_num or w == "سف":
                parts[i] = "سقف" + tail
            continue
        if w not in CONTEXT_ONLY:
            continue
        neighbors = [words[j] for j in (k - 1, k + 1) if 0 <= j < len(words)]
        if any(is_num(n) and parts[n].rstrip("،,.:؛") not in CONTEXT_ONLY and parts[n] != "و" for n in neighbors):
            parts[i] = NUMBER_VARIANTS[w] + tail
    return "".join(parts)


def fix_asr_text(text: str) -> str:
    text = _GLUED_RE.sub(lambda m: m.group(1) + " و", text)
    for pat, rep in _SPLIT_NUMBERS:
        text = re.sub(rf"(?<!{W}){pat}(?!{W})", rep, text)
    text = _word_sub(text, WORD_FIXES)
    text = _word_sub(text, {k: v for k, v in NUMBER_VARIANTS.items() if k not in CONTEXT_ONLY})
    text = _fix_glued_numbers(text)
    return _fix_context_numbers(text)
