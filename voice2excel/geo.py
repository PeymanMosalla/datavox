"""داده پایه نشانی‌های شهر که همراه برنامه ارائه می‌شود.

فایل داده فشرده و رمزشده است تا محتوایش به‌شکل خوانا در بسته برنامه نباشد. در رابط کاربری
فهرست نمی‌شود؛ فقط در کنار واژه‌نامه کاربر به موتور تشخیص نشانی کمک می‌کند و واژه‌نامه کاربر
همیشه بر آن مقدم است. ساخت فایل: scripts/build_geo.py
"""
from __future__ import annotations

import hashlib
import json
import os
import zlib
from functools import lru_cache
from pathlib import Path

ASSET = Path(__file__).resolve().parent / "assets" / "geo.dat"
_MAGIC = b"V2XG1"
_KEY = bytes.fromhex("a2461943cc76ed39b3ab0c30b7cf0c9780785fd1de8176824b7c8748c4f123d3")


def _keystream(nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(_KEY + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:n])


def _xor(data: bytes, nonce: bytes) -> bytes:
    n = len(data)
    return (int.from_bytes(data, "big") ^ int.from_bytes(_keystream(nonce, n), "big")).to_bytes(n, "big")


def encode(obj: dict) -> bytes:
    nonce = os.urandom(16)
    body = zlib.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    tag = hashlib.sha256(_KEY + nonce + body).digest()[:8]
    return _MAGIC + nonce + tag + _xor(body, nonce)


def decode(blob: bytes) -> dict:
    if not blob.startswith(_MAGIC):
        raise ValueError("unknown format")
    nonce, tag, enc = blob[5:21], blob[21:29], blob[29:]
    body = _xor(enc, nonce)
    if hashlib.sha256(_KEY + nonce + body).digest()[:8] != tag:
        raise ValueError("corrupt data")
    return json.loads(zlib.decompress(body).decode("utf-8"))


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return decode(ASSET.read_bytes())
    except (OSError, ValueError, zlib.error):
        return {}  # برنامه بدون داده پایه هم کار می‌کند


def base_streets() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """[(نام استاندارد، شکل‌های دیگر)]."""
    return tuple((s[0], tuple(s[1])) for s in _data().get("s", []))


def base_names() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(نام‌خانوادگی‌های رایج، نام‌های کوچک رایج)."""
    d = _data()
    return tuple(d.get("n", [])), tuple(d.get("f", []))
