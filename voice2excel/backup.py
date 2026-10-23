"""پشتیبان‌گیری خودکار روزانه از اطلاعات برنامه و بازگردانی آن.

هر پشتیبان یک فایل zip است: پایگاه داده (رونوشت سازگار با API پشتیبان‌گیری خود SQLite، حتی در
حین کار برنامه)، تنظیمات، نگاشت‌های اکسل و یک manifest. فایل‌های صوتی به‌خاطر حجم در پشتیبان
نیستند (متن ویس‌ها و همه رکوردها هستند).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .config import DATA_DIR, reset_settings_cache, settings_path
from .database import Database

KEEP_AUTO = 14
KEEP_MANUAL = 20
_NAME_RE = re.compile(r"^backup-\d{8}-\d{6}-(auto|manual|before-restore)\.zip$")
REASON_LABELS = {"auto": "خودکار روزانه", "manual": "دستی", "before-restore": "پیش از بازگردانی"}


class BackupError(Exception):
    pass


def backup_dir() -> Path:
    d = DATA_DIR / "auto-backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for t in ("audio_files", "records", "entities", "corrections", "exports"):
        try:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            out[t] = 0
    return out


def create_backup(db: Database, reason: str = "manual") -> dict:
    if reason not in REASON_LABELS:
        raise ValueError(reason)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir() / f"backup-{stamp}-{reason}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "voice2excel.db"
        dst = sqlite3.connect(snap)
        try:
            with db.write_lock:
                db.conn().backup(dst)  # رونوشت سازگار؛ نوشتن هم‌زمان در این لحظه منتظر می‌ماند
            counts = _counts(dst)
        finally:
            dst.close()
        manifest = {"app": "voice2excel", "version": __version__, "created_at": datetime.now().isoformat(timespec="seconds"),
                    "reason": reason, "counts": counts}
        part = target.with_suffix(".partial")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "voice2excel.db")
            if settings_path().exists():
                z.write(settings_path(), "settings.json")
            for p in sorted((DATA_DIR / "profiles").glob("*.json")):
                z.write(p, f"profiles/{p.name}")
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(part, target)
    prune()
    return {"name": target.name, **manifest, "size": target.stat().st_size}


def list_backups() -> list[dict]:
    out = []
    for p in sorted(backup_dir().glob("backup-*.zip"), reverse=True):
        if not _NAME_RE.match(p.name):
            continue
        try:
            with zipfile.ZipFile(p) as z:
                manifest = json.loads(z.read("manifest.json"))
        except (zipfile.BadZipFile, KeyError, ValueError):
            manifest = {"reason": "?", "created_at": "", "counts": {}, "damaged": True}
        out.append({"name": p.name, "size": p.stat().st_size, **manifest,
                    "reason_label": REASON_LABELS.get(manifest.get("reason"), "")})
    return out


def prune() -> None:
    by_reason: dict[str, list[Path]] = {}
    for p in sorted(backup_dir().glob("backup-*.zip"), reverse=True):
        m = _NAME_RE.match(p.name)
        if m:
            by_reason.setdefault(m.group(1), []).append(p)
    for reason, files in by_reason.items():
        keep = KEEP_AUTO if reason == "auto" else KEEP_MANUAL
        for old in files[keep:]:
            old.unlink(missing_ok=True)


def backup_path(name: str) -> Path:
    if not _NAME_RE.match(name):
        raise BackupError("نام فایل پشتیبان نامعتبر است.")
    p = backup_dir() / name
    if not p.exists():
        raise BackupError("فایل پشتیبان پیدا نشد.")
    return p


def maybe_daily_backup(db: Database) -> dict | None:
    """اگر از آخرین پشتیبان خودکار بیش از یک روز گذشته، پشتیبان تازه ساخته می‌شود."""
    autos = [b for b in list_backups() if b.get("reason") == "auto" and b.get("created_at")]
    if autos:
        last = datetime.fromisoformat(autos[0]["created_at"])
        if datetime.now() - last < timedelta(days=1):
            return None
    if not db.one("SELECT COUNT(*) n FROM audio_files")["n"] and not db.one("SELECT COUNT(*) n FROM entities")["n"]:
        return None  # برنامه هنوز اطلاعاتی ندارد
    return create_backup(db, "auto")


def restore_backup(db: Database, name: str) -> dict:
    """بازگردانی کامل پایگاه داده، تنظیمات و نگاشت‌ها از یک پشتیبان.

    پیش از هر تغییر: سالم بودن فایل بررسی و از وضعیت فعلی یک پشتیبان «پیش از بازگردانی» گرفته می‌شود.
    """
    src_zip = backup_path(name)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(src_zip) as z:
                manifest = json.loads(z.read("manifest.json"))
                if manifest.get("app") != "voice2excel":
                    raise BackupError("این فایل، پشتیبان برنامه ثبت ویس نیست.")
                z.extractall(tmp)
        except (zipfile.BadZipFile, KeyError, ValueError) as e:
            raise BackupError("فایل پشتیبان خراب است.") from e
        snap = Path(tmp) / "voice2excel.db"
        src = sqlite3.connect(snap)
        try:
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("پایگاه داده داخل پشتیبان سالم نیست.")
            safety = create_backup(db, "before-restore")
            with db.write_lock:
                src.backup(db.conn())  # جایگزینی کامل محتوای پایگاه داده فعلی
        finally:
            src.close()
        if (Path(tmp) / "settings.json").exists():
            shutil.copy2(Path(tmp) / "settings.json", settings_path())
        prof_src = Path(tmp) / "profiles"
        if prof_src.exists():
            prof_dst = DATA_DIR / "profiles"
            for p in prof_dst.glob("*.json"):
                p.unlink()
            for p in prof_src.glob("*.json"):
                shutil.copy2(p, prof_dst / p.name)
        reset_settings_cache()
    return {"restored": name, "safety_backup": safety["name"], "counts": manifest.get("counts", {})}
