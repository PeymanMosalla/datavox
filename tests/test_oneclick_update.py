"""نصب به‌روزرسانی با یک کلیک: فقط با بسته آماده و اجراکننده جدید؛ موتور با کد ویژه خاموش می‌شود."""
import pytest
from fastapi.testclient import TestClient

from voice2excel import server, updater


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    exits = []

    class FakeTimer:  # خاموش کردن واقعی، فرایند آزمون را می‌بست
        def __init__(self, _delay, fn):
            self.fn = fn

        def start(self):
            exits.append(self.fn)

    monkeypatch.setattr(server.threading, "Timer", FakeTimer)
    monkeypatch.setattr(server.os, "_exit", lambda code: exits.append(code))
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                    headers=server.auth_headers()) as c:
        yield c, exits


def test_apply_needs_staged_update_and_new_launcher(client, monkeypatch):
    c, exits = client
    monkeypatch.delenv("V2X_LAUNCHER", raising=False)
    monkeypatch.setattr(updater, "staged_info", lambda: None)
    assert c.post("/api/update/apply").status_code == 409
    monkeypatch.setattr(updater, "staged_info", lambda: {"version": "9.9.9", "notes": ""})
    assert c.get("/api/update").json()["one_click"] is False
    r = c.post("/api/update/apply")
    assert r.status_code == 409 and "خروج از برنامه" in r.json()["detail"]  # اجراکننده قدیمی: روش قبلی
    assert not exits


def test_apply_exits_with_restart_code(client, monkeypatch):
    c, exits = client
    monkeypatch.setenv("V2X_LAUNCHER", "2")
    monkeypatch.setattr(updater, "staged_info", lambda: {"version": "9.9.9", "notes": ""})
    assert c.get("/api/update").json()["one_click"] is True
    r = c.post("/api/update/apply").json()
    assert r["restarting"] and r["to"] == "9.9.9"
    exits[0]()  # همان کاری که زمان‌سنج پس از نیم ثانیه می‌کند
    assert exits[-1] == server.RESTART_FOR_UPDATE
    assert not (server.DATA_DIR / ".quit").exists()  # این خاموشی «خروج» نیست؛ پنجره باز می‌ماند


def test_quit_leaves_marker_for_launcher(client):
    c, exits = client
    (server.DATA_DIR / ".quit").unlink(missing_ok=True)
    assert c.post("/api/shutdown").json()["ok"]
    assert (server.DATA_DIR / ".quit").exists()
    exits[0]()
    assert exits[-1] == 0
    (server.DATA_DIR / ".quit").unlink()
