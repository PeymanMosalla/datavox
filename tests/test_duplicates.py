"""ویس تکراری (نسخه ۲.۷.۱): یک ویس می‌تواند در چند فایل اکسل باشد.

- آپلود از رایانه: هیچ ویسی رد نمی‌شود؛ رابط کاربری پیش از آپلود با /api/upload/check می‌پرسد.
- «از همان استفاده شود»: /api/files/{id}/reuse متن و ردیف‌های ویس پردازش‌شده را بدون تبدیل دوباره به فایل دیگر می‌آورد.
- گوشی و پوشه ورودی (کسی برای پرسیدن نیست): فقط ویسی که همین حالا در همان فایل هست دوباره اضافه نمی‌شود.
- فایل صوتی مشترک با حذف یک رونوشت پاک نمی‌شود.
"""
import sqlite3

from voice2excel import server
from voice2excel.database import Database
from voice2excel.deduplicator import file_sha256
from tests.test_dests import _add_file, client  # noqa: F401  (fixture)
from tests.test_excel import make_company_like
from tests.test_templates import _add_approved

TEXT = "مهندس رجبی شماره 09151234567 آدرس سجادیه 58"


def _upload(c, path, dest):
    return c.post("/api/upload", files=[("files", (path.name, path.read_bytes(), "audio/wav"))],
                  data={"visit_date": "1405/07/28", "dest": dest}).json()["results"][0]


def test_upload_same_voice_into_two_files(client, wav_factory, tmp_path):  # noqa: F811
    a = _add_file(client, make_company_like(tmp_path / "الف.xlsx"))
    b = _add_file(client, make_company_like(tmp_path / "ب.xlsx"))
    w = wav_factory("v.wav", 1.0)
    r1, r2, r3 = _upload(client, w, a["name"]), _upload(client, w, b["name"]), _upload(client, w, b["name"])
    assert r1["result"] == r2["result"] == r3["result"] == "added"  # کاربر خودش «خیر، دوباره پردازش شود» زده است
    m = client.post("/api/upload/check", json={"hashes": [file_sha256(w)], "dest": b["name"]}).json()["matches"]
    assert m[file_sha256(w)]["same_dest"] is True  # در همین فایل هم هست: همان ترجیح داده می‌شود


def test_check_reports_processed_voice_in_other_file(client, db, settings, tmp_path):  # noqa: F811
    a = _add_file(client, make_company_like(tmp_path / "الف.xlsx"))
    b = _add_file(client, make_company_like(tmp_path / "ب.xlsx"))
    sha = "ab" * 32
    _add_approved(db, settings, TEXT, sha, dest=a["name"])
    m = client.post("/api/upload/check", json={"hashes": [sha, "cd" * 32, "نامعتبر"], "dest": b["name"]}).json()["matches"]
    assert list(m) == [sha]
    assert m[sha]["processed"] and not m[sha]["same_dest"] and m[sha]["rows"] == 1 and m[sha]["dest_label"] == "الف.xlsx"


def test_reuse_copies_rows_without_reprocessing(client, db, settings, tmp_path):  # noqa: F811
    a = _add_file(client, make_company_like(tmp_path / "الف.xlsx"))
    b = _add_file(client, make_company_like(tmp_path / "ب.xlsx"))
    sha = "ef" * 32
    _add_approved(db, settings, TEXT, sha, dest=a["name"])
    src = db.one("SELECT id FROM audio_files WHERE sha256=?", (sha,))["id"]
    r = client.post(f"/api/files/{src}/reuse", json={"dest": b["name"]}).json()
    assert r["result"] == "reused"
    new = db.one("SELECT * FROM audio_files WHERE id=?", (r["id"],))
    assert new["dest"] == b["name"] and new["status"] == "done" and new["sha256"] == sha
    rec = db.list_records("r.audio_id=?", (r["id"],))[0]
    assert rec["values"]["engineer_name"] == "مهندس رجبی" and rec["review_state"] == "approved"
    # همان ویس در فایل دیگر، تکراری این ردیف حساب نمی‌شود
    assert not [d for d in rec["validation"].get("duplicates", []) if d.get("source") == "db"]
    assert db.one("SELECT raw_text FROM transcripts WHERE audio_id=?", (r["id"],))["raw_text"] == TEXT
    # دوباره به همان فایل: لازم نیست
    assert client.post(f"/api/files/{src}/reuse", json={"dest": a["name"]}).status_code == 409


def test_phone_and_inbox_skip_only_same_file(client, db, wav_factory, tmp_path):  # noqa: F811
    a = _add_file(client, make_company_like(tmp_path / "الف.xlsx"))
    b = _add_file(client, make_company_like(tmp_path / "ب.xlsx"))
    w = wav_factory("v.wav", 1.0)
    batch = db.create_batch("t", "1405/07/28")
    with open(w, "rb") as fh:
        assert server._register_file(fh, "v.wav", batch, "1405/07/28", False, a["name"])["result"] == "added"
    with open(w, "rb") as fh:
        assert server._register_file(fh, "v (1).wav", batch, "1405/07/28", False, a["name"])["result"] == "duplicate"
    with open(w, "rb") as fh:
        assert server._register_file(fh, "v.wav", batch, "1405/07/28", False, b["name"])["result"] == "added"


def test_deleting_one_copy_keeps_shared_audio(client, db, wav_factory, tmp_path):  # noqa: F811
    a = _add_file(client, make_company_like(tmp_path / "الف.xlsx"))
    b = _add_file(client, make_company_like(tmp_path / "ب.xlsx"))
    w = wav_factory("v.wav", 1.0)
    r1, r2 = _upload(client, w, a["name"]), _upload(client, w, b["name"])
    stored = db.one("SELECT stored_name FROM audio_files WHERE id=?", (r1["id"],))["stored_name"]
    path = server.DATA_DIR / "uploads" / stored
    assert client.delete(f"/api/files/{r1['id']}").json()["ok"] and path.exists()
    assert client.delete(f"/api/files/{r2['id']}").json()["ok"] and not path.exists()


def test_old_database_unique_hash_is_removed(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE batches(id INTEGER PRIMARY KEY, name TEXT, visit_date TEXT, created_at TEXT)")
    con.execute("CREATE TABLE audio_files(id INTEGER PRIMARY KEY, batch_id INTEGER, original_name TEXT NOT NULL, "
                "stored_name TEXT, sha256 TEXT UNIQUE, size INTEGER, duration REAL, visit_date TEXT, date_source TEXT, "
                "status TEXT NOT NULL DEFAULT 'queued', error TEXT, attempts INTEGER NOT NULL DEFAULT 0, model TEXT, "
                "processing_seconds REAL, peak_rss_mb REAL, audio_deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT, "
                "updated_at TEXT, dest TEXT)")
    con.execute("CREATE TABLE transcripts(audio_id INTEGER PRIMARY KEY REFERENCES audio_files(id) ON DELETE CASCADE, raw_text TEXT)")
    con.execute("INSERT INTO audio_files(id, original_name, sha256, status, dest) VALUES(7, 'a.ogg', 'h1', 'done', 'default')")
    con.execute("INSERT INTO transcripts(audio_id, raw_text) VALUES(7, 'سلام')")
    con.commit()
    con.close()
    d = Database(p)
    assert d.one("SELECT original_name, dest FROM audio_files WHERE id=7") == {"original_name": "a.ogg", "dest": "default"}
    d.add_audio(d.create_batch("t", "1405/07/28"), "b.ogg", None, "h1", 1, "1405/07/28", "user", "other")  # دیگر خطای UNIQUE نمی‌دهد
    assert d.one("SELECT COUNT(*) n FROM audio_files WHERE sha256='h1'")["n"] == 2
    assert d.one("SELECT raw_text FROM transcripts WHERE audio_id=7")["raw_text"] == "سلام"
    assert d.q("PRAGMA foreign_key_check") == []
    d.close()
    Database(p).close()  # بار دوم: کاری نمی‌کند
