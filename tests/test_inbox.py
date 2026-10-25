"""آزمون پوشه ورودی خودکار."""
import os
import time

from fastapi.testclient import TestClient

from voice2excel import server
from voice2excel.inbox import Inbox


def test_inbox_takes_only_new_finished_audio(tmp_path):
    old = tmp_path / "old.ogg"
    old.write_bytes(b"x" * 10)
    os.utime(old, (1000, 1000))
    since = time.time() - 5
    (tmp_path / "note.txt").write_bytes(b"x")
    (tmp_path / "~tmp.ogg").write_bytes(b"x")
    v = tmp_path / "PTT-20261020-WA0001.opus"
    v.write_bytes(b"a" * 10)
    box = Inbox()
    assert box.poll(tmp_path, since) == []  # اولین بار فقط اندازه ثبت می‌شود
    v.write_bytes(b"a" * 20)  # هنوز در حال دانلود
    assert box.poll(tmp_path, since) == []
    assert box.poll(tmp_path, since) == [v]  # اندازه ثابت ماند
    assert box.poll(tmp_path, since) == []  # یک بار برداشته می‌شود
    assert box.poll(tmp_path / "missing", since) == []


def test_inbox_registers_and_dates_from_filename(db, settings, tmp_path, wav_factory, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setattr(server, "model_available", lambda n: False)
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)  # بررسی پوشه فقط به دست خود آزمون
    with TestClient(server.app, client=("127.0.0.1", 50000)) as c:
        assert c.put("/api/settings", json={"inbox_dir": str(tmp_path / "nope")}).status_code == 400
        old = wav_factory("old.wav", 0.5)
        os.replace(old, inbox / "old.wav")
        os.utime(inbox / "old.wav", (1000, 1000))
        assert c.put("/api/settings", json={"inbox_dir": str(inbox)}).status_code == 200
        assert c.get("/api/status").json()["setup"]["inbox"] == str(inbox)
        new = wav_factory("PTT-20261020-WA0001.wav", 0.5)
        os.replace(new, inbox / new.name)
        box = Inbox()
        assert server.inbox_poll_once(box) == 0
        assert server.inbox_poll_once(box) == 1
        files = c.get("/api/files").json()["files"]
        assert [f["original_name"] for f in files] == ["PTT-20261020-WA0001.wav"]  # ویس قدیمی برداشته نشد
        assert files[0]["visit_date"] == "1405/07/28" and files[0]["date_source"] == "filename"
        assert c.put("/api/settings", json={"inbox_dir": ""}).status_code == 200
        assert server.inbox_poll_once(Inbox()) == 0
