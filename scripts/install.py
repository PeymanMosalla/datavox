"""نصب یک‌باره برنامه: محیط مجازی، کتابخانه‌ها، مدل گفتار و بررسی سلامت.

فقط از کتابخانه استاندارد Python استفاده می‌کند تا پیش از نصب وابستگی‌ها قابل اجرا باشد.
استفاده: install.bat  (یا: python scripts/install.py [--model small])
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe" if os.name == "nt" else ROOT / ".venv" / "bin" / "python"


def say(msg: str) -> None:
    print(msg, flush=True)


def run(args: list[str]) -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.call(args, cwd=ROOT, env=env)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    model = "large-v3-turbo"
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]
    say("============================================")
    say("  نصب برنامه DataVox (فقط یک بار، با اینترنت)")
    say("============================================")
    say(f"[1/4] Python {sys.version.split()[0]}")
    if sys.version_info[:2] not in ((3, 11), (3, 12), (3, 13)):
        say("[خطا] نسخه Python باید 3.11 تا 3.13 باشد (پیشنهاد: 3.12).")
        return 1

    if not VENV_PY.exists():
        say("[2/4] ساخت محیط مجازی...")
        venv.create(ROOT / ".venv", with_pip=True)
    else:
        say("[2/4] محیط مجازی از قبل وجود دارد.")

    say("[3/4] نصب کتابخانه‌ها (چند دقیقه طول می‌کشد)...")
    run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "-q"])
    if run([str(VENV_PY), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]) != 0:
        say("[خطا] نصب کتابخانه‌ها کامل نشد. اتصال اینترنت را بررسی کنید و install.bat را دوباره اجرا کنید.")
        return 1

    say(f"[4/4] دریافت مدل تبدیل گفتار «{model}»...")
    if (ROOT / "models" / model / "model.bin").exists():
        say("مدل از قبل دریافت شده است.")
    elif run([str(VENV_PY), "-m", "voice2excel.model_download", model]) != 0:
        say("[خطا] دریافت مدل ناموفق بود. download_model.bat را دوباره اجرا کنید، یا پوشه "
            f"models\\{model} را از رایانه‌ای که برنامه روی آن نصب است کپی کنید.")
        return 1

    if model != "large-v3-turbo":
        run([str(VENV_PY), "-c", f"from voice2excel.config import save_settings; save_settings({{'model_name': '{model}'}})"])
    say("")
    say("بررسی سلامت نصب...")
    rc = run([str(VENV_PY), "-m", "voice2excel.healthcheck"])
    say("")
    if rc == 0:
        say("نصب کامل شد. از این به بعد برنامه را با run.bat اجرا کنید (بدون نیاز به اینترنت).")
    else:
        say("نصب انجام شد ولی بررسی سلامت مشکلی گزارش کرد؛ پیام‌های بالا را ببینید.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
