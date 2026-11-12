"""ساخت بسته به‌روزرسانی سبک (فقط کد برنامه) برای نسخه قابل‌حمل.

استفاده:
    .venv\\Scripts\\python.exe scripts\\build_update.py [--notes "تغییرات این نسخه"]

خروجی: dist/DataVox-update-<نسخه>.zip  (با --win7: dist/DataVox-update-<نسخه>-win7.zip برای بسته ویندوز ۷)
شرط: کتابخانه‌ها (requirements.txt) و نسخه Python با بسته کاملِ نصب‌شده یکی باشد؛ وگرنه برنامه
بسته را رد می‌کند و باید بسته کامل (build_portable.py) ساخته شود.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
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
    ap.add_argument("--no-compile", action="store_true", help="کد متنی (فقط برای آزمون)")
    ap.add_argument("--win7", action="store_true", help="(در شاخه windows7-only همیشه فعال است)")
    a = ap.parse_args()
    a.win7 = True  # شاخه windows7-only فقط به‌روزرسانی بسته ویندوز ۷ می‌سازد
    out = ROOT / "dist" / f"DataVox-update-{a.version}-oldcpu.zip"  # شاخه oldcpu: فقط به‌روزرسانی بسته oldcpu
    # راهنماها کنار exe با نام‌های Guide.html و Recording-Guide.html قرار دارند (منبع: صفحه‌های داخل برنامه)
    web = ROOT / "voice2excel" / "web"
    extras = []
    for src, name in ((web / "guide.html", "Guide.html"), (web / "recording-guide.html", "Recording-Guide.html")):
        tmp = ROOT / "dist" / name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(src.read_bytes())
        extras.append(tmp)
    key = load_signing_key()  # پیش از کامپایل طولانی، تا نبود کلید زود معلوم شود
    pkg = Path(a.src)
    with tempfile.TemporaryDirectory(prefix="v2x-upd-") as work:
        if not a.no_compile:
            from compile_app import compile_package
            compile_package(pkg, Path(work) / "voice2excel")
            pkg = Path(work) / "voice2excel"
        m = build_update_zip(pkg, out, compute_runtime_id(PY_VERSION, runtime_requirements(a.win7)), a.version,
                             extras, a.notes, signing_key=key)
    for tmp in extras:
        tmp.unlink(missing_ok=True)
    print(f"بسته به‌روزرسانی ساخته شد: {out} ({out.stat().st_size / 1e6:.1f} مگابایت، {len(m['files'])} فایل)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
