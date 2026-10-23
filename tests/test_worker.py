import shutil

from voice2excel.config import DATA_DIR
from voice2excel.deduplicator import file_sha256
from voice2excel.transcriber import TranscriptResult
from voice2excel.worker import Worker

TEXTS = {
    1.0: "مهندس رجبی شماره 09373451255 آدرس سجادیه 58 قطعه دوم سازه فلز 7 سقف",
    1.5: "مهندس نصیری شماره 09151112233 آدرس فلاحی 34 تعداد 5 سقف",
    2.0: "مهندس عبدی شماره 09155554433 آدرس خرمشهر 19 نبش هویزه 16",
}


class FakeTranscriber:
    """جایگزین مدل گفتار: متن را بر اساس طول ویس برمی‌گرداند."""

    def __init__(self, stop_after=None):
        self.settings = None
        self.calls = 0
        self.stop_after = stop_after

    def transcribe(self, audio, hotwords=None, should_stop=None):
        self.calls += 1
        if self.stop_after and self.calls >= self.stop_after and should_stop:
            from voice2excel.transcriber import TranscriptionCancelled
            raise TranscriptionCancelled()
        dur = round(len(audio) / 16000 * 2) / 2
        return TranscriptResult(text=TEXTS.get(dur, ""), model="fake")


def add(db, path, name=None):
    sha = file_sha256(path)
    stored = sha[:20] + path.suffix
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    shutil.copy(path, DATA_DIR / "uploads" / stored)
    batch = db.create_batch("t", "1405/07/28")
    return db.add_audio(batch, name or path.name, stored, sha, path.stat().st_size, "1405/07/28", "user")


def test_queue_continues_after_broken_file(db, settings, wav_factory, tmp_path):
    good1 = add(db, wav_factory("a.wav", 1.0))
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"this is not audio" * 100)
    bad = add(db, broken)
    silent = add(db, wav_factory("silent.wav", 1.2, amp=0.0))
    good2 = add(db, wav_factory("b.wav", 1.5, amp=0.25))
    w = Worker(db, FakeTranscriber())
    w.start()
    w.join(60)
    rows = {r["id"]: r for r in db.q("SELECT * FROM audio_files")}
    assert rows[good1]["status"] == "done"
    assert rows[good2]["status"] == "done"
    assert rows[bad]["status"] == "failed" and "خراب" in rows[bad]["error"]
    assert rows[silent]["status"] == "failed" and "بی‌صدا" in rows[silent]["error"]
    recs = db.list_records()
    assert {r["values"]["engineer_name"] for r in recs} == {"مهندس رجبی", "مهندس نصیری"}


def test_full_transcript_saved(db, settings, wav_factory):
    aid = add(db, wav_factory("a.wav", 1.0))
    w = Worker(db, FakeTranscriber())
    w.start(); w.join(30)
    t = db.transcript(aid)
    assert t["raw_text"] == TEXTS[1.0]
    assert t["normalized_text"] and t["processed_text"]


def test_recovery_after_crash(db, settings, wav_factory):
    aid = add(db, wav_factory("a.wav", 1.0))
    db.claim(aid)  # شبیه‌سازی بسته‌شدن برنامه در میانه پردازش
    assert db.one("SELECT status FROM audio_files WHERE id=?", (aid,))["status"] == "processing"
    assert db.recover_interrupted() == 1
    w = Worker(db, FakeTranscriber())
    w.start(); w.join(30)
    assert db.one("SELECT status FROM audio_files WHERE id=?", (aid,))["status"] == "done"


def test_no_double_claim(db, wav_factory):
    aid = add(db, wav_factory("a.wav", 1.0))
    assert db.claim(aid) is True
    assert db.claim(aid) is False


def test_cancel_keeps_previous_results(db, settings, wav_factory):
    a = add(db, wav_factory("a.wav", 1.0))
    b = add(db, wav_factory("b.wav", 1.5, amp=0.25))
    w = Worker(db, FakeTranscriber(stop_after=2))
    w.start(); w.join(30)
    st = {r["id"]: r["status"] for r in db.q("SELECT id, status FROM audio_files")}
    assert st[a] == "done"
    assert st[b] == "queued"  # فایل لغوشده به صف برگشت
    assert len(db.list_records()) == 1


def test_reprocess_does_not_overwrite_manual_edits(db, settings, wav_factory):
    aid = add(db, wav_factory("a.wav", 1.0))
    w = Worker(db, FakeTranscriber())
    w.start(); w.join(30)
    rec = db.list_records()[0]
    db.update_record(rec["id"], values_json={**rec["values"], "engineer_name": "مهندس رجبی‌نیا"}, manually_edited=1)
    db.set_audio(aid, status="queued")
    w = Worker(db, FakeTranscriber())
    w.start(); w.join(30)
    recs = db.list_records()
    assert len(recs) == 1 and recs[0]["values"]["engineer_name"] == "مهندس رجبی‌نیا"


def test_missing_model_stops_queue_without_losing_files(db, settings, wav_factory, monkeypatch):
    from voice2excel.transcriber import Transcriber
    aid = add(db, wav_factory("a.wav", 1.0))
    settings.model_name = "large-v3"  # نصب نشده
    monkeypatch.setattr("voice2excel.transcriber.model_available", lambda n: False)
    w = Worker(db, Transcriber(settings))
    w.start(); w.join(30)
    row = db.one("SELECT status, error FROM audio_files WHERE id=?", (aid,))
    assert row["status"] == "queued" and "مدل" in row["error"]
    assert "مدل" in w.last_error


def _encode_mp3(path, seconds=2.0):
    import av
    import numpy as np
    import pytest
    try:
        out = av.open(str(path), "w")
        st = out.add_stream("mp3", rate=16000)
    except Exception:
        pytest.skip("encoder mp3 در دسترس نیست")
    st.layout = "mono"
    t = np.arange(int(16000 * seconds)) / 16000
    samples = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
    frame.sample_rate = 16000
    for p in st.encode(frame):
        out.mux(p)
    for p in st.encode(None):
        out.mux(p)
    out.close()
    return path


def test_truncated_tail_keeps_healthy_part(tmp_path, settings):
    from voice2excel.audio_processor import load_audio
    p = _encode_mp3(tmp_path / "t.mp3")
    with open(p, "ab") as f:
        f.write(b"\x00" * 7 + b"\xff\xfb\x90\x00" + b"garbage" * 50)
    warnings = []
    audio = load_audio(p, warnings)
    assert len(audio) / 16000 > 1.0


def test_reextract_keeps_manual_edits_and_updates_others(db, settings, wav_factory):
    from voice2excel.pipeline import reextract_all
    a = add(db, wav_factory("a.wav", 1.0))
    b = add(db, wav_factory("b.wav", 1.5, amp=0.25))
    w = Worker(db, FakeTranscriber())
    w.start(); w.join(30)
    recs = {r["audio_id"]: r for r in db.list_records()}
    db.update_record(recs[a]["id"], values_json={**recs[a]["values"], "engineer_name": "مهندس اصلاح‌شده"}, manually_edited=1)
    db.update_record(recs[b]["id"], values_json={"engineer_name": "قدیمی"})  # شبیه نتیجه قواعد قدیمی
    res = reextract_all(db, settings)
    assert res == {"reextracted": 1, "protected": 1}
    after = {r["audio_id"]: r for r in db.list_records()}
    assert after[a]["values"]["engineer_name"] == "مهندس اصلاح‌شده"
    assert after[b]["values"]["engineer_name"] == "مهندس نصیری"


class LoadableFake(FakeTranscriber):
    """جایگزین مدل با وضعیت بارگذاری، برای آزمون آماده نگه داشتن مدل."""

    def __init__(self):
        super().__init__()
        self.loaded = False
        self.loads = 0

    @property
    def state(self):
        return "ready" if self.loaded else "unloaded"

    def load(self):
        self.loads += 1
        self.loaded = True

    def unload(self):
        self.loaded = False


def test_warmup_loads_once_and_idle_unloads(db, settings, wav_factory):
    import time
    settings.model_idle_minutes = 0.002  # حدود ۰٫۱ ثانیه برای آزمون
    fake = LoadableFake()
    w = Worker(db, fake)
    assert w.warmup() is True
    w._warm_thread.join(5)
    assert fake.loaded and fake.loads == 1
    assert w.warmup() is False  # مدل آماده است؛ دوباره بارگذاری نمی‌شود
    time.sleep(0.6)
    assert not fake.loaded  # پس از بی‌کاری آزاد شد


def test_model_stays_loaded_between_batches(db, settings, wav_factory):
    settings.model_idle_minutes = 10
    fake = LoadableFake()
    fake.load()
    add(db, wav_factory("a.wav", 1.0))
    w = Worker(db, fake)
    w.start(); w.join(30)
    assert fake.loaded  # بلافاصله پس از صف آزاد نمی‌شود
    w._cancel_idle_unload()
