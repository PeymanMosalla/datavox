"""آزمون قالب‌های خروجی اکسل: ساخت فایل جدید با ستون‌ها، قالب مقادیر و ظاهر دلخواه."""
import io

import openpyxl
from fastapi.testclient import TestClient

from voice2excel import excel_mapping, excel_template, server
from voice2excel.excel_mapping import format_date, format_phone
from voice2excel.pipeline import build_records


def _add_approved(db, settings, text, sha):
    batch = db.create_batch("t", "1405/07/28")
    aid = db.add_audio(batch, f"{sha}.ogg", None, sha, 1, "1405/07/28", "user")
    _, _, recs = build_records(db, settings, text, "1405/07/28")
    for r in recs:
        r["review_state"], r["approved_by"] = "approved", "user"
    db.save_results(aid, {"raw_text": text, "normalized_text": text, "processed_text": text}, recs)
    db.set_audio(aid, status="done")


def test_value_formats():
    assert format_date("1405/07/28", "long") == "۲۸ مهر ۱۴۰۵"
    assert format_date("1405/07/28", "persian") == "۱۴۰۵/۰۷/۲۸"
    assert format_date("1405/07/28", None) == "1405/07/28" and format_date("نامعلوم", "long") == "نامعلوم"
    assert format_phone("09151234567", True) == "0915 123 4567" and format_phone("38123456", True) == "38123456"


def test_clean_rejects_bad_input():
    tpl = excel_template.new_template("t_x", "گزارش", "C:/")
    tpl["columns_list"].append({"field": "not_a_field"})
    tpl["style"]["header"]["fill"] = "javascript:alert(1)"
    tpl["style"]["body"]["size"] = 500
    c = excel_template.clean(tpl)
    assert all(x["field"] != "not_a_field" for x in c["columns_list"])
    assert c["style"]["header"]["fill"] == "#FFFFFF" and c["style"]["body"]["size"] == 36
    tpl["columns_list"] = [{"field": "phone", "title": "a"}, {"field": "address", "title": "a"}]
    try:
        excel_template.clean(tpl)
        raise AssertionError("duplicate titles accepted")
    except ValueError:
        pass


def test_template_flow_new_file(db, settings, tmp_path):
    with TestClient(server.app, client=("127.0.0.1", 50000)) as c:
        meta = c.get("/api/templates").json()
        assert "row_number" in [f["key"] for f in meta["fields"]] and meta["presets"]["green"]["fill"]
        name = c.post("/api/templates", json={"title": "گزارش مدیر"}).json()["name"]
        tpl = c.get(f"/api/templates/{name}").json()["template"]
        tpl["output"] = {"folder": str(tmp_path), "file": "گزارش مدیر"}
        tpl["columns_list"] = [
            {"field": "row_number", "title": "ردیف", "width": 6, "align": "center"},
            {"field": "visit_date", "title": "تاریخ", "width": 16},
            {"field": "engineer_name", "title": "نام", "width": 20},
            {"field": "phone", "title": "تلفن", "width": 16},
            {"field": "constant", "title": "بازاریاب", "value": "آقای صالحی"},
        ]
        tpl["style"]["header"]["fill"] = "#138A52"
        tpl["policy"] = {"date_format": "long", "phone_group": True, "name_title": "drop", "bogus": 1}
        saved = c.put(f"/api/templates/{name}", json=tpl).json()["template"]
        assert "bogus" not in saved["policy"]
        assert c.put(f"/api/templates/{name}", json={**tpl, "output": {"folder": str(tmp_path / "x"), "file": "a"}}).status_code == 400

        pv = c.post("/api/templates/preview", json=saved).json()
        assert pv["headers"] == ["ردیف", "تاریخ", "نام", "تلفن", "بازاریاب"] and pv["rows"][0][0] == "1"
        assert pv["rows"][0][4] == "آقای صالحی"
        sample = c.post("/api/templates/sample", json=saved)
        ws = openpyxl.load_workbook(io.BytesIO(sample.content))["Sheet1"]
        assert ws["A1"].value == "ردیف" and ws["A1"].fill.fgColor.rgb == "FF138A52" and ws.sheet_view.rightToLeft

        _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "s1")
        assert c.post(f"/api/templates/{name}/activate").status_code == 200
        st = c.get("/api/status").json()
        assert st["setup"]["excel_ready"] and st["setup"]["excel_name"] == "گزارش مدیر.xlsx"
        com = c.post("/api/excel/commit", json={}).json()
        assert com["applied"]
        out = tmp_path / "گزارش مدیر.xlsx"
        ws = openpyxl.load_workbook(out)["Sheet1"]
        assert [ws.cell(2, i).value for i in range(1, 6)] == ["1", "۲۸ مهر ۱۴۰۵", "رجبی", "0915 123 4567", "آقای صالحی"]
        assert ws.freeze_panes == "A2" and ws.auto_filter.ref == "A1:E2" and ws["C2"].font.name == "Tahoma"
        assert ws["D2"].alignment.readingOrder == 1  # شماره گروه‌بندی‌شده در شیت راست‌به‌چپ وارونه نشود

        # ثبت دوم: شماره ردیف ادامه پیدا می‌کند و ردیف‌های راه‌راه رنگ می‌گیرند
        _add_approved(db, settings, "مهندس کاظمی شماره 09371234567 آدرس امامت 60", "s2")
        com2 = c.post("/api/excel/commit", json={}).json()
        ws = openpyxl.load_workbook(out)["Sheet1"]
        assert ws.cell(3, 1).value == "2" and ws.cell(3, 3).value == "کاظمی" and ws.auto_filter.ref == "A1:E3"
        assert ws.cell(2, 3).fill.fgColor.rgb != ws.cell(3, 3).fill.fgColor.rgb
        before = out.read_bytes()
        assert c.post(f"/api/exports/{com2['export_id']}/undo").json()["restored"]
        assert openpyxl.load_workbook(out)["Sheet1"].max_row == 2 and out.read_bytes() != before

        # تغییر ستون‌ها روی فایلی که ساخته شده: هشدار تغییر نام فایل
        saved["columns_list"] = saved["columns_list"][:3]
        assert "نام فایل" in c.put(f"/api/templates/{name}", json=saved).json()["warning"]

        assert c.delete(f"/api/templates/{name}").status_code == 400  # قالب فعال
        assert c.delete(f"/api/templates/{excel_mapping.COMPANY}").status_code == 400
        server.save_settings({"active_profile": excel_mapping.COMPANY})  # تنظیمات آزمون‌های دیگر دست نخورد


def test_company_mapping_page_ignores_active_template(db, settings, tmp_path):
    """صفحه نگاشت فایل شرکت هرگز قالب «فایل جدید» فعال را بازنویسی نمی‌کند."""
    with TestClient(server.app, client=("127.0.0.1", 50000)) as c:
        name = c.post("/api/templates", json={"title": "x"}).json()["name"]
        c.post(f"/api/templates/{name}/activate")
        assert c.get("/api/excel/profile").json()["profile"] is None or \
            c.get("/api/excel/profile").json()["profile"]["name"] == excel_mapping.COMPANY
        assert excel_mapping.load_profile(name)["mode"] == "new"
        server.save_settings({"active_profile": excel_mapping.COMPANY})
        assert c.delete(f"/api/templates/{name}").json()["ok"]


def test_new_template_writes_date_on_every_row(db, settings, tmp_path):
    """برخلاف فایل شرکت، فایل تازه تاریخ هر ردیف را دارد (مگر کاربر خلافش را بخواهد)."""
    tpl = excel_template.clean({**excel_template.new_template("t_d", "روزانه", str(tmp_path)), "policy": {}})
    excel_mapping.save_profile(tpl)
    prof = excel_template.writer_profile(excel_mapping.load_profile("t_d"))
    assert prof["policy"]["date_first_row_only"] is False and prof["policy"]["blank_row_between_dates"] is False
    from voice2excel.excel_writer import write_export
    recs = [{"id": i, "audio_id": i, "building_index": 0, "original_name": "a", "transcript": "", "validation": {},
             "values": {"visit_date": "1405/07/28", "engineer_name": n, "phone": "09151234567"}} for i, n in enumerate(["الف", "ب"])]
    rep = write_export(prof, recs)
    ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
    assert ws["A2"].value == ws["A3"].value == "1405/07/28"
    excel_mapping.delete_profile("t_d")
