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
    assert not licensing.status()["ok"]
    st = licensing.install(_make())
    assert st["ok"] and st["customer"] == "شرکت آزمون"


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
    assert not st["ok"] and "عقب" in st["error"]


def test_server_locked_until_activated(db, lic, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                    headers=server.auth_headers()) as c:
        assert c.get("/api/records").status_code == 402
        assert c.post("/api/files/retry-failed").status_code == 402
        assert c.get("/api/status").status_code == 200  # Voice2Excel.exe با همین، آماده بودن برنامه را می‌سنجد
        info = c.get("/api/license").json()
        assert not info["ok"] and info["machine"] == licensing.machine_code()
        assert c.post("/api/license", json={"text": "V2X1.bad.bad"}).status_code == 400
        r = c.post("/api/license", json={"text": _make(expires="2099-03-20")})
        assert r.status_code == 200 and r.json()["ok"] and r.json()["expires_jalali"] == "1478/01/01"
        assert c.get("/api/records").status_code == 200
