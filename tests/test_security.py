"""آزمون‌های امنیتی: هر حفره‌ای که پیدا و بسته شده، اینجا یک آزمون دارد تا دوباره باز نشود."""
import pytest
from fastapi.testclient import TestClient

from voice2excel import server

LOCAL = {"client": ("127.0.0.1", 50000), "base_url": "http://127.0.0.1:8765"}


def _client(**headers):
    return TestClient(server.app, **LOCAL, headers=headers)


# ---------- ۱. فرمان یا خواندن داده از صفحه سایت‌های دیگر ----------
def test_foreign_site_cannot_send_commands(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with _client() as c:
        # درخواست «ساده» مرورگر از سایت دیگر (فرم، بدون کلید): پیش‌تر پذیرفته می‌شد
        for path in ("/api/lan/new-pin", "/api/files/retry-failed", "/api/records/revalidate-all", "/api/shutdown"):
            r = c.post(path, headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
            assert r.status_code == 403, path
        # حتی بدون Origin، فرمان بدون کلید محرمانه پذیرفته نمی‌شود
        assert c.post("/api/files/retry-failed").status_code == 403
        assert c.post("/api/files/retry-failed", headers={"X-V2X-Token": "wrong"}).status_code == 403
        assert c.post("/api/files/retry-failed", headers=server.auth_headers()).status_code == 200
        # خواندن (GET) از صفحه خود برنامه بدون کلید ممکن است (پخش صدا، دانلود)؛ خواندن از سایت دیگر را مرورگر نمی‌گذارد
        assert c.get("/api/status").status_code == 200


def test_dns_rebinding_host_is_rejected(db, monkeypatch):
    """دامنه مهاجم که به 127.0.0.1 اشاره می‌کند: مرورگر آن را هم‌مبدأ می‌داند، پس خود برنامه باید رد کند."""
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://evil.example:8765",
                    headers=server.auth_headers()) as c:
        assert c.get("/api/records?filter=all").status_code == 403
        assert c.get("/api/fs", params={"path": "C:/Users"}).status_code == 403
        assert c.get("/").status_code == 403
    for host in ("localhost:8765", "127.0.0.1:8765", "[::1]:8765"):
        with TestClient(server.app, client=("127.0.0.1", 50000), base_url=f"http://{host}") as c:
            assert c.get("/api/status").status_code == 200, host


def test_token_only_in_app_page(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with _client() as c:
        page = c.get("/")
        assert server.API_TOKEN in page.text and page.headers["cache-control"] == "no-store"
        assert server.API_TOKEN not in c.get("/api/status").text
        assert server.API_TOKEN not in c.get("/static/index.html").text


def test_lan_ip_host_allowed_only_when_lan_enabled(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server.lan, "lan_addresses", lambda: ["192.168.1.50"])
    server._lan_ips["at"] = 0
    with TestClient(server.app, client=("192.168.1.60", 50000), base_url="http://192.168.1.50:8765") as c:
        server.save_settings({"lan_enabled": False, "lan_pin": ""})
        assert c.get("/m").status_code == 403
        server.save_settings({"lan_enabled": True, "lan_pin": "123456"})
        server._lan_ips["at"] = 0
        assert c.get("/m").status_code == 200
        # گوشی فقط صفحه آپلود را دارد و رمز لازم است؛ کلید محرمانه برنامه را ندارد و لازم هم ندارد
        assert c.post("/api/m/check", headers={"X-PIN": "000000"}).status_code == 401
        assert c.post("/api/files/retry-failed").status_code == 403
    server.save_settings({"lan_enabled": False, "lan_pin": ""})


# ---------- ۷. ورودی‌ها: فایل جعلی، حجم زیاد، بمب فشرده ----------
def _upload(c, name, data):
    return c.post("/api/upload", files=[("files", (name, data, "application/octet-stream"))],
                  data={"visit_date": "1405/07/28"}).json()["results"][0]


def test_fake_or_huge_audio_rejected(db, monkeypatch, wav_factory):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server, "model_available", lambda name: False)
    with _client(**server.auth_headers()) as c:
        for fake in (b"MZ\x90\x00 program", b"PK\x03\x04 zip", b"<html><script>x</script>", b"%PDF-1.7"):
            r = _upload(c, "voice.mp3", fake)
            assert r["result"] == "error" and "صوتی نیست" in r["message"], fake
        assert _upload(c, "ok.wav", wav_factory("a.wav", 0.5).read_bytes())["result"] == "added"
        monkeypatch.setattr(server, "MAX_AUDIO_BYTES", 1000)
        r = _upload(c, "big.wav", wav_factory("b.wav", 0.5).read_bytes())
        assert r["result"] == "error" and "گیگابایت" in r["message"]
    assert not [p for p in (server.DATA_DIR / "uploads").glob(".incoming_*")]  # فایل نیمه‌کاره نماند


def test_oversized_request_rejected_before_reading(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server, "MAX_REQUEST_BYTES", 100)
    with _client(**server.auth_headers()) as c:
        assert c.post("/api/upload", content=b"x" * 500).status_code == 413
        assert c.post("/api/upload", headers={"Content-Length": "abc"}, content=b"").status_code in (400, 413)


def test_security_headers_and_no_inline_script(db, monkeypatch):
    """صفحه در قاب سایت دیگر باز نمی‌شود (کلیک فریبنده) و فقط کد خود برنامه اجرا می‌شود (در برابر XSS)."""
    import re
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with _client() as c:
        for path in ("/", "/m"):
            r = c.get(path)
            assert r.headers["x-frame-options"] == "DENY"
            csp = r.headers["content-security-policy"]
            assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-eval" not in csp
            assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", r.text), path  # اسکریپت درون‌خطی با CSP اجرا نمی‌شود
            assert not re.search(r"\son[a-z]+\s*=", r.text), path
        assert c.get("/api/status").headers["x-content-type-options"] == "nosniff"
    js = (server.WEB_DIR / "app.js").read_text(encoding="utf-8") + (server.WEB_DIR / "m.js").read_text(encoding="utf-8")
    assert not re.search(r"\bon[a-z]+=\?[\"']", js) and "eval(" not in js and "new Function" not in js


def _bomb_xlsx(path, size=2 * 1024 * 1024):
    import zipfile
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", b"0" * size)
    return path


def test_excel_zip_bomb_rejected(db, monkeypatch, tmp_path):
    from voice2excel import excel_reader
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(excel_reader, "MAX_UNPACKED_BYTES", 1024 * 1024)
    bomb = _bomb_xlsx(tmp_path / "bomb.xlsx")
    assert bomb.stat().st_size < 50 * 1024  # کوچک روی دیسک، بزرگ پس از باز شدن
    rep = excel_reader.inspect_workbook(bomb)
    assert any(r["level"] == "block" and "غیرعادی" in r["message"] for r in rep["risks"])
    with _client(**server.auth_headers()) as c:
        r = c.post("/api/knowledge/analyze", files=[("files", ("b.xlsx", bomb.read_bytes(), "application/octet-stream"))])
        assert "غیرعادی" in r.json()["files"][0]["error"]
        r = c.post("/api/templates/from-file", files={"file": ("b.xlsx", bomb.read_bytes(), "application/octet-stream")})
        assert r.status_code == 400 and "غیرعادی" in r.json()["detail"]
        r = c.post("/api/templates/from-file", files={"file": ("x.xlsx", b"not a zip", "application/octet-stream")})
        assert r.status_code == 400


def test_backup_restore_extracts_only_known_parts(db, monkeypatch):
    import zipfile

    from voice2excel import backup
    made = backup.create_backup(db, "manual")
    with zipfile.ZipFile(backup.backup_path(made["name"]), "a") as z:
        z.writestr("../../evil.py", "x")
        z.writestr("voice2excel/server.py", "x")
    extracted = []
    real = zipfile.ZipFile.extract
    monkeypatch.setattr(zipfile.ZipFile, "extract",
                        lambda self, m, path=None, pwd=None: extracted.append(getattr(m, "filename", m)) or real(self, m, path, pwd))
    backup.restore_backup(db, made["name"])
    assert "voice2excel.db" in extracted and not [n for n in extracted if "evil" in n or n.endswith(".py")]
    monkeypatch.setattr(backup, "MAX_RESTORE_BYTES", 10)
    with pytest.raises(backup.BackupError, match="غیرعادی"):
        backup.restore_backup(db, made["name"])


# ---------- ۸. حریم خصوصی ----------
def test_phone_numbers_masked_in_events_and_tracebacks(db):
    import logging

    from voice2excel.logger import _MaskFilter, mask_sensitive
    db.log_event("ثبت در اکسل ناموفق: مقدار 0915 123 4567 و ۰۹۱۲۱۲۳۴۵۶۷ و شماره09351234567")
    msg = db.q("SELECT message FROM events")[0]["message"]
    assert "4567" not in msg and "1234567" not in msg and "091***" in msg
    assert mask_sensitive("backup-20261026-101500-manual.zip") == "backup-20261026-101500-manual.zip"
    try:
        raise ValueError("bad phone 09151234567")
    except ValueError:
        import sys
        rec = logging.LogRecord("x", logging.ERROR, "", 0, "failed %s", ("09121112233",), sys.exc_info())
    _MaskFilter().filter(rec)
    out = logging.Formatter().format(rec)
    assert "09151234567" not in out and "09121112233" not in out


def test_full_wipe_needs_phrase_and_removes_everything(db, monkeypatch, wav_factory):
    from voice2excel import backup
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server, "model_available", lambda name: False)
    with _client(**server.auth_headers()) as c:
        assert _upload(c, "a.wav", wav_factory("a.wav", 0.5).read_bytes())["result"] == "added"
        db.log_event("رخداد آزمون")
        db.set_meta("inbox_since", "123")
        backup.create_backup(db, "manual")
        assert c.post("/api/maintenance/wipe", json={"confirm": "بله"}).status_code == 400
        assert db.one("SELECT COUNT(*) n FROM audio_files")["n"] == 1
        assert c.post("/api/maintenance/wipe", json={"confirm": "پاک شود"}).json()["ok"]
    for t in ("audio_files", "batches", "events", "records", "entities"):
        assert db.one(f"SELECT COUNT(*) n FROM {t}")["n"] == 0, t
    assert db.get_meta("inbox_since") == "123"  # پوشه ورودی، ویس‌های قدیمی را دوباره اضافه نکند
    assert not list((server.DATA_DIR / "uploads").iterdir()) and not backup.list_backups()


# ---------- ۹. یافته‌های بررسی ایستا ----------
def test_open_folder_only_inside_allowed_dirs(db, monkeypatch):
    opened = []
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server.os, "startfile", lambda p: opened.append(p), raising=False)
    monkeypatch.setattr(server, "_write_profile", lambda *a, **k: None)
    sibling = server.DATA_DIR.parent / (server.DATA_DIR.name + "-other")  # پیش‌تر با مقایسه پیشوندی پذیرفته می‌شد
    sibling.mkdir(exist_ok=True)
    with _client(**server.auth_headers()) as c:
        assert c.post("/api/open-folder", json={"path": str(sibling)}).status_code == 403
        assert c.post("/api/open-folder", json={"path": str(server.DATA_DIR / ".." / "..")}).status_code == 403
        assert c.post("/api/open-folder", json={"path": str(server.DATA_DIR / "uploads")}).status_code == 200
    assert len(opened) == 1


# ---------- آزمون‌های نفوذ ----------
def test_cross_site_get_cannot_trigger_anything(db, monkeypatch):
    """تصویری در سایت دیگر با نشانی /api/fs و مسیر شبکه‌ای سرور مهاجم: ویندوز به آن سرور وصل می‌شد و هش
    رمز کاربر را می‌فرستاد. حالا مرورگر Sec-Fetch-Site را می‌فرستد و درخواست پیش از رسیدن به برنامه رد می‌شود."""
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    touched = []
    with _client() as c:
        monkeypatch.setattr(server.Path, "is_dir", lambda self: touched.append(str(self)) or False)
        for site in ("cross-site", "same-site"):
            for path in ("/api/fs?path=%5C%5Cevil%5Cshare", "/api/files/1/audio", "/api/report/records.xlsx", "/static/app.js"):
                r = c.get(path, headers={"Sec-Fetch-Site": site, "Sec-Fetch-Mode": "no-cors"})
                assert r.status_code == 403, (site, path)
        assert not [p for p in touched if "evil" in p]
        monkeypatch.undo()
        # باز کردن خود برنامه از پیوند یک صفحه دیگر مجاز است (کلید را آن صفحه نمی‌تواند بخواند)
        assert c.get("/", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}).status_code == 200
        # درخواست‌های خود برنامه
        assert c.get("/api/status", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
        assert c.get("/", headers={"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"}).status_code == 200


def test_formula_injection_never_becomes_formula(tmp_path):
    """مقدار یا عنوان ستونی که با = شروع شود (از ویس، اصلاح دستی یا قالبِ دریافتی از دیگری) فرمول نمی‌شود."""
    import io

    import openpyxl

    from voice2excel import excel_template
    evil = "=cmd|' /C calc'!A0"
    tpl = excel_template.new_template("t_x", "x", str(tmp_path))
    tpl["columns_list"][0]["title"] = evil
    tpl = excel_template.clean(tpl)
    data = excel_template.build_sample(tpl, [["=HYPERLINK(\"http://evil\",\"x\")", "+98 915", "@SUM(1)", "-1+2"]])
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    cells = [ws.cell(1, 1), ws.cell(2, 1), ws.cell(2, 2), ws.cell(2, 3), ws.cell(2, 4)]
    assert ws.cell(1, 1).value == evil
    assert all(c.data_type == "s" for c in cells), [(c.value, c.data_type) for c in cells]


def test_path_traversal_in_names_rejected(db, monkeypatch):
    from voice2excel import excel_mapping
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    assert excel_mapping._safe_name(r"..\..\settings") == "_settings"
    with _client(**server.auth_headers()) as c:
        for bad in ("..%5C..%5Csettings", "..%2F..%2Fsettings", "%2E%2E%5Cvoice2excel"):
            assert c.get(f"/api/templates/{bad}").status_code in (404, 400), bad
            assert c.get(f"/api/backups/{bad}/download").status_code in (404, 400), bad
        assert c.post("/api/knowledge/preview", json={"token": r"..\..\voice2excel.db", "sheet": "x", "header_row": 1,
                                                      "columns": {"A": "engineer"}}).status_code == 400

