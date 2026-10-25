"""سرور محلی (FastAPI) و API رابط کاربری.

فقط روی 127.0.0.1 گوش می‌دهد؛ هیچ داده‌ای به بیرون از رایانه ارسال نمی‌شود.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import string
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, backup, dictionary, excel_mapping, excel_template, knowledge, lan, learning, pipeline, updater
from .audio_processor import is_supported
from .config import (AVAILABLE_MODELS, DATA_DIR, MODELS_DIR, SAMPLES_DIR, SUPPORTED_AUDIO_EXTENSIONS, WEB_DIR,
                     ensure_dirs, load_settings, save_settings)
from .database import Database, get_db, now
from .dates_fa import date_from_filename, format_jalali, from_gregorian, parse_jalali, today_jalali
from .deduplicator import file_sha256
from .excel_reader import inspect_workbook, lock_status, read_rows
from .excel_writer import ExcelWriteError, preview, replace_original, write_export
from .inbox import Inbox
from .logger import get_logger
from .schema import COMPUTED_FIELDS, FIELD_DEFS, FIELD_LABELS
from .text_style import infer_style
from .transcriber import installed_models, model_available
from .worker import Worker

log = get_logger("server")


@asynccontextmanager
async def _lifespan(_app):
    _startup()
    yield


app = FastAPI(title="ثبت ویس", version=__version__, docs_url=None, redoc_url=None, lifespan=_lifespan)


_last_request = {"t": time.time()}
IDLE_EXIT_SECONDS = 15 * 60
_pin_limiter = lan.FailureLimiter()


@app.middleware("http")
async def _lan_guard(request, call_next):
    """دستگاه‌های دیگر شبکه فقط به صفحه آپلود گوشی (با رمز) دسترسی دارند؛ بقیه فقط از خود رایانه."""
    host = request.client.host if request.client else None
    if lan.is_local(host):
        return await call_next(request)
    path = request.url.path
    s = load_settings()
    if not s.lan_enabled or not s.lan_pin or not lan.remote_path_allowed(path):
        return JSONResponse(status_code=403, content={"detail": "این بخش فقط از روی خود رایانه در دسترس است."})
    if lan.needs_pin(path):
        if _pin_limiter.blocked(host):
            return JSONResponse(status_code=429, content={"detail": "تلاش ناموفق زیاد بود؛ چند دقیقه دیگر دوباره امتحان کنید."})
        if not lan.pin_ok(request.headers.get("x-pin"), s.lan_pin):
            _pin_limiter.fail(host)
            return JSONResponse(status_code=401, content={"detail": "رمز نادرست است."})
        _pin_limiter.reset(host)
    return await call_next(request)


@app.middleware("http")
async def _no_cache(request, call_next):
    """پس از به‌روزرسانی برنامه، مرورگر نسخه قدیمی رابط را از حافظه نهان نخواند."""
    _last_request["t"] = time.time()
    response = await call_next(request)
    if not request.url.path.startswith("/api/files/") and not request.url.path.startswith("/static/fonts"):
        response.headers["Cache-Control"] = "no-cache"
    return response

_worker: Worker | None = None
_download_state: dict = {"name": None, "status": "idle", "message": ""}


def db() -> Database:
    return get_db()


def worker() -> Worker:
    global _worker
    if _worker is None:
        _worker = Worker(db())
    return _worker


def set_worker(w: Worker | None) -> None:
    global _worker
    _worker = w


def _write_profile(create: bool = False) -> dict | None:
    """نگاشت قالب فعال برای ثبت؛ قالب «فایل جدید» به نگاشت فایل خود برنامه تبدیل می‌شود.

    create: اگر فایل خروجی قالب هنوز ساخته نشده، با سرستون ساخته شود (فقط هنگام ثبت و پیش‌نمایش).
    """
    prof = excel_mapping.load_profile(load_settings().active_profile)
    if prof and prof.get("mode") == "new":
        try:
            return excel_template.writer_profile(prof, create)
        except FileNotFoundError as e:
            if create:
                err(400, str(e))
            return None
    return prof


# ---------- نامزدهای تکرار از فایل اکسل مقصد ----------
_excel_cache: dict = {"key": None, "rows": []}


def _excel_candidates() -> list[dict]:
    prof = _write_profile()
    if not prof or not prof.get("excel_path"):
        return []
    p = Path(prof["excel_path"])
    if not p.exists():
        return []
    key = (str(p), p.stat().st_mtime, tuple(sorted(prof["columns"].items())))
    if _excel_cache["key"] != key:
        cols = {c: f for c, f in prof["columns"].items() if f in ("engineer_name", "phone", "address", "project_name")}
        _excel_cache["rows"] = read_rows(p, prof["sheet"], prof["header_row"], cols) if cols else []
        _excel_cache["key"] = key
    return _excel_cache["rows"]


def _startup() -> None:
    ensure_dirs()
    n = db().recover_interrupted()
    if n:
        db().log_event(f"{n} فایل نیمه‌کاره پس از بسته‌شدن برنامه به صف برگشت.", "warning")
    pipeline.set_excel_candidates_provider(_excel_candidates)
    from .extractor import EXTRACTOR_VERSION
    if db().get_meta("extractor_version") != EXTRACTOR_VERSION:
        try:
            res = pipeline.reextract_all(db(), load_settings())
            if res["reextracted"]:
                db().log_event(f"پس از به‌روزرسانی، {res['reextracted']} ویس با قواعد جدید دوباره استخراج شد "
                               f"({res['protected']} ویس به‌خاطر اصلاح یا تأیید دستی دست نخورد).")
        except Exception:
            log.exception("reextract on upgrade failed")
        db().set_meta("extractor_version", EXTRACTOR_VERSION)
    if os.environ.get("V2X_AUTO_EXIT") == "1":
        threading.Thread(target=_idle_watchdog, name="idle-watchdog", daemon=True).start()
    threading.Thread(target=_daily_backup_loop, name="daily-backup", daemon=True).start()
    threading.Thread(target=_inbox_loop, name="inbox", daemon=True).start()


def inbox_poll_once(box: Inbox) -> int:
    """یک دور بررسی پوشه ورودی: ثبت ویس‌های تازه و شروع پردازش. خروجی: تعداد ویس‌های افزوده."""
    s = load_settings()
    if not s.inbox_dir:
        return 0
    files = box.poll(s.inbox_dir, float(db().get_meta("inbox_since") or 0))
    if not files:
        return 0
    batch = db().create_batch("پوشه ورودی", format_jalali(today_jalali()))
    added = 0
    for f in files:
        try:
            visit = format_jalali(from_gregorian(datetime.fromtimestamp(f.stat().st_mtime).date()))
            with open(f, "rb") as fh:
                added += _register_file(fh, f.name, batch, visit, True)["result"] == "added"
        except OSError:
            log.exception("inbox file failed: %s", f)
    if added:
        db().log_event(f"{added} ویس از پوشه ورودی اضافه شد.")
        if model_available(s.model_name):
            worker().start()
    return added


def _inbox_loop() -> None:
    box = Inbox()
    while True:
        try:
            inbox_poll_once(box)
        except Exception:
            log.exception("inbox poll failed")
        time.sleep(4)


def _daily_backup_loop() -> None:
    """هنگام اجرا و سپس هر ساعت بررسی می‌شود که پشتیبان روزانه گرفته شده باشد."""
    while True:
        try:
            made = backup.maybe_daily_backup(db())
            if made:
                log.info("پشتیبان خودکار روزانه ساخته شد: %s", made["name"])
        except Exception:
            log.exception("daily backup failed")
        time.sleep(3600)


def _idle_watchdog() -> None:
    """نسخه قابل‌حمل پنجره ندارد: اگر مرورگر بسته شده و کاری در جریان نیست، برنامه بسته می‌شود."""
    while True:
        time.sleep(30)
        if worker().running:
            _last_request["t"] = time.time()
            continue
        if time.time() - _last_request["t"] > IDLE_EXIT_SECONDS:
            log.info("بسته‌شدن خودکار پس از بی‌کاری")
            os._exit(0)


def err(status: int, msg: str):
    raise HTTPException(status_code=status, detail=msg)


# ---------- وضعیت ----------
@app.get("/api/status")
def status():
    d = db()
    files = d.counts()
    rec = {r["k"]: r["n"] for r in d.q(
        """SELECT CASE
             WHEN exported_at IS NOT NULL THEN 'exported'
             WHEN review_state='rejected' THEN 'rejected'
             WHEN review_state='approved' THEN 'approved'
             ELSE 'review' END k, COUNT(*) n FROM records GROUP BY k""")}
    w = worker().state()
    remaining = files.get("queued", 0) + files.get("processing", 0)
    done_run = w["run_done"]
    progress = 100 if remaining == 0 else round(100 * done_run / max(1, done_run + remaining))
    s = load_settings()
    return {
        "files": {
            "total": sum(files.values()), "queued": files.get("queued", 0), "processing": files.get("processing", 0),
            "done": files.get("done", 0), "failed": files.get("failed", 0),
        },
        "records": {k: rec.get(k, 0) for k in ("review", "approved", "exported", "rejected")},
        "worker": w,
        "progress": progress,
        "model": {"name": s.model_name, "available": model_available(s.model_name)},
        "version": __version__,
        "today": format_jalali(today_jalali()),
        "pending_replace": d.one("SELECT COUNT(*) n FROM exports WHERE status='created' AND replaced_original_at IS NULL")["n"],
        "setup": _setup_state(),
    }


def _setup_state() -> dict:
    """وضعیت گام‌های راه‌اندازی اولیه (برای راهنمای اجرای اول)."""
    prof = _write_profile()
    return {
        "excel_ready": bool(prof and prof.get("confirmed") and Path(prof["excel_path"]).parent.is_dir()),
        "excel_name": Path(prof["excel_path"]).name if prof and prof.get("excel_path") else "",
        "dictionary": db().one("SELECT COUNT(*) n FROM entities")["n"],
        "corrections": db().one("SELECT COUNT(*) n FROM corrections")["n"],
        "inbox": load_settings().inbox_dir,
        "template_mode": (prof or {}).get("mode", "append"),
        "template_title": (prof or {}).get("title", ""),
    }


def _sample_files() -> tuple[list[Path], Path | None]:
    if not SAMPLES_DIR.is_dir():
        return [], None
    voices = sorted(p for p in SAMPLES_DIR.iterdir() if p.is_file() and is_supported(p.name))
    excel = next(iter(sorted(SAMPLES_DIR.glob("*.xlsx"))), None)
    return voices, excel


@app.get("/api/meta")
def meta():
    voices, excel = _sample_files()
    return {
        "fields": [{"key": k, "label": label, "group": g} for k, label, g in FIELD_DEFS],
        "computed": [{"key": k, "label": v} for k, v in COMPUTED_FIELDS.items()],
        "entity_types": dictionary.ENTITY_TYPES,
        "audio_extensions": sorted(SUPPORTED_AUDIO_EXTENSIONS),
        "samples": {"voices": len(voices), "excel": str(excel) if excel else "", "dir": str(SAMPLES_DIR)},
        "auto_exit": os.environ.get("V2X_AUTO_EXIT") == "1",
    }


@app.post("/api/shutdown")
def shutdown():
    """خروج از برنامه (دکمه «خروج» در رابط). پردازش در جریان متوقف و فایل به صف برمی‌گردد."""
    worker().cancel()

    def bye():
        worker().join(20)
        os._exit(0)

    threading.Timer(0.5, bye).start()
    return {"ok": True}


# ---------- فایل‌های صوتی ----------
def _register_file(src_stream, original_name: str, batch_id: int, visit_date: str, use_filename_date: bool) -> dict:
    uploads = DATA_DIR / "uploads"
    ext = Path(original_name).suffix.lower()
    tmp = uploads / f".incoming_{uuid.uuid4().hex}{ext}"
    size = 0
    with open(tmp, "wb") as out:
        while True:
            chunk = src_stream.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    sha = file_sha256(tmp)
    existing = db().find_audio_by_hash(sha)
    if existing:
        tmp.unlink(missing_ok=True)
        return {"name": original_name, "result": "duplicate", "existing_id": existing["id"],
                "message": f"این فایل قبلاً با نام «{existing['original_name']}» اضافه شده است."}
    if size == 0:
        tmp.unlink(missing_ok=True)
        return {"name": original_name, "result": "error", "message": "فایل خالی است."}
    stored = f"{sha[:20]}{ext}"
    os.replace(tmp, uploads / stored)
    vd, source = visit_date, "user"
    if use_filename_date:
        fd = date_from_filename(original_name)
        if fd:
            vd, source = format_jalali(fd), "filename"
    aid = db().add_audio(batch_id, original_name, stored, sha, size, vd, source)
    return {"name": original_name, "result": "added", "id": aid, "visit_date": vd, "date_source": source}


def _check_visit_date(visit_date: str) -> str:
    d = parse_jalali(visit_date)
    if d is None:
        err(400, "تاریخ بازدید باید شمسی و مانند 1405/07/28 باشد.")
    return format_jalali(d)


async def _store_uploads(files: list[UploadFile], batch_name: str, visit_date: str, use_filename_date: bool) -> list[dict]:
    """ذخیره فایل‌های آپلودی (رایانه یا گوشی) و افزودن به صف؛ مدل هم از همین حالا آماده می‌شود."""
    vd = _check_visit_date(visit_date or format_jalali(today_jalali()))
    batch = db().create_batch(batch_name, vd)
    results = []
    for f in files:
        name = Path(f.filename or "audio").name
        if not is_supported(name):
            results.append({"name": name, "result": "error", "message": "قالب این فایل پشتیبانی نمی‌شود."})
            continue
        try:
            results.append(_register_file(f.file, name, batch, vd, use_filename_date))
        except Exception as e:
            results.append({"name": name, "result": "error", "message": f"ذخیره فایل ناموفق بود: {e}"})
        finally:
            await f.close()
    if any(r["result"] == "added" for r in results) and model_available(load_settings().model_name):
        worker().warmup()
    return results


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...), visit_date: str = Form(""), use_filename_date: bool = Form(True)):
    return {"results": await _store_uploads(files, f"آپلود {datetime.now():%H:%M}", visit_date, use_filename_date)}


# ---------- آپلود از گوشی (شبکه محلی) ----------
_PHONE_BATCH = "گوشی: "


@app.get("/m")
def mobile_page():
    return FileResponse(WEB_DIR / "m.html")


@app.post("/api/m/check")
def mobile_check():
    """رمز در میان‌افزار بررسی شده است؛ اینجا فقط اطلاعات صفحه برگردانده می‌شود."""
    return {"ok": True, "today": format_jalali(today_jalali()), "extensions": sorted(SUPPORTED_AUDIO_EXTENSIONS)}


@app.post("/api/m/upload")
async def mobile_upload(files: list[UploadFile] = File(...), visit_date: str = Form(""), sender: str = Form("")):
    sender = (sender or "").strip()[:40] or "بدون نام"
    results = await _store_uploads(files, _PHONE_BATCH + sender, visit_date, True)
    s = load_settings()
    if s.lan_auto_start and any(r["result"] == "added" for r in results) and model_available(s.model_name):
        worker().start()
    # فقط نتیجه افزودن به گوشی برمی‌گردد، نه شناسه داخلی یا مسیر فایل
    return {"results": [{"name": r["name"], "result": r["result"], "message": r.get("message", "")} for r in results]}


@app.get("/api/m/recent")
def mobile_recent(sender: str = ""):
    """وضعیت آخرین ویس‌های فرستاده‌شده از گوشی همین فرستنده (فقط نام فایل و وضعیت پردازش)."""
    rows = db().q("""SELECT a.original_name, a.status, a.created_at FROM audio_files a JOIN batches b ON b.id=a.batch_id
                     WHERE b.name=? ORDER BY a.id DESC LIMIT 20""", (_PHONE_BATCH + ((sender or "").strip()[:40] or "بدون نام"),))
    return {"files": rows}


class LanIn(BaseModel):
    enabled: bool
    auto_start: bool = True


@app.get("/api/lan")
def lan_info():
    s = load_settings()
    bound = os.environ.get("V2X_BIND_HOST", s.host)
    return {
        "enabled": s.lan_enabled, "pin": s.lan_pin, "auto_start": s.lan_auto_start,
        "urls": [f"http://{ip}:{s.port}/m" for ip in lan.lan_addresses()],
        "restart_needed": s.lan_enabled != (bound == "0.0.0.0"),
    }


@app.put("/api/lan")
def lan_set(body: LanIn):
    s = load_settings()
    updates = {"lan_enabled": body.enabled, "lan_auto_start": body.auto_start}
    if body.enabled and not s.lan_pin:
        updates["lan_pin"] = lan.generate_pin()
    save_settings(updates)
    return lan_info()


@app.post("/api/lan/new-pin")
def lan_new_pin():
    save_settings({"lan_pin": lan.generate_pin()})
    return lan_info()


class FolderImport(BaseModel):
    path: str
    visit_date: str = ""
    use_filename_date: bool = True
    recursive: bool = False


@app.post("/api/import-folder")
def import_folder(body: FolderImport):
    folder = Path(body.path)
    if not folder.is_dir():
        err(400, "پوشه پیدا نشد.")
    vd = _check_visit_date(body.visit_date or format_jalali(today_jalali()))
    it = folder.rglob("*") if body.recursive else folder.iterdir()
    files = sorted(p for p in it if p.is_file() and is_supported(p.name))
    if not files:
        err(400, "در این پوشه فایل صوتی پشتیبانی‌شده‌ای پیدا نشد.")
    batch = db().create_batch(f"پوشه {folder.name}", vd)
    results = []
    for p in files:
        try:
            with open(p, "rb") as fh:
                results.append(_register_file(fh, p.name, batch, vd, body.use_filename_date))
        except OSError as e:
            results.append({"name": p.name, "result": "error", "message": f"خواندن فایل ناموفق بود: {e.strerror}"})
    if any(r["result"] == "added" for r in results) and model_available(load_settings().model_name):
        worker().warmup()
    return {"results": results}


@app.post("/api/samples/import")
def import_samples():
    """افزودن ویس‌های نمونه (گفتار مصنوعی با اطلاعات ساختگی) برای امتحان برنامه."""
    voices, _ = _sample_files()
    if not voices:
        err(404, "ویس نمونه‌ای همراه برنامه نیست.")
    return import_folder(FolderImport(path=str(SAMPLES_DIR), visit_date="", use_filename_date=False))


@app.get("/api/files")
def list_files():
    rows = db().q(
        """SELECT a.id, a.original_name, a.size, a.duration, a.visit_date, a.date_source, a.status, a.error,
                  a.attempts, a.model, a.processing_seconds, a.peak_rss_mb, a.audio_deleted, a.created_at,
                  (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id) AS records,
                  (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id AND r.review_state='pending') AS pending,
                  (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id AND r.exported_at IS NOT NULL) AS exported
           FROM audio_files a ORDER BY a.id DESC""")
    return {"files": rows}


def _get_file(fid: int) -> dict:
    f = db().one("SELECT * FROM audio_files WHERE id=?", (fid,))
    if not f:
        err(404, "فایل پیدا نشد.")
    return f


def _protected_records(fid: int) -> int:
    return db().one(
        "SELECT COUNT(*) n FROM records WHERE audio_id=? AND (manually_edited=1 OR exported_at IS NOT NULL OR "
        "(review_state!='pending' AND approved_by='user'))", (fid,))["n"]


@app.delete("/api/files/{fid}")
def delete_file(fid: int):
    f = _get_file(fid)
    if f["status"] == "processing":
        err(409, "این فایل در حال پردازش است.")
    if db().one("SELECT COUNT(*) n FROM records WHERE audio_id=? AND exported_at IS NOT NULL", (fid,))["n"]:
        err(409, "رکوردهای این فایل در اکسل ثبت شده‌اند و حذف آن مجاز نیست.")
    with db().tx() as c:
        c.execute("DELETE FROM records WHERE audio_id=?", (fid,))
        c.execute("DELETE FROM transcripts WHERE audio_id=?", (fid,))
        c.execute("DELETE FROM audio_files WHERE id=?", (fid,))
    if f["stored_name"]:
        (DATA_DIR / "uploads" / f["stored_name"]).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/files/{fid}/retry")
def retry_file(fid: int):
    f = _get_file(fid)
    if f["status"] == "processing":
        err(409, "این فایل در حال پردازش است.")
    if f["status"] == "done" and _protected_records(fid):
        err(409, "رکوردهای این فایل اصلاح، تأیید یا ثبت شده‌اند؛ پردازش دوباره آن‌ها را بازنویسی نمی‌کند. "
                 "در صورت نیاز، رکوردها را در بخش بازبینی اصلاح کنید.")
    if f["audio_deleted"]:
        err(409, "فایل صوتی این مورد پاک شده است.")
    db().set_audio(fid, status="queued", error=None)
    return {"ok": True}


@app.post("/api/files/retry-failed")
def retry_failed():
    with db().tx() as c:
        n = c.execute("UPDATE audio_files SET status='queued', error=NULL WHERE status='failed' AND audio_deleted=0").rowcount
    return {"requeued": n}


@app.get("/api/files/{fid}/audio")
def file_audio(fid: int):
    f = _get_file(fid)
    p = DATA_DIR / "uploads" / (f["stored_name"] or "")
    if f["audio_deleted"] or not p.exists():
        err(404, "فایل صوتی موجود نیست.")
    return FileResponse(p, filename=f["original_name"])


@app.post("/api/queue/start")
def queue_start():
    s = load_settings()
    if not model_available(s.model_name):
        err(409, f"مدل گفتار «{s.model_name}» نصب نیست. از بخش تنظیمات مدل را دریافت کنید یا download_model.bat را اجرا کنید.")
    started = worker().start()
    return {"started": started}


@app.post("/api/model/warmup")
def model_warmup():
    """بارگذاری مدل در پس‌زمینه تا اولین ویس منتظر بارگذاری نماند."""
    if not model_available(load_settings().model_name):
        return {"started": False, "state": "missing"}
    return {"started": worker().warmup(), "state": worker().state()["model_state"]}


@app.post("/api/queue/cancel")
def queue_cancel():
    worker().cancel()
    return {"ok": True}


# ---------- رکوردها ----------
def _record_out(r: dict) -> dict:
    return {
        "id": r["id"], "audio_id": r["audio_id"], "original_name": r.get("original_name"),
        "building_index": r["building_index"], "building_count": r["building_count"],
        "values": r["values"], "validation": r["validation"], "status": r["status"],
        "review_state": r["review_state"], "approved_by": r["approved_by"],
        "duplicate_decision": r["duplicate_decision"], "manually_edited": r["manually_edited"],
        "exported_at": r["exported_at"], "export_row": r["export_row"], "export_id": r["export_id"],
        "evidence": r["extracted"].get("meta", {}).get("evidence", {}),
        "times": r["extracted"].get("meta", {}).get("times", {}),
        "low_confidence": r["extracted"].get("meta", {}).get("low_confidence", {}),
        "low_times": r["extracted"].get("meta", {}).get("low_times", {}),
        "audio_available": not r.get("audio_deleted"),
    }


_FILTERS = {
    "review": "r.review_state='pending' AND r.exported_at IS NULL",
    "approved": "r.review_state='approved' AND r.exported_at IS NULL",
    "exported": "r.exported_at IS NOT NULL",
    "rejected": "r.review_state='rejected' AND r.exported_at IS NULL",
    "all": "1=1",
}


@app.get("/api/records")
def list_records(filter: str = "review", audio_id: int | None = None):
    where = _FILTERS.get(filter, "1=1")
    args: tuple = ()
    if audio_id:
        where += " AND r.audio_id=?"
        args = (audio_id,)
    return {"records": [_record_out(r) for r in db().list_records(where, args)]}


def _get_record(rid: int) -> dict:
    r = db().list_records("r.id=?", (rid,))
    if not r:
        err(404, "رکورد پیدا نشد.")
    return r[0]


@app.get("/api/records/{rid}")
def get_record(rid: int):
    r = _get_record(rid)
    out = _record_out(r)
    out["transcript"] = db().transcript(r["audio_id"])
    out["extracted_values"] = r["extracted"].get("values", {})
    out["ambiguities"] = r["extracted"].get("meta", {}).get("ambiguities", [])
    out["edits"] = db().q("SELECT id, field, old_value, new_value, action, at, undone FROM record_edits WHERE record_id=? ORDER BY id DESC", (rid,))
    return out


class RecordPatch(BaseModel):
    values: dict[str, str]


@app.patch("/api/records/{rid}")
def patch_record(rid: int, body: RecordPatch):
    r = _get_record(rid)
    if r["exported_at"]:
        err(409, "این رکورد در اکسل ثبت شده است؛ برای ویرایش ابتدا ثبت آن را بازگردانید.")
    values = dict(r["values"])
    changed = False
    for k, v in body.values.items():
        if k not in FIELD_LABELS and k != "floors_unit":
            continue
        v = (v or "").strip()
        if k == "phone":
            from .normalizer import to_ascii_digits
            v = "\n".join(to_ascii_digits(x).replace(" ", "").replace("-", "") for x in v.replace("،", "\n").split("\n") if x.strip())
        if values.get(k, "") != v:
            db().log_edit(rid, k, values.get(k, ""), v, "edit")
            learning.learn_from_edit(db(), k, values.get(k, ""), v)
            values[k] = v
            changed = True
    if changed:
        db().update_record(rid, values_json={k: v for k, v in values.items() if v}, manually_edited=1)
        pipeline.revalidate(db(), load_settings(), rid)
    return get_record(rid)


class RecordAction(BaseModel):
    action: str  # approve / reject / reopen
    add_to_dictionary: bool = False


@app.post("/api/records/{rid}/action")
def record_action(rid: int, body: RecordAction):
    r = _get_record(rid)
    if r["exported_at"]:
        err(409, "این رکورد در اکسل ثبت شده است.")
    if body.action == "approve":
        if body.add_to_dictionary:
            _add_values_to_dictionary(r["values"], "تأیید رکورد")
        _touch_dictionary(r["values"])
        db().update_record(rid, review_state="approved", approved_by="user")
        db().log_edit(rid, "*", r["review_state"], "approved", "approve")
    elif body.action == "reject":
        db().update_record(rid, review_state="rejected", approved_by="user")
        db().log_edit(rid, "*", r["review_state"], "rejected", "reject")
    elif body.action == "reopen":
        db().update_record(rid, review_state="pending", approved_by=None)
        db().log_edit(rid, "*", r["review_state"], "pending", "reopen")
    else:
        err(400, "عملیات نامعتبر است.")
    pipeline.revalidate(db(), load_settings(), rid)
    return get_record(rid)


def _touch_dictionary(values: dict) -> None:
    """نام و خیابان رکورد تأییدشده یک بار دیگر «استفاده» شمرده می‌شوند (اولویت در راهنمایی مدل گفتار)."""
    import re as _re
    if values.get("engineer_name"):
        dictionary.touch_by_name(db(), values["engineer_name"], "engineer")
    if values.get("street"):
        street = _re.sub(r"^(?:خیابان|خیابون|بلوار|بولوار)\s+", "", _re.sub(r"\s*\d+.*$", "", values["street"])).strip()
        if street:
            dictionary.touch_by_name(db(), street, "street")


def _add_values_to_dictionary(values: dict, source: str) -> list[str]:
    added = []
    from .normalizer import strip_title
    if values.get("engineer_name"):
        _, bare = strip_title(values["engineer_name"])
        if bare:
            dictionary.add_entity(db(), bare, "engineer", source=source)
            added.append(bare)
    if values.get("project_name"):
        dictionary.add_entity(db(), values["project_name"], "project", source=source)
        added.append(values["project_name"])
    return added


class AcceptSuggestion(BaseModel):
    field: str
    value: str


@app.post("/api/records/{rid}/accept")
def accept_suggestion(rid: int, body: AcceptSuggestion):
    r = _get_record(rid)
    if r["exported_at"]:
        err(409, "این رکورد در اکسل ثبت شده است.")
    values = dict(r["values"])
    db().log_edit(rid, body.field, values.get(body.field, ""), body.value, "accept")
    learning.learn_from_edit(db(), body.field, values.get(body.field, ""), body.value)
    values[body.field] = body.value
    db().update_record(rid, values_json=values, manually_edited=1)
    pipeline.revalidate(db(), load_settings(), rid)
    return get_record(rid)


class DictFromField(BaseModel):
    field: str


_FIELD_ENTITY = {"engineer_name": "engineer", "project_name": "project", "street": "street", "neighborhood": "neighborhood",
                 "city": "city"}


@app.post("/api/records/{rid}/dictionary")
def record_to_dictionary(rid: int, body: DictFromField):
    r = _get_record(rid)
    etype = _FIELD_ENTITY.get(body.field)
    val = r["values"].get(body.field, "")
    if not etype or not val:
        err(400, "این فیلد قابل افزودن به واژه‌نامه نیست.")
    if body.field == "street":
        import re as _re
        val = _re.sub(r"^(?:خیابان|خیابون|بلوار|بولوار)\s+", "", _re.sub(r"\s*\d+.*$", "", val)).strip()
    dictionary.add_entity(db(), val, etype, source="بازبینی")
    db().log_edit(rid, body.field, "", val, "dictionary")
    pipeline.revalidate(db(), load_settings(), rid)
    return get_record(rid)


_UNDOABLE = ("edit", "accept", "approve", "reject", "reopen", "duplicate")


@app.post("/api/records/{rid}/undo")
def undo_last(rid: int):
    """بازگشت آخرین تغییرِ بازنگشته این رکورد (اصلاح فیلد، پذیرش پیشنهاد، تأیید، رد یا تصمیم تکرار)."""
    r = _get_record(rid)
    if r["exported_at"]:
        err(409, "این رکورد در اکسل ثبت شده است؛ ابتدا آن خروجی را بازگردانید.")
    e = db().one(f"SELECT * FROM record_edits WHERE record_id=? AND undone=0 AND action IN ({','.join('?' * len(_UNDOABLE))}) "
                 "ORDER BY id DESC LIMIT 1", (rid, *_UNDOABLE))
    if not e:
        err(404, "تغییری برای بازگشت وجود ندارد.")
    values = dict(r["values"])
    if e["action"] in ("edit", "accept"):
        if e["old_value"]:
            values[e["field"]] = e["old_value"]
        else:
            values.pop(e["field"], None)
        still_edited = db().one("SELECT COUNT(*) n FROM record_edits WHERE record_id=? AND undone=0 AND id!=? "
                                "AND action IN ('edit','accept')", (rid, e["id"]))["n"]
        db().update_record(rid, values_json=values, manually_edited=1 if still_edited else 0)
        learning.unlearn_edit(db(), e["field"], e["old_value"] or "", e["new_value"] or "")
    elif e["action"] in ("approve", "reject", "reopen"):
        prev = e["old_value"] or "pending"
        db().update_record(rid, review_state=prev, approved_by=None if prev == "pending" else "user")
    elif e["action"] == "duplicate":
        fields = {"duplicate_decision": e["old_value"] or None}
        if e["new_value"] == "skip":
            fields.update(review_state="pending", approved_by=None)
        db().update_record(rid, **fields)
    with db().tx() as c:
        c.execute("UPDATE record_edits SET undone=1 WHERE id=?", (e["id"],))
    pipeline.revalidate(db(), load_settings(), rid)
    return get_record(rid)


class DuplicateDecision(BaseModel):
    decision: str  # keep / skip


@app.post("/api/records/{rid}/duplicate")
def duplicate_decision(rid: int, body: DuplicateDecision):
    r = _get_record(rid)
    if body.decision == "skip":
        db().update_record(rid, duplicate_decision="skip", review_state="rejected", approved_by="user")
    elif body.decision == "keep":
        db().update_record(rid, duplicate_decision="keep")
    else:
        err(400, "تصمیم نامعتبر است.")
    db().log_edit(rid, "duplicate", r["duplicate_decision"] or "", body.decision, "duplicate")
    return get_record(rid)


@app.post("/api/records/reextract-all")
def reextract_all():
    if worker().running:
        err(409, "در حین پردازش ممکن نیست؛ پس از پایان صف دوباره تلاش کنید.")
    return pipeline.reextract_all(db(), load_settings())


@app.post("/api/records/revalidate-all")
def revalidate_all():
    ids = [r["id"] for r in db().q("SELECT id FROM records WHERE exported_at IS NULL")]
    for rid in ids:
        pipeline.revalidate(db(), load_settings(), rid)
    return {"count": len(ids)}


# ---------- واژه‌نامه ----------
@app.get("/api/dictionary")
def dict_list(type: str | None = None, q: str = ""):
    counts = {r["type"]: r["n"] for r in db().q("SELECT type, COUNT(*) n FROM entities GROUP BY type")}
    return {"entities": dictionary.list_entities(db(), type or None, q), "counts": counts}


class EntityIn(BaseModel):
    canonical: str
    type: str
    notes: str = ""


@app.post("/api/dictionary")
def dict_add(body: EntityIn):
    try:
        eid = dictionary.add_entity(db(), body.canonical, body.type, source="کاربر", notes=body.notes)
    except ValueError as e:
        err(400, str(e))
    return {"id": eid}


class AliasIn(BaseModel):
    alias: str


@app.post("/api/dictionary/{eid}/alias")
def dict_alias(eid: int, body: AliasIn):
    try:
        dictionary.add_alias(db(), eid, body.alias, source="کاربر")
    except ValueError as e:
        err(400, str(e))
    return {"ok": True}


class RenameIn(BaseModel):
    canonical: str


@app.patch("/api/dictionary/{eid}")
def dict_rename(eid: int, body: RenameIn):
    try:
        dictionary.rename_entity(db(), eid, body.canonical, source="کاربر")
    except ValueError as e:
        err(400, str(e))
    return {"ok": True}


@app.delete("/api/dictionary/{eid}")
def dict_delete(eid: int):
    dictionary.delete_entity(db(), eid)
    return {"ok": True}


@app.get("/api/dictionary/{eid}/history")
def dict_history(eid: int):
    return {"history": db().q("SELECT * FROM entity_changes WHERE entity_id=? ORDER BY id DESC", (eid,))}


@app.get("/api/corrections")
def corrections_list():
    return {"corrections": learning.list_corrections(db()), "groups": learning.GROUP_LABELS,
            "threshold": load_settings().learn_auto_threshold}


class CorrectionPatch(BaseModel):
    enabled: bool


@app.patch("/api/corrections/{cid}")
def corrections_patch(cid: int, body: CorrectionPatch):
    learning.set_enabled(db(), cid, body.enabled)
    return {"ok": True}


@app.delete("/api/corrections/{cid}")
def corrections_delete(cid: int):
    learning.delete_correction(db(), cid)
    return {"ok": True}


def _after_knowledge_change() -> dict:
    """پس از تغییر واژه‌نامه از فایل اکسل: ویس‌ها با واژگان تازه دوباره استخراج (اگر صف در جریان نباشد)
    و رکوردهای منتظر بازبینی دوباره سنجیده می‌شوند. رکوردهای اصلاح یا تأییدشده دستی دست نمی‌خورند."""
    res = {"reextracted": 0, "protected": 0}
    if not worker().running:
        res = pipeline.reextract_all(db(), load_settings())
    pending = [r["id"] for r in db().q("SELECT id FROM records WHERE review_state='pending' AND exported_at IS NULL")]
    for rid in pending:
        pipeline.revalidate(db(), load_settings(), rid)
    return {**res, "revalidated": len(pending), "total": db().one("SELECT COUNT(*) n FROM entities")["n"]}


_PROFILE_ROLES = {"engineer_name": "engineer", "address": "address", "project_name": "project"}


@app.post("/api/dictionary/seed-from-excel")
def dict_seed():
    """یادگیری از فایل اکسل شرکتِ نگاشت‌شده (همان «آموزش از اکسل» با ستون‌های نگاشت)."""
    prof = excel_mapping.load_profile(excel_mapping.COMPANY)
    if not prof:
        err(400, "ابتدا در بخش «خروجی اکسل» فایل شرکت و نگاشت ستون‌ها را مشخص کنید.")
    roles = {c: _PROFILE_ROLES[f] for c, f in prof["columns"].items() if f in _PROFILE_ROLES}
    if not roles:
        err(400, "ستون نام یا آدرس در نگاشت مشخص نشده است.")
    p = Path(prof["excel_path"])
    if not p.exists():
        err(404, "فایل اکسل شرکت پیدا نشد.")
    sha = file_sha256(p)
    zero = {"engineer": 0, "street": 0, "project": 0}
    src = knowledge.find_source_by_sha(db(), sha)
    if src:
        return {"added": zero, "rows": src["rows"], "already": True, "revalidated": 0,
                "total": db().one("SELECT COUNT(*) n FROM entities")["n"]}
    h = knowledge.harvest_file(p, prof["sheet"], prof["header_row"], roles)
    res = knowledge.import_harvest(db(), h, p.name, sha, prof["sheet"], roles)
    return {**_after_knowledge_change(), "added": res["added"], "rows": h.rows, "already": False}


# ---------- آموزش از فایل اکسل ----------
KB_DIR = DATA_DIR / "tmp" / "knowledge"
KB_MAX_BYTES = 50 * 1024 * 1024
_KB_TOKEN = re.compile(r"^[0-9a-f]{32}\.xls[xm]$")


def _kb_path(token: str) -> Path:
    if not _KB_TOKEN.match(token or ""):
        err(400, "شناسه فایل نامعتبر است.")
    p = KB_DIR / token
    if not p.exists():
        err(404, "فایل بارگذاری‌شده پیدا نشد؛ دوباره انتخابش کنید.")
    return p


def _kb_roles(columns: dict[str, str]) -> dict[str, str]:
    roles = {c: r for c, r in (columns or {}).items() if r in knowledge.ROLES and r}
    if len(set(roles.values())) != len(roles):
        err(400, "هر نقش (نام، آدرس، پروژه) فقط به یک ستون داده می‌شود.")
    if not roles:
        err(400, "دست‌کم ستون نام یا آدرس را مشخص کنید.")
    return roles


def _kb_preview(p: Path, sheet: str, header_row: int, roles: dict[str, str]) -> dict:
    return knowledge.preview(db(), knowledge.harvest_file(p, sheet, header_row, roles)) if roles else {}


@app.post("/api/knowledge/analyze")
async def knowledge_analyze(files: list[UploadFile] = File(...)):
    """بارگذاری فایل‌های اکسل و پیشنهاد نقش ستون‌ها با پیش‌نمایش آنچه یاد گرفته می‌شود (هنوز چیزی ثبت نمی‌شود)."""
    KB_DIR.mkdir(parents=True, exist_ok=True)
    for old in KB_DIR.iterdir():
        if time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    out = []
    for f in files:
        name = Path(f.filename or "file.xlsx").name
        ext = Path(name).suffix.lower()
        if ext not in (".xlsx", ".xlsm"):
            out.append({"name": name, "error": "فقط فایل XLSX یا XLSM (فایل XLS قدیمی را در Excel با قالب XLSX ذخیره کنید)."})
            continue
        token = f"{uuid.uuid4().hex}{ext}"
        path = KB_DIR / token
        size = 0
        with open(path, "wb") as fh:
            while chunk := await f.read(1 << 20):
                size += len(chunk)
                if size > KB_MAX_BYTES:
                    break
                fh.write(chunk)
        if size > KB_MAX_BYTES:
            path.unlink(missing_ok=True)
            out.append({"name": name, "error": "حجم فایل بیش از ۵۰ مگابایت است."})
            continue
        try:
            info = knowledge.analyze_workbook(path)
        except Exception:
            log.exception("knowledge analyze failed")
            path.unlink(missing_ok=True)
            out.append({"name": name, "error": "فایل اکسل باز نشد (خراب یا رمزدار است)."})
            continue
        sha = file_sha256(path)
        item = {"name": name, "token": token, "sha256": sha, "already": knowledge.find_source_by_sha(db(), sha), **info}
        main = next((s for s in info["sheets"] if s["name"] == info["sheet"]), None)
        item["preview"] = _kb_preview(path, main["name"], main["header_row"], main["roles"]) if main else {}
        out.append(item)
    return {"files": out, "roles": knowledge.ROLES}


class KbChoice(BaseModel):
    token: str
    sheet: str
    header_row: int
    columns: dict[str, str]
    name: str = ""


@app.post("/api/knowledge/preview")
def knowledge_preview(body: KbChoice):
    p = _kb_path(body.token)
    return {"preview": _kb_preview(p, body.sheet, body.header_row, _kb_roles(body.columns))}


@app.post("/api/knowledge/import")
def knowledge_import(body: KbChoice):
    p = _kb_path(body.token)
    roles = _kb_roles(body.columns)
    sha = file_sha256(p)
    if knowledge.find_source_by_sha(db(), sha):
        err(409, "این فایل قبلاً یاد گرفته شده است.")
    h = knowledge.harvest_file(p, body.sheet, body.header_row, roles)
    res = knowledge.import_harvest(db(), h, Path(body.name or body.token).name, sha, body.sheet, roles)
    p.unlink(missing_ok=True)
    db().log_event(f"آموزش از اکسل «{body.name}»: {sum(res['added'].values())} نام و خیابان تازه از {h.rows} ردیف.")
    return {**_after_knowledge_change(), **res, "rows": h.rows}


@app.get("/api/knowledge/sources")
def knowledge_sources():
    return {"sources": knowledge.list_sources(db())}


@app.delete("/api/knowledge/sources/{sid}")
def knowledge_remove(sid: int):
    try:
        res = knowledge.remove_source(db(), sid)
    except KeyError:
        err(404, "این منبع پیدا نشد.")
    return {**_after_knowledge_change(), **res}


# ---------- اکسل ----------
class PathIn(BaseModel):
    path: str


@app.post("/api/excel/inspect")
def excel_inspect(body: PathIn):
    p = Path(body.path.strip().strip('"'))
    rep = inspect_workbook(p)
    if not rep.get("exists"):
        err(404, "فایل پیدا نشد.")
    prof = excel_mapping.load_profile(excel_mapping.COMPANY)
    if prof and Path(prof.get("excel_path", "")) == p:
        suggested = prof
    else:
        sheets = rep.get("sheets", [])
        main = max(sheets, key=lambda s: s["data_rows"]) if sheets else None
        suggested = excel_mapping.new_profile(excel_mapping.COMPANY, str(p), main["name"], main["header_row"],
                                              main["headers"]) if main else None
    return {"report": rep, "profile": suggested}


@app.get("/api/excel/profile")
def excel_profile():
    return {"profile": excel_mapping.load_profile(excel_mapping.COMPANY)}


@app.put("/api/excel/profile")
def excel_profile_save(profile: dict):
    p = Path(profile.get("excel_path", ""))
    if not p.exists():
        err(400, "فایل اکسل این نگاشت پیدا نشد.")
    rep = inspect_workbook(p)
    sheet = next((s for s in rep.get("sheets", []) if s["name"] == profile.get("sheet")), None)
    if not sheet:
        err(400, "شیت انتخاب‌شده در فایل نیست.")
    hr = int(profile.get("header_row") or sheet["header_row"])
    import openpyxl

    from .excel_reader import header_map
    wb = openpyxl.load_workbook(p)
    try:
        headers = header_map(wb[sheet["name"]], hr)
    finally:
        wb.close()
    fields_allowed = {k for k, _, _ in FIELD_DEFS} | set(COMPUTED_FIELDS) | {"followup"}
    columns = {c: f for c, f in (profile.get("columns") or {}).items() if f in fields_allowed and c in headers}
    if not columns:
        err(400, "دست‌کم یک ستون باید به یک فیلد نگاشت شود.")
    if len(set(columns.values())) != len(columns):
        err(400, "یک فیلد به بیش از یک ستون نگاشت شده است.")
    clean = {
        "name": excel_mapping.COMPANY,
        "excel_path": str(p),
        "sheet": sheet["name"],
        "header_row": hr,
        "headers": headers,
        "columns": columns,
        "protected": [c for c in profile.get("protected", []) if c in headers and c not in columns],
        "policy": {**excel_mapping.DEFAULT_POLICY, **(profile.get("policy") or {})},
        "confirmed": True,
        "confirmed_at": now(),
    }
    if not clean["policy"].get("text_style"):
        # سبک نوشتن (جداکننده، نوع رقم) از ردیف‌های موجود همان فایل استخراج می‌شود
        style_cols = {c: f for c, f in columns.items() if f in ("address", "notes_composed", "technical_summary")}
        rows = read_rows(p, sheet["name"], hr, style_cols, raw=True) if style_cols else []
        samples = [r.get(f, "") for r in rows for f in style_cols.values()]
        clean["policy"]["text_style"] = infer_style(samples)
    excel_mapping.save_profile(clean)
    save_settings({"last_excel_path": str(p)})
    _excel_cache["key"] = None
    return {"profile": clean}


def _approved_records() -> list[dict]:
    rows = db().list_records("r.review_state='approved' AND r.exported_at IS NULL")
    for r in rows:
        t = db().one("SELECT processed_text FROM transcripts WHERE audio_id=?", (r["audio_id"],))
        r["transcript"] = (t or {}).get("processed_text", "")
    return rows


@app.post("/api/excel/preview")
def excel_preview():
    prof = _confirmed_profile()
    recs = _approved_records()
    pending = db().one("SELECT COUNT(*) n FROM records WHERE review_state='pending' AND exported_at IS NULL")["n"]
    if not recs:
        return {"rows": [], "pending": pending, "profile": prof, "lock": lock_status(Path(prof["excel_path"]))}
    try:
        plan = preview(prof, recs)
    except ExcelWriteError as e:
        err(400, str(e))
    names = {r["id"]: r["original_name"] for r in recs}
    for p in plan["rows"]:
        p["original_name"] = names.get(p["record_id"], "")
    plan.update({"pending": pending, "profile": prof, "lock": lock_status(Path(prof["excel_path"]))})
    return plan


class ExportIn(BaseModel):
    record_ids: list[int] | None = None


_export_lock = threading.Lock()


def _confirmed_profile() -> dict:
    prof = _write_profile(create=True)
    if not prof or not prof.get("confirmed"):
        err(400, "ابتدا نگاشت ستون‌ها را بررسی و ذخیره کنید.")
    return prof


def _export(prof: dict, record_ids: list[int] | None = None) -> dict:
    """ساخت خروجی (روی کپی) و ثبت آن؛ باید زیر _export_lock صدا زده شود."""
    import json
    recs = _approved_records()
    if record_ids:
        recs = [r for r in recs if r["id"] in set(record_ids)]
    try:
        rep = write_export(prof, recs)
    except ExcelWriteError as e:
        db().log_event(f"ثبت در اکسل ناموفق: {e}", "error")
        err(400, str(e))
    rep["output_sha"] = file_sha256(Path(rep["output_path"]))
    with db().tx() as c:
        cur = c.execute(
            """INSERT INTO exports(created_at, target_path, output_path, backup_path, profile, rows_written,
               first_row, last_row, record_ids_json, status, report_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (now(), rep["target_path"], rep["output_path"], rep["backup_path"], prof["name"], len(rep["rows"]),
             rep["first_row"], rep["last_row"], json.dumps([x["record_id"] for x in rep["rows"]]), "created",
             json.dumps(rep, ensure_ascii=False)))
        eid = cur.lastrowid
        for x in rep["rows"]:
            c.execute("UPDATE records SET exported_at=?, export_id=?, export_row=? WHERE id=?",
                      (now(), eid, x["row"], x["record_id"]))
    rep["export_id"] = eid
    return rep


@app.post("/api/excel/export")
def excel_export(body: ExportIn):
    prof = _confirmed_profile()
    with _export_lock:
        return _export(prof, body.record_ids)


@app.post("/api/excel/commit")
def excel_commit(body: ExportIn):
    """ثبت یک‌مرحله‌ای: نوشتن روی کپی، بررسی، و جایگزینی فایل اصلی (با پشتیبانی که پیش از نوشتن گرفته شده).

    اگر جایگزینی ممکن نباشد (مثلاً فایل در Excel باز شد)، خروجی ساخته‌شده می‌ماند و بعداً قابل اعمال است.
    """
    prof = _confirmed_profile()
    lock = lock_status(Path(prof["excel_path"]))
    if lock["write_blocked"] or lock["owner_file"]:
        err(409, lock["message"] or "فایل اکسل شرکت باز است؛ آن را ببندید و دوباره تلاش کنید.")
    with _export_lock:
        rep = _export(prof, body.record_ids)
        try:
            replace_original(rep["output_path"], rep["target_path"], rep["target_sha"], backup_path=rep["backup_path"])
        except ExcelWriteError as e:
            rep["applied"] = False
            rep["message"] = f"ردیف‌ها در یک کپی ثبت شدند ولی فایل اصلی به‌روز نشد: {e}"
            return rep
        with db().tx() as c:
            c.execute("UPDATE exports SET replaced_original_at=?, status='applied' WHERE id=?", (now(), rep["export_id"]))
        rep["applied"] = True
        return rep


# ---------- قالب‌های خروجی اکسل ----------
_SAMPLE_VALUES = [
    {"visit_date": "1405/07/28", "engineer_name": "مهندس رجبی", "phone": "09151234567", "address": "سجادیه 58 ، قطعه دوم",
     "floors": "7", "structure_type": "فلز", "executed": "3 سقف اجرا شده", "notes": "شماره را نگهبان داد"},
    {"visit_date": "1405/07/28", "engineer_name": "مهندس کاظمی", "phone": "09371234567", "address": "امامت 60 ، پلاک 18",
     "floors": "6", "structure_type": "بتون", "stage": "تازه استارت خورده"},
    {"visit_date": "1405/07/29", "engineer_name": "آقای احمدی", "phone": "09121234567\n09351234567", "address": "فلاحی 34",
     "floors": "5", "structure_type": "فلز", "followup_action": "قرار شد دوشنبه زنگ بزنیم", "followup_date": "1405/08/03"},
]


def _template_info(name: str, prof: dict, active: str) -> dict:
    new = prof.get("mode") == "new"
    return {"name": name, "title": prof.get("title") or ("فایل شرکت" if not new else name), "mode": prof.get("mode", "append"),
            "active": name == active, "target": excel_template.target_path(prof).name if new else Path(prof.get("excel_path", "")).name}


def _sample_records() -> list[dict]:
    """چند رکورد واقعی اخیر برای پیش‌نمایش (اگر نباشد، نمونه ساختگی)."""
    rows = db().list_records("r.review_state!='rejected'")[-4:]
    return [{"id": r["id"], "values": r["values"], "original_name": r["original_name"], "transcript": "",
             "validation": r["validation"]} for r in rows] or \
        [{"id": i, "values": v, "original_name": "sample.ogg", "transcript": "", "validation": {}} for i, v in enumerate(_SAMPLE_VALUES)]


def _clean_template(body: dict) -> dict:
    try:
        return excel_template.clean(body)
    except ValueError as e:
        err(400, str(e))


@app.get("/api/templates")
def templates_list():
    active = load_settings().active_profile
    items = [_template_info(n, p, active) for n in excel_mapping.list_profiles() if (p := excel_mapping.load_profile(n))]
    return {"templates": items, "active": active, "fields": [{"key": k, "label": excel_template.field_label(k)}
            for k in [*(k for k, _, _ in FIELD_DEFS), *COMPUTED_FIELDS, "followup", *excel_template.EXTRA_FIELDS]],
            "presets": {k: {"label": v[0], "fill": v[1], "color": v[2], "zebra": v[3]} for k, v in excel_template.PRESETS.items()},
            "fonts": excel_template.installed_fonts(), "aligns": excel_template.ALIGNS}


@app.get("/api/templates/{name}")
def template_get(name: str):
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "قالب پیدا نشد.")
    return {"template": prof, "target": str(excel_template.target_path(prof)) if prof.get("mode") == "new" else prof.get("excel_path", "")}


class TemplateNew(BaseModel):
    title: str


@app.post("/api/templates")
def template_create(body: TemplateNew):
    title = body.title.strip()[:60]
    if not title:
        err(400, "نام قالب را بنویسید.")
    name = "t_" + uuid.uuid4().hex[:8]
    folder = Path.home() / "Documents"
    tpl = excel_template.new_template(name, title, str(folder if folder.is_dir() else Path.home()))
    excel_mapping.save_profile(tpl)
    return {"name": name}


@app.put("/api/templates/{name}")
def template_save(name: str, body: dict):
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "قالب پیدا نشد.")
    if prof.get("mode") != "new":
        # فایل شرکت: فقط قالب مقادیر؛ ستون‌ها و ظاهر فایل موجود دست نمی‌خورد
        prof["policy"] = {**prof.get("policy", {}), **{k: v for k, v in (body.get("policy") or {}).items()
                                                      if k in excel_mapping.VALUE_FORMAT_KEYS}}
        excel_mapping.save_profile(prof)
        return {"template": prof}
    tpl = _clean_template({**body, "name": name})
    if not Path(tpl["output"]["folder"]).is_dir():
        err(400, "پوشه خروجی پیدا نشد.")
    tpl["policy"] = {k: v for k, v in (tpl.get("policy") or {}).items() if k in excel_mapping.VALUE_FORMAT_KEYS}
    warning = ""
    target = excel_template.target_path(tpl)
    if target.exists():
        old = excel_template.writer_profile(prof, create=False)["headers"]
        if old != excel_template.writer_profile(tpl, create=False)["headers"]:
            warning = (f"فایل «{target.name}» با ستون‌های قبلی ساخته شده است؛ برای ثبت با ستون‌های جدید، "
                       "نام فایل خروجی را عوض کنید تا فایل تازه ساخته شود.")
    excel_mapping.save_profile(tpl)
    return {"template": tpl, "warning": warning}


@app.delete("/api/templates/{name}")
def template_delete(name: str):
    if name == excel_mapping.COMPANY:
        err(400, "قالب فایل شرکت حذف نمی‌شود.")
    if name == load_settings().active_profile:
        err(400, "قالب فعال حذف نمی‌شود؛ اول قالب دیگری را فعال کنید.")
    excel_mapping.delete_profile(name)
    return {"ok": True}


@app.post("/api/templates/{name}/activate")
def template_activate(name: str):
    if not excel_mapping.load_profile(name):
        err(404, "قالب پیدا نشد.")
    save_settings({"active_profile": name})
    _excel_cache["key"] = None
    return {"ok": True}


def _template_rows(body: dict) -> tuple[dict, list[list[str]]]:
    """مقدار ستون‌ها برای چند رکورد نمونه، با همان قالب‌بندی مقادیری که در ثبت به کار می‌رود."""
    tpl = _clean_template(body)
    prof = excel_template.writer_profile(tpl, create=False)
    cols = list(prof["headers"])
    rows = []
    for i, rec in enumerate(_sample_records(), start=1):
        cells = excel_mapping.cell_values(prof, rec)
        rows.append([str(i) if prof["columns"][c] == "row_number" else cells.get(c, "") for c in cols])
    return tpl, rows


@app.post("/api/templates/preview")
def template_preview(body: dict):
    tpl, rows = _template_rows(body)
    return {"headers": [c["title"] for c in tpl["columns_list"]], "rows": rows}


@app.post("/api/templates/sample")
def template_sample(body: dict):
    tpl, rows = _template_rows(body)
    data = excel_template.build_sample(tpl, rows)
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=sample.xlsx"})


@app.get("/api/exports")
def exports():
    return {"exports": db().q("SELECT id, created_at, target_path, output_path, backup_path, rows_written, first_row, "
                              "last_row, status, replaced_original_at FROM exports ORDER BY id DESC")}


def _get_export(eid: int) -> dict:
    e = db().one("SELECT * FROM exports WHERE id=?", (eid,))
    if not e:
        err(404, "خروجی پیدا نشد.")
    return e


@app.post("/api/exports/{eid}/replace-original")
def export_replace(eid: int):
    import json
    e = _get_export(eid)
    if e["status"] != "created":
        err(409, "این خروجی قابل جایگزینی نیست.")
    rep = json.loads(e["report_json"])
    try:
        res = replace_original(e["output_path"], e["target_path"], rep["target_sha"])
    except ExcelWriteError as ex:
        err(409, str(ex))
    with db().tx() as c:
        c.execute("UPDATE exports SET replaced_original_at=?, status='applied' WHERE id=?", (now(), eid))
    return res


@app.post("/api/exports/{eid}/undo")
def export_undo(eid: int):
    """بازگشت یک ثبت: رکوردها به «آماده ثبت» برمی‌گردند و اگر فایل اصلی پس از ثبت دست نخورده باشد،
    به نسخه پیش از ثبت برگردانده می‌شود."""
    import json
    e = _get_export(eid)
    if e["status"] == "undone":
        err(409, "این خروجی قبلاً بازگردانده شده است.")
    restored = False
    if e["status"] == "applied":
        rep = json.loads(e["report_json"] or "{}")
        target, backup = Path(e["target_path"]), Path(e["backup_path"])
        written_sha = rep.get("output_sha") or (file_sha256(Path(e["output_path"])) if Path(e["output_path"]).exists() else "")
        if target.exists() and backup.exists() and written_sha and file_sha256(target) == written_sha:
            try:
                replace_original(str(backup), str(target), written_sha)
            except ExcelWriteError as ex:
                err(409, str(ex))
            restored = True
    with db().tx() as c:
        c.execute("UPDATE records SET exported_at=NULL, export_id=NULL, export_row=NULL WHERE export_id=?", (eid,))
        c.execute("UPDATE exports SET status='undone' WHERE id=?", (eid,))
    msg = "رکوردها به حالت «آماده ثبت» برگشتند."
    if restored:
        msg = "ثبت برگشت خورد: فایل اکسل به حالت پیش از ثبت برگشت و رکوردها دوباره آماده ثبت‌اند."
    elif e["replaced_original_at"]:
        msg += " فایل اصلی پس از ثبت تغییر کرده بود و دست نخورد؛ نسخه پیش از ثبت در پوشه backups هست."
    return {"ok": True, "restored": restored, "message": msg}


@app.get("/api/exports/{eid}/download")
def export_download(eid: int):
    e = _get_export(eid)
    p = Path(e["output_path"])
    if not p.exists():
        err(404, "فایل خروجی پیدا نشد.")
    return FileResponse(p, filename=p.name)


class OpenIn(BaseModel):
    path: str


@app.post("/api/open-folder")
def open_folder(body: OpenIn):
    p = Path(body.path)
    target = p if p.is_dir() else p.parent
    allowed = [DATA_DIR.resolve()]
    prof = _write_profile()
    if prof:
        allowed.append(Path(prof["excel_path"]).resolve().parent)
    if not any(str(target.resolve()).startswith(str(a)) for a in allowed):
        err(403, "باز کردن این مسیر مجاز نیست.")
    if hasattr(os, "startfile"):
        os.startfile(str(target))  # noqa: S606 - فقط پوشه‌های برنامه
    return {"ok": True}


# ---------- مرورگر فایل محلی (برای انتخاب پوشه ویس یا فایل اکسل) ----------
@app.get("/api/fs")
def fs_list(path: str = "", kind: str = "audio"):
    if not path:
        home = Path.home()
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if os.name == "nt" else ["/"]
        quick = [str(p) for p in (home / "Desktop", home / "Documents", home / "Downloads", home) if p.exists()]
        return {"path": "", "parent": None, "dirs": [{"name": q, "path": q} for q in quick + drives], "files": []}
    p = Path(path)
    if not p.is_dir():
        err(400, "پوشه پیدا نشد.")
    exts = SUPPORTED_AUDIO_EXTENSIONS if kind == "audio" else {".xlsx", ".xlsm"}
    dirs, files = [], []
    try:
        for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if c.name.startswith((".", "~$", "$")):
                continue
            try:
                if c.is_dir():
                    dirs.append({"name": c.name, "path": str(c)})
                elif c.suffix.lower() in exts:
                    files.append({"name": c.name, "path": str(c), "size": c.stat().st_size})
            except OSError:
                continue
    except PermissionError:
        err(403, "دسترسی به این پوشه وجود ندارد.")
    parent = str(p.parent) if p.parent != p else ""
    return {"path": str(p), "parent": parent, "dirs": dirs, "files": files}


# ---------- گزارش‌ها ----------
def _xlsx_response(wb, name: str):
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    from urllib.parse import quote
    return StreamingResponse(bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


def _report_sheet(wb, title: str, headers: list[str], rows: list[list]):
    from openpyxl.styles import Font, PatternFill
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8EEF7")
    from .excel_writer import safe_set
    for row in rows:
        ws.append([None] * len(row))
        for i, v in enumerate(row, start=1):
            safe_set(ws.cell(ws.max_row, i), "" if v is None else v)
    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[openpyxl_col(i)].width = 28
    return ws


def openpyxl_col(i: int) -> str:
    from openpyxl.utils import get_column_letter
    return get_column_letter(i)


@app.get("/api/report/errors.xlsx")
def report_errors():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    files = db().q("SELECT original_name, status, error, attempts, updated_at FROM audio_files WHERE error IS NOT NULL OR status='failed'")
    _report_sheet(wb, "فایل‌های ناموفق", ["نام فایل", "وضعیت", "خطا", "تعداد تلاش", "زمان"],
                  [[f["original_name"], f["status"], f["error"], f["attempts"], f["updated_at"]] for f in files])
    recs = db().list_records("r.review_state!='approved' OR r.status!='ready'")
    rows = []
    for r in recs:
        for k, fc in r["validation"].get("fields", {}).items():
            if fc["status"] != "valid":
                rows.append([r["original_name"], r["id"], FIELD_LABELS.get(k, k), r["values"].get(k, ""), fc["status"],
                             " ؛ ".join(fc["reasons"])])
    _report_sheet(wb, "هشدارهای رکوردها", ["فایل", "شناسه رکورد", "فیلد", "مقدار", "وضعیت", "علت"], rows)
    events = db().q("SELECT at, level, audio_id, message FROM events ORDER BY id DESC LIMIT 500")
    _report_sheet(wb, "رخدادها", ["زمان", "سطح", "شناسه فایل", "پیام"],
                  [[e["at"], e["level"], e["audio_id"], e["message"]] for e in events])
    return _xlsx_response(wb, f"گزارش-خطاها-{datetime.now():%Y%m%d-%H%M}.xlsx")


@app.get("/api/report/records.xlsx")
def report_records():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    keys = [k for k, _, _ in FIELD_DEFS]
    recs = db().list_records()
    rows = []
    for r in recs:
        t = db().one("SELECT raw_text, processed_text FROM transcripts WHERE audio_id=?", (r["audio_id"],)) or {}
        rows.append([r["id"], r["original_name"], r["status"], r["review_state"], r["exported_at"] or "",
                     *[r["values"].get(k, "") for k in keys], " ؛ ".join(r["validation"].get("reasons", [])),
                     t.get("raw_text", ""), t.get("processed_text", "")])
    _report_sheet(wb, "رکوردها", ["شناسه", "فایل", "وضعیت", "بازبینی", "ثبت در اکسل", *[FIELD_LABELS[k] for k in keys],
                                  "علت‌ها", "متن خام ویس", "متن پردازش‌شده"], rows)
    return _xlsx_response(wb, f"گزارش-کامل-{datetime.now():%Y%m%d-%H%M}.xlsx")


# ---------- تنظیمات و مدل ----------
@app.get("/api/settings")
def get_settings():
    from dataclasses import asdict
    try:
        import psutil
        ram = round(psutil.virtual_memory().total / 1e9, 1)
        rss = round(psutil.Process().memory_info().rss / 1e6)
    except Exception:
        ram, rss = None, None
    perf = db().one("SELECT COUNT(*) n, AVG(processing_seconds) avg_s, MAX(peak_rss_mb) peak, AVG(duration) avg_d "
                    "FROM audio_files WHERE status='done'")
    return {
        "settings": asdict(load_settings()),
        "models": AVAILABLE_MODELS,
        "installed_models": installed_models(),
        "download": _download_state,
        "system": {"ram_gb": ram, "process_mb": rss, "cpu_count": os.cpu_count(), "data_dir": str(DATA_DIR),
                   "models_dir": str(MODELS_DIR)},
        "performance": perf,
    }


@app.put("/api/settings")
def put_settings(updates: dict):
    allowed = {"model_name", "compute_type", "cpu_threads", "beam_size", "vad_filter", "initial_prompt",
               "use_dictionary_hotwords", "hotwords_limit", "review_spoken_phones", "learn_auto_threshold", "kb_auto_spelling","model_idle_minutes", "required_fields", "default_area_code", "default_city",
               "similarity_suggest", "min_duration_sec", "open_browser", "inbox_dir"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    if "model_name" in clean and clean["model_name"] not in AVAILABLE_MODELS:
        err(400, "مدل نامعتبر است.")
    if "inbox_dir" in clean:
        clean["inbox_dir"] = str(clean["inbox_dir"] or "").strip().strip('"')
        if clean["inbox_dir"] and not Path(clean["inbox_dir"]).is_dir():
            err(400, "پوشه ورودی پیدا نشد.")
        if clean["inbox_dir"] != load_settings().inbox_dir:
            db().set_meta("inbox_since", str(time.time()))  # ویس‌های قدیمی پوشه برداشته نمی‌شوند
    if worker().running and ("model_name" in clean or "compute_type" in clean):
        err(409, "در حین پردازش نمی‌توان مدل را تغییر داد.")
    s = save_settings(clean)
    from dataclasses import asdict
    return {"settings": asdict(s)}


class ModelIn(BaseModel):
    name: str


@app.post("/api/models/download")
def model_download(body: ModelIn):
    """دریافت مدل (تنها کاری که اینترنت می‌خواهد و فقط با دستور کاربر انجام می‌شود)."""
    if body.name not in AVAILABLE_MODELS:
        err(400, "مدل نامعتبر است.")
    if _download_state["status"] == "running":
        err(409, "دریافت مدل دیگری در جریان است.")

    def run():
        from .model_download import download_model
        _download_state.update(name=body.name, status="running", message="در حال دریافت...")
        try:
            download_model(body.name)
            _download_state.update(status="done", message="مدل با موفقیت دریافت شد.")
        except Exception as e:
            _download_state.update(status="error", message=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


# ---------- نگهداری ----------
class PurgeIn(BaseModel):
    scope: str = "exported"  # exported / done


@app.post("/api/maintenance/purge-audio")
def purge_audio(body: PurgeIn):
    if body.scope == "exported":
        rows = db().q("""SELECT a.id, a.stored_name FROM audio_files a WHERE a.audio_deleted=0 AND a.status='done'
                         AND NOT EXISTS (SELECT 1 FROM records r WHERE r.audio_id=a.id AND r.exported_at IS NULL
                                         AND r.review_state!='rejected')""")
    elif body.scope == "done":
        rows = db().q("SELECT id, stored_name FROM audio_files WHERE audio_deleted=0 AND status='done'")
    else:
        err(400, "دامنه نامعتبر است.")
    for r in rows:
        if r["stored_name"]:
            (DATA_DIR / "uploads" / r["stored_name"]).unlink(missing_ok=True)
        db().set_audio(r["id"], audio_deleted=1)
    for p in (DATA_DIR / "tmp").glob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)
    return {"deleted": len(rows)}


@app.get("/api/backups")
def backups_list():
    return {"backups": backup.list_backups(), "dir": str(backup.backup_dir())}


@app.post("/api/backups")
def backups_create():
    return backup.create_backup(db(), "manual")


@app.post("/api/backups/{name}/restore")
def backups_restore(name: str):
    if worker().running:
        err(409, "در حین پردازش ویس‌ها نمی‌توان بازگردانی کرد؛ ابتدا پردازش را متوقف کنید.")
    try:
        res = backup.restore_backup(db(), name)
    except backup.BackupError as e:
        err(400, str(e))
    _excel_cache["key"] = None
    db().log_event(f"اطلاعات از پشتیبان «{name}» بازگردانده شد (پشتیبان وضعیت قبلی: {res['safety_backup']}).", "warning")
    return res


@app.get("/api/backups/{name}/download")
def backups_download(name: str):
    try:
        p = backup.backup_path(name)
    except backup.BackupError as e:
        err(404, str(e))
    return FileResponse(p, filename=p.name)


@app.get("/api/update")
def update_info():
    return {"version": __version__, "supported": updater.current_runtime_id() is not None,
            "staged": updater.staged_info()}


@app.post("/api/update")
async def update_upload(file: UploadFile = File(...)):
    """بسته به‌روزرسانی سبک را اعتبارسنجی و برای اعمال در اجرای بعدی آماده می‌کند."""
    tmp = DATA_DIR / "tmp" / f"update-{uuid.uuid4().hex}.zip"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = 0
        with open(tmp, "wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > updater.MAX_UPDATE_BYTES:
                    err(400, "حجم فایل برای بسته به‌روزرسانی بیش از حد است.")
                out.write(chunk)
        try:
            res = updater.stage_update(tmp)
        except updater.UpdateError as e:
            err(400, str(e))
    finally:
        tmp.unlink(missing_ok=True)
        await file.close()
    db().log_event(f"به‌روزرسانی نسخه {res['version']} آماده شد؛ با اجرای دوباره برنامه اعمال می‌شود.")
    return res


@app.delete("/api/update")
def update_cancel():
    updater.cancel_staged()
    return {"ok": True}


@app.get("/api/events")
def events():
    return {"events": db().q("SELECT * FROM events ORDER BY id DESC LIMIT 100")}


# ---------- فایل‌های رابط ----------
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # pragma: no cover
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": f"خطای داخلی: {type(exc).__name__}"})
