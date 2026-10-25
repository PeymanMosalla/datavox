"""تبدیل کد برنامه به ماژول‌های کامپایل‌شده (.pyd) تا کد خوانا همراه بسته نرود.

هر فایل جداگانه با Nuitka کامپایل و کنار بقیه در همان پوشه گذاشته می‌شود؛ ساختار پوشه برنامه، مسیر web و
assets، به‌روزرسانی سبک و اجرای «python -m voice2excel» دست نمی‌خورند. فقط __init__ (شماره نسخه) و
__main__ (اجرا با -m) متن می‌مانند. توضیحات درون کد (docstring) هم در خروجی نیست.

استفاده (در build_portable و build_update خودکار صدا زده می‌شود):
    .venv\\Scripts\\python.exe scripts\\compile_app.py <پوشه خروجی>
بار اول کامپایلر MinGW (حدود ۱۰۰ مگابایت) را Nuitka خودش دریافت می‌کند.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_SOURCE = {"__init__.py", "__main__.py"}


def _compile_one(py: Path, jobs: int) -> Path:
    with tempfile.TemporaryDirectory(prefix="v2x-nk-") as tmp:
        cmd = [sys.executable, "-m", "nuitka", "--mode=module", str(py), f"--output-dir={tmp}", "--mingw64",
               "--assume-yes-for-downloads", "--remove-output", "--no-pyi-file", "--quiet", f"--jobs={jobs}",
               "--python-flag=no_docstrings"]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        built = list(Path(tmp).glob(f"{py.stem}.*.pyd"))
        if res.returncode or len(built) != 1:
            raise RuntimeError(f"کامپایل {py.name} ناموفق بود:\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")
        dst = py.with_name(built[0].name)
        shutil.move(str(built[0]), dst)
        return dst


def compile_package(src: Path, dest: Path) -> list[Path]:
    """کپی بسته src در dest و جایگزینی هر .py (جز KEEP_SOURCE) با .pyd همان ماژول."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyd"))
    sources = sorted((p for p in dest.glob("*.py") if p.name not in KEEP_SOURCE), key=lambda p: -p.stat().st_size)
    workers = max(1, min(len(sources), (os.cpu_count() or 4) // 2))
    with ThreadPoolExecutor(workers) as pool:  # بزرگ‌ترها اول، تا آخر کار منتظر یک فایل بزرگ نمانیم
        built = list(pool.map(lambda p: _compile_one(p, 2), sources))
    for p in sources:
        p.unlink()
    left = sorted(str(p.relative_to(dest)) for p in dest.rglob("*.py"))
    if left != sorted(KEEP_SOURCE):
        raise RuntimeError(f"فایل متنی کد در بسته مانده است: {left}")
    return built


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    dest = Path(sys.argv[1]).resolve() / "voice2excel"
    built = compile_package(ROOT / "voice2excel", dest)
    size = sum(p.stat().st_size for p in built) / 1e6
    print(f"{len(built)} ماژول کامپایل شد ({size:.1f} مگابایت): {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
