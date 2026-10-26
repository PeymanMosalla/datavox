"""انتقال واژه‌نامه به رایانه دیگر: فقط نام‌ها و اصلاحات، بدون رکورد و ویس؛ ورود فقط اضافه می‌کند."""
import json

from fastapi.testclient import TestClient

from voice2excel import backup, dictionary, server, vault


def _client():
    return TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                      headers=server.auth_headers())


def _seed(db):
    eid = dictionary.add_entity(db, "کاظمی", "engineer")
    dictionary.add_alias(db, eid, "کازمی")
    dictionary.add_entity(db, "سجادیه", "street")
    with db.tx() as c:
        c.execute("INSERT INTO corrections(field_group, wrong, right, count, enabled) VALUES('address','سجادیع','سجادیه',3,1)")
    db.log_event("تماس با 09151234567")


def _counts(db):
    return [db.one(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("entities", "aliases", "corrections")]


def test_dictionary_moves_without_customer_data(db, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(backup, "_key_file", lambda: tmp_path / "backup-key.json")
    _seed(db)
    before = _counts(db)
    with _client() as c:
        assert c.post("/api/dictionary/export").status_code == 400  # رمزگذاری روشن ولی بی‌گذرواژه
        c.put("/api/backups/encryption", json={"enabled": True, "password": "رمز-امن-آزمون"})
        r = c.post("/api/dictionary/export")
        assert r.status_code == 200 and ".v2xdict" in r.headers["content-disposition"] and vault.is_encrypted(r.content)
        data = json.loads(vault.decrypt(r.content, "رمز-امن-آزمون"))
        text = json.dumps(data, ensure_ascii=False)
        assert "کازمی" in text and "سجادیع" in text and "0915" not in text and "records" not in data
        db.wipe_all()  # مثل رایانه تازه
        imp = lambda blob, pw="": c.post("/api/dictionary/import", data={"password": pw},  # noqa: E731
                                         files={"file": ("d", blob, "application/octet-stream")})
        res = imp(r.content).json()["added"]
        assert res == {"entities": 2, "aliases": 1, "corrections": 1} and _counts(db) == before
        assert imp(r.content).json()["added"] == {"entities": 0, "aliases": 0, "corrections": 0}  # دوباره: تکراری نمی‌شود
        assert db.one("SELECT COUNT(*) n FROM entity_changes WHERE action='alias'")["n"] == 1
        # رایانه دیگر با گذرواژه دیگر: گذرواژه فایل لازم است
        c.put("/api/backups/encryption", json={"enabled": True, "password": "گذرواژه-دیگر-۲"})
        assert imp(r.content).status_code == 400 and imp(r.content, "رمز-امن-آزمون").status_code == 200
        for bad in (b"not json", json.dumps({"app": "x"}).encode(),
                    json.dumps({"app": "voice2excel", "type": "dictionary", "entities": "zz"}).encode()):
            assert imp(bad).status_code == 400, bad


def test_dictionary_import_ignores_invalid_items(db):
    data = {"app": "voice2excel", "type": "dictionary", "entities": [
        {"t": "engineer", "c": "رضایی"}, {"t": "hacker", "c": "x"}, {"t": "street", "c": "x" * 500}, "junk",
        {"t": "street", "c": "وکیل‌آباد", "a": ["وکیل آباد", 5, ""]}],
        "corrections": [{"g": "name", "w": "رضاعی", "r": "رضایی"}, {"g": "evil", "w": "a", "r": "b"}]}
    assert dictionary.import_data(db, data) == {"entities": 2, "aliases": 1, "corrections": 1}
