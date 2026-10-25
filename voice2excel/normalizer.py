"""نرمال‌سازی متن فارسی.

متن خام هرگز تغییر نمی‌کند؛ این توابع نسخه‌ای جداگانه برای پردازش و نمایش می‌سازند.
"""
from __future__ import annotations

import re

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ٱ": "ا",
    "إ": "ا", "أ": "ا", "ٲ": "ا", "ؤ": "و",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "ـ": None,  # کشیده
    "\u200f": None, "\u200e": None, "\ufeff": None,
    " ": " ", " ": " ", " ": " ",
    "٬": ",", "٫": ".",
})
# اعراب
_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭ]")
_ZWNJ = "\u200c"
_MULTI_SPACE = re.compile(r"[ \t]+")
_ZWNJ_AROUND_SPACE = re.compile(r" *‌+ *")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([،,.؛;:!?؟])")
_PUNCT_NO_SPACE = re.compile(r"([،؛؟])(?=\S)")

_TO_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# پیشوند و پسوندهایی که با نیم‌فاصله نوشته می‌شوند
_MI_PREFIX = re.compile(r"(?<![\w‌])(ن?می) (?=[؀-ۿ]{2,})")
_HA_SUFFIX = re.compile(r"(?<=[؀-ۿ]{2}) (ها|های|هایی|هایش|هاشون|هامون|تر|ترین)(?![؀-ۿ])")


def to_ascii_digits(text: str) -> str:
    return str(text).translate(_TO_ASCII_DIGITS)


def to_persian_digits(text: str) -> str:
    return str(text).translate(_TO_PERSIAN_DIGITS)


def normalize_chars(text: str) -> str:
    """یکسان‌سازی حروف عربی/فارسی، ارقام و حذف اعراب و کشیده."""
    if not text:
        return ""
    text = str(text).translate(_CHAR_MAP)
    return _DIACRITICS.sub("", text)


def normalize_spaces(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZWNJ_AROUND_SPACE.sub(lambda m: " " if " " in m.group(0) else _ZWNJ, text)
    text = re.sub(_ZWNJ + "{2,}", _ZWNJ, text)
    lines = [_MULTI_SPACE.sub(" ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _PUNCT_NO_SPACE.sub(r"\1 ", text)
    return text.strip()


def fix_half_spaces(text: str) -> str:
    """اصلاح نیم‌فاصله در «می» و «ها» که در خروجی گفتار رایج است."""
    text = _MI_PREFIX.sub(lambda m: m.group(1) + _ZWNJ, text)
    return _HA_SUFFIX.sub(lambda m: _ZWNJ + m.group(1), text)


def normalize_text(text: str) -> str:
    """نرمال‌سازی کامل برای ذخیره در فیلد «متن نرمال‌شده»."""
    return normalize_spaces(fix_half_spaces(normalize_spaces(normalize_chars(text))))


# --- کلید مقایسه برای نام‌ها (فقط برای جست‌وجو؛ هرگز نمایش داده یا ذخیره به‌جای اصل نمی‌شود) ---

# حروفی که در خروجی گفتار به‌جای هم نوشته می‌شوند
_PHONETIC = str.maketrans({
    "ث": "س", "ص": "س", "ذ": "ز", "ض": "ز", "ظ": "ز", "ط": "ت", "ح": "ه", "غ": "ق",
    "آ": "ا", "ع": "ا", "ء": None, _ZWNJ: None, " ": None, "-": None, ".": None,
})
_TITLES = re.compile(r"^(مهندس|مندس|آقای|اقای|آقا|اقا|خانم|خانوم|دکتر|جناب|سرکار|حاج|حاجی)\s+")


def strip_title(name: str) -> tuple[str, str]:
    """جداکردن عنوان (مهندس/آقای/...) از نام. خروجی: (عنوان، نام)."""
    name = normalize_text(name)
    m = _TITLES.match(name)
    if not m:
        return "", name
    title = m.group(1)
    title = {"مندس": "مهندس", "اقای": "آقای", "اقا": "آقا", "خانوم": "خانم"}.get(title, title)
    return title, name[m.end():].strip()


def sound_key(text: str) -> str:
    """کلید آوایی کل متن (بدون حذف عنوان)؛ برای نام خیابان‌ها («حاجی آبادی» ≠ «عبادی»)."""
    return normalize_chars(normalize_text(text)).translate(_PHONETIC).strip()


def match_key(text: str) -> str:
    """کلید مقایسه آوایی برای تشخیص املاهای محتمل نام شخص (عنوان «مهندس/آقای» حذف می‌شود)."""
    _, bare = strip_title(text)
    return normalize_chars(bare).translate(_PHONETIC).strip()
