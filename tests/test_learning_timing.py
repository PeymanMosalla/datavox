"""یادگیری از اصلاحات و نگاشت فیلدها به زمان ویس."""
from voice2excel import learning
from voice2excel.extractor import extract
from voice2excel.pipeline import build_records
from voice2excel.timing import TimeMap, field_times


def words_of(pairs):
    """[(واژه، شروع، پایان، احتمال)] ← فهرست واژه‌های زمان‌دار به شکل خروجی Whisper."""
    return [{"word": w, "start": s, "end": e, "prob": p} for w, s, e, p in pairs]


RAW = words_of([
    ("مهندس", 0.0, 0.5, 0.95), ("رجبی،", 0.5, 1.0, 0.9),
    ("سفر", 1.2, 1.5, 0.6), ("نه", 1.5, 1.7, 0.9), ("سد", 1.7, 1.9, 0.4), ("و", 1.9, 2.0, 0.9),
    ("سی", 2.0, 2.2, 0.9), ("و", 2.2, 2.3, 0.9), ("هفت،", 2.3, 2.6, 0.9),
    ("سیصد", 2.7, 3.1, 0.9), ("و", 3.1, 3.2, 0.9), ("چهل", 3.2, 3.5, 0.9), ("و", 3.5, 3.6, 0.9), ("پنج،", 3.6, 3.9, 0.9),
    ("دوازده،", 4.0, 4.5, 0.9), ("پنجاه", 4.6, 5.0, 0.9), ("و", 5.0, 5.1, 0.9), ("پنج،", 5.1, 5.4, 0.9),
    ("سجادیه", 5.6, 6.1, 0.95), ("پنجاه", 6.1, 6.5, 0.9), ("و", 6.5, 6.6, 0.9), ("هشت،", 6.6, 6.9, 0.9),
    ("قطعه", 7.0, 7.3, 0.9), ("دوم،", 7.3, 7.6, 0.9),
    ("سازه", 7.8, 8.2, 0.9), ("بتن،", 8.2, 8.6, 0.41), ("تعداد", 8.7, 9.1, 0.9), ("هفت", 9.1, 9.4, 0.9), ("سقف", 9.4, 9.8, 0.9),
])
TEXT = " ".join(w["word"] for w in RAW)


def test_field_times_follow_the_voice():
    r = extract(TEXT)
    rec = r.records[0]
    spans = {k: fv.span for k, fv in rec.fields.items() if fv.span}
    times, low = field_times(r.text, RAW, spans)
    # نام: از «مهندس» تا «رجبی»
    assert times["engineer_name"][0] <= 0.0 + 0.01 and 0.9 <= times["engineer_name"][1] <= 1.3
    # شماره (همه رقم‌اند و با متن خام یکی نیستند): از پایان «رجبی» تا آغاز «سجادیه»
    assert 0.7 <= times["phone"][0] <= 1.2 and 5.4 <= times["phone"][1] <= 5.9
    # آدرس: از «سجادیه» تا «دوم»
    assert 5.3 <= times["address"][0] <= 5.6 and 7.5 <= times["address"][1] <= 7.9
    # واژه کم‌اطمینان داخل بازه شماره برای نمایش به کاربر
    assert "سد" in low.get("phone", [])
    assert "بتن" in low.get("structure_type", [])


def test_time_map_without_words():
    assert TimeMap("متن", []).span_time(0, 3) is None


def test_build_records_stores_times(db, settings):
    _, _, recs = build_records(db, settings, TEXT, "1405/07/29", words=RAW)
    assert "phone" in recs[0]["extracted"]["meta"]["times"]


def test_correction_pairs_learn_words_not_numbers():
    assert learning.correction_pairs("مهندس گلزی", "مهندس گلزاری") == [("گلزی", "گلزاری")]
    assert learning.correction_pairs("شاهد هیفته، پلاک 14", "شاهد 17، پلاک 14") == [("هیفته", "17")]
    assert learning.correction_pairs("امامت 17", "امامت 19") == []  # تصمیم مخصوص همین ساختمان


def test_learning_suggests_then_applies_automatically(db, settings):
    settings.learn_auto_threshold = 2
    text = "مهندس گلزی، شماره 09121234567، آدرس شاهد 12، پلاک 4"
    # بار اول: فقط پیشنهاد
    learning.learn_from_edit(db, "engineer_name", "مهندس گلزی", "مهندس گلزاری")
    _, _, recs = build_records(db, settings, text, "1405/07/29")
    assert recs[0]["values"]["engineer_name"] == "مهندس گلزی"
    assert "مهندس گلزاری" in recs[0]["validation"]["fields"]["engineer_name"]["suggestions"]
    # بار دوم: اعمال خودکار، با یادداشت توضیحی
    learning.learn_from_edit(db, "engineer_name", "مهندس گلزی", "مهندس گلزاری")
    _, _, recs = build_records(db, settings, text, "1405/07/29")
    assert recs[0]["values"]["engineer_name"] == "مهندس گلزاری"
    notes = recs[0]["extracted"]["meta"]["field_notes"]["engineer_name"]
    assert any("اصلاح خودکار" in n for n in notes)


def test_learning_is_scoped_by_field_group(db, settings):
    settings.learn_auto_threshold = 1
    learning.learn_from_edit(db, "engineer_name", "مهندس شاهد", "مهندس شاهدی")
    _, _, recs = build_records(db, settings, "مهندس کریمی، شماره 09121234567، آدرس شاهد 12", "1405/07/29")
    assert recs[0]["values"]["address"].startswith("شاهد 12")  # اصلاح نام در آدرس اعمال نشد


def test_disabled_correction_not_applied(db, settings):
    settings.learn_auto_threshold = 1
    text = "مهندس کریمی، شماره 09121234567، آدرس فلاری 34"
    learning.learn_from_edit(db, "address", "فلاری 34", "فلاحی 34")
    _, _, recs = build_records(db, settings, text, "1405/07/29")
    assert recs[0]["values"]["address"] == "فلاحی 34"  # فعال: اعمال می‌شود
    learning.set_enabled(db, learning.list_corrections(db)[0]["id"], False)
    _, _, recs = build_records(db, settings, text, "1405/07/29")
    assert recs[0]["values"]["address"] == "فلاری 34"  # غیرفعال: اعمال نمی‌شود
