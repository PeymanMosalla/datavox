"""اجرای پنل فروشنده: .venv\\Scripts\\python.exe -m seller (یا «پنل فروشنده.bat»)."""
import sys
import threading
import webbrowser

import uvicorn

PORT = 8790


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    url = f"http://127.0.0.1:{PORT}/"
    print(f"پنل فروشنده: {url}  (برای بستن، این پنجره را ببندید)")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("seller.app:app", host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
