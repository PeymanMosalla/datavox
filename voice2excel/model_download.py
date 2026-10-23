"""دریافت یک‌باره مدل گفتار در پوشه models.

این تنها بخشی از برنامه است که به اینترنت نیاز دارد و فقط با دستور صریح کاربر
(اجرای download_model.bat یا دکمه دریافت در تنظیمات) اجرا می‌شود.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .config import AVAILABLE_MODELS, MODELS_DIR


def download_model(name: str) -> Path:
    if name not in AVAILABLE_MODELS:
        raise ValueError(f"مدل ناشناخته: {name}")
    os.environ.pop("HF_HUB_OFFLINE", None)
    import huggingface_hub.constants as hc

    hc.HF_HUB_OFFLINE = False
    from faster_whisper.utils import download_model as fw_download

    target = MODELS_DIR / name
    tmp = MODELS_DIR / f".{name}.partial"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fw_download(name, output_dir=str(tmp))
    except Exception as e:
        raise RuntimeError(
            "دریافت مدل ناموفق بود. اتصال اینترنت را بررسی کنید و دوباره تلاش کنید. "
            "اگر اینترنت محدود است، پوشه مدل را از رایانه دیگری در models کپی کنید. "
            f"(جزئیات: {type(e).__name__}: {e})"
        ) from e
    if not (tmp / "model.bin").exists():
        raise RuntimeError("فایل‌های مدل کامل دریافت نشدند؛ دوباره تلاش کنید.")
    if target.exists():
        shutil.rmtree(target)
    os.replace(tmp, target)
    shutil.rmtree(tmp / ".cache", ignore_errors=True)
    shutil.rmtree(target / ".cache", ignore_errors=True)
    return target


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    name = argv[1] if len(argv) > 1 else "large-v3-turbo"
    print(f"دریافت مدل «{name}» در {MODELS_DIR} ...")
    try:
        p = download_model(name)
    except Exception as e:
        print(f"خطا: {e}")
        return 1
    size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6
    print(f"انجام شد: {p} ({size:.0f} مگابایت)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
