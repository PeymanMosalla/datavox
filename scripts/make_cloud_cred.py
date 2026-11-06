"""ساخت cloud.json (حساب موتور آنلاین نسخه oldcpu) از فایل متنی کاربر؛ کلید هرگز در مخزن ثبت یا چاپ نمی‌شود.

    python scripts/make_cloud_cred.py <cloudflare.txt> <cloud.json>

فایل ورودی: خط account=<شناسه ۳۲ نویسه‌ای حساب> و کلید یا در خط token=... یا در دستور نمونه Cloudflare
(بعد از «Bearer»). در cloud.json کلید فقط کمی پوشانده می‌شود (رمزگذاری واقعی نیست)؛ این کلید فقط اجازه Workers AI دارد.
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path


def read_cred(src: Path) -> tuple[str, str]:
    t = src.read_text(encoding="utf-8-sig")
    acc = re.search(r"account\s*=\s*([0-9a-f]{32})", t)
    tok = re.search(r'Bearer\s+([^\s"\\]+)', t) or re.search(r"token\s*=\s*([A-Za-z0-9_\-]{20,})", t)
    if not acc or not tok:
        raise SystemExit(f"شناسه حساب یا کلید در {src} پیدا نشد.")
    return acc.group(1), tok.group(1)


def write_cloud_json(src: Path, dst: Path) -> None:
    acc, token = read_cred(src)
    dst.write_text(json.dumps({"a": acc, "t": base64.b64encode(token[::-1].encode()).decode()}), encoding="utf-8")


if __name__ == "__main__":
    write_cloud_json(Path(sys.argv[1]), Path(sys.argv[2]))
    print("ok")
