"""ساخت بسته به‌روزرسانی سبک (فقط کد برنامه) برای نسخه قابل‌حمل.

استفاده:
    .venv\\Scripts\\python.exe scripts\\build_update.py [--notes "تغییرات این نسخه"]

خروجی: dist/Voice2Excel-update-<نسخه>.zip
شرط: کتابخانه‌ها (requirements.txt) و نسخه Python با بسته کاملِ نصب‌شده یکی باشد؛ وگرنه برنامه
بسته را رد می‌کند و باید بسته کامل (build_portable.py) ساخته شود.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_portable import PY_VERSION, runtime_requirements  # noqa: E402

from voice2excel import __version__  # noqa: E402
from voice2excel.updater import build_update_zip, compute_runtime_id  # noqa: E402


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
    extras = [ROOT / "packaging" / "Guide.html"]
    guide = ROOT / "voice2excel" / "web" / "recording-guide.html"
    # راهنمای ضبط کنار exe با نام Recording-Guide.html قرار دارد
    tmp_guide = ROOT / "dist" / "Recording-Guide.html"
    tmp_guide.parent.mkdir(parents=True, exist_ok=True)
    tmp_guide.write_bytes(guide.read_bytes())
    extras.append(tmp_guide)
    m = build_update_zip(Path(a.src), out, compute_runtime_id(PY_VERSION, runtime_requirements()), a.version,
                         extras, a.notes)
    tmp_guide.unlink(missing_ok=True)
    print(f"بسته به‌روزرسانی ساخته شد: {out} ({out.stat().st_size / 1e6:.1f} مگابایت، {len(m['files'])} فایل)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
