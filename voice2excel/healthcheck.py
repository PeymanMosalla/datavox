"""بررسی سلامت نصب: کتابخانه‌ها، مدل گفتار، پوشه‌ها و اجرای آفلاین مدل روی یک صدای آزمایشی."""
from __future__ import annotations

import os
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ok = True

    def line(good: bool, msg: str):
        nonlocal ok
        ok &= good
        print(("[درست] " if good else "[مشکل] ") + msg)

    line(sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)), f"نسخه Python: {sys.version.split()[0]}")
    for mod in ("faster_whisper", "ctranslate2", "av", "fastapi", "uvicorn", "openpyxl", "jdatetime", "numpy"):
        try:
            __import__(mod)
            line(True, f"کتابخانه {mod}")
        except Exception as e:
            line(False, f"کتابخانه {mod} بارگذاری نشد: {e}")
    from .config import DATA_DIR, MODELS_DIR, ensure_dirs, load_settings
    from .transcriber import Transcriber, installed_models, model_available

    ensure_dirs()
    line(True, f"پوشه داده: {DATA_DIR}")
    s = load_settings()
    line(model_available(s.model_name), f"مدل فعال «{s.model_name}» در {MODELS_DIR}")
    print("مدل‌های نصب‌شده:", ", ".join(installed_models()) or "هیچ")
    if model_available(s.model_name):
        import numpy as np

        try:
            t0 = time.time()
            tr = Transcriber(s)
            tr.load()
            audio = (0.1 * np.sin(2 * np.pi * 220 * np.arange(16000) / 16000)).astype(np.float32)
            tr.transcribe(audio)
            line(True, f"اجرای آفلاین مدل ({time.time() - t0:.1f} ثانیه)")
        except Exception as e:
            line(False, f"اجرای مدل ناموفق: {type(e).__name__}: {e}")
    try:
        import psutil

        ram = psutil.virtual_memory().total / 1e9
        line(ram >= 3.5, f"RAM رایانه: {ram:.1f} گیگابایت")
    except Exception:
        pass
    print("نتیجه:", "سالم" if ok else "مشکل دارد؛ موارد بالا را بررسی کنید.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
