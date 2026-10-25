"""واژگان شناخته‌شده (خیابان‌ها و نام مهندس‌ها) برای موتور استخراج و یکسان‌سازی املا.

از واژه‌نامه کاربر (فایل‌های اکسل و تأییدها) و داده پایه نشانی‌های شهر (geo) ساخته می‌شود و دو کار می‌کند:
1. ترتیب: وقتی «سجادیه 58» در متن آمد، آدرس از همان‌جا آغاز می‌شود، حتی اگر واژه «آدرس» گفته
   نشده یا آدرس جای دیگری از ویس آمده باشد؛ نام شناخته‌شده بدون «مهندس» هم نام شناخته می‌شود.
2. املا: نامی که با املای دیگری از یک نام شناخته‌شده هم‌آواست («فلاهی»، «سجا دیه») به املای
   واژه‌نامه («فلاحی»، «سجادیه») برمی‌گردد. فقط هم‌آوای دقیق و یکتا؛ شباهت تقریبی فقط پیشنهاد است.

قواعد احتیاط:
- نامی که هم خیابان است و هم نام شخص («مطهری») یا واژه عمومی است، فقط با «عدد» پشتش خیابان شمرده می‌شود.
- واژه‌نامه کاربر بر داده پایه مقدم است: املای کاربر برنده است و خیابان‌های داده پایه نام‌های
  مهندس کاربر را مبهم نمی‌کنند.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache

from .normalizer import match_key, sound_key, strip_title

MAX_WORDS = 3
_L = "ء-غف-يٱ-ۓ‌"  # حروف و نیم‌فاصله (بدون ویرگول و نشانه‌های عربی که در همان بازه یونیکدند)
_TOKEN = re.compile(rf"[{_L}]+|\d[\d/]*|[^\s{_L}\d]")
_SHORT_NUMBER = re.compile(r"\d{1,4}(?:/\d{1,3})?")
# واژه‌هایی که پیش از نام خیابان می‌آیند؛ مرز بند پیش از آن‌ها گذاشته می‌شود
_LEAD_WORDS = {"آدرس", "آدرسش", "آدرسشون", "نشانی", "خیابان", "خیابون", "بلوار", "بولوار", "نبش", "انتهای",
               "ابتدای", "جنب", "روبروی", "روبه‌روی", "میدان", "میدون", "کوی", "شهرک", "و"}
# پس از نام خیابان می‌آیند («امامت پلاک 8»)
_AFTER_STREET = {"پلاک", "قطعه", "نبش", "کوچه", "بن‌بست", "انتهای", "ابتدای", "جنب", "روبروی", "روبه‌روی"}
# عددی که پس از این واژه‌ها بیاید، جزو مشخصات فنی است نه آدرس
_TECH_BEFORE_NUMBER = {"تعداد", "تا", "سقف", "طبقه", "واحد", "متر", "متری", "سازه", "شماره"}
# «رضایی 2 تا پروژه»: عددی که واحد شمارش پشتش آمده، شماره خیابان نیست
_UNIT_AFTER_NUMBER = {"تا", "سقف", "طبقه", "واحد", "متر", "متری", "روز", "ماه", "سال", "ساعت", "بار", "نفر",
                      "تومن", "تومان", "میلیون", "دقیقه", "هفته", "پروژه", "ساختمان"}


@lru_cache(maxsize=1)
def _common_keys() -> frozenset[str]:
    from . import extractor as x
    from .numbers_fa import NUMBER_WORDS

    words = (x.NAME_STOP | x._FILLER | set(x.TECH_WORDS) | set(x.STREET_WORDS) | set(x.TITLES) | set(x.ADDRESS_CUES)
             | set(x.NAME_CUES) | set(x.CITIES) | set(x.BUILDING_TYPES) | set(NUMBER_WORDS) | x._ORDINALS
             | _LEAD_WORDS | _AFTER_STREET | _TECH_BEFORE_NUMBER | _UNIT_AFTER_NUMBER
             | {"سمت", "راست", "چپ", "صفر", "سفر", "سد", "صف"})
    return frozenset(sound_key(w) for w in words)


def _phrase(words: list[str]) -> str | None:
    return " ".join(words) if words and all(_is_word(w) for w in words) else None


@dataclass
class Lexicon:
    # کلید آوایی ← املاهای استاندارد (برای یکسان‌سازی املا)
    street_spell: dict[str, set[str]] = field(default_factory=dict)
    engineer_spell: dict[str, set[str]] = field(default_factory=dict)
    # همه املاهای ثبت‌شده (استاندارد و شکل‌های دیگر)؛ املای ثبت‌شده هرگز تغییر داده نمی‌شود
    street_names: set[str] = field(default_factory=set)
    engineer_names: set[str] = field(default_factory=set)
    # خیابان‌ها جز واژه‌های عمومی (با عدد پشتشان خیابان‌اند، حتی اگر نام شخص هم باشند)
    shared_keys: set[str] = field(default_factory=set)
    # کلیدهای قابل‌اتکا بدون عدد (نه واژه عمومی، نه مشترک میان خیابان و نام شخص)
    street_keys: set[str] = field(default_factory=set)
    engineer_keys: set[str] = field(default_factory=set)
    # نام‌های کوچک رایج («علی کازمی» ← هر واژه جدا یکسان می‌شود)
    first_spell: dict[str, set[str]] = field(default_factory=dict)
    first_names: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, entries, base=(), base_names=((), ())) -> "Lexicon":
        """entries: [(نوع، املای استاندارد، املای ثبت‌شده)] از واژه‌نامه کاربر؛ base: [(خیابان، شکل‌های دیگر)]؛
        base_names: (نام‌خانوادگی‌های رایج، نام‌های کوچک رایج)."""
        lex = cls()
        for etype, canonical, alias in entries:
            if etype not in ("street", "engineer"):
                continue
            street = etype == "street"
            spell, names, key = ((lex.street_spell, lex.street_names, sound_key) if street else
                                 (lex.engineer_spell, lex.engineer_names, match_key))
            for n in (canonical, alias):
                if n:
                    names.add(n)
                    spell.setdefault(key(n), set()).add(canonical)
        user_streets = set(lex.street_spell)
        for canonical, aliases in base:
            for n in (canonical, *aliases):
                k = sound_key(n)
                if k in user_streets:
                    continue  # املای واژه‌نامه کاربر مقدم است
                lex.street_names.add(n)
                lex.street_spell.setdefault(k, set()).add(canonical)
        surnames, first = base_names
        user_engineers = set(lex.engineer_spell)
        for n in surnames:
            k = match_key(n)
            if k not in user_engineers:  # املای واژه‌نامه کاربر مقدم است
                lex.engineer_names.add(n)
                lex.engineer_spell.setdefault(k, set()).add(n)
        for n in first:
            lex.first_names.add(n)
            lex.first_spell.setdefault(match_key(n), set()).add(n)
        common = _common_keys()
        good = {k for k in set(lex.street_spell) | set(lex.engineer_spell) if len(k) >= 3 and k not in common}
        lex.shared_keys = {k for k in lex.street_spell if k in good}
        lex.street_keys = {k for k in lex.shared_keys if k not in lex.engineer_spell}
        lex.engineer_keys = {k for k in lex.engineer_spell if k in good and k not in user_streets}
        return lex

    def __bool__(self) -> bool:
        return bool(self.street_spell or self.engineer_spell)

    # ---------- تشخیص ترتیب ----------
    @staticmethod
    def _len_at(words: list[str], i: int, keys: set[str]) -> int:
        """تعداد واژه‌های نامی از keys که از words[i] آغاز می‌شود (بلندترین؛ ۰ یعنی هیچ)."""
        for n in range(min(MAX_WORDS, len(words) - i), 0, -1):
            p = _phrase(words[i:i + n])
            if p and sound_key(p) in keys:
                return n
        return 0

    def _street_then_number(self, words: list[str], i: int) -> int:
        """«سجادیه 58»: خیابان + عدد کوتاه (نه «رضایی 2 تا»)."""
        n = self._len_at(words, i, self.shared_keys)
        if not n or i + n >= len(words) or not _SHORT_NUMBER.fullmatch(words[i + n]):
            return 0
        after = words[i + n + 1] if i + n + 1 < len(words) else ""
        return 0 if after in _UNIT_AFTER_NUMBER else n

    def _ends_with_street(self, words: list[str], j: int) -> bool:
        """آیا واژه‌های پیش از words[j] به نام خیابانی (حتی هم‌نام با شخص) ختم می‌شوند؟
        نامِ پس از عنوان («مهندس رحیمی») خیابان حساب نمی‌شود."""
        from .extractor import TITLES

        for n in range(1, min(MAX_WORDS, j) + 1):
            if j - n > 0 and words[j - n - 1] in TITLES:
                break
            p = _phrase(words[j - n:j])
            if p and sound_key(p) in self.street_spell:
                return True
        return False

    def starts_with_street(self, text: str) -> bool:
        """«سجادیه 58، قطعه دوم» یا «امامت پلاک 8»: بند با خیابان شناخته‌شده آغاز می‌شود."""
        words = [m.group(0) for m in _TOKEN.finditer(text)]
        i = 1 if words[:1] == ["و"] else 0
        if self._street_then_number(words, i):
            return True
        n = self._len_at(words, i, self.street_keys)
        return bool(n) and i + n < len(words) and words[i + n] in _AFTER_STREET

    def is_engineer(self, text: str) -> bool:
        words = [w for w in (m.group(0) for m in _TOKEN.finditer(text)) if _is_word(w)]
        return 1 <= len(words) <= MAX_WORDS and match_key(" ".join(words)) in self.engineer_keys

    def street_cuts(self, text: str, protected: list[tuple[int, int]] = ()) -> list[int]:
        """مکان آغاز آدرس‌هایی که بدون مرز روشن به بند قبلی چسبیده‌اند.

        «مهندس رجبی سجادیه 58» ← مرز پیش از «سجادیه»؛ «سازه فلز 7 سقف خیابان امامت 60» ← پیش از «خیابان».
        مرز گذاشته نمی‌شود اگر نام خیابان پس از عنوان آمده باشد («مهندس مطهری») یا ادامه آدرس قبلی باشد
        («فلاحی 34 فاطمیه 5»).
        """
        from .extractor import TITLES

        toks = list(_TOKEN.finditer(text))
        words = [m.group(0) for m in toks]
        cuts: list[int] = []
        for i in range(len(words)):
            if not self._street_then_number(words, i):
                continue
            if any(a <= toks[i].start() < b for a, b in protected):
                continue
            j = i
            while j > 0 and words[j - 1] in _LEAD_WORDS:
                j -= 1
            prev = words[j - 1] if j > 0 else ""
            if prev in TITLES:
                continue
            if prev and prev[0].isdigit() and not (j > 1 and words[j - 2] in _TECH_BEFORE_NUMBER):
                continue  # ادامه آدرس («فلاحی 34 فاطمیه 5») یا شمارش («2 واحدی 110 متری»)؛ ولی «تعداد 7 سجادیه 58» مرز دارد
            if self._ends_with_street(words, j):
                continue  # ادامه آدرس: «بلوار جانباز مهدی 32»
            if j > 0:
                cuts.append(toks[j].start())
        return cuts

    # ---------- یکسان‌سازی املا ----------
    @staticmethod
    def _canonical(name: str, spell: dict[str, set[str]], known: set[str], key) -> str | None:
        if not name or name in known:
            return None
        k = key(name)
        cands = spell.get(k, set())
        if len(cands) > 1:
            # «فلاحی» و «شهید فلاحی» (شکل کوتاهش «فلاحی»): نامی که خودش همان صدا را دارد مقدم است
            cands = {c for c in cands if key(c) == k} or cands
        if len(cands) != 1:
            return None  # ناشناخته یا مبهم (دو نام هم‌آوا)
        canon = next(iter(cands))
        return canon if canon != name else None

    def canonical_engineer(self, bare: str) -> str | None:
        """املای واژه‌نامه برای کل نام؛ اگر کل نام شناخته نبود، هر واژه جدا («علی کازمی» ← «علی کاظمی»)."""
        whole = self._canonical(bare, self.engineer_spell, self.engineer_names, match_key)
        if whole and _letters(whole) == _letters(bare):
            return None  # «حسن زاده» و «حسن‌زاده» هر دو درست‌اند؛ سبک نوشتن کاربر حفظ می‌شود
        words = bare.split()
        if whole or not 2 <= len(words) <= MAX_WORDS or bare in self.engineer_names:
            return whole
        fixed = [w if w in self.engineer_names or w in self.first_names else
                 self._canonical(w, self.engineer_spell, self.engineer_names, match_key)
                 or self._canonical(w, self.first_spell, self.first_names, match_key) or w for w in words]
        return " ".join(fixed) if fixed != words else None

    def fix_streets(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """نام خیابان‌های پیش از هر عدد را به املای واژه‌نامه برمی‌گرداند. خروجی: (متن، [(قبلی، جدید)])."""
        toks = list(_TOKEN.finditer(text))
        words = [m.group(0) for m in toks]
        repl: list[tuple[int, int, str, str]] = []
        for k, w in enumerate(words):
            if not w[0].isdigit():
                continue
            for n in range(min(MAX_WORDS, k), 0, -1):
                if not _phrase(words[k - n:k]):
                    continue
                a, b = toks[k - n].start(), toks[k - 1].end()
                phrase = text[a:b]
                if phrase in self.street_names:
                    break
                canon = self._canonical(phrase, self.street_spell, self.street_names, sound_key)
                if canon:
                    repl.append((a, b, phrase, canon))
                    break
        changes = []
        for a, b, old, new in reversed(repl):
            text = text[:a] + new + text[b:]
            changes.append((old, new))
        return text, changes[::-1]


def _letters(s: str) -> str:
    return re.sub(r"[\s‌]", "", s)


def _is_word(w: str) -> bool:
    return bool(w) and not w[0].isdigit() and re.fullmatch(rf"[{_L}]+", w) is not None


def unify_spelling(values: dict, lex: Lexicon, rec=None) -> dict:
    """املای نام مهندس و خیابان‌ها مطابق واژه‌نامه (فقط هم‌آوای دقیق و یکتا)."""
    out = dict(values)

    def note(field: str, old: str, new: str) -> None:
        if rec is not None and field in rec.fields:
            rec.fields[field].notes.append(f"املای «{old}» مطابق واژه‌نامه به «{new}» یکسان شد.")

    name = values.get("engineer_name")
    if name:
        title, bare = strip_title(name)
        canon = lex.canonical_engineer(bare)
        if canon:
            out["engineer_name"] = f"{title} {canon}".strip()
            note("engineer_name", bare, canon)
    for f in ("address", "street"):
        if values.get(f):
            out[f], changes = lex.fix_streets(values[f])
            for old, new in changes:
                note(f, old, new)
    return out


# ---------- ساخت از واژه‌نامه (با حافظه موقت) ----------
_cache: dict = {"sig": None, "lex": None}
_cache_lock = threading.Lock()


def get_lexicon(db, base: bool = True) -> Lexicon:
    """واژگان فعلی؛ فقط وقتی واژه‌نامه تغییر کرده باشد دوباره ساخته می‌شود.

    base: داده پایه نشانی‌های شهر هم در کنار واژه‌نامه کاربر به کار رود.
    """
    from .geo import base_names, base_streets

    sig = (str(db.path), base, tuple(db.one(
        "SELECT (SELECT COUNT(*) FROM aliases) a, (SELECT COALESCE(MAX(id), 0) FROM aliases) b, "
        "(SELECT COUNT(*) FROM entities) c, (SELECT COALESCE(MAX(id), 0) FROM entity_changes) d").values()))
    with _cache_lock:
        if _cache["sig"] != sig:
            rows = db.q("SELECT e.type, e.canonical, a.alias FROM entities e JOIN aliases a ON a.entity_id=e.id "
                        "WHERE e.type IN ('street', 'engineer')")
            _cache["lex"] = Lexicon.build(((r["type"], r["canonical"], r["alias"]) for r in rows),
                                          base_streets() if base else (), base_names() if base else ((), ()))
            _cache["sig"] = sig
        return _cache["lex"]
