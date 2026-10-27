

def test_quality_tips_only_for_really_bad_audio():
    """راهنمای ضبط فقط وقتی که در آزمون با نویز افزوده، استخراج واقعاً خراب شد؛ ویس معمولی هیچ هشداری نمی‌گیرد."""
    import numpy as np

    from voice2excel.audio_processor import quality_tips
    rng = np.random.default_rng(0)
    t = np.arange(16000 * 8) / 16000
    room = rng.standard_normal(len(t)) * 0.002  # صدای زمینه اتاق آرام (مثل ضبط واقعی، نه سکوت مطلق)
    speech = (0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 1.5 * t) > 0) + room).astype(np.float32)  # گفتار با مکث

    def noisy(snr_db):
        return np.clip(speech + rng.standard_normal(len(speech)).astype(np.float32) * 0.3 / 10 ** (snr_db / 20), -1, 1)
    assert quality_tips(speech) == [] and quality_tips(noisy(25)) == []
    assert "نویز" in quality_tips(noisy(3))[0]
    assert "ضعیف" in quality_tips(speech * 0.003)[0]
    assert "بلند" in quality_tips(np.clip(speech * 30, -1, 1))[0]
    assert quality_tips(np.zeros(100, dtype=np.float32)) == []
