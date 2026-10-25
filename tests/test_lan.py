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


def _login(c, pin="482913", name="صالحی"):
    return c.post("/api/m/login", headers={"X-PIN": pin}, json={"name": name})


def test_remote_only_upload_page_with_pin(db, settings, wav_factory, monkeypatch):
    settings.lan_enabled, settings.lan_pin, settings.lan_auto_start = True, "482913", False
    monkeypatch.setattr(server, "_pin_limiter", lan.FailureLimiter())
    with phone_client() as c:
        assert c.get("/m").status_code == 200
        # بقیه بخش‌ها حتی با رمز درست فقط از روی خود رایانه
        for path in ("/api/status", "/api/records?filter=all", "/api/settings", "/api/backups", "/"):
            assert c.get(path, headers={"X-PIN": "482913"}).status_code == 403, path
        assert _login(c, pin="000000").status_code == 401
        # خود رمز فقط برای ورود است؛ بقیه درخواست‌ها کلید گوشی را می‌خواهند
        assert c.post("/api/m/check", headers={"X-PIN": "482913"}).status_code == 401
        token = _login(c).json()["token"]
        dev = {"X-Device": token}
        assert c.post("/api/m/check", headers=dev).json()["name"] == "صالحی"
        wav = wav_factory("phone.wav", 1.0)
        r = c.post("/api/m/upload", headers=dev, files=[("files", (wav.name, wav.read_bytes(), "audio/wav"))],
                   data={"visit_date": "1405/08/02", "sender": "کس دیگر"}).json()
        assert r["results"][0]["result"] == "added" and "id" not in r["results"][0]
        assert db.one("SELECT name FROM batches ORDER BY id DESC LIMIT 1")["name"] == "گوشی: صالحی"  # نه نام دلخواه فرم
        assert c.get("/api/m/recent", headers=dev).json()["files"][0]["original_name"] == "phone.wav"
        other = {"X-Device": _login(c, name="رضایی").json()["token"]}
        assert c.get("/api/m/recent?sender=صالحی", headers=other).json()["files"] == []  # ویس دیگران دیده نمی‌شود
    assert "482913" not in str(db.q("SELECT * FROM lan_devices")) and token not in str(db.q("SELECT * FROM lan_devices"))
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765", headers=server.auth_headers()) as local:  # از خود رایانه همه چیز در دسترس است
        assert local.get("/api/status").status_code == 200
        assert sorted(d["name"] for d in local.get("/api/lan").json()["devices"]) == sorted(["رضایی", "صالحی"])


def test_device_revoke_and_new_pin(db, settings, monkeypatch):
    settings.lan_enabled, settings.lan_pin = True, "482913"
    monkeypatch.setattr(server, "_pin_limiter", lan.FailureLimiter())
    monkeypatch.setattr(server, "save_settings", lambda u: [setattr(settings, k, v) for k, v in u.items()] and settings)
    with phone_client() as c:
        a = {"X-Device": _login(c, name="الف").json()["token"]}
        b = {"X-Device": _login(c, name="ب").json()["token"]}
        with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                        headers=server.auth_headers()) as local:
            dev_a = next(d for d in local.get("/api/lan").json()["devices"] if d["name"] == "الف")
            assert local.delete(f"/api/lan/devices/{dev_a['id']}").status_code == 200
            assert c.post("/api/m/check", headers=a).status_code == 401
            assert c.post("/api/m/check", headers=b).status_code == 200
            local.post("/api/lan/new-pin")
            assert c.post("/api/m/check", headers=b).status_code == 401  # رمز جدید: همه گوشی‌ها برداشته شدند
            assert not local.get("/api/lan").json()["devices"]


def test_lan_auto_off_after_idle(db, settings, monkeypatch):
    import time
    settings.lan_enabled, settings.lan_pin, settings.lan_idle_hours = True, "482913", 4
    saved = {}
    monkeypatch.setattr(server, "save_settings", lambda u: saved.update(u))
    db.set_meta("lan_enabled_at", str(time.time() - 3600))
    assert not server.lan_auto_off()
    db.set_meta("lan_enabled_at", str(time.time() - 5 * 3600))
    assert server.lan_auto_off() and saved == {"lan_enabled": False}
    settings.lan_idle_hours = 0
    assert not server.lan_auto_off()


def test_pin_bruteforce_blocked(db, settings, monkeypatch):
    settings.lan_enabled, settings.lan_pin = True, "482913"
    monkeypatch.setattr(server, "_pin_limiter", lan.FailureLimiter(max_failures=3))
    with phone_client("192.168.1.77") as c:
        for _ in range(3):
            assert _login(c, pin="111111").status_code == 401
        # پس از تلاش‌های ناموفق، حتی رمز درست هم موقتاً پذیرفته نمی‌شود
        assert _login(c).status_code == 429
    with phone_client("192.168.1.78") as other:  # دستگاه دیگر مسدود نیست
        assert _login(other).status_code == 200
    with phone_client("192.168.1.79") as guess:  # حدس زدن کلید گوشی هم شمرده می‌شود
        for _ in range(3):
            assert guess.post("/api/m/check", headers={"X-Device": "guess"}).status_code == 401
        assert guess.post("/api/m/check", headers={"X-Device": "guess"}).status_code == 429


def test_generate_pin_format():
    pins = {lan.generate_pin() for _ in range(50)}
    assert all(len(p) == 6 and p.isdigit() for p in pins) and len(pins) > 40
