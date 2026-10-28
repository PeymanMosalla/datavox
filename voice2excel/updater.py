"""به‌روزرسانی سبک نسخه قابل‌حمل: فقط کد برنامه (حدود ۱ مگابایت) به‌جای بسته کامل ۱٫۸ گیگابایتی.

روند:
1. scripts/build_update.py یک zip با کد برنامه و manifest می‌سازد (نسخه، شناسه محیط اجرا، هش هر فایل).
2. کاربر فایل را در «تنظیمات» انتخاب می‌کند؛ اینجا اعتبارسنجی و در پوشه update-staged آماده می‌شود.
3. DataVox.exe در اجرای بعدی نسخه آماده را جایگزین می‌کند و اگر برنامه بالا نیامد، نسخه قبلی را برمی‌گرداند.

اگر کتابخانه‌ها یا Python تغییر کرده باشند (شناسه محیط اجرا متفاوت)، به‌روزرسانی سبک پذیرفته نمی‌شود و بسته کامل لازم است.

امنیت: manifest با کلید خصوصی سازنده امضا می‌شود (Ed25519، فایل manifest.sig) و برنامه فقط بسته‌ای را
می‌پذیرد که امضایش با کلید عمومی زیر بخواند؛ هش هر فایل در همان manifest امضاشده است، پس تغییر حتی یک بایت
از کد، بسته را نامعتبر می‌کند. کلید خصوصی فقط نزد سازنده است (خارج از مخزن).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from . import __version__, ed25519

APP_ROOT = Path(__file__).resolve().parent.parent  # در نسخه قابل‌حمل: <پوشه برنامه>/app
BASE_DIR = APP_ROOT.parent
RUNTIME_FILE = APP_ROOT / "runtime.json"
STAGE_DIR = BASE_DIR / "update-staged"
MAX_UPDATE_BYTES = 30 * 1024 * 1024
MAX_UNPACKED_BYTES = 120 * 1024 * 1024  # در برابر فایل فشرده‌ای که پس از باز شدن بسیار بزرگ می‌شود
UPDATE_PUBLIC_KEY = bytes.fromhex("4abcac16343d36a4e002cec3ef9a6052fa539fc12a786bd4ae65d64c23bbea12")
# امضا در «توضیح» فایل zip است، نه یک فایل داخل آن، تا نسخه‌های پیش از ۲٫۰ (که هر فایلِ بیرون از
# فهرست را رد می‌کنند) هم بتوانند همین بسته را نصب کنند
SIG_PREFIX = b"V2X-SIG1:"
ROOT_EXTRAS = {"Guide.html", "Recording-Guide.html"}  # فایل‌های کنار DataVox.exe که با به‌روزرسانی عوض می‌شوند


class UpdateError(Exception):
    pass


def compute_runtime_id(python_version: str, requirements: list[str]) -> str:
    """شناسه محیط اجرا: نسخه Python (اصلی.فرعی) + کتابخانه‌های زمان اجرا با نسخه دقیق."""
    major_minor = ".".join(python_version.split(".")[:2])
    payload = major_minor + "|" + "\n".join(sorted(r.strip().lower() for r in requirements if r.strip()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def current_runtime_id() -> str | None:
    if not RUNTIME_FILE.exists():
        return None
    try:
        return json.loads(RUNTIME_FILE.read_text(encoding="utf-8")).get("runtime_id")
    except (OSError, ValueError):
        return None


def parse_version(v: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(\.\d+){1,3}", v or ""):
        raise UpdateError(f"نسخه نامعتبر: {v}")
    return tuple(int(x) for x in v.split("."))


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in name and ":" not in name


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_update(zip_path: Path) -> dict:
    """اعتبارسنجی کامل بسته به‌روزرسانی (بدون نوشتن هیچ فایلی)."""
    if zip_path.stat().st_size > MAX_UPDATE_BYTES:
        raise UpdateError("حجم فایل برای بسته به‌روزرسانی بیش از حد است.")
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise UpdateError("فایل به‌روزرسانی خراب است یا zip نیست.") from e
    with z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not all(_safe_member(n) for n in names):
            raise UpdateError("بسته شامل مسیر نامعتبر است و پذیرفته نمی‌شود.")
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED_BYTES:
            raise UpdateError("حجم بسته پس از باز شدن غیرعادی است و پذیرفته نمی‌شود.")
        try:
            raw = z.read("manifest.json")
            manifest = json.loads(raw)
        except (KeyError, ValueError) as e:
            raise UpdateError("بسته به‌روزرسانی manifest ندارد.") from e
        try:
            sig = bytes.fromhex(z.comment.removeprefix(SIG_PREFIX).decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            sig = b""
        if not z.comment.startswith(SIG_PREFIX) or not ed25519.verify(UPDATE_PUBLIC_KEY, raw, sig):
            raise UpdateError("این بسته امضای معتبر سازنده برنامه را ندارد و پذیرفته نمی‌شود "
                              "(ممکن است دست‌کاری یا از منبع نامعتبر گرفته شده باشد).")
        if manifest.get("app") != "voice2excel" or manifest.get("type") != "update":
            raise UpdateError("این فایل، بسته به‌روزرسانی برنامه DataVox نیست.")
        new_v = manifest.get("version", "")
        if parse_version(new_v) <= parse_version(__version__):
            raise UpdateError(f"نسخه این بسته ({new_v}) از نسخه فعلی ({__version__}) جدیدتر نیست.")
        rid = current_runtime_id()
        if rid is None:
            raise UpdateError("به‌روزرسانی سبک فقط در نسخه قابل‌حمل (DataVox.exe) پشتیبانی می‌شود.")
        if manifest.get("runtime_id") != rid:
            raise UpdateError("این نسخه به کتابخانه‌های تازه نیاز دارد؛ بسته کامل برنامه را نصب کنید.")
        files: dict = manifest.get("files") or {}
        if not files or not any(f.startswith("voice2excel/") for f in files):
            raise UpdateError("بسته به‌روزرسانی کد برنامه ندارد.")
        for name, digest in files.items():
            if not _safe_member(name) or not (name.startswith("voice2excel/") or name in ROOT_EXTRAS):
                raise UpdateError(f"فایل غیرمجاز در بسته: {name}")
            try:
                data = z.read(name)
            except KeyError as e:
                raise UpdateError(f"فایل {name} در بسته نیست.") from e
            if _sha256(data) != digest:
                raise UpdateError(f"فایل {name} آسیب دیده است (هش نادرست).")
        extra = set(names) - set(files) - {"manifest.json"}
        if extra:
            raise UpdateError("بسته فایل‌های ثبت‌نشده در manifest دارد.")
    return manifest


def stage_update(zip_path: Path) -> dict:
    """آماده‌سازی به‌روزرسانی برای اعمال در اجرای بعدی DataVox.exe."""
    manifest = inspect_update(zip_path)
    tmp = STAGE_DIR.with_name(STAGE_DIR.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        for name in manifest["files"]:
            target = tmp / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    (tmp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    tmp.rename(STAGE_DIR)
    return {"version": manifest["version"], "files": len(manifest["files"]), "notes": manifest.get("notes", "")}


def staged_info() -> dict | None:
    m = STAGE_DIR / "manifest.json"
    if not m.exists():
        return None
    try:
        data = json.loads(m.read_text(encoding="utf-8"))
        return {"version": data.get("version"), "notes": data.get("notes", "")}
    except (OSError, ValueError):
        return None


def cancel_staged() -> None:
    shutil.rmtree(STAGE_DIR, ignore_errors=True)


def build_update_zip(src_pkg: Path, out_zip: Path, runtime_id: str, version: str, extras: list[Path] = (),
                     notes: str = "", signing_key: bytes | None = None) -> dict:
    """ساخت بسته به‌روزرسانی (در scripts/build_update.py و آزمون‌ها). signing_key: کلید خصوصی امضا (۳۲ بایت)."""
    files: dict[str, str] = {}
    entries: list[tuple[str, bytes]] = []
    for p in sorted(src_pkg.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        arc = "voice2excel/" + p.relative_to(src_pkg).as_posix()
        data = p.read_bytes()
        files[arc] = _sha256(data)
        entries.append((arc, data))
    for p in extras:
        data = p.read_bytes()
        files[p.name] = _sha256(data)
        entries.append((p.name, data))
    manifest = {"app": "voice2excel", "type": "update", "version": version, "runtime_id": runtime_id,
                "files": files, "notes": notes}
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", raw)
        if signing_key:
            z.comment = SIG_PREFIX + ed25519.sign(signing_key, raw).hex().encode()
        for arc, data in entries:
            z.writestr(arc, data)
    return manifest
