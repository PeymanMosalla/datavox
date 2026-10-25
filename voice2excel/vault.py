"""رمزگذاری فایل با گذرواژه (برای پشتیبانی که از برنامه بیرون برده می‌شود)، فقط با کتابخانه استاندارد.

کلید از گذرواژه با PBKDF2-SHA256 ساخته می‌شود؛ رمز جریانی SHAKE-256 (کلید + نانس + شماره تکه) و
درستی فایل با HMAC-SHA256 روی کل فایل رمزشده (رمز سپس امضا). گذرواژه نادرست یا هر تغییری در فایل،
پیش از رمزگشایی شناخته می‌شود.

قالب: MAGIC | salt(16) | nonce(16) | iterations(4) | داده رمزشده | tag(32)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import struct

MAGIC = b"V2XB1"
ITERATIONS = 600_000
CHUNK = 1 << 20
MIN_PASSWORD = 8
_HEAD = len(MAGIC) + 16 + 16 + 4


class VaultError(Exception):
    """پیام قابل فهم برای کاربر."""


def _keys(password: str, salt: bytes, iterations: int) -> tuple[bytes, bytes]:
    k = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=64)
    return k[:32], k[32:]


def _xor_stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), CHUNK):
        part = data[i:i + CHUNK]
        ks = hashlib.shake_256(key + nonce + struct.pack(">Q", i // CHUNK)).digest(len(part))
        out += (int.from_bytes(part, "little") ^ int.from_bytes(ks, "little")).to_bytes(len(part), "little")
    return bytes(out)


def encrypt(data: bytes, password: str) -> bytes:
    if len(password) < MIN_PASSWORD:
        raise VaultError(f"گذرواژه باید دست‌کم {MIN_PASSWORD} نویسه باشد.")
    salt, nonce = os.urandom(16), os.urandom(16)
    enc_key, mac_key = _keys(password, salt, ITERATIONS)
    body = MAGIC + salt + nonce + struct.pack(">I", ITERATIONS) + _xor_stream(enc_key, nonce, data)
    return body + hmac.new(mac_key, body, hashlib.sha256).digest()


def is_encrypted(head: bytes) -> bool:
    return head.startswith(MAGIC)


def decrypt(blob: bytes, password: str) -> bytes:
    if not is_encrypted(blob) or len(blob) < _HEAD + 32:
        raise VaultError("این فایل، پشتیبان رمزدار «ثبت ویس» نیست.")
    salt, nonce = blob[5:21], blob[21:37]
    (iterations,) = struct.unpack(">I", blob[37:41])
    if not 100_000 <= iterations <= 10_000_000:  # فایل دست‌کاری‌شده برنامه را با شمارش بی‌پایان معطل نکند
        raise VaultError("این فایل خراب است.")
    enc_key, mac_key = _keys(password, salt, iterations)
    body, tag = blob[:-32], blob[-32:]
    if not hmac.compare_digest(hmac.new(mac_key, body, hashlib.sha256).digest(), tag):
        raise VaultError("گذرواژه نادرست است یا فایل تغییر کرده است.")
    return _xor_stream(enc_key, nonce, body[_HEAD:])
