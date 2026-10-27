"""مجوز آفلاین: فقط مجوز امضاشده برای همین رایانه و در مهلت پذیرفته می‌شود."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from voice2excel import ed25519, licensing, server

KEY = bytes(range(1, 33))  # کلید آزمون (کلید واقعی فروشنده خارج از مخزن است)


@pytest.fixture()
def lic(tmp_path, monkeypatch):
    monkeypatch.setattr(licensing, "LICENSE_PUBLIC_KEY", ed25519.public_key(KEY))
    monkeypatch.setattr(licensing, "LICENSE_FILE", tmp_path / "license.v2x")
    monkeypatch.setattr(licensing, "SEEN_FILE", tmp_path / "license.seen")
    monkeypatch.setattr(licensing, "REQUIRED", True)
    licensing._cache["key"] = None
    yield
    licensing._cache["key"] = None


def _make(**over):
    data = {"customer": "شرکت آزمون", "machine": licensing.machine_code(), "issued": date.today().isoformat(), **over}
    return licensing.encode(data, KEY)


def test_machine_code_is_stable_and_readable():
    c = licensing.machine_code()
    assert c == licensing.machine_code() and len(c) == 19 and c.count("-") == 3


def test_valid_license_accepted(lic):
    assert licensing.status()["mode"] == "trial" and not licensing.licensed()  # بدون مجوز: دوره آزمایشی
    st = licensing.install(_make())
    assert st["ok"] and st["mode"] == "licensed" and st["customer"] == "شرکت آزمون" and "trial" not in st


@pytest.mark.parametrize("text, msg", [
    ("hello", "مجوز «ثبت ویس» نیست"),
    (lambda: _make(machine="AAAA-BBBB-CCCC-DDDD"), "رایانه دیگری"),
    (lambda: _make(expires=(date.today() - timedelta(days=1)).isoformat()), "مهلت"),
    (lambda: licensing.encode({"customer": "x", "machine": licensing.machine_code()}, bytes(32)), "امضای"),
])
def test_bad_licenses_rejected(lic, text, msg):
    with pytest.raises(licensing.LicenseError, match=msg):
        licensing.install(text() if callable(text) else text)
    assert not licensing.LICENSE_FILE.exists()


def test_tampered_license_rejected(lic):
    """تغییر نام مشتری یا برداشتن مهلت در متن مجوز، امضا را باطل می‌کند."""
    import base64
    import json
    head, body, sig = _make(expires="2027-01-01").split(".")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    data.pop("expires")
    forged = base64.urlsafe_b64encode(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":")).encode()).decode().rstrip("=")
    with pytest.raises(licensing.LicenseError, match="امضای"):
        licensing.install(f"{head}.{forged}.{sig}")


def test_clock_rollback_detected(lic, monkeypatch):
    licensing.install(_make(expires=(date.today() + timedelta(days=30)).isoformat()))
    licensing.SEEN_FILE.write_text((date.today() + timedelta(days=10)).isoformat())
    licensing._cache["key"] = None
    st = licensing.status()
    assert not st["licensed"] and "عقب" in st["error"] and st["mode"] == "trial"  # مجوز نامعتبر؛ برمی‌گردد به آزمایشی


def test_trial_then_expired_then_licensed(db, lic, monkeypatch, wav_factory):
    """آزمایشی: همه چیز باز. پس از پایان: فقط ویس تازه بسته، رکوردها و اکسل باز. با مجوز: دوباره همه باز."""
    from voice2excel import trial
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server, "model_available", lambda name: False)
    wav = wav_factory("a.wav", 0.5).read_bytes()
    up = lambda c: c.post("/api/upload", files=[("files", ("a.wav", wav, "audio/wav"))],  # noqa: E731
                          data={"visit_date": "1405/08/04"})
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                    headers=server.auth_headers()) as c:
        info = c.get("/api/license").json()
        assert info["ok"] and info["mode"] == "trial" and info["trial"]["voices_left"] == 10
        assert up(c).status_code == 200 and c.get("/api/records").status_code == 200
        assert c.post("/api/update").status_code == 402  # به‌روزرسانی فقط با اشتراک
        for _ in range(10):
            trial.record_voice()
        info = c.get("/api/license").json()
        assert not info["ok"] and info["mode"] == "expired" and info["trial"]["reason"] == "ویس"
        assert up(c).status_code == 402 and c.post("/api/queue/start").status_code == 402
        assert c.post("/api/files/1/retry").status_code == 402 and c.post("/api/import-folder", json={"path": "x"}).status_code == 402
        for path in ("/api/records", "/api/status", "/api/backups", "/api/dictionary"):  # رکوردهای قبلی باز
            assert c.get(path).status_code == 200, path
        assert c.post("/api/excel/commit", json={}).status_code != 402
        assert c.post("/api/license", json={"text": "V2X1.bad.bad"}).status_code == 400
        r = c.post("/api/license", json={"text": _make(expires="2099-03-20")})
        assert r.status_code == 200 and r.json()["ok"] and r.json()["expires_jalali"] == "1478/01/01"
        assert up(c).status_code == 200
        trial.record_voice()  # با اشتراک شمرده نمی‌شود (note_processed)، ولی حتی اگر شود، مهم نیست
        assert c.get("/api/license").json()["mode"] == "licensed"


def test_subscription_lapse_and_renewal_reminder(db, lic, monkeypatch):
    """اشتراک یک‌ساله: روزهای مانده گزارش می‌شود؛ پس از پایان، «تمدید» (نه «آزمایشی») و رکوردها باز."""
    from voice2excel import trial
    licensing.install(_make(expires=(date.today() + timedelta(days=10)).isoformat()))
    st = licensing.status()
    assert st["mode"] == "licensed" and st["days_left"] == 10
    licensing.LICENSE_FILE.write_text(_make(expires=(date.today() - timedelta(days=1)).isoformat()), encoding="utf-8")
    licensing._cache["key"] = None
    trial._write_all({"m": licensing.machine_code(), "s": "2020-01-01", "d": date.today().isoformat(), "v": 0})
    st = licensing.status()
    assert st["mode"] == "expired" and st["lapsed"] and not licensing.can_process()
    assert licensing.install(_make())["mode"] == "licensed"  # مجوز نامحدود تازه
    assert "days_left" not in licensing.status()


def test_contact_info_shown_only_when_set(db, lic, monkeypatch, tmp_path):
    import json
    from pathlib import Path
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    real = Path(licensing.__file__).parent / "assets" / "contact.json"
    assert set(json.loads(real.read_text(encoding="utf-8"))) <= {"name", "phone", "telegram", "whatsapp", "bale", "email"}
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                    headers=server.auth_headers()) as c:
        info = c.get("/api/license").json()
        assert set(info["contact"]) == {"name", "phone", "telegram", "whatsapp", "bale", "email"} and info["version"]
