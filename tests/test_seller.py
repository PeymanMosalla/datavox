"""پنل فروشنده: صدور، تمدید و پیگیری مجوزها (با کلید آزمون، در پوشه موقت)."""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from seller import app as panel
from seller import store as st
from voice2excel import ed25519, licensing

KEY = bytes(range(7, 39))
CODE = "ABCD-EFGH-IJKL-MNOP"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    (tmp_path / "license-signing.key").write_text(KEY.hex())
    monkeypatch.setattr(st, "KEYS_DIR", tmp_path)
    monkeypatch.setattr(licensing, "LICENSE_PUBLIC_KEY", ed25519.public_key(KEY))
    monkeypatch.setattr(panel, "_store", st.Store(tmp_path / "seller.db"))
    monkeypatch.setattr(panel, "CONTACT_FILE", tmp_path / "contact.json")
    monkeypatch.setattr(panel, "LICENSES_DIR", tmp_path / "licenses")
    with TestClient(panel.app, base_url="http://127.0.0.1:8790", headers={"X-Token": panel.TOKEN}) as c:
        yield c, tmp_path


def test_issue_year_and_forever(env):
    c, tmp = env
    r = c.post("/api/issue", json={"name": "شرکت الف", "phone": "۰۹۱۲۱۲۳۴۵۶۷", "machine": CODE.lower(), "amount": 5000000})
    assert r.status_code == 200
    lic = r.json()
    data = licensing.decode(lic["text"])
    assert data["machine"] == CODE and data["customer"] == "شرکت الف"
    assert data["expires"] == (date.today() + timedelta(days=365)).isoformat() and lic["expires_j"]
    assert (tmp / "licenses" / lic["file"]).read_text(encoding="utf-8") == lic["text"]
    r2 = c.post("/api/issue", json={"name": "الف", "phone": "09121234567", "machine": "QRST-UVWX-YZ23-4567", "kind": "forever"})
    assert "expires" not in licensing.decode(r2.json()["text"])
    custs = c.get("/api/customers").json()["customers"]
    assert len(custs) == 1 and len(custs[0]["machines"]) == 2 and custs[0]["paid"] == 5000000  # همان تلفن، همان مشتری
    assert c.get(f"/api/licenses/{lic['id']}/file").text == lic["text"]


def test_renew_keeps_remaining_days_and_due_list(env):
    c, _ = env
    s = panel._store
    cid = s.find_or_create("ب", "0915")
    early = s.issue(cid, CODE, "year", start=date.today() - timedelta(days=350))  # ۱۵ روز مانده
    assert early["state"] == "soon"
    assert [x["id"] for x in c.get("/api/due").json()["licenses"]] == [early["id"]]
    new = c.post(f"/api/licenses/{early['id']}/renew", json={"amount": 100}).json()
    assert new["expires"] == (date.fromisoformat(early["expires"]) + timedelta(days=365)).isoformat()  # روزی از دست نرفت
    assert c.get("/api/due").json()["licenses"] == []
    lapsed = s.issue(cid, "QRST-UVWX-YZ23-4567", "year", start=date.today() - timedelta(days=400))
    assert lapsed["state"] == "lapsed"
    renewed = c.post(f"/api/licenses/{lapsed['id']}/renew", json={}).json()
    assert renewed["expires"] == (date.today() + timedelta(days=365)).isoformat()  # از امروز
    assert c.post(f"/api/licenses/{renewed['id']}/renew", json={"kind": "forever"}).json()["expires"] is None


def test_bad_input_and_security(env):
    c, _ = env
    assert c.post("/api/issue", json={"name": "x", "machine": "bad-code"}).status_code == 400
    assert c.post("/api/issue", json={"name": " ", "machine": CODE}).status_code == 400
    with TestClient(panel.app, base_url="http://127.0.0.1:8790") as no_token:
        assert no_token.post("/api/issue", json={"name": "x", "machine": CODE}).status_code == 403
    with TestClient(panel.app, base_url="http://evil.example:8790", headers={"X-Token": panel.TOKEN}) as evil:
        assert evil.get("/api/customers").status_code == 403
    assert c.get("/api/customers", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.get("/").headers["x-frame-options"] == "DENY" and panel.TOKEN in c.get("/").text


def test_contact_saved_for_customer_app(env):
    c, tmp = env
    r = c.put("/api/contact", json={"name": "فروشنده", "phone": "0912", "telegram": "@seller_id", "whatsapp": "0912",
                                    "bale": "@bale_id", "email": "a@b.com"}).json()
    assert r["telegram"] == "seller_id" and r["bale"] == "bale_id" and r["email"] == "a@b.com"
    assert c.put("/api/contact", json={"email": "not-an-email"}).status_code == 400
    assert json.loads((tmp / "contact.json").read_text(encoding="utf-8"))["name"] == "فروشنده"


def test_old_license_files_imported_once(env, tmp_path):
    _, tmp = env
    folder = tmp / "old"
    folder.mkdir()
    text = licensing.encode({"customer": "قدیمی", "machine": CODE, "issued": "2026-10-26"}, KEY)
    (folder / "a.v2x").write_text(text, encoding="utf-8")
    assert panel._store.import_folder(folder) == 1 and panel._store.import_folder(folder) == 0
    assert panel._store.customers()[0]["machines"][0]["state"] == "forever"
