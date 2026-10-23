from voice2excel.normalizer import match_key, normalize_text, strip_title, to_ascii_digits
from voice2excel.numbers_fa import convert_number_words, find_number_runs, words_to_int
from voice2excel.phone import classify, compare_key, phones_from_runs


def test_digits_persian_arabic_english_unified():
    assert to_ascii_digits("۰۹۱۵ ٠٩١٥ 0915") == "0915 0915 0915"
    assert normalize_text("پلاک ۱۲ و ٣٤") == "پلاک 12 و 34"


def test_arabic_ya_kaf_normalized():
    assert normalize_text("مهندس كريمي") == "مهندس کریمی"
    assert normalize_text("علي") == "علی"


def test_spaces_and_half_spaces():
    assert normalize_text("  سقف   ها  اجرا   شده ") == "سقف‌ها اجرا شده"
    assert normalize_text("می شه") == "می‌شه"
    assert normalize_text("آدرس ، پلاک") == "آدرس، پلاک"


def test_raw_text_not_modified():
    raw = "مهندس كريمي ۰۹۱۵"
    normalize_text(raw)
    assert raw == "مهندس كريمي ۰۹۱۵"


def test_strip_title_and_match_key():
    assert strip_title("مهندس رجبی") == ("مهندس", "رجبی")
    assert strip_title("مندس صالحی") == ("مهندس", "صالحی")
    # حروف هم‌آوا کلید یکسان دارند (فقط برای پیشنهاد)
    assert match_key("مهندس ثابتی") == match_key("سابتی")


def test_spoken_phone_groups():
    runs = find_number_runs("صفر نهصد و پونزده صد و بیست و سه چهل و پنج شصت و هفت")
    assert len(runs) == 1
    assert runs[0].groups == ["0", "915", "123", "45", "67"]
    assert runs[0].ambiguous is False


def test_ambiguous_grouping_flagged():
    runs = find_number_runs("صفر نهصد پانزده")
    assert runs[0].digits == "0915"
    assert runs[0].ambiguous is True


def test_colloquial_and_suffix():
    text, _ = convert_number_words("هفتا سقف داره و دوازده واحد")
    assert "7 تا سقف" in text
    assert "12 واحد" in text
    assert words_to_int("شیش") == 6
    assert words_to_int("صد و بیست") == 120
    assert words_to_int("دو هزار و پونصد") == 2500


def test_non_number_words_kept():
    text, _ = convert_number_words("نه، فعلاً نه. بعد سه راهی اول، سه شنبه")
    assert "نه" in text and "سه راهی" in text and "سه شنبه" in text


def test_leading_zero_preserved_and_text():
    kind, norm, _ = classify("09151234567")
    assert (kind, norm) == ("mobile", "09151234567")
    kind, norm, notes = classify("9151234567")
    assert norm == "09151234567" and notes
    assert classify("+989151234567")[1] == "09151234567"
    assert classify("00989151234567")[1] == "09151234567"


def test_incomplete_phone_detected():
    kind, norm, _ = classify("091551246")
    assert kind == "incomplete"
    assert norm == "091551246"  # هیچ رقمی ساخته نمی‌شود


def test_landline_and_local():
    assert classify("05138001234")[0] == "landline"
    assert classify("38001234")[0] == "local"


def test_phone_from_runs_with_plate_adjacent():
    text, runs = convert_number_words("پلاک 12 شماره 09151234567")
    phones = phones_from_runs(text, runs)
    assert [p.normalized for p in phones] == ["09151234567"]
    assert phones[0].explicit


def test_two_phones_in_one_run():
    text, runs = convert_number_words("شماره 09151234567 و 09357654321")
    assert [p.normalized for p in phones_from_runs(text, runs)] == ["09151234567", "09357654321"]


def test_compare_key_ignores_leading_zero():
    assert compare_key("09151234567") == compare_key(9151234567) == compare_key("+98 915 123 4567")


def test_asr_phonetic_number_fixes():
    from voice2excel.asr_fixes import fix_asr_text
    text, runs = convert_number_words(fix_asr_text("شماره سفر ناسد و سیو هفد، سی سد و چیلو پنج، دوازده، پنجا و پنج"))
    assert [p.normalized for p in phones_from_runs(text, runs)] == ["09373451255"]
    assert "7 سقف" in convert_number_words(fix_asr_text("هفت سف، سه سفش اجرا شده"))[0]


def test_asr_fixes_do_not_touch_real_words():
    from voice2excel.asr_fixes import fix_asr_text
    assert fix_asr_text("برای سفر رفته بودن") == "برای سفر رفته بودن"
    assert fix_asr_text("سد کرج") == "سد کرج"


def test_split_hundreds_from_large_model():
    # خروجی واقعی large-v3-turbo: «نه سد» به‌جای «نهصد»
    from voice2excel.asr_fixes import fix_asr_text
    text, runs = convert_number_words(fix_asr_text("شماره تماس سفر، نه سد و سی و هفت، سی سد و چل و پنج، دوازده، پنجا و پنج"))
    assert [p.normalized for p in phones_from_runs(text, runs)] == ["09373451255"]
    text, runs = convert_number_words(fix_asr_text("شماره سفر، نه سد و پانزده، سد و یازده، بیست و دو، سی و سه"))
    assert [p.normalized for p in phones_from_runs(text, runs)] == ["09151112233"]
