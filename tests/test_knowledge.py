"""آزمون آموزش از فایل اکسل: خواندن نام و خیابان، ثبت و حذف منبع، و اثر واژگان بر استخراج و املا."""
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from voice2excel import dictionary, geo, knowledge, lexicon, server
from voice2excel.extractor import extract
from voice2excel.lexicon import Lexicon, unify_spelling
from voice2excel.pipeline import build_records
from voice2excel.schema import ExtractedRecord, FieldValue


def streets(cell):
    return [(s.canonical, sorted(s.aliases)) for s in knowledge.streets_from_address(cell)]


# ---------- خواندن سلول‌ها ----------
def test_names_from_cell():
    assert knowledge.names_from_cell("مهندس طاهری\nمهندس رحیمی ") == [("engineer", "طاهری"), ("engineer", "رحیمی")]
    assert knowledge.names_from_cell("مهندس سجادی\n09151234567") == [("engineer", "سجادی")]
    assert knowledge.names_from_cell("مهندس سجادی 0915-123-4567") == [("engineer", "سجادی")]
    assert knowledge.names_from_cell("مندس صالحی") == [("engineer", "صالحی")]
    assert knowledge.names_from_cell("محمودآبادی") == [("engineer", "محمودآبادی")]
    assert knowledge.names_from_cell("گروه ساختمانی سازمند") == [("project", "گروه ساختمانی سازمند")]
    for bad in ("شماره نگهبان و سرپرست کارگاه", "اسمشون افشین ، فامیلشو نمیدونن", "شماره جوشکاره ولی همه کاره همینه",
                "", None, "09151234567"):
        assert knowledge.names_from_cell(bad) == [], bad


def test_streets_from_address():
    assert streets("سجادیه 58 ، قطعه دوم") == [("سجادیه", [])]
    assert streets("ساجدی 7 ، فتح 8 ، پلاک 146/1") == [("ساجدی", []), ("فتح", [])]
    assert streets("ابوطالب 8 نبش کوچه شهید واحدی 7") == [("ابوطالب", []), ("شهید واحدی", ["واحدی"])]
    assert streets("بلوار جانباز ، مهدی 32 ، قطعه اول سمت راست") == [("جانباز", []), ("مهدی", [])]
    assert streets("موسوی قوچانی 28 - نبش شهید اسدالله زاده 13") == [
        ("موسوی قوچانی", []), ("شهید اسدالله زاده", ["اسدالله زاده"])]
    assert streets("امیریه 60 ، خوش منظر7/5") == [("امیریه", []), ("خوش منظر", [])]
    assert streets("طبرسی شمالی 4 ، نبش حیدری نسب 1") == [("طبرسی شمالی", []), ("حیدری نسب", [])]
    assert streets("نبش فلاحی 7 ، قطعه اول") == [("فلاحی", [])]
    # متن فنی یا جزئیات، نام خیابان نیست
    assert streets("سازه فلز ، تعداد 7 سقف ، 3 سقف اجرا شده") == []
    assert streets("کوچه اول سمت راست ، پلاک 12") == []


def test_detect_roles_from_headers_and_content():
    headers = {"A": "تاریخ بازدید", "B": "آدرس پروژه", "C": "نام کارفرما", "D": "همراه کارفرما", "E": "توضیحات"}
    samples = {"A": ["1405/07/28"] * 5, "B": ["سجادیه 58", "امامت 60 ، پلاک 8"], "C": ["مهندس رجبی", "مهندس عبدی"],
               "D": ["09151234567"] * 3, "E": ["سازه فلز"]}
    assert knowledge.detect_roles(headers, samples) == {"B": "address", "C": "engineer"}
    # بدون عنوان معنادار، از محتوا
    assert knowledge.detect_roles({"A": "ستون۱", "B": "ستون۲"},
                                  {"A": ["مهندس رجبی", "آقای عبدی"], "B": ["سجادیه 58", "امامت 60"]}) == {
        "A": "engineer", "B": "address"}


# ---------- ثبت و حذف منبع ----------
def test_import_merges_homophones_and_tracks_source(db):
    h = knowledge.harvest(["مهندس علیزاده", "مهندس علیزاده", "مهندس علی زاده", "مهندس رجبی"],
                          ["سجادیه 58", "سجادیه 61", "شهید اصغری 5"])
    res = knowledge.import_harvest(db, h, "a.xlsx")
    assert res["added"] == {"engineer": 2, "street": 2, "project": 0}
    e = db.one("SELECT * FROM entities WHERE canonical='علیزاده'")
    assert e["use_count"] == 3
    aliases = {r["alias"] for r in db.q("SELECT alias FROM aliases WHERE entity_id=?", (e["id"],))}
    assert aliases == {"علیزاده", "علی زاده"}
    assert dictionary.lookup(db, "اصغری", "street")[0].canonical == "شهید اصغری"

    # فایل دوم: نام موجود فقط شمارش و شکل تازه می‌گیرد
    dictionary.touch_by_name(db, "مهندس رجبی", "engineer")  # تأیید یک رکورد
    res2 = knowledge.import_harvest(db, knowledge.harvest(["مهندس رجبی", "مهندس کاظمی"], []), "b.xlsx")
    assert res2["added"]["engineer"] == 1
    assert db.one("SELECT use_count FROM entities WHERE canonical='رجبی'")["use_count"] == 3

    # حذف فایل اول: نام‌هایی که فقط همین فایل آورده حذف می‌شوند؛ «رجبی» که تأیید و در فایل دوم هم بوده می‌ماند
    knowledge.remove_source(db, res["source_id"])
    names = {r["canonical"] for r in db.q("SELECT canonical FROM entities")}
    assert names == {"رجبی", "کاظمی"}
    assert db.one("SELECT use_count FROM entities WHERE canonical='رجبی'")["use_count"] == 2
    assert [s["name"] for s in knowledge.list_sources(db)] == ["b.xlsx"]
    with pytest.raises(KeyError):
        knowledge.remove_source(db, res["source_id"])


def test_preview_counts_new_and_existing(db):
    dictionary.add_entity(db, "رجبی", "engineer")
    p = knowledge.preview(db, knowledge.harvest(["مهندس رجبی", "مهندس عبدی", "مهندس عبدی"], ["امامت 60"]))
    assert p["engineer"] == {"total": 2, "new": 1, "new_samples": ["عبدی"], "variants": 0}
    assert p["street"]["new"] == 1


# ---------- واژگان در استخراج ----------
LEX = Lexicon.build([
    ("street", "سجادیه", "سجادیه"), ("street", "امامت", "امامت"), ("street", "فلاحی", "فلاحی"),
    ("street", "فاطمیه", "فاطمیه"), ("street", "جانباز", "جانباز"), ("street", "مهدی", "مهدی"),
    ("street", "آموزگار", "آموزگار"), ("street", "شهید رحیمی", "رحیمی"), ("street", "مطهری", "مطهری"),
    ("engineer", "رجبی", "رجبی"), ("engineer", "کاظمی", "کاظمی"), ("engineer", "فلاحی", "فلاحی"),
    ("engineer", "مطهری", "مطهری"), ("engineer", "رحیمی", "رحیمی"), ("engineer", "صالحی", "صالحی"),
    ("engineer", "علیزاده", "علی زاده"),
])


@pytest.mark.parametrize("text,name,addr", [
    ("مهندس رجبی سجادیه 58 قطعه دوم 09151234567 سازه فلز 7 سقف", "مهندس رجبی", "سجادیه 58 قطعه دوم"),
    ("سازه فلز، 7 سقف، سجادیه 58، قطعه دوم، مهندس رجبی، 09151234567", "مهندس رجبی", "سجادیه 58، قطعه دوم"),
    ("رجبی، 09151234567، تعداد 7 سقف، امامت 60 پلاک 18", "رجبی", "امامت 60 پلاک 18"),
    ("09151234567 مهندس رجبی امامت 60", "مهندس رجبی", "امامت 60"),
    ("مهندس مطهری خیابان امامت 60 سازه بتن", "مهندس مطهری", "خیابان امامت 60"),
    ("مهندس رحیمی سجادیه 58", "مهندس رحیمی", "سجادیه 58"),
    ("مهندس رجبی شماره 09151234567 آدرس بلوار جانباز مهدی 32 قطعه اول", "مهندس رجبی", "بلوار جانباز مهدی 32 قطعه اول"),
    ("مهندس رجبی، فلاحی 34 فاطمیه 5، سازه فلز", "مهندس رجبی", "فلاحی 34 فاطمیه 5"),
    ("سلام، کاظمی، شماره 09151234567، سازه فلز 7 سقف، آدرس امامت 60", "کاظمی", "امامت 60"),
    ("هفت سقف سازه فلز، آموزگار 29 کوچه اول، شماره 09151234567 مهندس صالحی", "مهندس صالحی", "آموزگار 29 کوچه اول"),
])
def test_lexicon_finds_name_and_address_in_any_order(text, name, addr):
    r = extract(text, None, lexicon=LEX).records[0]
    assert r.get("engineer_name") == name
    assert r.get("address").replace("،", "").split() == addr.replace("،", "").split()


def test_without_lexicon_behaviour_unchanged():
    r = extract("مهندس رجبی شماره 09151234567 آدرس سجادیه 58 قطعه دوم", None).records[0]
    assert r.get("address") == "سجادیه 58 قطعه دوم"
    assert extract("مهندس رجبی سجادیه 58", None, lexicon=Lexicon()).records[0].get("engineer_name") == "مهندس رجبی سجادیه"


def test_name_after_title_is_never_cut_as_street():
    # «مطهری» هم خیابان است؛ پس از «مهندس» نام شخص است، حتی با عدد پشت سرش
    assert LEX.street_cuts("مهندس مطهری 12") == []
    assert extract("مهندس مطهری، شماره 09151234567", None, lexicon=LEX).records[0].get("engineer_name") == "مهندس مطهری"


# ---------- یکسان‌سازی املا ----------
def _rec(**fields):
    rec = ExtractedRecord()
    for k, v in fields.items():
        rec.fields[k] = FieldValue(value=v)
    return rec


def test_unify_spelling_homophones_only():
    lex = Lexicon.build([("engineer", "کاظمی", "کاظمی"), ("engineer", "نصیری", "نصیری"), ("street", "فلاحی", "فلاحی"),
                         ("street", "سجادیه", "سجادیه"), ("engineer", "ثابتی", "ثابتی"), ("engineer", "سابتی", "سابتی"),
                         ("engineer", "علیزاده", "علی زاده"), ("street", "امام رضا", "امام رضا")])
    vals = {"engineer_name": "مهندس کازمی", "address": "فلاهی 34، سجا دیه 5 پلاک 8", "street": "فلاهی 34"}
    rec = _rec(**vals)
    out = unify_spelling(vals, lex, rec)
    assert out["engineer_name"] == "مهندس کاظمی"
    assert out["address"] == "فلاحی 34، سجادیه 5 پلاک 8"
    assert out["street"] == "فلاحی 34"
    assert any("کازمی" in n for n in rec.fields["engineer_name"].notes)
    # دو نام هم‌آوا در واژه‌نامه: تصمیم با کاربر است
    assert unify_spelling({"engineer_name": "مهندس صابتی"}, lex)["engineer_name"] == "مهندس صابتی"
    # املای ثبت‌شده (شکل دیگر) دست نمی‌خورد؛ نام فقط مشابه هم تغییر نمی‌کند
    assert unify_spelling({"engineer_name": "مهندس علی زاده"}, lex)["engineer_name"] == "مهندس علی زاده"
    assert unify_spelling({"engineer_name": "مهندس کاظمیان"}, lex)["engineer_name"] == "مهندس کاظمیان"
    assert unify_spelling({"address": "امام رضا 41"}, lex)["address"] == "امام رضا 41"


def test_pipeline_uses_dictionary_lexicon(db, settings):
    knowledge.import_harvest(db, knowledge.harvest(["مهندس کاظمی"], ["سجادیه 58"]), "co.xlsx")
    _, _, recs = build_records(db, settings, "مهندس کازمی سجادیه 58 قطعه دوم شماره 09151234567", "1405/07/28")
    v = recs[0]["values"]
    assert v["engineer_name"] == "مهندس کاظمی" and v["address"] == "سجادیه 58 قطعه دوم"
    assert recs[0]["validation"]["fields"]["engineer_name"]["status"] == "valid"
    settings.kb_auto_spelling = False
    _, _, recs = build_records(db, settings, "مهندس کازمی سجادیه 58", "1405/07/28")
    assert recs[0]["values"]["engineer_name"] == "مهندس کازمی"


def test_lexicon_cache_refreshes_on_change(db):
    assert not lexicon.get_lexicon(db, base=False)
    dictionary.add_entity(db, "امامت", "street")
    assert "امامت" in lexicon.get_lexicon(db, base=False).street_names


# ---------- داده پایه شهر ----------
def test_geo_roundtrip_and_tamper():
    blob = geo.encode({"v": 1, "s": [["سجادیه", [], 5]]})
    assert "سجادیه".encode() not in blob  # محتوا خوانا نیست
    assert geo.decode(blob)["s"][0][0] == "سجادیه"
    with pytest.raises(ValueError):
        geo.decode(blob[:-1] + bytes([blob[-1] ^ 1]))


def test_bundled_city_data_loads():
    streets = dict(geo.base_streets())
    assert len(streets) > 500 and "سجادیه" in streets and "امامت" in streets


def test_base_streets_work_with_empty_dictionary(db, settings):
    _, _, recs = build_records(db, settings, "مهندس رجبی سجادیه 58 قطعه دوم شماره 09151234567 سازه فلز", "1405/07/28")
    assert recs[0]["values"]["engineer_name"] == "مهندس رجبی"
    assert recs[0]["values"]["address"] == "سجادیه 58 قطعه دوم"
    settings.kb_base_pack = False
    _, _, recs = build_records(db, settings, "مهندس رجبی سجادیه 58 قطعه دوم", "1405/07/28")
    assert recs[0]["values"]["engineer_name"] == "مهندس رجبی سجادیه"


def test_user_dictionary_overrides_base_data():
    base = [("فلاحی", ()), ("رضایی", ())]
    # کاربر املای دیگری دارد: املای کاربر برنده است
    lex = Lexicon.build([("street", "فلاهی", "فلاهی")], base)
    assert lex.fix_streets("فلاهی 34")[0] == "فلاهی 34"
    # خیابان داده پایه نام مهندس کاربر را مبهم نمی‌کند
    lex = Lexicon.build([("engineer", "رضایی", "رضایی")], base)
    assert lex.is_engineer("رضایی")
    # «رضایی 2 تا پروژه» آدرس نیست
    assert lex.street_cuts("مهندس محمد رضایی 2 تا پروژه دارن") == []
    assert lex.street_cuts("مهندس رجبی فلاحی 34") != []


# ---------- API ----------
def _xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_knowledge_api_flow(db, settings):
    data = _xlsx([["تاریخ", "آدرس پروژه", "نام کارفرما", "همراه کارفرما"],
                  ["1405/07/01", "سجادیه 58 ، قطعه دوم", "مهندس رجبی", "09151234567"],
                  ["1405/07/02", "امامت 60 ، پلاک 8", "مهندس علی زاده", "09151234568"],
                  ["1405/07/03", "امامت 12", "مهندس علیزاده", ""]])
    with TestClient(server.app, client=("127.0.0.1", 50000)) as c:
        r = c.post("/api/knowledge/analyze", files=[
            ("files", ("co.xlsx", data, "application/octet-stream")), ("files", ("old.xls", b"x", "application/octet-stream"))]).json()
        f, bad = r["files"]
        assert "error" in bad
        sheet = next(s for s in f["sheets"] if s["name"] == f["sheet"])
        assert sheet["roles"] == {"B": "address", "C": "engineer"}
        assert f["preview"]["engineer"]["total"] == 2 and f["preview"]["engineer"]["variants"] == 1
        assert f["preview"]["street"]["new_samples"] == ["امامت", "سجادیه"]
        body = {"token": f["token"], "sheet": f["sheet"], "header_row": sheet["header_row"], "name": f["name"],
                "columns": {"C": "engineer"}}
        p = c.post("/api/knowledge/preview", json=body).json()["preview"]
        assert p["street"]["total"] == 0
        assert c.post("/api/knowledge/preview", json={**body, "columns": {"B": "engineer", "C": "engineer"}}).status_code == 400
        assert c.post("/api/knowledge/preview", json={**body, "token": "../../x.xlsx"}).status_code == 400

        res = c.post("/api/knowledge/import", json={**body, "columns": sheet["roles"]}).json()
        assert res["added"] == {"engineer": 2, "street": 2, "project": 0} and res["rows"] == 3
        srcs = c.get("/api/knowledge/sources").json()["sources"]
        assert srcs[0]["name"] == "co.xlsx" and srcs[0]["new_entities"] == 4

        # همان فایل دوباره یاد گرفته نمی‌شود
        again = c.post("/api/knowledge/analyze", files=[("files", ("co.xlsx", data, "application/octet-stream"))]).json()
        f2 = again["files"][0]
        assert f2["already"]["id"] == srcs[0]["id"]
        assert c.post("/api/knowledge/import", json={**body, "token": f2["token"], "columns": sheet["roles"]}).status_code == 409

        assert c.delete(f"/api/knowledge/sources/{srcs[0]['id']}").json()["removed"] == 4
        assert db.one("SELECT COUNT(*) n FROM entities")["n"] == 0
        assert c.delete(f"/api/knowledge/sources/{srcs[0]['id']}").status_code == 404


def test_counts_and_quantities_are_not_streets():
    lex = Lexicon.build([], [("واحدی", ()), ("سجادیه", ())])
    # «دو واحدی 110 متری» شمارش است، نه خیابان «واحدی»
    r = extract("سازه فلز، تعداد 6 سقف، دو واحدی 110 و 113 متری، سقف و دیوار اجرا شده", None, lexicon=lex).records[0]
    assert not r.get("address")
    # ولی پس از «تعداد 7»، خیابان بعدی آدرس است
    assert lex.street_cuts("تعداد 7 سجادیه 58") != []


def test_base_names_fix_homophones_only():
    lex = Lexicon.build([], (), (("کاظمی", "حسن‌زاده", "صیفی", "سیفی", "رضایی"), ("علی",)))
    assert lex.canonical_engineer("کازمی") == "کاظمی"
    assert lex.canonical_engineer("علی کازمی") == "علی کاظمی"  # هر واژه جدا
    assert lex.canonical_engineer("حسن زاده") is None  # فقط فاصله فرق دارد: سبک کاربر حفظ می‌شود
    assert lex.canonical_engineer("صیفی") is None and lex.canonical_engineer("سیفی") is None
    assert lex.canonical_engineer("کاظمیان") is None  # فقط مشابه، نه هم‌آوا
    assert lex.is_engineer("رضایی")  # نام بدون «مهندس» شناخته می‌شود
    # واژه‌نامه کاربر بر فهرست عمومی مقدم است
    lex = Lexicon.build([("engineer", "کازمی", "کازمی")], (), (("کاظمی",), ()))
    assert lex.canonical_engineer("کازمی") is None


def test_bundled_names_load():
    surnames, first = geo.base_names()
    assert len(surnames) > 400 and "کاظمی" in surnames and "علی" in first
