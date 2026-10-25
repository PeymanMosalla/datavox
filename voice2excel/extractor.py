"""موتور استخراج اطلاعات از متن ویس.

روش: متن به بندهای کوچک شکسته می‌شود (با نشانه‌گذاری و واژه‌های آغازگر مثل «شماره»،
«آدرس»، «سازه»)، هر بند بر اساس معنا و جایگاهش دسته‌بندی می‌شود و سپس فیلدها از
بندهای مربوط استخراج می‌شوند. اگر چند ساختمان در یک ویس معرفی شده باشد، هر کدام
رکورد جداگانه می‌شود. هیچ مقداری که در متن نیامده ساخته نمی‌شود.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import jdatetime

from . import phone as phone_mod
from .asr_fixes import fix_asr_text
from .dates_fa import find_followup_time, format_jalali
from .normalizer import normalize_text
from .numbers_fa import NumberRun, convert_number_words
from .schema import ExtractedRecord, ExtractionResult, FieldValue, PhoneInfo, Segment

# با هر تغییر در قواعد استخراج افزایش می‌یابد؛ برنامه پس از به‌روزرسانی، رکوردهای دست‌نخورده را دوباره استخراج می‌کند
EXTRACTOR_VERSION = "6"

W = r"[\w‌]"  # نویسه‌ی واژه (شامل نیم‌فاصله)
B_START = rf"(?<!{W})"
B_END = rf"(?!{W})"

TITLES = ["حاج آقا", "مهندس", "مندس", "آقای", "اقای", "آقا", "اقا", "خانم", "خانوم", "دکتر", "حاجی", "حاج"]
TITLE_CANON = {"مندس": "مهندس", "اقای": "آقای", "اقا": "آقا", "خانوم": "خانم", "حاجی": "حاج"}
NAME_CUES = ["اسمشون", "اسمشان", "اسمش", "اسم", "نام", "کارفرما", "صاحب‌کار", "صاحبکار", "مالک"]
ADDRESS_CUES = ["آدرسشون", "آدرسش", "آدرس", "نشانی"]
STREET_WORDS = [
    "خیابان", "خیابون", "بلوار", "بولوار", "کوچه", "پلاک", "نبش", "میدان", "میدون", "بزرگراه",
    "اتوبان", "جاده", "شهرک", "قطعه", "محله", "منطقه", "روبروی", "روبه‌روی", "جنب", "انتهای",
    "ابتدای", "کوی", "بلوک", "تقاطع", "چهارراه", "فلکه", "فرعی", "حاشیه",
]
TECH_WORDS = [
    "سازه", "سازش", "سقف", "طبقه", "واحد", "اسکلت", "فونداسیون", "فنداسیون", "دیوار", "بتن", "بتون",
    "فلز", "فلزی", "اجرا", "استارت", "نازک", "سفت", "آماده", "متراژ", "زیربنا", "گودبرداری", "تیرچه",
    "پروانه", "مجوز", "نقشه", "مسکونی", "تجاری", "اداری",
]
PROJECT_CUES = ["گروه ساختمانی", "پروژه", "مجتمع", "برج", "شرکت"]
FOLLOWUP_CUES = [
    "قرار شد", "قرار شده", "قراره", "پیگیری", "تماس بگیرین", "تماس بگیرید", "تماس بگیرن", "تماس بگیر",
    "زنگ بزنین", "زنگ بزنید", "زنگ بزنن", "زنگ بزن", "هماهنگ کنین", "هماهنگ کنید", "بفرستین", "بفرستید",
    "باید صبر کنیم", "صبر کنیم", "بعدا تماس", "بعداً تماس", "دوباره تماس", "مجدد تماس",
]
NOTE_CUES = ["توضیحات", "ضمنا", "ضمناً", "در ضمن", "نکته"]

_PREPOSITIONS = {"رو", "را", "به", "از", "با", "برای", "پیش", "که", "خود", "خودِ", "توسط", "طرف", "مال", "ماله"}
NAME_STOP = set(
    """هست هستن هستند هستش است بود بودن میشه می‌شه شماره تلفن موبایل همراه آدرس نشانی پروژه سازه تعداد که و
    از با رو را برای به گفت گفتن گفته میگه می‌گه میگن می‌گن اسم نام کارفرما ساختمان پلاک خیابان بلوار کوچه نبش
    تو توی داخل هم همه اینه این اون آن دارن داره داد دادن نیستن نیست نمیدونن نمی‌دونن نمیدونم نمی‌دونم فامیلشو
    فامیلش فامیلی ایشون ایشان خودشون خود سرپرست نگهبان جوشکار جوشکاره کارگاه پیمانکار صاحب‌کار صاحبکار مالک
    شون ها هستیم بودند گفتند فرمودن بودش بله آره نه سلام خب خوب ببخشید یعنی بعد قبل الان""".split()
)
CITIES = [
    "مشهد", "تهران", "اصفهان", "شیراز", "تبریز", "کرج", "قم", "اهواز", "کرمانشاه", "ارومیه", "رشت", "زاهدان",
    "کرمان", "همدان", "یزد", "اردبیل", "بندرعباس", "اراک", "زنجان", "قزوین", "سنندج", "خرم‌آباد", "گرگان",
    "ساری", "بجنورد", "بیرجند", "سبزوار", "نیشابور", "قوچان", "تربت حیدریه", "تربت‌حیدریه", "چناران",
    "طرقبه", "شاندیز", "گناباد", "کاشمر", "فریمان", "سرخس", "تربت جام", "بابل", "آمل", "کاشان", "ساوه",
]
BUILDING_TYPES = [
    "مجتمع مسکونی", "مجتمع تجاری", "تجاری مسکونی", "مسکونی", "تجاری", "اداری", "ویلایی", "ویلا",
    "آپارتمان", "درمانی", "آموزشی", "صنعتی", "هتل", "بیمارستان",
]

_NEW_BLOCK_RE = re.compile(
    rf"{B_START}(?:(?:پروژه|ساختمان|مورد|آدرس)\s*(?:ی\s*)?(?:دوم|سوم|چهارم|پنجم|بعدی|دیگه|دیگر|دیگشون)"
    rf"|(?:یه|یک)\s+(?:پروژه|ساختمان)\s+(?:دیگه|دیگر))"
)


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


# واژه‌هایی که پیش از آن‌ها بند جدید آغاز می‌شود، و واژه‌هایی که اگر پیش از آن‌ها بیایند، شکستن انجام نمی‌شود
_SPLIT_MARKERS: list[tuple[list[str], set[str]]] = [
    (["شماره", "تلفن", "موبایل"], {"این", "اون", "همین", "که", "و", "پلاک", "یه", "یک", "تا", "رو", "دو", "خود"}),
    (ADDRESS_CUES, {"اسم", "نام", "این", "اون", "همین"}),
    (TITLES, _PREPOSITIONS | {"اسم", "اسمشون", "اسمش", "نام", "شماره", "تلفن", "آقای", "آقا", "اقا", "اسم", "حاج", "این", "اون", "و"}),
    (["اسمشون", "اسمش", "اسم"], {"این", "و"}),
    (["گروه ساختمانی", "پروژه", "مجتمع"], {"آدرس", "اسم", "نام", "شماره", "این", "اون", "همین", "سر", "تو", "توی", "داخل", "کل", "مهندس", "یه", "یک", "دو", "از"}),
    (["سازه", "تعداد", "اسکلت"], {"نوع"}),
    (["ساختمان"], {"آدرس", "این", "اون", "همین", "تو", "توی", "داخل", "سر", "یه", "یک", "اسم", "نام", "شماره", "و"}),
    (["مسکونی", "تجاری", "اداری", "ویلایی"], {"ساختمان", "مجتمع", "پروژه", "و", "واحد", "بخش"}),
    # «قرار شد» و «پیگیری» جمله تازه‌ای آغاز می‌کنند؛ «زنگ بزنین» معمولاً پایان جمله‌ای است که زمانش قبل از آن آمده
    (["قرار شد", "قرار شده", "پیگیری"], {"برای", "و"}),
    (NOTE_CUES, set()),
]
_MARKER_RE = re.compile(rf"{B_START}({_alt(sum((m for m, _ in _SPLIT_MARKERS), []))}){B_END}")
_FOLLOWUP_RE = re.compile(rf"{B_START}(?:{_alt(FOLLOWUP_CUES)})")
_MARKER_EXCEPTIONS = {}
for _words, _exc in _SPLIT_MARKERS:
    for _w in _words:
        _MARKER_EXCEPTIONS[_w] = _exc


@dataclass
class Clause:
    text: str
    start: int
    end: int
    category: str = "note"
    block: int = 0
    consumed: list[tuple[int, int]] = field(default_factory=list)  # بخش‌های مصرف‌شده نسبت به text


def split_clauses(text: str, extra_cuts: list[int] | tuple = ()) -> list[Clause]:
    """شکستن متن به بند. ویرگول مرز بند نیست، چون Whisper گاهی میان همه واژه‌ها ویرگول می‌گذارد
    («مهندس، کازمی، شماره، ...»)؛ مرزها از نقطه و واژه‌های آغازگر (شماره، آدرس، سازه، ...) می‌آیند.

    extra_cuts: مکان‌های اضافه برای شکستن؛ ابتدا و انتهای شماره‌های تلفن، تا وقتی بازاریاب واژه «شماره» و
    «آدرس» را نمی‌گوید («مهندس رجبی، صفر نهصد…، سجادیه ۵۸»)، نام، شماره و آدرس از هم جدا شوند.
    """
    clauses: list[Clause] = []
    for m in re.finditer(r"[^.؛;!?؟\n]+", text):
        piece, base = m.group(0), m.start()
        cuts = [0] + [c - base for c in extra_cuts if base < c < base + len(piece)]
        for mm in _MARKER_RE.finditer(piece):
            if mm.start() == 0:
                continue
            before = piece[:mm.start()].split()
            prev = before[-1] if before else ""
            if prev in _MARKER_EXCEPTIONS.get(mm.group(1), set()):
                continue
            if not piece[:mm.start()].strip():
                continue
            cuts.append(mm.start())
        # جمله پیگیری («... دوشنبه هفته بعد زنگ بزنین») از ویرگولِ پیش از خودش جدا می‌شود
        for mm in _FOLLOWUP_RE.finditer(piece):
            comma = max(piece.rfind("،", 0, mm.start()), piece.rfind(",", 0, mm.start()))
            if comma > 0 and piece[:comma].strip() and comma + 1 not in cuts:
                cuts.append(comma + 1)
        cuts = sorted(set(cuts))
        cuts.append(len(piece))
        for a, b in zip(cuts, cuts[1:]):
            seg = piece[a:b]
            stripped = seg.strip(" \t،,")
            if not stripped:
                continue
            offset = base + a + (len(seg) - len(seg.lstrip(" \t،,")))
            clauses.append(Clause(stripped, offset, offset + len(stripped)))
    return clauses


def _starts_with(text: str, words) -> str | None:
    m = re.match(rf"^(?:و\s+|هم\s+)?({_alt(words)}){B_END}", text)
    return m.group(1) if m else None


def _contains(text: str, words) -> bool:
    return re.search(rf"{B_START}(?:{_alt(words)})", text) is not None


def _digit_count(text: str) -> int:
    return len(re.findall(r"\d", text))


def _looks_like_address(text: str) -> bool:
    if _contains(text, STREET_WORDS):
        return True
    return _starts_like_street(text) and _digit_count(text) <= 12


def _starts_like_street(text: str) -> bool:
    """«سجادیه 58، قطعه دوم» یا «فلاحی 34 فاطمیه 5»: نام (نه واژه فنی) + عدد کوتاه."""
    if _starts_with(text, TECH_WORDS + ["تعداد", "سازه"] + TITLES + NAME_CUES):
        return False
    return re.match(r"^[؀-ۿ‌ ]{2,30}\s\d{1,4}(?:[\s،,.]|$)", text) is not None


_GREETING = {"سلام", "الو", "درود", "خب", "خوب", "ببخشید", "عرض", "کنم", "بله", "آره", "وقت", "بخیر", "و"}
_GREETING_RE = re.compile(rf"^(?:(?:{_alt(_GREETING)})[\s،,.:]*)+(?=\S)")


def _strip_greeting(text: str) -> str:
    """«سلام، کاظمی» ← «کاظمی»: واژه‌های احوال‌پرسی آغاز بند جزو نام نیستند."""
    return _GREETING_RE.sub("", text)


def _looks_like_bare_name(text: str) -> bool:
    """«رجبی» یا «علی میرزایی» بدون عنوان: ۱ تا ۳ واژه، بدون عدد، بدون واژه کلیدی."""
    words = [w.strip("،,.:") for w in text.split() if w.strip("،,.:")]
    if not 1 <= len(words) <= 3 or re.search(r"\d", text):
        return False
    return not any(w in NAME_STOP or w in _FILLER or _contains(w, TECH_WORDS + STREET_WORDS + ADDRESS_CUES)
                   for w in words)


def classify(clauses: list[Clause], lexicon=None) -> None:
    """دسته‌بندی بندها. اولویت با واژه‌های کلیدی است؛ سپس خیابان‌ها و نام‌های شناخته‌شده واژه‌نامه
    (lexicon، در هر جای ویس)؛ اگر نبودند، ترتیب قالب ضبط (نام ← شماره ← آدرس ← مشخصات فنی) و الگوی متن."""
    prev = None
    for idx, c in enumerate(clauses):
        t = c.text
        nxt = clauses[idx + 1].text if idx + 1 < len(clauses) else ""
        cat = None
        if _starts_with(t, NOTE_CUES):
            cat = "note"
        elif _contains(t, FOLLOWUP_CUES):
            cat = "followup"
        elif _starts_with(t, ADDRESS_CUES):
            cat = "address"
        elif _starts_with(t, ["شماره", "تلفن", "موبایل", "همراه"]) and not re.match(r"^شماره\s+پلاک", t):
            cat = "phone" if _digit_count(t) >= 4 else "phone_cue"
        elif _starts_with(t, TITLES) or _starts_with(t, NAME_CUES):
            cat = "name"
        elif _starts_with(t, PROJECT_CUES):
            cat = "project"
        elif _digit_count(t) >= 7 and len(re.sub(r"[\d\s\-+،,]", "", t)) <= 3:
            cat = "phone"
        elif lexicon and lexicon.starts_with_street(t):
            cat = "address"  # خیابان شناخته‌شده + عدد یا پلاک: «سجادیه 58» پس از مشخصات فنی هم آدرس است
        elif lexicon and _looks_like_bare_name(_strip_greeting(t)) and lexicon.is_engineer(_strip_greeting(t)):
            cat = "name"  # نام شناخته‌شده بدون «مهندس»
        elif prev in (None, "note") and idx <= 1 and _looks_like_bare_name(_strip_greeting(t)) and _is_phone_like(nxt):
            cat = "name"  # «رجبی، صفر نهصد…»: نام بدون «مهندس» درست پیش از شماره
        elif prev in ("name", "phone", "phone_cue") and _starts_like_street(t):
            cat = "address"  # آدرس بدون واژه «آدرس»، پس از نام یا شماره (حتی اگر مشخصات فنی هم پشتش آمده باشد)
        elif _contains(t, TECH_WORDS) and not _starts_with(t, STREET_WORDS):
            cat = "tech"
        elif _starts_with(t, STREET_WORDS) or _contains(t, CITIES):
            cat = "address"
        elif prev in ("address",) and _looks_like_address(t):
            cat = "address"
        elif prev == "phone_cue" and _digit_count(t) >= 4:
            cat = "phone"
        elif prev in (None, "name", "phone", "phone_cue") and _looks_like_address(t):
            cat = "address"
        else:
            cat = "note"
        c.category = cat
        prev = cat


def _is_phone_like(text: str) -> bool:
    return _digit_count(text) >= 7 and len(re.sub(r"[\d\s\-+،,]", "", text)) <= 3


def assign_blocks(clauses: list[Clause]) -> int:
    """تقسیم بندها میان ساختمان‌ها. ساختمان تازه فقط وقتی آغاز می‌شود که نشانه روشنی باشد:
    «پروژه دوم/بعدی»، آدرس دوم، یا نام دوم پس از آن‌که ساختمان فعلی نام و آدرس/مشخصات دارد."""
    block = 0
    has_address = has_tech = has_name = False
    for c in clauses:
        explicit_new = _NEW_BLOCK_RE.search(c.text) is not None
        new_block = False
        if explicit_new and (has_address or has_tech):
            new_block = True
        elif c.category == "address" and _starts_with(c.text, ADDRESS_CUES) and has_address:
            new_block = True
        elif (c.category == "name" and has_name and (has_address or has_tech)
              and _starts_with(c.text, TITLES + NAME_CUES)):
            new_block = True
        if new_block:
            block += 1
            has_address = has_tech = has_name = False
        c.block = block
        if c.category == "address":
            has_address = True
        elif c.category == "tech":
            has_tech = True
        elif c.category == "name":
            has_name = True
    return block + 1


# ---------- استخراج فیلدها ----------

_TITLE_RE = re.compile(rf"{B_START}({_alt(TITLES)}){B_END}")
_NAME_CUE_RE = re.compile(rf"^(?:و\s+)?(?:{_alt(NAME_CUES)})(?:\s+(?:کارفرما|پروژه|ایشون))?(?:\s*(?:هم|:))?\s+")
_ORDINALS = {"اول", "دوم", "سوم", "چهارم", "پنجم", "اولی", "دومی", "سومی", "بعدی", "دیگه", "دیگر", "قبلی"}


def _name_tokens(rest: str) -> list[str]:
    out = []
    for tok in rest.split():
        clean = tok.strip("،,.:؛")
        if not clean:
            continue  # ویرگولِ تنها (رایج در خروجی Whisper)
        if re.search(r"\d", clean) or clean in NAME_STOP:
            break
        if re.search(r"(?:شون|شان)$", clean) and len(clean) > 4:
            break
        if not re.fullmatch(r"[؀-ۿ‌]+", clean):
            break
        out.append(clean)
        if len(out) == 3:
            break
    return out


def extract_name(clauses: list[Clause]) -> tuple[str, str, Clause, list[str]] | None:
    """خروجی: (عنوان، نام، بند مبدأ، توضیحات)."""
    for c in clauses:
        if c.category in ("note", "followup", "tech"):
            continue
        t = c.text
        # «اسمشون افشین ...» یا «اسم مهندس رجبی»
        m = _NAME_CUE_RE.match(t)
        title = ""
        if m:
            rest = t[m.end():]
            tm = re.match(rf"^({_alt(TITLES)}){B_END}\s*", rest)
            if tm:
                title, rest = tm.group(1), rest[tm.end():]
        else:
            tm = _TITLE_RE.search(t)
            if tm:
                before = t[:tm.start()].split()
                if before and before[-1] in _PREPOSITIONS:
                    continue
                title, rest = tm.group(1), t[tm.end():]
            elif c.category == "name":
                rest = _strip_greeting(t)  # نام بدون عنوان که از جایگاهش یا از واژه‌نامه تشخیص داده شد
            else:
                continue
        tokens = _name_tokens(rest)
        if not tokens:
            continue
        title = TITLE_CANON.get(title, title)
        notes = []
        tail = rest[len(" ".join(tokens)):].strip()
        if re.search(r"فامیل\S*\s+(?:رو\s+)?(?:نمی‌?\s?دون|نمیدون|ندار)", tail):
            notes.append("نام خانوادگی گفته نشده است.")
        name_span = (t.find(tokens[0]), t.find(tokens[-1]) + len(tokens[-1]))
        c.consumed.append((0, name_span[1]))
        return title, " ".join(tokens), c, notes
    return None


def extract_project(clauses: list[Clause]) -> tuple[str, Clause] | None:
    for c in clauses:
        if c.category != "project":
            continue
        m = re.match(rf"^(?:و\s+)?({_alt(PROJECT_CUES)})\s+(?:اسمش\s+|به\s+اسم\s+|به\s+نام\s+)?", c.text)
        if not m:
            continue
        cue = m.group(1)
        tokens = []
        for tok in c.text[m.end():].split():
            clean = tok.strip("،,.:؛")
            if (not clean or clean in NAME_STOP or clean in _ORDINALS or re.search(r"\d", clean)
                    or _contains(clean, TECH_WORDS + STREET_WORDS + ADDRESS_CUES)):
                break
            tokens.append(clean)
            if len(tokens) == 4:
                break
        if not tokens:
            continue
        name = " ".join(tokens)
        value = name if cue == "پروژه" else f"{cue} {name}"
        c.consumed.append((0, m.end() + len(name)))
        return value, c
    return None


_ADDR_LEAD = re.compile(rf"^(?:و\s+)?(?:{_alt(ADDRESS_CUES)})(?:\s+(?:پروژه|ساختمان|کارگاه|ایشون))?(?:\s*(?:هم|:|اینه|هست))*\s*")
_ADDR_TAIL = re.compile(r"(?:^|\s)(?:هست|هستش|است|میشه|می‌شه|اینه|بود|هستن)[\s،,]*$")
_ADDR_TECH_CUT = re.compile(
    r"[،,]?\s*(?:\d+\s*(?:تا\s*)?(?:سقف|طبقه|واحد)|(?<![\w‌])(?:سازه|سازش|اسکلت|تعداد|فونداسیون|"
    r"تازه\s*(?:استارت|شروع)|مسکونی|تجاری|اداری|ساختمان)(?![\w‌]))"
)
_ADDR_KEYWORD_COMMA = re.compile(r"(خیابان|خیابون|بلوار|بولوار|کوچه|پلاک|قطعه|نبش|میدان|میدون|کوی|شهرک)\s*[،,]\s*")
_ADDR_WORD_NUM_COMMA = re.compile(r"([؀-ۿ‌])\s*[،,]\s*(\d)")


def _clean_address(t: str) -> str:
    """حذف ویرگول‌های بی‌جای خروجی گفتار: «خیابان، امامت، 60، پلاک، 18» ← «خیابان امامت 60، پلاک 18»."""
    t = _ADDR_KEYWORD_COMMA.sub(r"\1 ", t)
    t = _ADDR_WORD_NUM_COMMA.sub(r"\1 \2", t)
    t = re.sub(r"\s*[،,]\s*", "، ", t)
    return re.sub(r"\s+", " ", t).strip(" ،,")


def extract_address(clauses: list[Clause]) -> tuple[str, str, dict[str, str], list[int] | None] | None:
    parts, evidence, used = [], [], []
    for c in clauses:
        if c.category != "address":
            continue
        t = _ADDR_LEAD.sub("", c.text.strip(" ،,"))
        # اگر مشخصات فنی بدون واژه آغازگر پشت آدرس آمده («سجادیه 58، 7 سقف…»)، آدرس همان‌جا تمام می‌شود
        cut = _ADDR_TECH_CUT.search(t)
        if cut and cut.start() > 0:
            t = t[:cut.start()]
        t = _clean_address(_ADDR_TAIL.sub("", t))
        c.consumed.append((0, len(c.text)))
        if t:
            parts.append(t)
            evidence.append(c.text)
            used.append(c)
    if not parts:
        return None
    address = " ، ".join(parts)
    return address, " ، ".join(evidence), address_components(address), _span(used)


def address_components(address: str) -> dict[str, str]:
    comp: dict[str, str] = {}
    m = re.search(rf"{B_START}({_alt(CITIES)}){B_END}", address)
    if m:
        comp["city"] = m.group(1)
    m = re.search(r"(?:محله|منطقه|شهرک|کوی)\s+([^\s،,]+(?:\s+\d+)?)", address)
    if m:
        comp["neighborhood"] = m.group(0)
    m = re.search(r"(?:خیابان|خیابون|بلوار|بولوار)\s+([^\d،,]+?)(?:\s+(\d+))?(?=\s*[،,]|\s+(?:پلاک|کوچه|نبش|قطعه)|$)", address)
    if m:
        comp["street"] = m.group(0).strip()
    else:
        m = re.match(r"^([؀-ۿ‌ ]{2,30}?)\s+(\d{1,4})(?=\s|$|[،,])", address)
        if m and not _starts_with(m.group(1), ["پلاک", "کوچه", "قطعه"]):
            comp["street"] = m.group(0).strip()
    m = re.search(r"(?:کوچه|فرعی)\s+([^\s،,]+(?:\s+\d+)?)", address)
    if m:
        comp["alley"] = m.group(0)
    plates = re.findall(r"(?:پلاک\s*\d+|قطعه\s+[^\s،,]+)", address)
    if plates:
        comp["plate"] = " ، ".join(plates)
    return comp


# --- فنی ---
_EXEC_N = re.compile(
    r"(\d+)\s*(?:تا\s*)?(?:سقف|طبقه)(?:‌?(?:ش|شون|اش))?\s*(?:رو\s*|را\s*)?(?:هم\s*)?"
    r"(?:اجرا|ریخته|زده|بسته|احرا)\s*(?:شده|کردن|کرده|کردند|شدن|شده‌اند)"
)
_EXEC_ALL = re.compile(
    r"(?:همه\s*(?:ی\s*)?)?(?:سقف‌?(?:ها|ا)|سقفها)(?:‌?(?:ش|شون))?\s*"
    r"(?:و\s*(?:دیوار‌?(?:ها|ا)?|دیوارها)\s*)?(?:هم\s*)?(?:کامل\s*)?(?:اجرا|ریخته|زده|احرا)\s*شده"
)
_WALLS = re.compile(
    r"(?:سقف|دیوار)‌?(?:ها|ا)?\s*و\s*(?:سقف|دیوار)‌?(?:ها|ا)?\s*(?:هم\s*)?(?:اجرا\s*)?شده"
)
_FLOORS = re.compile(r"(?:تعداد\s*)?(\d+)\s*(?:تا\s*)?(سقف|طبقه)(?!‌?(?:ها|ا))")
_UNITS = re.compile(r"(?:تعداد\s*)?(\d+)\s*(?:تا\s*)?واحد")
_STRUCT = re.compile(
    r"(?:سازه|سازش|سازه‌اش|ساز|اسکلت)(?:\s*(?:ی|اش|ش|شون))?\s*(?:هم\s*)?(?:از\s*نوع\s*)?"
    r"(فلزی|فلز|آهنی|آهن|بتنی|بتن|بتونی|بتون)"
)
_STAGE_PATTERNS = [
    r"تازه\s*(?:استارت|شروع)\s*(?:خورده|شده|کردن|کرده)",
    r"(?:در\s*(?:مرحله\s*(?:ی\s*)?|حال\s*)?)?(?:گودبرداری|فونداسیون|فنداسیون|سفت‌?\s*کاری|نازک‌?\s*کاری|"
    r"دیوار\s*چینی|دیوارچینی|نما\s*کاری|نماکاری|تاسیسات|گچ‌?\s*کاری|کاشی‌?\s*کاری)"
    r"(?:\s*(?:هستن|هستند|است|هست|شده|میکنن|می‌کنن|هستش))?",
    r"(?:کار\s*|ساختمان\s*|پروژه\s*)?(?:تقریبا|تقریباً)\s*آماده\S*",
    r"کار\s*آماده\S*",
    r"در\s*حال\s*اجرای\s*اسکلت|اسکلت\s*(?:کار\s*)?(?:تموم|تمام)\s*شده",
]
_STAGE = re.compile("|".join(f"(?:{p})" for p in _STAGE_PATTERNS))
_BTYPE = re.compile(rf"{B_START}({_alt(BUILDING_TYPES)}){B_END}")
_PERMIT = re.compile(rf"{B_START}(?:پروانه|مجوز|جواز|نقشه)")
_NEED = re.compile(r"نیاز\s*(?:دارن|دارند|داره|دارد)|لازم\s*(?:دارن|دارند|داره)|احتیاج|می‌?\s?خوان|میخوان|دنبال\s+\S+\s+(?:هستن|هستند)")


def _struct_value(word: str) -> str:
    return "فلز" if word.startswith(("فلز", "آهن")) else "بتون"


def extract_tech(text: str) -> tuple[dict[str, str], list[tuple[int, int]]]:
    """استخراج ویژگی‌های فنی از متن یک ساختمان. خروجی: (فیلدها، بازه‌های مصرف‌شده)."""
    out: dict[str, str] = {}
    spans: list[tuple[int, int]] = []
    # ویرگول‌های میان واژه‌ها («تعداد 6، سقف») با فاصله هم‌طول جایگزین می‌شوند تا مکان‌ها حفظ شود
    masked = text.replace("،", " ").replace(",", " ")

    def mask(m):
        nonlocal masked
        spans.append(m.span())
        masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]

    m = _EXEC_N.search(masked)
    if m:
        unit = "طبقه" if "طبقه" in m.group(0) else "سقف"
        out["executed"] = f"{m.group(1)} {unit} اجرا شده"
        mask(m)
    else:
        m = _EXEC_ALL.search(masked)
        if m:
            out["executed"] = "سقف‌ها و دیوار اجرا شده" if "دیوار" in m.group(0) else "سقف‌ها اجرا شده"
            mask(m)
    m = _WALLS.search(masked)
    if m:
        out["executed"] = "سقف و دیوار اجرا شده"
        mask(m)
    m = _FLOORS.search(masked)
    if m:
        out["floors"] = m.group(1)
        out["floors_unit"] = m.group(2)
        mask(m)
    m = _UNITS.search(masked)
    if m:
        out["units"] = m.group(1)
        mask(m)
    m = _STRUCT.search(masked)
    if m:
        out["structure_type"] = _struct_value(m.group(1))
        mask(m)
    stages = []
    for m in list(_STAGE.finditer(masked)):
        stages.append(re.sub(r"\s+", " ", m.group(0)).strip())
        spans.append(m.span())
    if stages:
        out["stage"] = " ، ".join(dict.fromkeys(stages))
    m = _BTYPE.search(masked)
    if m:
        out["building_type"] = m.group(1)
        spans.append(m.span())
    return out, spans


_FILLER = set(
    """و هم که اینم این اون رو را هست است هستش دیگه خب خوب بله آره یعنی ببخشید سلام عرض کنم میشه می‌شه
    شماره تماس تلفن موبایل همراه شمارشون شماره‌شون شمارش آدرس آدرسش نشانی اسم نام اسمشون اسمش سازه تعداد
    پروژه مهندس آقای خانم ایشون ساختمان تا با ،""".split()
)


def _span(clauses: list[Clause]) -> list[int] | None:
    """بازه مشترک چند بند در متن پردازش‌شده."""
    return [min(c.start for c in clauses), max(c.end for c in clauses)] if clauses else None


def _remainder(text: str, spans: list[tuple[int, int]]) -> str:
    keep = list(text)
    for a, b in spans:
        for i in range(max(0, a), min(len(keep), b)):
            keep[i] = " "
    rest = re.sub(r"\s+", " ", "".join(keep)).strip(" ،,.")
    meaningful = [w for w in rest.split() if w not in _FILLER and not w.isdigit()]
    return rest if len(meaningful) >= 2 else ""


@dataclass
class _Ctx:
    text: str
    runs: list[NumberRun]
    base_date: jdatetime.date | None


def extract(raw_or_normalized: str, base_date: jdatetime.date | None = None, lexicon=None) -> ExtractionResult:
    """استخراج همه رکوردهای یک ویس از متن آن.

    lexicon: خیابان‌ها و نام‌های شناخته‌شده (lexicon.Lexicon)؛ بدون آن فقط قواعد عمومی به کار می‌روند.
    """
    normalized = fix_asr_text(normalize_text(raw_or_normalized))
    text, runs = convert_number_words(normalized)
    all_phones = phone_mod.phones_from_runs(text, runs)
    # شماره تلفن، بند مستقل است؛ مرزهایش حتی بدون واژه «شماره» یا «آدرس» نام و آدرس را جدا می‌کنند
    cuts = [x for p in all_phones if len(p.normalized) >= 10 for x in (p.start, p.end)]
    if lexicon:
        # «مهندس رجبی سجادیه 58»: آدرس از خیابان شناخته‌شده آغاز می‌شود
        cuts += lexicon.street_cuts(text, [(p.start, p.end) for p in all_phones])
    clauses = split_clauses(text, cuts)
    classify(clauses, lexicon)
    nblocks = assign_blocks(clauses) if clauses else 1

    records: list[ExtractedRecord] = []
    prev: ExtractedRecord | None = None
    for b in range(nblocks):
        bc = [c for c in clauses if c.block == b]
        rec = _extract_block(bc, all_phones, text, base_date, b, nblocks, prev)
        records.append(rec)
        prev = rec
    if not records:
        records = [ExtractedRecord()]
    if nblocks > 1:
        for r in records:
            r.ambiguities.append(f"در این ویس {nblocks} ساختمان تشخیص داده شد؛ جداسازی را بررسی کنید.")
    segments = [Segment(text=c.text, category=c.category, block=c.block) for c in clauses]
    return ExtractionResult(records=records, segments=segments, text=text)


def _extract_block(bc, all_phones, text, base_date, index, count, prev) -> ExtractedRecord:
    rec = ExtractedRecord(building_index=index, building_count=count)
    f = rec.fields
    if not bc:
        return rec
    span = (bc[0].start, bc[-1].end)

    # نام
    name = extract_name(bc)
    if name:
        title, bare, clause, notes = name
        rec.title = title
        f["engineer_name"] = FieldValue(value=f"{title} {bare}".strip(), evidence=clause.text, notes=notes,
                                        span=[clause.start, clause.end])
    elif prev and prev.get("engineer_name"):
        f["engineer_name"] = FieldValue(
            value=prev.get("engineer_name"), evidence=prev.fields["engineer_name"].evidence, inherited=True,
            notes=["نام در این بخش تکرار نشده و از ساختمان قبلی همین ویس برداشته شد."],
        )
        rec.title = prev.title

    # شماره
    block_phones = [p for p in all_phones if span[0] <= p.start <= span[1]]
    for c in bc:
        for p in block_phones:
            if c.start <= p.start <= c.end:
                c.consumed.append((p.start - c.start, p.end - c.start))
    if block_phones:
        rec.phones = [PhoneInfo(heard=p.heard, normalized=p.normalized, kind=p.kind, explicit=p.explicit,
                                ambiguous=p.ambiguous, notes=p.notes, from_words=p.from_words) for p in block_phones]
        ev = " ، ".join(c.text for c in bc if any(c.start <= p.start <= c.end for p in block_phones))
        f["phone"] = FieldValue(value="\n".join(p.normalized for p in block_phones), evidence=ev,
                                span=[min(p.start for p in block_phones), max(p.end for p in block_phones)])
    elif prev and prev.phones:
        rec.phones = [p.model_copy() for p in prev.phones]
        f["phone"] = FieldValue(
            value=prev.get("phone"), evidence=prev.fields["phone"].evidence, inherited=True,
            notes=["شماره در این بخش گفته نشده و از ساختمان قبلی همین ویس برداشته شد."],
        )

    # پروژه
    proj = extract_project(bc)
    if proj:
        f["project_name"] = FieldValue(value=proj[0], evidence=proj[1].text, span=[proj[1].start, proj[1].end])

    # آدرس
    addr = extract_address(bc)
    if addr:
        address, ev, comps, aspan = addr
        f["address"] = FieldValue(value=address, evidence=ev, span=aspan)
        for k, v in comps.items():
            f[k] = FieldValue(value=v, evidence=ev, span=aspan)

    # فنی: روی بندهای فنی و یادداشت‌ها (عبارت‌های فنی گاهی وسط توضیحات می‌آیند)
    tech_clauses = [c for c in bc if c.category in ("tech", "note", "project", "name", "address")]
    tech_found: dict[str, str] = {}
    tech_evidence: list[Clause] = []
    for c in tech_clauses:
        found, spans = extract_tech(c.text)
        for k, v in found.items():
            tech_found.setdefault(k, v)
        if found:
            tech_evidence.append(c)
            c.consumed.extend(spans)
            if c.category in ("note", "project", "name"):
                c.category = c.category if c.category != "note" else "tech"
    for k in ("executed", "floors", "units", "structure_type", "stage", "building_type"):
        if k in tech_found:
            f[k] = FieldValue(value=tech_found[k], evidence=" ، ".join(c.text for c in tech_evidence),
                              span=_span(tech_evidence))
    if "floors_unit" in tech_found and "floors" in f:
        f["floors_unit"] = FieldValue(value=tech_found["floors_unit"], evidence=f["floors"].evidence,
                                      span=f["floors"].span)

    # مجوز و نیاز مشتری
    for c in bc:
        if _PERMIT.search(c.text) and "permit_status" not in f:
            f["permit_status"] = FieldValue(value=c.text, evidence=c.text, span=[c.start, c.end])
            c.consumed.append((0, len(c.text)))
        elif _NEED.search(c.text) and "customer_need" not in f and c.category != "followup":
            f["customer_need"] = FieldValue(value=c.text, evidence=c.text, span=[c.start, c.end])
            c.consumed.append((0, len(c.text)))

    # پیگیری
    fu = [c for c in bc if c.category == "followup"]
    if fu:
        action = " ، ".join(c.text for c in fu)
        f["followup_action"] = FieldValue(value=action, evidence=action, span=_span(fu))
        for c in fu:
            c.consumed.append((0, len(c.text)))
    when = find_followup_time(" ، ".join(c.text for c in (fu or bc)), base_date)
    if when and (fu or re.search(r"تماس|زنگ|پیگیری|مراجعه|بازدید", " ".join(c.text for c in bc))):
        f["followup_time_text"] = FieldValue(value=when.text, evidence=when.text, notes=[when.reason])
        if when.date:
            f["followup_date"] = FieldValue(value=format_jalali(when.date), evidence=when.text, notes=[when.reason])
        if "followup_action" not in f:
            ctx = next((c.text for c in bc if when.text in c.text), when.text)
            f["followup_action"] = FieldValue(value=ctx, evidence=ctx)

    # توضیحات: هر چیزی که در فیلدهای دیگر جا نگرفت، کامل نگه داشته می‌شود
    notes = []
    for c in bc:
        if c.category in ("followup",):
            continue
        if c.category in ("address",) and c.consumed:
            continue
        if not c.consumed:
            if c.category in ("phone_cue",) or _remainder(c.text, []) == "":
                continue
            notes.append(c.text)
        else:
            rest = _remainder(c.text, c.consumed)
            if rest:
                notes.append(rest)
    if notes:
        f["notes"] = FieldValue(value=" ، ".join(notes), evidence=" ، ".join(notes))

    if len(rec.phones) > 1:
        rec.ambiguities.append(f"{len(rec.phones)} شماره برای این ساختمان گفته شده است.")
    return rec
