"""VAD با numpy (برای ویندوز ۷) باید همان خروجی onnxruntime را بدهد."""
import os
from pathlib import Path

import numpy as np
import pytest

from voice2excel.vad_numpy import NumpySileroVAD, install_fallback, onnx_initializers

vad = pytest.importorskip("faster_whisper.vad")
MODEL = os.path.join(vad.get_assets_path(), "silero_vad_v6.onnx")
SAMPLES = sorted((Path(__file__).resolve().parent.parent / "packaging" / "samples").glob("*.mp3"))


def _audio():
    from voice2excel.audio_processor import load_audio

    rng = np.random.default_rng(0)
    yield "noise", rng.standard_normal(16000 * 5).astype(np.float32) * 0.05
    yield "silence", np.zeros(16000 * 2, dtype=np.float32)
    for p in SAMPLES[:3]:
        yield p.name, load_audio(p)


def test_reads_onnx_weights():
    w = onnx_initializers(MODEL)
    assert w["encoder.feature_extractor.forward_basis_buffer"].shape == (258, 1, 256)
    assert w["onnx::LSTM_209"].shape == (1, 512, 128)
    assert w["encoder.conv_layers.0.weight"].dtype == np.float32


def test_matches_onnxruntime():
    pytest.importorskip("onnxruntime")
    ort, npv = vad.SileroVADModel(MODEL), NumpySileroVAD(MODEL)
    for name, a in _audio():
        a = np.pad(a, (0, 512 - a.shape[0] % 512))
        p1, p2 = ort(a), npv(a)
        assert p1.shape == p2.shape and p2.dtype == np.float32, name
        assert np.abs(p1 - p2).max() < 1e-4, name


def test_same_speech_segments(monkeypatch):
    pytest.importorskip("onnxruntime")
    original = vad.SileroVADModel
    for name, a in _audio():
        vad.get_vad_model.cache_clear()
        expected = vad.get_speech_timestamps(a, vad.VadOptions())
        monkeypatch.setattr(vad, "SileroVADModel", NumpySileroVAD)
        vad.get_vad_model.cache_clear()
        assert vad.get_speech_timestamps(a, vad.VadOptions()) == expected, name
        monkeypatch.setattr(vad, "SileroVADModel", original)
    vad.get_vad_model.cache_clear()


def test_fallback_when_onnxruntime_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "onnxruntime":
            raise ImportError("DLL load failed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(vad, "SileroVADModel", vad.SileroVADModel)  # پس از آزمون برگردانده می‌شود
    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert install_fallback() is True
    assert vad.SileroVADModel is NumpySileroVAD
    vad.get_vad_model.cache_clear()
    assert isinstance(vad.get_vad_model(), NumpySileroVAD)
    vad.get_vad_model.cache_clear()
