"""هر ویس به یک فایل اکسل تعلق دارد: افزودن، شمارش، ثبت و انتقال جدا برای هر فایل."""
import sqlite3

import openpyxl
import pytest
from fastapi.testclient import TestClient

from voice2excel import excel_mapping, server
from voice2excel.database import Database
from tests.test_excel import make_company_like
from tests.test_templates import _add_approved


@pytest.fixture()
def client(db, settings):
    before = set(excel_mapping.list_profiles())
    active = server.load_settings().active_profile
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                    headers=server.auth_headers()) as c:
        yield c
    for n in set(excel_mapping.list_profiles()) - before:  # فایل‌های این آزمون از فهرست برداشته شوند
        excel_mapping.delete_profile(n)
    server.save_settings({"active_profile": active})


def _add_file(c, path):
    prof = c.post("/api/excel/inspect", json={"path": str(path)}).json()["profile"]
    return c.put("/api/excel/profile", json=prof).json()["profile"]


def test_two_files_keep_their_own_voices(client, db, settings, tmp_path):
    a = _add_file(client, make_company_like(tmp_path / "الف.xlsx"))
    b = _add_file(client, make_company_like(tmp_path / "ب.xlsx"))
    assert a["name"] != b["name"]
    # همان فایل دوباره: همان نام فهرست، نه فایل تکراری
    again = client.post("/api/excel/inspect", json={"path": str(tmp_path / "الف.xlsx")}).json()["profile"]
    assert again["name"] == a["name"]
    dup = {**again, "name": b["name"]}
    assert client.put("/api/excel/profile", json=dup).status_code == 409

    _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "d1", dest=a["name"])
    _add_approved(db, settings, "مهندس کاظمی شماره 09371234567 آدرس امامت 60", "d2", dest=b["name"])
    _add_approved(db, settings, "مهندس نوری شماره 09121234567 آدرس فلاحی 34", "d3", dest=b["name"])
    ds = {d["name"]: d for d in client.get("/api/dests").json()["dests"]}
    assert ds[a["name"]]["configured"] and ds[a["name"]]["voices"] == 1 and ds[a["name"]]["ready"] == 1
    assert ds[b["name"]]["voices"] == 2 and ds[b["name"]]["file_rows"] == {"rows": 3, "last_row": 5, "exists": True}

    com = client.post("/api/excel/commit", json={"dest": b["name"]}).json()
    assert com["applied"] and len(com["rows"]) == 2
    ws = openpyxl.load_workbook(tmp_path / "ب.xlsx")["Sheet1"]
    names = [ws.cell(r, 3).value for r in range(2, ws.max_row + 1)]
    assert "مهندس کاظمی" in names and "مهندس رجبی" not in names
    ws_a = openpyxl.load_workbook(tmp_path / "الف.xlsx")["Sheet1"]
    assert "مهندس رجبی" not in [ws_a.cell(r, 3).value for r in range(2, ws_a.max_row + 1)]
    ds = {d["name"]: d for d in client.get("/api/dests").json()["dests"]}
    assert ds[b["name"]]["written"] == 2 and ds[b["name"]]["file_rows"]["rows"] == 5
    assert ds[b["name"]]["last_commit"]["rows_written"] == 2
    assert ds[a["name"]]["written"] == 0

    # فهرست ویس‌ها و ردیف‌ها با فیلتر فایل
    assert len(client.get(f"/api/files?dest={b['name']}").json()["files"]) == 2
    assert len(client.get(f"/api/records?filter=all&dest={a['name']}").json()["records"]) == 1

    # انتقال: ویس ثبت‌شده منتقل نمی‌شود؛ ویس ثبت‌نشده منتقل می‌شود
    fid_b = client.get(f"/api/files?dest={b['name']}").json()["files"][0]["id"]
    assert client.patch(f"/api/files/{fid_b}", json={"dest": a["name"]}).status_code == 409
    fid_a = client.get(f"/api/files?dest={a['name']}").json()["files"][0]["id"]
    assert client.patch(f"/api/files/{fid_a}", json={"dest": "f_00000000"}).status_code == 404
    assert client.patch(f"/api/files/{fid_a}", json={"dest": b["name"]}).json()["dest"] == b["name"]
    assert client.get(f"/api/dests/{b['name']}").json()["ready"] == 1

    # حذف از فهرست: فایلی که ویس ثبت‌نشده دارد حذف نمی‌شود
    server.save_settings({"active_profile": a["name"]})
    assert client.delete(f"/api/templates/{b['name']}").status_code == 409
    assert client.delete(f"/api/templates/{a['name']}").status_code == 400  # فایل ویس‌های خودکار


def test_upload_binds_voice_to_chosen_file(client, db, settings, tmp_path, wav_factory):
    a = _add_file(client, make_company_like(tmp_path / "x.xlsx"))
    w = wav_factory("v.wav", 1.0)
    r = client.post("/api/upload", files=[("files", (w.name, w.read_bytes(), "audio/wav"))],
                    data={"visit_date": "1405/07/28", "dest": a["name"]}).json()["results"][0]
    assert r["result"] == "added"
    assert db.one("SELECT dest FROM audio_files WHERE id=?", (r["id"],))["dest"] == a["name"]
    bad = client.post("/api/upload", files=[("files", ("z.wav", w.read_bytes() + b"x", "audio/wav"))],
                      data={"visit_date": "1405/07/28", "dest": "f_00000000"})
    assert bad.status_code == 404


def test_orphan_voices_can_be_adopted(client, db, settings, tmp_path):
    a = _add_file(client, make_company_like(tmp_path / "y.xlsx"))
    _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "o1", dest="f_deadbeef")
    orphans = client.get("/api/dests").json()["orphans"]
    assert [o["dest"] for o in orphans] == ["f_deadbeef"] and orphans[0]["ready"] == 1
    assert client.post(f"/api/dests/{a['name']}/adopt", json={"source": "f_deadbeef"}).json()["moved"] == 1
    assert client.get("/api/dests").json()["orphans"] == []


def test_old_database_voices_are_bound_on_startup(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE audio_files(id INTEGER PRIMARY KEY, batch_id INTEGER, original_name TEXT NOT NULL, "
                "stored_name TEXT, sha256 TEXT UNIQUE, size INTEGER, duration REAL, visit_date TEXT, date_source TEXT, "
                "status TEXT NOT NULL DEFAULT 'queued', error TEXT, attempts INTEGER NOT NULL DEFAULT 0, model TEXT, "
                "processing_seconds REAL, peak_rss_mb REAL, audio_deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT, updated_at TEXT)")
    con.execute("INSERT INTO audio_files(original_name, status) VALUES('a.ogg', 'done')")
    con.commit()
    con.close()
    d = Database(p)
    assert d.one("SELECT dest FROM audio_files")["dest"] is None
    assert d.bind_unassigned("default") == 1 and d.one("SELECT dest FROM audio_files")["dest"] == "default"
    assert d.bind_unassigned("other") == 0
    d.close()


def test_voice_table_shows_fate_of_each_voice(client, db, settings, tmp_path):
    a = _add_file(client, make_company_like(tmp_path / "z.xlsx"))
    _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "v1", dest=a["name"])
    _add_approved(db, settings, "مهندس کاظمی شماره 09371234567 آدرس امامت 60", "v2", dest=a["name"])
    batch = db.create_batch("t", "1405/07/28")
    empty = db.add_audio(batch, "خالی.ogg", None, "v3", 1, "1405/07/28", "user", a["name"])
    db.save_results(empty, {"raw_text": "سلام", "normalized_text": "سلام", "processed_text": "سلام"}, [])
    db.set_audio(empty, status="done")
    failed = db.add_audio(batch, "خراب.ogg", None, "v4", 1, "1405/07/28", "user", a["name"])
    db.set_audio(failed, status="failed", error="فایل صوتی خراب است.")
    first = client.get(f"/api/records?filter=approved&dest={a['name']}").json()["records"][0]["id"]
    assert client.post("/api/excel/commit", json={"dest": a["name"], "record_ids": [first]}).json()["applied"]
    vs = {v["original_name"]: v for v in client.get(f"/api/dests/{a['name']}/voices").json()["voices"]}
    assert vs["v1.ogg"]["stage"] == "written" and vs["v1.ogg"]["records"][0]["export_row"] == 7
    assert vs["v1.ogg"]["records"][0]["file"] == "z.xlsx"
    assert vs["v2.ogg"]["stage"] == "ready"
    assert vs["خالی.ogg"]["stage"] == "no_rows" and vs["خراب.ogg"]["stage"] == "failed"
    why = client.get(f"/api/files/{empty}/why").json()
    assert why["text"] == "سلام" and why["status"] == "done"


def test_review_rows_use_the_file_columns(client, db, settings, tmp_path):
    a = _add_file(client, make_company_like(tmp_path / "c.xlsx"))
    _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "c1", dest=a["name"])
    d = client.get(f"/api/dests/{a['name']}/cells?filter=approved").json()
    letters = [c["letter"] for c in d["columns"]]
    assert letters[:5] == ["A", "B", "C", "D", "E"] and d["next_row"] == 6
    row = next(iter(d["rows"].values()))
    assert row["C"] == "مهندس رجبی" and row["D"] == "09151234567"
    assert client.get("/api/dests/nope/cells").status_code == 404


def test_history_lists_commits_with_rows(client, db, settings, tmp_path):
    a = _add_file(client, make_company_like(tmp_path / "h.xlsx"))
    _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "h1", dest=a["name"])
    assert client.post("/api/excel/commit", json={"dest": a["name"]}).json()["applied"]
    ex = client.get(f"/api/exports?dest={a['name']}").json()["exports"]
    assert len(ex) == 1 and ex[0]["file"] == "h.xlsx" and ex[0]["dest_listed"] and ex[0]["date_jalali"].startswith("14")
    assert ex[0]["items"] == [{"row": 7, "name": "مهندس رجبی", "voice": "h1.ogg"}]
    assert client.get("/api/exports?dest=f_00000000").json()["exports"] == []


def test_copy_first_option_leaves_original_until_applied(client, db, settings, tmp_path):
    src = make_company_like(tmp_path / "k.xlsx")
    a = _add_file(client, src)
    _add_approved(db, settings, "مهندس رجبی شماره 09151234567 آدرس سجادیه 58", "k1", dest=a["name"])
    before = src.read_bytes()
    server.save_settings({"review_copy_first": True})
    try:
        com = client.post("/api/excel/commit", json={"dest": a["name"]}).json()
    finally:
        server.save_settings({"review_copy_first": False})
    assert not com["applied"] and com["copy_only"] and src.read_bytes() == before
    assert client.get(f"/api/dests/{a['name']}").json()["pending_apply"] == 1
    eid = com["export_ids"][0]
    assert client.post(f"/api/exports/{eid}/replace-original").status_code == 200
    ws = openpyxl.load_workbook(src)["Sheet1"]
    assert ws.cell(7, 3).value == "مهندس رجبی"
    assert client.get(f"/api/dests/{a['name']}").json()["pending_apply"] == 0


def test_file_check_explains_problems_in_plain_words(client, db, settings, tmp_path):
    src = make_company_like(tmp_path / "chk.xlsx")
    a = _add_file(client, src)
    ok = client.get(f"/api/dests/{a['name']}/check").json()
    assert not ok["blocked"] and ok["items"][-1]["level"] == "ok"
    # Excel فایل را باز کرده (فایل ~$)
    owner = src.with_name("~$" + src.name)
    owner.write_bytes(b"x")
    try:
        c = client.get(f"/api/dests/{a['name']}/check").json()
        assert c["blocked"] and any("Excel باز است" in x["text"] for x in c["items"])
    finally:
        owner.unlink()
    # عنوان یک ستون عوض شده و یک ستون تازه اضافه شده
    wb = openpyxl.load_workbook(src)
    ws = wb["Sheet1"]
    ws["C1"] = "نام مشتری"
    ws["J1"] = "ستون تازه"
    wb.save(src)
    c = client.get(f"/api/dests/{a['name']}/check").json()
    texts = " ".join(x["text"] for x in c["items"])
    assert c["blocked"] and "ستون C" in texts and "ستون تازه" in texts
    assert any(x["fix"] == "columns" for x in c["items"])
    src.unlink()
    c = client.get(f"/api/dests/{a['name']}/check").json()
    assert c["blocked"] and c["items"][0]["fix"] == "file"
