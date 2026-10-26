"""دوره آزمایشی آفلاین: تا ۱۰ روز یا ۱۰ ویس (هرکدام زودتر برسد).

وضعیت دوره (تاریخ شروع، بیشترین تاریخ دیده‌شده، شمار ویس‌های پردازش‌شده) در چند جای ویندوز نگه داشته
می‌شود و هر نسخه با یک کد تأیید (HMAC وابسته به همین رایانه) مهر می‌شود تا نه قابل ویرایش دستی باشد و نه
با پاک کردن یک نسخه بازنشانی شود. همیشه بدبینانه‌ترین مقدار ملاک است: قدیمی‌ترین شروع و بیشترین شمار.

هدف، بستن راه‌های ساده بازنشانی (نصب دوباره، تغییر ساعت، کاربر تازه ویندوز) است؛ نه مقابله با نفوذگر حرفه‌ای.
فقط در نسخه قابل‌حمل فعال است (در اجرای توسعه و آزمون‌ها نه)، مانند licensing.REQUIRED.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
from datetime import date
from pathlib import Path

from .config import DATA_DIR
from .licensing import _machine_guid, machine_code

TRIAL_DAYS = 10
TRIAL_VOICES = 10
# فقط برای مهر ضدویرایش وضعیت دوره روی همین رایانه است؛ هیچ داده کاربری با آن رمز نمی‌شود
_SECRET = bytes.fromhex("9d1f7c4a6b2e8d05f3a9c1740e6b82d5c7a04f19e3b628da5c0f71b94e8d23a6")
_lock = threading.Lock()


def _key() -> bytes:
    return hashlib.sha256(_SECRET + b":" + _machine_guid().encode("utf-8", "replace")).digest()


def _store_paths() -> list[Path]:
    """چند مکان مستقل؛ هرچه بیشتر، بازنشانی سخت‌تر. نبود هر کدام (دسترسی/سکو) بی‌اشکال است."""
    paths = [DATA_DIR / ".v2xstate"]
    for env in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        base = os.environ.get(env)
        if base:
            paths.append(Path(base) / "Voice2Excel" / "state.dat")
    return paths


def _encode(rec: dict) -> str:
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return body + "." + hmac.new(_key(), raw, hashlib.sha256).hexdigest()


def _decode(text: str) -> dict | None:
    try:
        body, tag = text.strip().split(".", 1)
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(hmac.new(_key(), raw, hashlib.sha256).hexdigest(), tag):
            return None  # دست‌کاری‌شده یا مال رایانه دیگر
        rec = json.loads(raw)
        return rec if rec.get("m") == machine_code() else None
    except (ValueError, UnicodeDecodeError):
        return None


def _read_all() -> list[dict]:
    out = []
    for p in _store_paths():
        try:
            rec = _decode(p.read_text(encoding="utf-8"))
        except OSError:
            rec = None
        if rec:
            out.append(rec)
    rec = _read_registry()
    if rec:
        out.append(rec)
    return out


def _read_registry() -> dict | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Voice2Excel") as k:
            return _decode(winreg.QueryValueEx(k, "s")[0])
    except (ImportError, OSError, ValueError):
        return None


def _write_registry(text: str) -> None:
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Voice2Excel") as k:
            winreg.SetValueEx(k, "s", 0, winreg.REG_SZ, text)
    except (ImportError, OSError):
        pass


def _write_all(rec: dict) -> None:
    text = _encode(rec)
    for p in _store_paths():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        except OSError:
            pass
    _write_registry(text)


def _merge(recs: list[dict], today: date) -> dict:
    """بدبینانه‌ترین حالت: قدیمی‌ترین شروع، بیشترین تاریخ دیده‌شده (ساعت فقط جلو می‌رود)، بیشترین شمار ویس."""
    started = min((r["s"] for r in recs), default=today.isoformat())
    max_date = max([r.get("d", r["s"]) for r in recs] + [today.isoformat()])
    voices = max((int(r.get("v", 0)) for r in recs), default=0)
    return {"m": machine_code(), "s": started, "d": max_date, "v": voices}


def _state() -> dict:
    recs = _read_all()
    today = date.today()
    rec = _merge(recs, today)
    if len(recs) < len(_store_paths()) + 1 or not recs:  # نسخه تازه یا مکان پاک‌شده: دوباره همه‌جا نوشته شود
        _write_all(rec)
    return rec


def record_voice() -> None:
    """پس از پردازش موفق هر ویس صدا زده می‌شود؛ مستقل از پایگاه داده رکوردها."""
    with _lock:
        rec = _state()
        rec["v"] = int(rec["v"]) + 1
        _write_all(rec)


def info() -> dict:
    """وضعیت دوره آزمایشی برای نمایش و تصمیم‌گیری."""
    with _lock:
        rec = _state()
    today = date.today()
    used_days = (date.fromisoformat(rec["d"]) - date.fromisoformat(rec["s"])).days
    days_left = max(0, TRIAL_DAYS - used_days)
    voices_left = max(0, TRIAL_VOICES - int(rec["v"]))
    clock_back = (date.fromisoformat(rec["d"]) - today).days > 2
    active = days_left > 0 and voices_left > 0
    return {"active": active, "days_left": days_left, "voices_left": voices_left,
            "started": rec["s"], "voices_used": int(rec["v"]), "clock_back": clock_back,
            "reason": "" if active else ("روز" if days_left == 0 else "ویس")}
