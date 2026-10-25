"""ساخت بسته به‌روزرسانی سبک (فقط کد برنامه) برای نسخه قابل‌حمل.

استفاده:
    .venv\\Scripts\\python.exe scripts\\build_update.py [--notes "تغییرات این نسخه"]

خروجی: dist/Voice2Excel-update-<نسخه>.zip
شرط: کتابخانه‌ها (requirements.txt) و نسخه Python با بسته کاملِ نصب‌شده یکی باشد؛ وگرنه برنامه
بسته را رد می‌کند و باید بسته کامل (build_portable.py) ساخته شود.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_portable import PY_VERSION, runtime_requirements  # noqa: E402

from voice2excel import __version__  # noqa: E402
from voice2excel.updater import build_update_zip, compute_runtime_id  # noqa: E402


def load_signing_key() -> bytes:
    """کلید خصوصی امضای به‌روزرسانی؛ فقط روی رایانه سازنده و خارج از مخزن (هرگز در گیت یا بسته برنامه)."""
    p = Path(os.environ.get("V2X_UPDATE_KEY") or Path.home() / ".voice2excel-keys" / "update-signing.key")
    if not p.exists():
        raise SystemExit(f"کلید امضای به‌روزرسانی پیدا نشد: {p} — بدون آن بسته‌ای ساخته نمی‌شود که برنامه بپذیرد.")
    key = bytes.fromhex(p.read_text().strip())
    from voice2excel import ed25519
    from voice2excel.updater import UPDATE_PUBLIC_KEY
    if ed25519.public_key(key) != UPDATE_PUBLIC_KEY:
        raise SystemExit("این کلید با کلید عمومی داخل برنامه نمی‌خواند.")
    return key


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes", default="")
    ap.add_argument("--src", default=str(ROOT / "voice2excel"), help="پوشه کد (برای آزمون)")
    ap.add_argument("--version", default=__version__, help="نسخه (برای آزمون)")
    a = ap.parse_args()
    out = ROOT / "dist" / f"Voice2Excel-update-{a.version}.zip"
    # راهنماها کنار exe با نام‌های Guide.html و Recording-Guide.html قرار دارند (منبع: صفحه‌های داخل برنامه)
    web = ROOT / "voice2excel" / "web"
    extras = []
    for src, name in ((web / "guide.html", "Guide.html"), (web / "recording-guide.html", "Recording-Guide.html")):
        tmp = ROOT / "dist" / name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(src.read_bytes())
        extras.append(tmp)
    m = build_update_zip(Path(a.src), out, compute_runtime_id(PY_VERSION, runtime_requirements()), a.version,
                         extras, a.notes, signing_key=load_signing_key())
    for tmp in extras:
        tmp.unlink(missing_ok=True)
    print(f"بسته به‌روزرسانی ساخته شد: {out} ({out.stat().st_size / 1e6:.1f} مگابایت، {len(m['files'])} فایل)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
