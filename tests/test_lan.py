"""دسترسی از گوشی در شبکه محلی: فقط صفحه آپلود، با رمز."""
from fastapi.testclient import TestClient

from voice2excel import lan, server

PHONE = ("192.168.1.50", 50000)


def phone_client(ip="192.168.1.50"):
    return TestClient(server.app, client=(ip, 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers())


def test_local_detection():
    assert lan.is_local("127.0.0.1") and lan.is_local("::1")
    assert not lan.is_local("192.168.1.50") and not lan.is_local(None)


def test_remote_blocked_when_disabled(db, settings):
    settings.lan_enabled = False
    with phone_client() as c:
        assert c.get("/api/status").status_code == 403
        assert c.get("/m").status_code == 403


def test_remote_only_upload_page_with_pin(db, settings, wav_factory, monkeypatch):
    settings.lan_enabled, settings.lan_pin, settings.lan_auto_start = True, "482913", False
    monkeypatch.setattr(server, "_pin_limiter", lan.FailureLimiter())
    with phone_client() as c:
        assert c.get("/m").status_code == 200
        # بقیه بخش‌ها حتی با رمز درست فقط از روی خود رایانه
        for path in ("/api/status", "/api/records?filter=all", "/api/settings", "/api/backups", "/"):
            assert c.get(path, headers={"X-PIN": "482913"}).status_code == 403, path
        assert c.post("/api/m/check").status_code == 401
        assert c.post("/api/m/check", headers={"X-PIN": "000000"}).status_code == 401
        assert c.post("/api/m/check", headers={"X-PIN": "482913"}).json()["ok"]
        wav = wav_factory("phone.wav", 1.0)
        r = c.post("/api/m/upload", headers={"X-PIN": "482913"},
                   files=[("files", (wav.name, wav.read_bytes(), "audio/wav"))],
                   data={"visit_date": "1405/08/02", "sender": "صالحی"}).json()
        assert r["results"][0]["result"] == "added" and "id" not in r["results"][0]
        recent = c.get("/api/m/recent?sender=صالحی", headers={"X-PIN": "482913"}).json()["files"]
        assert recent[0]["original_name"] == "phone.wav"
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as local:  # از خود رایانه همه چیز در دسترس است
        assert local.get("/api/status").status_code == 200


def test_pin_bruteforce_blocked(db, settings, monkeypatch):
    settings.lan_enabled, settings.lan_pin = True, "482913"
    monkeypatch.setattr(server, "_pin_limiter", lan.FailureLimiter(max_failures=3))
    with phone_client("192.168.1.77") as c:
        for _ in range(3):
            assert c.post("/api/m/check", headers={"X-PIN": "111111"}).status_code == 401
        # پس از تلاش‌های ناموفق، حتی رمز درست هم موقتاً پذیرفته نمی‌شود
        assert c.post("/api/m/check", headers={"X-PIN": "482913"}).status_code == 429
    with phone_client("192.168.1.78") as other:  # دستگاه دیگر مسدود نیست
        assert other.post("/api/m/check", headers={"X-PIN": "482913"}).status_code == 200


def test_generate_pin_format():
    pins = {lan.generate_pin() for _ in range(50)}
    assert all(len(p) == 6 and p.isdigit() for p in pins) and len(pins) > 40
