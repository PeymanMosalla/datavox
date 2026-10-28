"""صدور مجوز «DataVox» برای یک رایانه (فقط روی رایانه فروشنده که کلید خصوصی را دارد).

استفاده:
    .venv\\Scripts\\python.exe scripts\\issue_license.py --machine ABCD-EFGH-IJKL-MNOP --customer "شرکت نمونه"
    ... --days 365            مهلت‌دار (بدون آن: دائمی)
    ... --this-machine        برای همین رایانه
خروجی: licenses/<مشتری>-<کد>.v2x (کنار مخزن، در گیت ثبت نمی‌شود). فایل یا متنش را برای مشتری بفرستید.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voice2excel import ed25519, licensing  # noqa: E402

_CODE = re.compile(r"^[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$")


def load_key() -> bytes:
    p = Path(os.environ.get("V2X_LICENSE_KEY") or Path.home() / ".voice2excel-keys" / "license-signing.key")
    if not p.exists():
        raise SystemExit(f"کلید امضای مجوز پیدا نشد: {p}")
    key = bytes.fromhex(p.read_text().strip())
    if ed25519.public_key(key) != licensing.LICENSE_PUBLIC_KEY:
        raise SystemExit("این کلید با کلید عمومی داخل برنامه نمی‌خواند.")
    return key


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", default="")
    ap.add_argument("--this-machine", action="store_true")
    ap.add_argument("--customer", required=True)
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    code = licensing.machine_code() if a.this_machine else a.machine.strip().upper()
    if not _CODE.match(code):
        raise SystemExit("کد رایانه باید مانند ABCD-EFGH-IJKL-MNOP باشد.")
    data = {"customer": a.customer.strip(), "machine": code, "issued": date.today().isoformat()}
    if a.days > 0:
        data["expires"] = (date.today() + timedelta(days=a.days)).isoformat()
    text = licensing.encode(data, load_key())
    assert licensing.decode(text) == data
    safe = re.sub(r"[^\w\-]+", "_", data["customer"]).strip("_") or "customer"
    out = Path(a.out) if a.out else ROOT / "licenses" / f"{safe}-{code[:4]}.v2x"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False))
    print(f"مجوز ساخته شد: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
