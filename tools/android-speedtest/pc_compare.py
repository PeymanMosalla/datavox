"""مقایسه دقت موتور گوشی (whisper.cpp، مدل‌های ggml) با موتور فعلی برنامه (faster-whisper) روی ۶ ویس نمونه.

    مرحله ۱ (با .venv برنامه):   python pc_compare.py ref
    مرحله ۲ (با pcenv):          python pc_compare.py ggml cache/ggml-large-v3-turbo-q5_0.bin ...
"""
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SAMPLES = sorted((ROOT / "app/assets/samples").glob("*.wav"))
OUT = ROOT / "build" / "compare.json"
PROMPT = ("سلام، مهندس، شماره تماس، آدرس خیابان، کوچه، پلاک، قطعه دوم، نبش، سازه فلز، سازه بتن، "
          "تعداد سقف، سقف‌ها اجرا شده، تازه استارت خورده، دیوارچینی، زنگ بزنین.")


def read(p):
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768


def load():
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def save(d):
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def ref():
    sys.path.insert(0, str(ROOT.parent / "voice2excel"))
    from voice2excel.config import load_settings
    from voice2excel.transcriber import Transcriber
    s = load_settings()
    s.model_name = "large-v3-turbo"
    t = Transcriber(s)
    d = load()
    d["ct2-turbo"] = {}
    for f in SAMPLES:
        t0 = time.time()
        d["ct2-turbo"][f.stem] = t.transcribe(read(f)).text
        print(f.stem, round(time.time() - t0, 1), d["ct2-turbo"][f.stem], flush=True)
    save(d)


def ggml(models):
    from pywhispercpp.model import Model
    d = load()
    for m in models:
        name = Path(m).stem
        model = Model(str(m), n_threads=8, language="fa", initial_prompt=PROMPT, no_context=True,
                      print_progress=False, print_realtime=False,
                      params_sampling_strategy=1, beam_search={"beam_size": 2, "patience": -1.0})
        d[name] = {}
        for f in SAMPLES:
            t0 = time.time()
            segs = model.transcribe(read(f))
            d[name][f.stem] = " ".join(s.text.strip() for s in segs)
            print(name, f.stem, round(time.time() - t0, 1), d[name][f.stem], flush=True)
        save(d)


if __name__ == "__main__":
    if sys.argv[1] == "ref":
        ref()
    else:
        ggml(sys.argv[2:])
