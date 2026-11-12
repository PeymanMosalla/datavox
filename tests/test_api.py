"""آزمون سرتاسری API: آپلود ← پردازش ← بازبینی ← ثبت در اکسل (با مدل گفتار جایگزین)."""
import time

import openpyxl
from fastapi.testclient import TestClient

from voice2excel import server
from voice2excel.worker import Worker

from .test_excel import make_company_like
from .test_worker import FakeTranscriber


def wait_idle(client, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = client.get("/api/status").json()
        if not s["worker"]["running"] and s["files"]["queued"] == 0:
            return s
        time.sleep(0.2)
    raise AssertionError("worker did not finish")


def test_end_to_end(db, settings, wav_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "model_available", lambda n: True)
    server.set_worker(Worker(db, FakeTranscriber()))
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
        a = wav_factory("PTT-20261020-WA0001.wav", 1.0)
        b = wav_factory("v2.wav", 1.5, amp=0.25)
        files = [("files", (p.name, p.read_bytes(), "audio/wav")) for p in (a, b)]
        r = c.post("/api/upload", files=files, data={"visit_date": "1405/07/28", "use_filename_date": "true"}).json()
        assert [x["result"] for x in r["results"]] == ["added", "added"]
        assert r["results"][0]["visit_date"] == "1405/07/28" and r["results"][0]["date_source"] == "filename"
        # ویس تکراری دیگر رد نمی‌شود؛ پیش از آپلود، رابط کاربری با /api/upload/check می‌پرسد (tests/test_duplicates.py)
        from voice2excel.deduplicator import file_sha256
        m = c.post("/api/upload/check", json={"hashes": [file_sha256(a)]}).json()["matches"]
        assert m[file_sha256(a)]["same_dest"] and not m[file_sha256(a)]["processed"]

        assert c.post("/api/queue/start").status_code == 200
        s = wait_idle(c)
        assert s["files"]["done"] == 2

        recs = c.get("/api/records?filter=all").json()["records"]
        assert len(recs) == 2
        rid = next(x["id"] for x in recs if x["values"]["engineer_name"] == "مهندس رجبی")
        # اصلاح دستی و ثبت سابقه
        rec = c.patch(f"/api/records/{rid}", json={"values": {"address": "سجادیه 58 ، قطعه دوم"}}).json()
        assert rec["values"]["address"] == "سجادیه 58 ، قطعه دوم" and rec["manually_edited"]
        assert rec["edits"][0]["old_value"] == "سجادیه 58 قطعه دوم"
        detail = c.get(f"/api/records/{rid}").json()
        assert detail["transcript"]["raw_text"].startswith("مهندس رجبی")
        for x in recs:
            assert c.post(f"/api/records/{x['id']}/action", json={"action": "approve", "add_to_dictionary": True}).status_code == 200
        # نام تأییدشده به واژه‌نامه رفت
        names = [e["canonical"] for e in c.get("/api/dictionary?type=engineer").json()["entities"]]
        assert "رجبی" in names

        src = make_company_like(tmp_path / "co.xlsx")
        before = src.read_bytes()
        ins = c.post("/api/excel/inspect", json={"path": str(src)}).json()
        prof = ins["profile"]
        assert prof["sheet"] == "Sheet1"
        saved = c.put("/api/excel/profile", json=prof).json()["profile"]
        assert saved["confirmed"]
        pv = c.post("/api/excel/preview").json()
        assert len(pv["rows"]) == 2
        rep = c.post("/api/excel/export", json={}).json()
        assert src.read_bytes() == before
        ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
        assert {ws.cell(r, 3).value for r in (rep["first_row"], rep["last_row"])} == {"مهندس رجبی", "مهندس نصیری"}

        # ثبت دوباره همان رکوردها ممکن نیست
        assert c.post("/api/excel/preview").json()["rows"] == []
        assert c.post("/api/excel/export", json={}).status_code == 400
        # رکورد ثبت‌شده قابل ویرایش نیست
        assert c.patch(f"/api/records/{rid}", json={"values": {"address": "x"}}).status_code == 409

        st = c.get("/api/status").json()
        assert st["records"]["exported"] == 2 and st["pending_replace"] == 1
        exp_id = rep["export_id"]
        assert c.post(f"/api/exports/{exp_id}/replace-original").status_code == 200
        assert src.read_bytes() != before
        # بازگردانی: فایل اصلی به نسخه پیش از ثبت برمی‌گردد و رکوردها دوباره آماده ثبت می‌شوند
        assert c.post(f"/api/exports/{exp_id}/undo").json()["restored"]
        assert src.read_bytes() == before
        assert c.get("/api/status").json()["records"]["approved"] == 2

        # ثبت یک‌مرحله‌ای: مستقیم در فایل اصلی، با پشتیبان؛ و بازگشت آن
        com = c.post("/api/excel/commit", json={}).json()
        assert com["applied"] and src.read_bytes() != before
        ws = openpyxl.load_workbook(src)["Sheet1"]
        assert ws.cell(com["first_row"], 3).value in ("مهندس رجبی", "مهندس نصیری")
        assert c.get("/api/status").json()["pending_replace"] == 0
        assert c.post(f"/api/exports/{com['export_id']}/undo").json()["restored"]
        assert src.read_bytes() == before

        # فایل اصلی پس از ثبت تغییر کرده: بازگشت فایل را دست نمی‌زند
        com = c.post("/api/excel/commit", json={}).json()
        wb = openpyxl.load_workbook(src); wb["Sheet1"]["A1"].comment = None; wb["Sheet1"].cell(1, 30).value = "x"; wb.save(src)
        edited = src.read_bytes()
        r = c.post(f"/api/exports/{com['export_id']}/undo").json()
        assert not r["restored"] and src.read_bytes() == edited
        # فایل باز در Excel: پیش از هر نوشتنی متوقف می‌شود
        owner = src.with_name("~$" + src.name)
        owner.write_bytes(b"x")
        assert c.post("/api/excel/commit", json={}).status_code == 409
        owner.unlink()
        assert src.read_bytes() == edited

        assert c.get("/api/report/errors.xlsx").status_code == 200
        assert c.get("/api/report/records.xlsx").status_code == 200
        assert c.get("/").status_code == 200
    server.set_worker(None)


def test_undo_edit_approve_and_learning(db, settings, monkeypatch):
    from voice2excel import learning
    from voice2excel.pipeline import build_records
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as c:
        batch = db.create_batch("t", "1405/07/29")
        aid = db.add_audio(batch, "x.ogg", None, "sha-undo", 1, "1405/07/29", "user")
        _, clauses, recs = build_records(db, settings, "مهندس گلزی، شماره 09121234567، آدرس شاهد 12", "1405/07/29")
        db.save_results(aid, {"raw_text": "", "normalized_text": "", "processed_text": ""}, recs)
        db.set_audio(aid, status="done")
        rid = db.list_records()[0]["id"]
        r = c.patch(f"/api/records/{rid}", json={"values": {"engineer_name": "مهندس گلزاری"}}).json()
        assert r["values"]["engineer_name"] == "مهندس گلزاری" and learning.list_corrections(db)
        c.post(f"/api/records/{rid}/action", json={"action": "approve"})
        # بازگشت به ترتیب عکس: اول تأیید، سپس اصلاح
        r = c.post(f"/api/records/{rid}/undo").json()
        assert r["review_state"] == "pending"
        r = c.post(f"/api/records/{rid}/undo").json()
        assert r["values"]["engineer_name"] == "مهندس گلزی" and not r["manually_edited"]
        assert learning.list_corrections(db) == []  # یادگیری هم برگشت
        assert c.post(f"/api/records/{rid}/undo").status_code == 404


def test_migration_adds_columns_to_old_database(tmp_path):
    import sqlite3
    from voice2excel.database import Database
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE record_edits(id INTEGER PRIMARY KEY, record_id INTEGER, field TEXT, old_value TEXT, "
                "new_value TEXT, action TEXT, at TEXT)")
    con.execute("INSERT INTO record_edits(record_id, field, action) VALUES(1, 'x', 'edit')")
    con.commit(); con.close()
    d = Database(p)
    row = d.one("SELECT undone FROM record_edits")
    assert row["undone"] == 0
    d.close()
