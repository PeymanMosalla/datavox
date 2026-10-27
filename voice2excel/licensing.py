"""مجوز استفاده آفلاین: هر مجوز برای یک رایانه صادر و با امضای سازنده بررسی می‌شود (بدون اینترنت).

روند: برنامه «کد رایانه» را نشان می‌دهد ← فروشنده با scripts/issue_license.py و کلید خصوصی خودش فایل مجوز
می‌سازد ← کاربر فایل (یا متن آن) را در صفحه فعال‌سازی وارد می‌کند. کپی برنامه روی رایانه دیگر کار نمی‌کند،
چون کد آن رایانه فرق دارد. فقط در نسخه قابل‌حمل اجباری است (در اجرای توسعه و آزمون‌ها نه).
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from datetime import date
from pathlib import Path

from . import ed25519
from .config import DATA_DIR

LICENSE_PUBLIC_KEY = bytes.fromhex("7030d3aeb7e8792da38cdee3c031dfbe7b6c42ec4ad92956b4d5ead5d25ba413")
PREFIX = "V2X1"
LICENSE_FILE = DATA_DIR / "license.v2x"
SEEN_FILE = DATA_DIR / "license.seen"  # آخرین تاریخ دیده‌شده؛ برگرداندن ساعت رایانه، مهلت را تمدید نکند


def _required() -> bool:
    from .updater import RUNTIME_FILE
    return RUNTIME_FILE.exists()


REQUIRED = _required()


class LicenseError(Exception):
    """پیام قابل فهم برای کاربر."""


class LicenseLapsed(LicenseError):
    """مجوز درست است ولی مهلت اشتراک گذشته (برای پیام «تمدید» به‌جای «فعال‌سازی»)."""


def _machine_guid() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            return str(winreg.QueryValueEx(k, "MachineGuid")[0])
    except (ImportError, OSError):
        import platform
        import uuid
        return f"{platform.node()}-{uuid.getnode():x}"


def machine_code() -> str:
    """کد ۱۶ نویسه‌ای این رایانه (از شناسه ویندوز؛ با نصب دوباره ویندوز عوض می‌شود)."""
    h = hashlib.sha256(("voice2excel-machine:" + _machine_guid().lower()).encode()).digest()
    s = base64.b32encode(h).decode()[:16]
    return "-".join(s[i:i + 4] for i in range(0, 16, 4))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def encode(data: dict, secret: bytes) -> str:
    """ساخت متن مجوز (فقط ابزار فروشنده)."""
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{PREFIX}.{_b64(raw)}.{_b64(ed25519.sign(secret, raw))}"


def decode(text: str) -> dict:
    parts = "".join((text or "").split()).split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LicenseError("این متن، مجوز «ثبت ویس» نیست.")
    try:
        raw, sig = _unb64(parts[1]), _unb64(parts[2])
    except ValueError:
        raise LicenseError("متن مجوز ناقص است؛ آن را کامل کپی کنید.") from None
    if not ed25519.verify(LICENSE_PUBLIC_KEY, raw, sig):
        raise LicenseError("امضای این مجوز معتبر نیست.")
    return json.loads(raw)


def _today() -> date:
    return date.today()


def evaluate(text: str) -> dict:
    """بررسی کامل یک مجوز برای همین رایانه و امروز."""
    data = decode(text)
    if data.get("machine") != machine_code():
        raise LicenseError("این مجوز برای رایانه دیگری صادر شده است.")
    exp = data.get("expires")
    if exp:
        today = _today()
        try:
            seen = date.fromisoformat(SEEN_FILE.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            seen = today
        if (seen - today).days > 2:
            raise LicenseError("تاریخ رایانه به عقب برگشته است؛ تاریخ را درست کنید.")
        if today > date.fromisoformat(exp):
            raise LicenseLapsed("مهلت اشتراک تمام شده است؛ برای تمدید با فروشنده تماس بگیرید.")
        if today > seen:
            try:
                SEEN_FILE.write_text(today.isoformat(), encoding="utf-8")
            except OSError:
                pass
    return data


_cache = {"key": None, "at": 0.0, "status": None}
_lock = threading.Lock()


def _license() -> dict:
    """نتیجه بررسی فایل مجوز (با حافظه کوتاه، چون بررسی امضا در هر درخواست لازم نیست)."""
    try:
        mtime = LICENSE_FILE.stat().st_mtime
    except OSError:
        mtime = None
    key = (mtime, _today())
    with _lock:
        if _cache["key"] == key and time.time() - _cache["at"] < 600:
            return _cache["status"]
        lic: dict = {"licensed": False}
        if mtime is not None:
            try:
                data = evaluate(LICENSE_FILE.read_text(encoding="utf-8"))
                lic = {"licensed": True, "customer": data.get("customer", ""), "expires": data.get("expires"),
                       "features": data.get("features", [])}
            except LicenseError as e:
                lic = {"licensed": False, "error": str(e), "lapsed": isinstance(e, LicenseLapsed)}
        _cache.update(key=key, at=time.time(), status=lic)
        return lic


def licensed() -> bool:
    """مجوز معتبر (اشتراک). در اجرای توسعه همیشه درست."""
    return not REQUIRED or _license()["licensed"]


def can_process() -> bool:
    """پردازش ویس تازه: با مجوز، یا در دوره آزمایشی فعال. رکوردهای قبلی همیشه در دسترس‌اند."""
    if licensed():
        return True
    from . import trial
    return trial.info()["active"]


def status() -> dict:
    lic = _license()
    st = {"required": REQUIRED, "machine": machine_code(), **lic}
    if not REQUIRED or lic["licensed"]:
        st.update(ok=True, mode="licensed" if lic["licensed"] else "dev")
        if lic.get("expires"):
            st["days_left"] = (date.fromisoformat(lic["expires"]) - _today()).days
        return st
    from . import trial
    t = trial.info()
    st.update(ok=t["active"], mode="trial" if t["active"] else "expired", trial=t)
    return st


def contact() -> dict:
    """راه‌های تماس فروشنده (از پنل فروشنده در بسته قرار می‌گیرد؛ خالی‌ها نمایش داده نمی‌شوند)."""
    try:
        data = json.loads((Path(__file__).resolve().parent / "assets" / "contact.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(data.get(k) or "").strip()[:80] for k in ("name", "phone", "telegram", "whatsapp", "bale", "email")}


def install(text: str) -> dict:
    evaluate(text)  # پیش از ذخیره؛ مجوز نادرست جای مجوز درست را نمی‌گیرد
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LICENSE_FILE.with_suffix(".tmp")
    tmp.write_text("".join(text.split()), encoding="utf-8")
    tmp.replace(LICENSE_FILE)
    _cache["key"] = None
    return status()


def note_processed() -> None:
    """هر ویس پردازش‌شده در دوره آزمایشی شمرده می‌شود (با اشتراک نه)."""
    if REQUIRED and not _license()["licensed"]:
        from . import trial
        trial.record_voice()
