"""آزمون قالب‌های خروجی اکسل: ساخت فایل جدید با ستون‌ها، قالب مقادیر و ظاهر دلخواه."""
import io

import openpyxl
from fastapi.testclient import TestClient

from voice2excel import excel_mapping, excel_template, server
from voice2excel.excel_mapping import format_date, format_phone
from voice2excel.pipeline import build_records


def _add_approved(db, settings, text, sha, vd="1405/07/28", dest=None):
    batch = db.create_batch("t", vd)
    aid = db.add_audio(batch, f"{sha}.ogg", None, sha, 1, vd, "user", dest or server.load_settings().active_profile)
    _, _, recs = build_records(db, settings, text, vd)
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
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
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
        assert pv["letters"] == ["A", "B", "C", "D", "E"] and pv["demo"]
        sample = c.post("/api/templates/sample", json=saved)
        ws = openpyxl.load_workbook(io.BytesIO(sample.content))["Sheet1"]
        assert ws["A1"].value == "ردیف" and ws["A1"].fill.fgColor.rgb == "FF138A52" and ws.sheet_view.rightToLeft

        _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "s1", dest=name)
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

        assert c.delete(f"/api/templates/{name}").status_code == 400  # فایل ویس‌های خودکار
        assert c.delete("/api/templates/f_00000000").status_code == 404  # فایلی که در فهرست نیست
        server.save_settings({"active_profile": excel_mapping.COMPANY})  # تنظیمات آزمون‌های دیگر دست نخورد


def test_company_mapping_page_ignores_active_template(db, settings, tmp_path):
    """صفحه نگاشت فایل شرکت هرگز قالب «فایل جدید» فعال را بازنویسی نمی‌کند."""
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
        name = c.post("/api/templates", json={"title": "x"}).json()["name"]
        c.post(f"/api/templates/{name}/activate")
        assert c.get("/api/excel/profile").json()["profile"] is None or \
            c.get("/api/excel/profile").json()["profile"]["name"] == excel_mapping.COMPANY
        assert excel_mapping.load_profile(name)["mode"] == "new"
        server.save_settings({"active_profile": excel_mapping.COMPANY})
        assert c.delete(f"/api/templates/{name}").json()["ok"]


def test_company_template_preview(db, settings, tmp_path):
    """پیش‌نمایش فایل شرکت: ستون‌های خود فایل به ترتیب حرف ستون، با قالب مقادیر ذخیره‌نشده صفحه."""
    from .test_excel import make_company_like
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
        prof = c.post("/api/excel/inspect", json={"path": str(make_company_like(tmp_path / "co.xlsx"))}).json()["profile"]
        saved = c.put("/api/excel/profile", json=prof).json()["profile"]
        _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "p1")
        body = {"name": saved["name"], "mode": saved.get("mode"), "policy": {"name_title": "drop", "phone_group": True}}
        pv = c.post("/api/templates/preview", json=body).json()
        letters = sorted(set(saved["headers"]) | set(saved["columns"]))
        assert pv["letters"] == letters and pv["headers"] == [saved["headers"].get(x, "") for x in letters]
        assert not pv["demo"] and pv["target"] == "co.xlsx"
        row = dict(zip(pv["fields"], pv["rows"][-1]))
        assert row["engineer_name"] == "رجبی" and row["phone"] == "0915 123 4567"
        assert excel_mapping.load_profile(saved["name"])["policy"].get("name_title") != "drop"  # پیش‌نمایش چیزی ذخیره نمی‌کند
        assert c.post("/api/templates/preview", json={"name": "nope"}).status_code == 404
        # ستون‌های ذخیره‌نشده صفحه هم در پیش‌نمایش می‌آیند (بدون ذخیره)
        pv2 = c.post("/api/templates/preview", json={**body, "headers": saved["headers"], "columns": {}, "protected": [letters[0]]}).json()
        assert not any(pv2["fields"]) and pv2["protected"] == [letters[0]] and not any(any(r) for r in pv2["rows"])
        assert excel_mapping.load_profile(saved["name"])["columns"] == saved["columns"]
        # کارت مقصد: یک جمله ساده درباره فایل و شیت
        info = next(t for t in c.get("/api/templates").json()["templates"] if t["name"] == saved["name"])
        assert info["confirmed"] and info["target"] == "co.xlsx" and info["sheet"] == saved["sheet"]
        # رنگ ردیف نامعتبر در ذخیره فایل موجود پذیرفته نمی‌شود
        bad = {**saved, "policy": {**saved["policy"], "highlights": {"warn": "javascript:alert(1)", "today": "#E3F5EC"}}}
        hl = c.put("/api/excel/profile", json=bad).json()["profile"]["policy"]["highlights"]
        assert hl["warn"] == "" and hl["today"].upper() == "#E3F5EC"


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


# ---------- مرحله ۲ ----------
def _rec(i, vd, **values):
    return {"id": i, "audio_id": i, "building_index": 0, "original_name": "a", "transcript": "", "status": "review",
            "validation": {"fields": {}}, "values": {"visit_date": vd, "engineer_name": f"مهندس {i}", "phone": "09151234567", **values}}


def test_highlight_rules():
    pol = {"highlights": excel_template.clean_highlights({"warn": "#FFF3DC", "today": "#E3F5EC", "followup": "#FDE8EA",
                                                          "followup_days": 3})}
    today = "1405/07/28"
    assert excel_template.highlight(pol, _rec(1, today, followup_date="1405/07/30"), today) == "#FDE8EA"
    assert excel_template.highlight(pol, _rec(1, "1405/07/20", followup_date="1405/08/20"), today) == ""
    bad = _rec(2, "1405/07/20")
    bad["validation"]["fields"]["phone"] = {"status": "invalid"}
    assert excel_template.highlight(pol, bad, today) == "#FFF3DC"  # ردیف ناقص
    assert excel_template.highlight(pol, _rec(3, today), today) == "#E3F5EC"
    assert excel_template.highlight({}, bad, today) == ""  # رنگ‌گذاری خاموش


def test_split_by_month_files_and_sheets(tmp_path):
    from voice2excel.excel_writer import write_export
    recs = [_rec(1, "1405/07/28"), _rec(2, "1405/07/29"), _rec(3, "1405/08/02")]
    for split, expect in (("month_file", {("روزانه 1405-07.xlsx", "Sheet1"): 2, ("روزانه 1405-08.xlsx", "Sheet1"): 1}),
                          ("month_sheet", {("روزانه.xlsx", "1405-07"): 2, ("روزانه.xlsx", "1405-08"): 1})):
        folder = tmp_path / split
        folder.mkdir()
        tpl = excel_template.clean({**excel_template.new_template("t", "روزانه", str(folder)),
                                    "output": {"folder": str(folder), "file": "روزانه", "split": split}})
        for vd, grp in excel_template.group_records(tpl, recs):
            rep = write_export(excel_template.writer_profile(tpl, visit_date=vd), grp)
            from voice2excel.excel_writer import replace_original
            replace_original(rep["output_path"], rep["target_path"], rep["target_sha"])
        got = {}
        for f in folder.glob("*.xlsx"):
            wb = openpyxl.load_workbook(f)
            for ws in wb.worksheets:
                got[(f.name, ws.title)] = ws.max_row - 1
        assert got == expect, (split, got)


def test_like_this_file_and_template_transfer(db, settings, tmp_path):
    tpl = excel_template.clean(excel_template.new_template("t", "مدیر", str(tmp_path)))
    tpl["style"]["header"].update(fill="#138A52", font="B Nazanin", size=13)
    tpl["style"]["zebra"] = "#E8F6EF"
    sample = tmp_path / "s.xlsx"
    sample.write_bytes(excel_template.build_sample(tpl, [["1405/07/28", "مهندس الف", "0915", "x", "y", "z"]] * 3))
    got = excel_template.from_file(sample)
    assert [c["title"] for c in got["columns_list"]] == [c["title"] for c in tpl["columns_list"]]
    assert got["columns_list"][1]["field"] == "engineer_name" and got["columns_list"][0]["field"] == "visit_date"
    s = got["style"]
    assert s["header"]["fill"] == "#138A52" and s["header"]["font"] == "B Nazanin" and s["header"]["size"] == 13
    assert s["zebra"] == "#E8F6EF" and s["rtl"] and s["freeze"] and s["filter"]
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
        r = c.post("/api/templates/from-file", files=[("file", ("s.xlsx", sample.read_bytes(), "application/octet-stream"))])
        assert r.json()["style"]["header"]["fill"] == "#138A52"
        assert c.post("/api/templates/from-file", files=[("file", ("s.txt", b"x", "text/plain"))]).status_code == 400
        name = c.post("/api/templates", json={"title": "انتقالی"}).json()["name"]
        exported = c.get(f"/api/templates/{name}/export")
        data = exported.json()
        assert data["v2x_template"] == 1 and "folder" not in data["output"]
        new = c.post("/api/templates/import", files=[("file", ("t.json", exported.content, "application/json"))]).json()["name"]
        assert new != name and c.get(f"/api/templates/{new}").json()["template"]["title"] == "انتقالی"
        assert c.post("/api/templates/import", files=[("file", ("t.json", b'{"x":1}', "application/json"))]).status_code == 400
        for n in (name, new):
            c.delete(f"/api/templates/{n}")


def test_commit_split_writes_and_undoes_each_file(db, settings, tmp_path):
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
        name = c.post("/api/templates", json={"title": "ماهانه"}).json()["name"]
        tpl = c.get(f"/api/templates/{name}").json()["template"]
        tpl["output"] = {"folder": str(tmp_path), "file": "ماهانه", "split": "month_file"}
        c.put(f"/api/templates/{name}", json=tpl)
        c.post(f"/api/templates/{name}/activate")
        _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "m1", "1405/07/28")
        _add_approved(db, settings, "مهندس کاظمی شماره 09371234567 آدرس امامت 60", "m2", "1405/08/02")
        com = c.post("/api/excel/commit", json={}).json()
        assert com["applied"] and len(com["export_ids"]) == 2 and len(com["rows"]) == 2
        assert com["files"] == ["ماهانه 1405-07.xlsx", "ماهانه 1405-08.xlsx"]
        for eid in com["export_ids"]:
            assert c.post(f"/api/exports/{eid}/undo").json()["restored"]
        for f in com["files"]:
            assert openpyxl.load_workbook(tmp_path / f)["Sheet1"].max_row == 1  # فقط سرستون
        server.save_settings({"active_profile": excel_mapping.COMPANY})
        c.delete(f"/api/templates/{name}")
