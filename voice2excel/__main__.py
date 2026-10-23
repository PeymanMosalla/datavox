"""اجرای برنامه: python -m voice2excel [--no-browser] [--auto-exit]

--auto-exit: اگر مرورگر بسته شود و برنامه مدتی بی‌کار بماند، خودش بسته می‌شود
(برای نسخه قابل‌حمل که بدون پنجره کنسول اجرا می‌شود).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def _ensure_streams(log_dir) -> None:
    """در pythonw (بدون کنسول) stdout و stderr وجود ندارند؛ به فایل گزارش هدایت می‌شوند."""
    if sys.stdout is None or sys.stderr is None:
        log_dir.mkdir(parents=True, exist_ok=True)
        f = open(log_dir / "console.log", "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    from .config import DATA_DIR, ensure_dirs, load_settings

    _ensure_streams(DATA_DIR / "logs")
    import uvicorn

    ensure_dirs()
    s = load_settings()
    url = f"http://{s.host}:{s.port}/"
    # با فعال بودن «آپلود از گوشی»، سرور روی همه رابط‌های شبکه گوش می‌دهد؛ دسترسی دستگاه‌های دیگر
    # در خود برنامه به صفحه آپلود با رمز محدود می‌شود (server.lan_guard)
    bind_host = "0.0.0.0" if s.lan_enabled and s.lan_pin else s.host
    os.environ["V2X_BIND_HOST"] = bind_host
    if not _port_free(s.host, s.port):
        print(f"برنامه از قبل در حال اجراست: {url}")
        if s.open_browser and "--no-browser" not in sys.argv:
            webbrowser.open(url)
        return 0
    if "--auto-exit" in sys.argv:
        os.environ["V2X_AUTO_EXIT"] = "1"
    print(f"برنامه ثبت ویس اجرا شد: {url}")
    print("برای بستن برنامه این پنجره را ببندید یا Ctrl+C بزنید.")
    if s.open_browser and "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("voice2excel.server:app", host=bind_host, port=s.port, log_level="warning", use_colors=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
