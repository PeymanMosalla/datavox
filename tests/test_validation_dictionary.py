from pathlib import Path

from voice2excel import dictionary
from voice2excel.deduplicator import file_sha256, find_similar
from voice2excel.pipeline import build_records
from voice2excel.validator import validate


def meta(phones=None, **kw):
    m = {"phones": phones or [], "inherited": [], "field_notes": {}, "ambiguities": []}
    m.update(kw)
    return m


def test_new_name_accepted_but_reviewed(db, settings):
    v = validate(db, {"engineer_name": "مهندس زرین‌کلک", "phone": "09151234567", "address": "امامت 60", "visit_date": "1405/07/28"},
                 meta(), settings)
    f = v.fields["engineer_name"]
    assert f.status == "review"
    assert any("نام جدید" in r for r in f.reasons)
    assert v.status == "review"


def test_dictionary_name_valid_and_ready(db, settings):
    settings.review_spoken_phones = False  # پس از کالیبراسیون
    dictionary.add_entity(db, "رجبی", "engineer")
    v = validate(db, {"engineer_name": "مهندس رجبی", "phone": "09373451255", "address": "سجادیه 58 قطعه دوم",
                      "visit_date": "1405/07/28"}, meta(), settings)
    assert v.fields["engineer_name"].status == "valid"
    assert v.fields["phone"].status == "valid"
    assert v.status == "ready"


def test_spelling_ambiguity_gives_suggestions_not_auto_fix(db, settings):
    dictionary.add_entity(db, "ثابتی", "engineer")
    values = {"engineer_name": "مهندس سابتی", "phone": "09151234567", "address": "امامت 60", "visit_date": "1405/07/28"}
    v = validate(db, values, meta(), settings)
    f = v.fields["engineer_name"]
    assert f.status == "review"
    assert "مهندس ثابتی" in f.suggestions
    assert values["engineer_name"] == "مهندس سابتی"  # مقدار خودکار تغییر نکرد


def test_similar_names_never_auto_merged(db):
    a = dictionary.add_entity(db, "ثابتی", "engineer")
    b = dictionary.add_entity(db, "سابتی", "engineer")
    assert a != b
    assert len(dictionary.list_entities(db, "engineer")) == 2


def test_rename_keeps_old_spelling_as_alias(db):
    eid = dictionary.add_entity(db, "پورطالبی", "engineer")
    dictionary.rename_entity(db, eid, "پور طالبی")
    m = dictionary.lookup(db, "پورطالبی", "engineer")
    assert m and m[0].entity_id == eid and m[0].exact
    hist = db.q("SELECT action FROM entity_changes WHERE entity_id=?", (eid,))
    assert [h["action"] for h in hist] == ["create", "rename"]


def test_incomplete_phone_goes_to_review(db, settings):
    v = validate(db, {"engineer_name": "مهندس رجبی", "phone": "091512345", "address": "امامت 60", "visit_date": "1405/07/28"},
                 meta(), settings)
    assert v.fields["phone"].status == "invalid"
    assert v.status == "review"


def test_ambiguous_phone_grouping_reviewed(db, settings):
    dictionary.add_entity(db, "کاظمی", "engineer")
    ph = [{"normalized": "09151234567", "explicit": True, "ambiguous": True, "notes": []}]
    v = validate(db, {"engineer_name": "مهندس کاظمی", "phone": "09151234567", "address": "امامت 60", "visit_date": "1405/07/28"},
                 meta(ph), settings)
    assert v.fields["phone"].status == "review"


def test_optional_missing_does_not_block(db, settings):
    settings.review_spoken_phones = False  # پس از کالیبراسیون
    dictionary.add_entity(db, "رجبی", "engineer")
    v = validate(db, {"engineer_name": "مهندس رجبی", "phone": "09373451255", "address": "سجادیه 58",
                      "visit_date": "1405/07/28"}, meta(), settings)
    assert "project_name" not in v.fields
    assert v.status == "ready"


def test_nothing_found_is_invalid(db, settings):
    v = validate(db, {"visit_date": "1405/07/28"}, meta(), settings)
    assert v.status == "invalid"


def test_user_edit_confirms_new_name(db, settings):
    v = validate(db, {"engineer_name": "مهندس زرین‌کلک", "phone": "09151234567", "address": "امامت 60", "visit_date": "1405/07/28"},
                 meta(), settings, edited={"engineer_name"})
    assert v.fields["engineer_name"].status == "valid"


def test_file_hash_duplicate(tmp_path):
    a = tmp_path / "a.ogg"
    b = tmp_path / "b.ogg"
    a.write_bytes(b"same-content")
    b.write_bytes(b"same-content")
    assert file_sha256(a) == file_sha256(b)


def test_similar_record_warns_only():
    existing = [{"ref": "ردیف 5", "engineer_name": "مهندس رجبی", "phone": "9373451255", "address": "سجادیه 58 ، قطعه دوم"}]
    same = find_similar({"engineer_name": "مهندس رجبی", "phone": "09373451255", "address": "سجادیه 58 قطعه دوم"}, existing, "excel")
    assert same and same[0]["level"] == "strong"
    other_building = find_similar({"engineer_name": "مهندس رجبی", "phone": "09373451255", "address": "فلاحی 34"}, existing, "excel")
    assert other_building and other_building[0]["level"] == "weak"  # یک مهندس، چند ساختمان


def test_build_records_auto_ready_after_dictionary(db, settings):
    settings.review_spoken_phones = False  # پس از کالیبراسیون
    dictionary.add_entity(db, "رجبی", "engineer")
    text, clauses, recs = build_records(db, settings, "مهندس رجبی شماره 09373451255 آدرس سجادیه 58 قطعه دوم سازه فلز", "1405/07/28")
    assert len(recs) == 1
    assert recs[0]["status"] == "ready"
    assert recs[0]["review_state"] == "approved" and recs[0]["approved_by"] == "auto"
    assert clauses


def test_spoken_phone_reviewed_until_calibrated(db, settings):
    dictionary.add_entity(db, "رجبی", "engineer")
    ph = [{"normalized": "09373451255", "explicit": True, "ambiguous": False, "from_words": False, "notes": []}]
    vals = {"engineer_name": "مهندس رجبی", "phone": "09373451255", "address": "سجادیه 58", "visit_date": "1405/07/28"}
    assert validate(db, vals, meta(ph), settings).fields["phone"].status == "review"
    settings.review_spoken_phones = False
    assert validate(db, vals, meta(ph), settings).fields["phone"].status == "valid"


def test_seed_counts_usage_and_hotwords_prefer_frequent(db):
    names = ["مهندس رجبی", "مهندس رجبی", "مهندس رجبی", "مهندس عبدی", "آقای نصیری", "شماره نگهبان"]
    addrs = ["سجادیه 58 ، قطعه دوم", "سجادیه 61", "امامت 60 ، پلاک 8"]
    added = dictionary.seed_from_rows(db, names, addrs, "اکسل")
    assert added == {"engineer": 3, "street": 2}
    hw = dictionary.hotwords(db, limit=2)
    assert hw.split("، ") == ["رجبی", "سجادیه"]  # پرتکرارترین مهندس و خیابان
    dictionary.touch_by_name(db, "مهندس عبدی", "engineer")
    assert db.one("SELECT use_count FROM entities WHERE canonical='عبدی'")["use_count"] == 2
