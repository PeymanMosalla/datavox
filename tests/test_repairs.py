"""اصلاح وسط حرف: مقدار دوم برداشته می‌شود؛ «نه» به معنی ۹ و «ببخشید» احوال‌پرسی دست نمی‌خورند."""
import pytest

from voice2excel.extractor import extract

BASE = "مهندس کاظمی شماره 09151112233 آدرس سجادیه 58"


def _f(text: str) -> tuple[dict, list[str], list[str]]:
    r = extract(text).records[0]
    vals = {k: fv.value for k, fv in r.fields.items()}
    notes = [n for fv in r.fields.values() for n in fv.notes if "اصلاح" in n]
    return vals, notes, [a for a in r.ambiguities if "اصلاح" in a]


@pytest.mark.parametrize("text, field, value", [
    # شماره کامل دوباره گفته شد (با واژه و با رقم)
    ("مهندس کاظمی شماره صفر نه یک پنج یک یک یک دو دو سه سه نه ببخشید صفر نه یک دو یک یک یک دو دو سه سه آدرس سجادیه 58",
     "phone", "09121112233"),
    ("مهندس کاظمی شماره 09151112233 اشتباه گفتم 09121112233 آدرس سجادیه 58", "phone", "09121112233"),
    # فقط گروه آخر شماره اصلاح شد
    ("مهندس کاظمی شماره 0915 111 22 33 ببخشید 34 آدرس سجادیه 58", "phone", "09151112234"),
    # نام، با تکرار عنوان
    ("مهندس کاظمی ببخشید مهندس کریمی شماره 09151112233 آدرس سجادیه 58", "engineer_name", "مهندس کریمی"),
    # آدرس، با تکرار نام خیابان
    ("مهندس کاظمی شماره 09151112233 آدرس فاطمی 5 ببخشید فاطمی 7", "address", "فاطمی 7"),
    ("مهندس کاظمی شماره 09151112233 آدرس سجادیه پلاک 34 اشتباه گفتم 43", "address", "سجادیه پلاک 43"),
    # فنی، با هم‌ترازی عدد و واژه
    (BASE + " تعداد 5 سقف نه ببخشید 6 سقف", "floors", "6"),
])
def test_second_value_wins_and_is_noted(text, field, value):
    vals, notes, amb = _f(text)
    assert vals[field] == value and notes and not amb


@pytest.mark.parametrize("text", [
    "سلام ببخشید مزاحم شدم " + BASE,                                       # احوال‌پرسی
    "مهندس کاظمی شماره صفر نه یک پنج یک یک یک دو دو سه سه آدرس سجادیه 58",  # «نه» یعنی ۹
    "مهندس کاظمی شماره نود و نه نه یک دو سه چهار پنج آدرس سجادیه 58",
    BASE + " ببخشید",                                                    # نشانه در پایان، بی‌مقدار دوم
    BASE + " ببخشید که دیر شد",
])
def test_no_false_corrections(text, monkeypatch):
    """خروجی دقیقاً همان است که بدون این بخش بود."""
    from voice2excel import repairs
    vals, notes, amb = _f(text)
    assert not notes and not amb
    monkeypatch.setattr(repairs, "prepare", lambda t: t)
    monkeypatch.setattr(repairs, "apply", lambda t, runs: (t, runs, []))
    assert _f(text)[0] == vals


def test_ambiguous_middle_group_goes_to_review_without_corrupting_address():
    vals, notes, amb = _f("مهندس کاظمی شماره 0915 111 22 33 ببخشید 112 آدرس سجادیه 58")
    assert vals["phone"] == "09151112233" and vals["address"] == "سجادیه 58"
    assert amb and "112" in amb[0] and not notes


def test_spoken_flag_kept_after_partial_fix():
    """شماره‌ای که با واژه گفته شده، پس از اصلاح هم «گفته‌شده با واژه» می‌ماند (تنظیم بازبینی شماره‌های گفتاری)."""
    r = extract("مهندس کاظمی شماره صفر نه یک پنج یک یک یک دو دو سه سه ببخشید سه چهار آدرس سجادیه 58").records[0]
    assert r.get("phone") == "09151112234" and r.phones[0].from_words
