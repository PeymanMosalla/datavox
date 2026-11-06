"""موتورهای نسخه oldcpu: ساخت کلمه از نشانه‌ها، تکه‌کردن ویس بلند، خطاهای موتور آنلاین و برگشت به موتور محلی."""
import io
import json
import urllib.error

import numpy as np
import pytest

from voice2excel import engines_oldcpu as E
from voice2excel.config import Settings


def hx(s: str) -> str:
    return s.encode("utf-8").hex()


def test_words_from_tokens_joins_subwords_and_partial_utf8():
    raw = "مهندس".encode()
    tokens = [
        {"t0": 0, "t1": 40, "p": 0.9, "plog": -0.1, "h": (b" " + raw[:3]).hex()},  # بایت ناقص UTF-8
        {"t0": 40, "t1": 80, "p": 0.7, "plog": -0.3, "h": raw[3:].hex()},
        {"t0": 90, "t1": 150, "p": 1.0, "plog": 0.0, "h": hx(" رجبی")},
    ]
    w = E._words_from_tokens(tokens)
    assert [x["word"] for x in w] == ["مهندس", "رجبی"]
    assert w[0]["start"] == 0.0 and w[0]["end"] == 0.8 and w[0]["prob"] == 0.8
    assert w[1]["start"] == 0.9 and w[1]["end"] == 1.5


def test_parse_local_result():
    raw = json.dumps({"segments": [{"t0": 0, "t1": 300, "nsp": 0.01, "text": hx(" سلام مهندس"),
                                    "tokens": [{"t0": 0, "t1": 100, "p": 1, "plog": -0.2, "h": hx(" سلام")},
                                               {"t0": 100, "t1": 300, "p": 1, "plog": -0.4, "h": hx(" مهندس")}]}]})
    d = E.parse_local_result(raw)
    assert d["text"] == "سلام مهندس"
    assert d["segments"][0]["end"] == 3.0 and d["avg_logprob"] == pytest.approx(-0.3)
    assert [w["word"] for w in d["words"]] == ["سلام", "مهندس"]


def test_split_points_short_and_long():
    sr = E.SR
    assert E._split_points(np.zeros(sr * 30, np.float32)) == [0, sr * 30]
    audio = np.random.default_rng(0).normal(0, 0.1, sr * 600).astype(np.float32)
    quiet = sr * 242
    audio[quiet:quiet + sr // 2] = 0  # لحظه بی‌صدا نزدیک مرز ۲۴۰ ثانیه
    pts = E._split_points(audio)
    assert pts[0] == 0 and pts[-1] == len(audio) and len(pts) == 4
    assert quiet <= pts[1] <= quiet + sr // 2
    assert all(b - a <= (E.CLOUD_CHUNK_SEC + 5) * sr for a, b in zip(pts, pts[1:]))


def _cloud(monkeypatch, response=None, error=None):
    eng = E.CloudEngine.__new__(E.CloudEngine)
    eng.cred = ("a" * 32, "tok")
    calls = []

    def fake_urlopen(req, timeout=None, context=None):
        calls.append(json.loads(req.data))
        if error:
            raise error
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(E.urllib.request, "urlopen", fake_urlopen)
    return eng, calls


def test_cloud_success_offsets_and_prompt(monkeypatch):
    resp = {"success": True, "result": {"transcription_info": {"language_probability": 0.98}, "segments": [
        {"start": 0, "end": 2.0, "text": " سلام", "avg_logprob": -0.2, "no_speech_prob": 0,
         "words": [{"word": " سلام", "start": 0.1, "end": 0.6}]}]}}
    eng, calls = _cloud(monkeypatch, resp)
    d = eng.transcribe(np.zeros(E.SR * 3, np.float32), "fa", "راهنما", True)
    assert d["text"] == "سلام" and d["words"][0]["word"] == "سلام" and d["language_prob"] == 0.98
    assert calls[0]["initial_prompt"] == "راهنما" and calls[0]["language"] == "fa" and calls[0]["vad_filter"] is True


@pytest.mark.parametrize("code,reason", [(429, "quota"), (401, "auth"), (403, "auth"), (500, "server")])
def test_cloud_http_errors(monkeypatch, code, reason):
    err = urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))
    eng, _ = _cloud(monkeypatch, error=err)
    with pytest.raises(E.CloudUnavailable) as ei:
        eng.transcribe(np.zeros(E.SR, np.float32), "fa", None, True)
    assert ei.value.reason == reason and ei.value.retry_after > 0


def test_cloud_network_error(monkeypatch):
    eng, _ = _cloud(monkeypatch, error=urllib.error.URLError("down"))
    with pytest.raises(E.CloudUnavailable) as ei:
        eng.transcribe(np.zeros(E.SR, np.float32), "fa", None, True)
    assert ei.value.reason == "network"


def test_cred_roundtrip(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from make_cloud_cred import write_cloud_json

    src = tmp_path / "cf.txt"
    src.write_text('account=' + "ab" * 16 + '\ntoken=curl "x" \\\n  -H "Authorization: Bearer cfut_SeCrEt-123"\n',
                   encoding="utf-8")
    dst = tmp_path / "cloud.json"
    write_cloud_json(src, dst)
    assert "SeCrEt" not in dst.read_text(encoding="utf-8")
    monkeypatch.setattr(E, "CLOUD_CRED", dst)
    assert E._load_cred() == ("ab" * 16, "cfut_SeCrEt-123")


class FakeLocal:
    loaded = False

    def __init__(self):
        self.calls = 0

    @staticmethod
    def available():
        return True

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False

    def transcribe(self, audio, threads, beam, language, prompt, should_stop=None):
        self.calls += 1
        return {"text": "محلی", "segments": [], "words": [], "language": "fa", "language_prob": 1.0, "avg_logprob": None}


class FakeCloud:
    configured = True

    def __init__(self, fail=None):
        self.fail = fail
        self.calls = 0

    def transcribe(self, audio, language, prompt, vad, should_stop=None):
        self.calls += 1
        if self.fail:
            raise self.fail
        return {"text": "آنلاین", "segments": [], "words": [], "language": "fa", "language_prob": 1.0,
                "avg_logprob": None}


def _tr(monkeypatch, cloud, mode="online"):
    from voice2excel.transcriber import OldCpuTranscriber

    monkeypatch.setattr(E, "LocalEngine", FakeLocal)
    OldCpuTranscriber.status = E.EngineStatus()
    s = Settings()
    s.speech_engine = mode
    t = OldCpuTranscriber(s)
    t.cloud, t.local = cloud, FakeLocal()
    return t


def test_hybrid_online_first(monkeypatch):
    t = _tr(monkeypatch, FakeCloud())
    r = t.transcribe(np.zeros(16000, np.float32))
    assert r.text == "آنلاین" and r.model.startswith("online") and t.local.calls == 0


def test_hybrid_falls_back_and_pauses_cloud(monkeypatch):
    cloud = FakeCloud(E.CloudUnavailable("quota", "سهمیه تمام شد", 3600))
    t = _tr(monkeypatch, cloud)
    r1 = t.transcribe(np.zeros(16000, np.float32))
    r2 = t.transcribe(np.zeros(16000, np.float32))
    assert r1.text == r2.text == "محلی" and r1.model.startswith("local")
    assert cloud.calls == 1  # پس از خطا تا پایان مهلت دوباره امتحان نمی‌شود
    st = t.status.as_dict("online", cloud, t.local)
    assert st["cloud_reason"] == "quota" and st["cloud_paused_minutes"] >= 59


def test_hybrid_offline_mode_never_calls_cloud(monkeypatch):
    cloud = FakeCloud()
    t = _tr(monkeypatch, cloud, mode="offline")
    assert t.transcribe(np.zeros(16000, np.float32)).text == "محلی" and cloud.calls == 0


def test_hybrid_cancel(monkeypatch):
    from voice2excel.transcriber import TranscriptionCancelled

    t = _tr(monkeypatch, FakeCloud(E.EngineCancelled()))
    with pytest.raises(TranscriptionCancelled):
        t.transcribe(np.zeros(16000, np.float32))
