from voice2excel.dates_fa import parse_jalali
from voice2excel.extractor import extract

BASE = parse_jalali("1405/07/28")  # سه‌شنبه


def one(text):
    r = extract(text, BASE)
    assert len(r.records) == 1, [x.fields for x in r.records]
    return {k: v.value for k, v in r.records[0].fields.items()}, r.records[0]


def test_standard_template_order():
    v, rec = one("مهندس رجبی شماره صفر نهصد و سی و هفت سیصد و چهل و پنج دوازده پنجاه و پنج "
                 "آدرس سجادیه پنجاه و هشت قطعه دوم سازه بتون هفت سقف سه سقفش اجرا شده")
    assert v["engineer_name"] == "مهندس رجبی"
    assert v["phone"] == "09373451255"
    assert v["address"] == "سجادیه 58 قطعه دوم"
    assert v["floors"] == "7" and v["structure_type"] == "بتون" and v["executed"] == "3 سقف اجرا شده"


def test_different_order_and_punctuation():
    v, _ = one("آدرس فلاحی 34 فاطمیه 5، مهندس نصیری، شماره 09151112233، تعداد 5 سقف، تازه استارت خورده")
    assert v["engineer_name"] == "مهندس نصیری"
    assert v["address"] == "فلاحی 34 فاطمیه 5"
    assert v["phone"] == "09151112233"
    assert v["stage"] == "تازه استارت خورده"


def test_new_unknown_name_accepted():
    v, _ = one("اسم مهندس بردیا زرین‌کلک. شماره 09121234567. آدرس خیابان امامت 60، پلاک 18")
    assert v["engineer_name"] == "مهندس بردیا زرین‌کلک"
    assert v["street"] == "خیابان امامت 60" and v["plate"] == "پلاک 18"


def test_side_notes_preserved():
    v, _ = one("مهندس نصیری شماره 09151112233 آدرس آزادی 73 تعداد 5 سقف. "
               "این شماره رو آقای عرفانیان داده و گفته بهشون بگین که آقای عرفانیان شماره رو داده")
    assert "عرفانیان" in v["notes"]
    assert v["engineer_name"] == "مهندس نصیری"  # نامِ داخل توضیحات، نام مهندس نیست


def test_followup_date_computed():
    v, _ = one("مهندس علی میرزایی شماره 09151234567 آدرس امامت 60. گفتن دوشنبه هفته بعد زنگ بزنین.")
    assert v["followup_time_text"] == "دوشنبه هفته بعد"
    assert v["followup_date"] == "1405/08/04"
    assert "زنگ بزنین" in v["followup_action"]


def test_followup_without_base_date_not_guessed():
    r = extract("مهندس رضایی شماره 09151234567. فردا زنگ بزنین", None)
    f = r.records[0].fields
    assert f["followup_time_text"].value == "فردا"
    assert "followup_date" not in f


def test_missing_fields_not_invented():
    v, _ = one("مهندس کاظمی گفتن فعلاً نیاز ندارن")
    assert "phone" not in v and "address" not in v


def test_multiple_buildings_separated():
    r = extract("مهندس عبدی شماره 09155554433 پروژه اول آدرس یوسف زاده 2 مظلوم 5 پلاک 11 سازه فلز 6 سقف. "
                "پروژه دوم آدرس خرمشهر 19 نبش هویزه 16 تعداد 7 سقف سه سقف اجرا شده", BASE)
    assert len(r.records) == 2
    a, b = r.records
    assert a.fields["address"].value.startswith("یوسف زاده 2")
    assert b.fields["address"].value.startswith("خرمشهر 19")
    assert b.fields["floors"].value == "7"
    # شماره و نامِ ساختمان دوم از ساختمان اول برداشته شده و علامت خورده است
    assert b.fields["phone"].inherited and b.fields["engineer_name"].inherited
    assert a.ambiguities and b.ambiguities


def test_full_transcript_kept_in_result():
    text = "مهندس رجبی شماره 09373451255 آدرس سجادیه 58"
    r = extract(text, BASE)
    assert r.text == text
    assert "".join(s.text for s in r.segments).replace(" ", "") == text.replace(" ", "")


def test_unknown_surname_note():
    v, _ = one("اسمشون افشین، فامیلشو نمیدونن. شماره نهصد و پونزده ۵۵۵ ۱۲ ۳۴. آدرس آزادی ۷۳")
    assert v["engineer_name"] == "افشین"
    assert v["phone"] == "09155551234"
    assert "فامیل" in v["notes"]


# ---- الگوهای ویس‌های واقعی (نام‌ها و رقم‌ها تغییر داده شده‌اند) ----

def test_no_cue_words_name_phone_address_in_template_order():
    # بازاریاب «شماره» و «آدرس» را نگفته؛ فقط ترتیب قالب را رعایت کرده
    v, _ = one("مهندس کریمی، سفر نه سد و سی و هفت، سیصد و چهل و پنج، دوازده، پنجا و پنج، "
               "سجادیه پنجا و هشت، قطعه دوم، سازه بتن، تعداد هفت سقف، سه سقف اجرا شده.")
    assert v["engineer_name"] == "مهندس کریمی"
    assert v["phone"] == "09373451255"
    assert v["address"] == "سجادیه 58، قطعه دوم"
    assert v["floors"] == "7" and v["executed"] == "3 سقف اجرا شده"
    assert "notes" not in v  # آدرس دیگر در ستون توضیحات نمی‌افتد


def test_phonetic_numbers_from_real_voice():
    # «نوود»، «چلا هشت»، «هیفته»، «بوتون»: املای آوایی مدل گفتار
    v, _ = one("مهندس گلستانی، سف نه سد و نوود و یک، پونسد و چلا هشت، پونزه بیست و پنج، "
               "شاهد هیفته، پلاک چارده، سازه بوتون، تعداد هفت سقف، چار سقف اجرا شده.")
    assert v["phone"] == "09915481525"
    assert v["address"] == "شاهد 17، پلاک 14"
    assert v["structure_type"] == "بتون" and v["executed"] == "4 سقف اجرا شده"


def test_bare_name_without_title_and_tech_after_address():
    v, _ = one("کریمی، صفر نهصد و پانزده، صد و بیست و سه، چهل و پنج، شصت و هفت، امامت شصت، پلاک هجده، هفت سقف، سقف‌ها اجرا شده")
    assert v["engineer_name"] == "کریمی"
    assert v["address"] == "امامت 60، پلاک 18"
    assert v["floors"] == "7"


def test_no_punctuation_at_all():
    v, _ = one("مهندس احمدی صفر نهصد و پانزده دویست و سی و چهار پنجاه و شش هفتاد و هشت "
               "سروش بیست و نه قطعه دوم سمت راست سازه بتنی تعداد شش سقف")
    assert v["phone"] == "09152345678"
    assert v["address"] == "سروش 29 قطعه دوم سمت راست"
    assert v["floors"] == "6" and v["structure_type"] == "بتون"


def test_real_words_not_turned_into_numbers():
    from voice2excel.asr_fixes import fix_asr_text
    assert "هفته" in fix_asr_text("دو هفته دیگه زنگ بزنین")
    assert "دوم" in fix_asr_text("قطعه دوم سه سقف")
    assert fix_asr_text("برای سفر رفته بودن") == "برای سفر رفته بودن"


def test_sarf_is_zero_not_part_of_name():
    # ویس مشتری: «صفر» آغاز شماره به‌صورت «صرف» شنیده شد و به انتهای نام چسبید
    for text, name, phone in [
        ("مهندس احمدی صرف نهصد و پانزده دویست و سی و چهار پنجاه و شش هفتاد و هشت آدرس سروش بیست و نه", "مهندس احمدی", "09152345678"),
        ("مهندس احمدی، صرف 915-234-56-78، آدرس سروش 29", "مهندس احمدی", "09152345678"),
        ("مهندس کاظمی سرف ۹۱۲ ۵۵۵ ۴۴ ۳۳ آدرس بلوار جانباز", "مهندس کاظمی", "09125554433"),
        ("مهندس نصیری شماره صرف نهصد و پانزده صد و یازده بیست و دو سی و سه", "مهندس نصیری", "09151112233"),
    ]:
        v, _ = one(text)
        assert v["engineer_name"] == name, text
        assert v["phone"] == phone, text


def test_sarf_as_real_word_unchanged():
    from voice2excel.asr_fixes import fix_asr_text
    assert fix_asr_text("صرف نظر از اینکه سازه فلزه") == "صرف نظر از اینکه سازه فلزه"
    assert "صرف" in fix_asr_text("بودجه صرف شده برای سقف")
