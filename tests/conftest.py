import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

import pytest

# پوشه داده جداگانه برای آزمون‌ها؛ پیش از import بسته تنظیم می‌شود
_TMP = Path(tempfile.mkdtemp(prefix="v2x-test-"))
os.environ["V2X_DATA_DIR"] = str(_TMP / "data")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice2excel import config  # noqa: E402
from voice2excel.database import Database, set_db  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_trial(tmp_path, monkeypatch):
    """آزمون‌ها هرگز وضعیت دوره آزمایشی این رایانه (AppData، ProgramData، رجیستری) را لمس نکنند."""
    from voice2excel import trial
    reg: dict = {}
    stores = [tmp_path / "trial" / n for n in ("data", "appdata", "local", "programdata")]
    monkeypatch.setattr(trial, "_store_paths", lambda: stores)
    monkeypatch.setattr(trial, "_read_registry", lambda: trial._decode(reg["s"]) if "s" in reg else None)
    monkeypatch.setattr(trial, "_write_registry", lambda text: reg.__setitem__("s", text))
    return stores, reg


@pytest.fixture()
def db(tmp_path):
    from voice2excel import pipeline

    d = Database(tmp_path / "test.db")
    set_db(d)
    pipeline.set_excel_candidates_provider(None)
    yield d
    set_db(None)
    pipeline.set_excel_candidates_provider(None)
    d.close()


@pytest.fixture()
def settings():
    config.reset_settings_cache()
    s = config.load_settings()
    s.required_fields = ["engineer_name", "phone", "address"]
    s.default_area_code = ""
    return s


def make_wav(path: Path, seconds: float, freq: float = 440.0, amp: float = 0.3, rate: int = 16000) -> Path:
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
        w.writeframes(frames)
    return path


@pytest.fixture()
def wav_factory(tmp_path):
    def make(name: str, seconds: float, amp: float = 0.3) -> Path:
        return make_wav(tmp_path / name, seconds, amp=amp)
    return make
