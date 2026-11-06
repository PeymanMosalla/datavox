"""سرور محلی (FastAPI) و API رابط کاربری.

فقط روی 127.0.0.1 گوش می‌دهد؛ هیچ داده‌ای به بیرون از رایانه ارسال نمی‌شود.
"""
from __future__ import annotations

import io
import os
import re
import secrets
import shutil
import string
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (__version__, backup, dictionary, excel_mapping, excel_template, knowledge, lan, learning, licensing,
               pipeline, updater)
from .audio_processor import MAX_AUDIO_BYTES, is_supported, looks_like_audio
from .config import (AVAILABLE_MODELS, DATA_DIR, MODELS_DIR, SAMPLES_DIR, SUPPORTED_AUDIO_EXTENSIONS, WEB_DIR,
                     ensure_dirs, load_settings, save_settings)
from .database import Database, get_db, now
from .dates_fa import date_from_filename, format_jalali, from_gregorian, parse_jalali, today_jalali
from .deduplicator import file_sha256
from .excel_reader import check_package, inspect_workbook, lock_status, read_rows
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


app = FastAPI(title="DataVox", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)


_last_request = {"t": time.time()}
IDLE_EXIT_SECONDS = 15 * 60
_pin_limiter = lan.FailureLimiter()


# کلید محرمانه هر بار اجرا: فقط در صفحه خود برنامه گذاشته می‌شود. هر فرمانی که چیزی را تغییر می‌دهد باید آن را
# همراه داشته باشد، پس صفحه‌های سایت‌های دیگر (حتی در همین مرورگر) نمی‌توانند به برنامه فرمان بدهند.
API_TOKEN = secrets.token_urlsafe(32)
TOKEN_HEADER = "x-v2x-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1", "[::1]"}


def auth_headers() -> dict[str, str]:
    """برای آزمون‌ها و ابزارهای داخلی."""
    return {TOKEN_HEADER: API_TOKEN}


def _host_name(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v.startswith("["):  # «[::1]:8765»
        return v[: v.find("]") + 1] if "]" in v else v
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


_lan_ips = {"at": 0.0, "ips": set()}


def _allowed_host(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    s = load_settings()
    if not (s.lan_enabled and s.lan_pin):
        return False
    if time.time() - _lan_ips["at"] > 30:  # نشانی شبکه این رایانه (با حافظه کوتاه، نه در هر درخواست)
        _lan_ips.update(at=time.time(), ips=set(lan.lan_addresses()))
    return host in _lan_ips["ips"]


@app.middleware("http")
async def _security_guard(request, call_next):
    """سه لایه در برابر صفحه‌های سایت‌های دیگر:
    ۱) نام میزبان باید همین رایانه باشد (جلوگیری از خواندن داده با دامنه‌ای که به 127.0.0.1 اشاره می‌کند)؛
    ۲) درخواست از صفحه یک مبدأ دیگر پذیرفته نمی‌شود؛
    ۳) فرمان‌های تغییردهنده کلید محرمانه این اجرا را لازم دارند (صفحه ارسال گوشی با رمز خودش محافظت می‌شود).
    """
    host = _host_name(request.headers.get("host"))
    if not _allowed_host(host):
        return JSONResponse(status_code=403, content={"detail": "درخواست نامعتبر."})
    origin = request.headers.get("origin")
    if origin and origin != "null" and _host_name(origin.split("://", 1)[-1]) != host:
        return JSONResponse(status_code=403, content={"detail": "درخواست از صفحه دیگری پذیرفته نمی‌شود."})
    path = request.url.path
    # حتی درخواست GET از سایت دیگر (مثلاً <img src=".../api/fs?path=\\سرور-مهاجم\x">) اجرا نشود؛ ویندوز با
    # چنین مسیری به سرور مهاجم وصل می‌شود و هش رمز کاربر را می‌فرستد. فقط باز کردن خود صفحه برنامه مجاز است.
    if (request.headers.get("sec-fetch-site") in ("cross-site", "same-site")
            and not (request.headers.get("sec-fetch-mode") == "navigate" and path in _APP_PAGES)):
        return JSONResponse(status_code=403, content={"detail": "درخواست از صفحه دیگری پذیرفته نمی‌شود."})
    try:
        too_big = int(request.headers.get("content-length") or 0) > MAX_REQUEST_BYTES
    except ValueError:
        too_big = True
    if too_big:  # پیش از آنکه بدنه درخواست روی دیسک موقت نوشته شود
        return JSONResponse(status_code=413, content={"detail": "حجم ارسال بیش از حد مجاز است؛ فایل‌ها را در چند نوبت بفرستید."})
    if (request.method not in _SAFE_METHODS and path.startswith("/api/") and not path.startswith("/api/m/")
            and not secrets.compare_digest(request.headers.get(TOKEN_HEADER, ""), API_TOKEN)):
        return JSONResponse(status_code=403, content={"detail": "نشست برنامه منقضی شده است؛ صفحه را دوباره باز کنید (F5)."})
    if licensing.REQUIRED and request.method == "POST":
        # پس از دوره آزمایشی فقط پذیرش و پردازش ویس تازه بسته است؛ رکوردها، اکسل و پشتیبان باز می‌مانند
        if _is_intake(path) and not licensing.can_process():
            return JSONResponse(status_code=402, content={"detail": _TRIAL_OVER, "license": True})
        if path == "/api/update" and not licensing.licensed():
            return JSONResponse(status_code=402, content={"detail": "به‌روزرسانی فقط برای نسخه دارای اشتراک است.",
                                                          "license": True})
    response = await call_next(request)
    response.headers.update(_SECURITY_HEADERS)
    if path in _APP_PAGES:
        response.headers["Content-Security-Policy"] = _CSP
    return response


# صفحه برنامه در قاب (iframe) سایت دیگری باز نمی‌شود تا با کلیک فریبنده فرمانی اجرا نشود؛ فایل‌ها با نوع
# اعلام‌شده خوانده می‌شوند (ویس جعلی به‌عنوان صفحه وب اجرا نمی‌شود)؛ در صفحه‌های برنامه فقط کد خود برنامه اجرا می‌شود.
_SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"}
_APP_PAGES = {"/", "/m", "/m/"}
MAX_REQUEST_BYTES = 4 * 1024 ** 3
_INTAKE = {"/api/upload", "/api/m/upload", "/api/import-folder", "/api/queue/start", "/api/files/retry-failed"}
_TRIAL_OVER = "دوره آزمایشی تمام شده است؛ برای پردازش ویس تازه، برنامه را فعال کنید. ردیف‌های قبلی در دسترس‌اند."


def _is_intake(path: str) -> bool:
    return path in _INTAKE or (path.startswith("/api/files/") and path.endswith("/retry"))
_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'")


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
        if path == "/api/m/login":  # فقط ورود با رمز؛ پس از آن هر گوشی کلید خودش را دارد
            ok = lan.pin_ok(request.headers.get("x-pin"), s.lan_pin)
        else:
            device = db().device_by_token(lan.token_hash(request.headers.get("x-device") or ""))
            ok = device is not None
            if ok:
                request.state.device = device
                db().touch_device(device["id"], host)
        if not ok:
            _pin_limiter.fail(host)
            return JSONResponse(status_code=401, content={"detail": "رمز نادرست است یا این گوشی از فهرست برداشته شده است."})
        _pin_limiter.reset(host)
    return await call_next(request)


@app.middleware("http")
async def _no_cache(request, call_next):
    """پس از به‌روزرسانی برنامه، مرورگر نسخه قدیمی رابط را از حافظه نهان نخواند."""
    _last_request["t"] = time.time()
    response = await call_next(request)
    if (not request.url.path.startswith("/api/files/") and not request.url.path.startswith("/static/fonts")
            and "no-store" not in response.headers.get("Cache-Control", "")):  # صفحه دارای کلید هرگز ذخیره نشود
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


def _write_profile(create: bool = False, visit_date: str | None = None, name: str | None = None) -> dict | None:
    """نگاشت یک فایل (پیش‌فرض: فایل ویس‌های خودکار) برای ثبت؛ قالب «فایل جدید» به نگاشت فایل خود برنامه تبدیل می‌شود.

    create: اگر فایل خروجی قالب هنوز ساخته نشده، با سرستون ساخته شود (فقط هنگام ثبت و پیش‌نمایش).
    visit_date: برای قالبی که فایل یا شیت هر روز/ماه را جدا می‌کند (پیش‌فرض: امروز).
    """
    prof = excel_mapping.load_profile(name or load_settings().active_profile)
    if prof and prof.get("mode") == "new":
        try:
            return excel_template.writer_profile(prof, create, visit_date)
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
    n = db().bind_unassigned(load_settings().active_profile)  # ویس‌های نسخه‌های قبل: به فایلی که تا الان فعال بود
    if n:
        log.info("%s ویس قبلی به فایل «%s» وصل شد.", n, load_settings().active_profile)
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
    if not s.inbox_dir or not licensing.can_process():
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
                added += _register_file(fh, f.name, batch, visit, True, s.active_profile)["result"] == "added"
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
    """هنگام اجرا و سپس هر ده دقیقه: پشتیبان روزانه گرفته شده باشد و دسترسی بی‌استفاده گوشی خاموش شود."""
    while True:
        try:
            made = backup.maybe_daily_backup(db())
            if made:
                log.info("پشتیبان خودکار روزانه ساخته شد: %s", made["name"])
            lan_auto_off()
        except Exception:
            log.exception("daily backup failed")
        time.sleep(600)  # پشتیبان روزانه است؛ این فاصله برای خاموش شدن به‌موقع دسترسی گوشی است


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
    try:  # DataVox.exe با دیدن این نشانه، پنجره را می‌بندد (به‌جای راه‌اندازی دوباره موتور)
        (DATA_DIR / ".quit").write_text("1")
    except OSError:
        pass

    def bye():
        worker().join(20)
        os._exit(0)

    threading.Timer(0.5, bye).start()
    return {"ok": True}


# ---------- مجوز ----------
def _license_out() -> dict:
    st = licensing.status()
    exp = st.get("expires")
    return {**st, "expires_jalali": format_jalali(from_gregorian(datetime.fromisoformat(exp).date())) if exp else None,
            "contact": licensing.contact(), "version": __version__}


@app.get("/api/license")
def license_info():
    return _license_out()


class LicenseIn(BaseModel):
    text: str


@app.post("/api/license")
def license_install(body: LicenseIn):
    if len(body.text) > 4000:
        err(400, "این متن، مجوز «DataVox» نیست.")
    try:
        licensing.install(body.text)
    except licensing.LicenseError as e:
        err(400, str(e))
    log.info("مجوز برنامه نصب شد.")
    return _license_out()


# ---------- فایل‌های صوتی ----------
def _register_file(src_stream, original_name: str, batch_id: int, visit_date: str, use_filename_date: bool,
                   dest: str) -> dict:
    uploads = DATA_DIR / "uploads"
    ext = Path(original_name).suffix.lower()
    tmp = uploads / f".incoming_{uuid.uuid4().hex}{ext}"
    size, head = 0, b""
    with open(tmp, "wb") as out:
        while True:
            chunk = src_stream.read(1 << 20)
            if not chunk:
                break
            head = head or chunk[:64]
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                break
            out.write(chunk)
    if size > MAX_AUDIO_BYTES or not looks_like_audio(head):
        tmp.unlink(missing_ok=True)
        return {"name": original_name, "result": "error",
                "message": "حجم فایل بیش از یک گیگابایت است." if size > MAX_AUDIO_BYTES else "این فایل صوتی نیست."}
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
    aid = db().add_audio(batch_id, original_name, stored, sha, size, vd, source, dest)
    return {"name": original_name, "result": "added", "id": aid, "visit_date": vd, "date_source": source}


def _check_visit_date(visit_date: str) -> str:
    d = parse_jalali(visit_date)
    if d is None:
        err(400, "تاریخ بازدید باید شمسی و مانند 1405/07/28 باشد.")
    return format_jalali(d)


def _check_dest(dest: str) -> str:
    """نام فایل اکسلی که ویس‌ها به آن اضافه می‌شوند؛ خالی = فایل ویس‌های خودکار (پوشه ورودی و گوشی)."""
    dest = (dest or "").strip() or load_settings().active_profile
    if not excel_mapping.load_profile(dest) and dest != excel_mapping.COMPANY:
        err(404, "این فایل اکسل در فهرست فایل‌ها نیست.")
    return dest


async def _store_uploads(files: list[UploadFile], batch_name: str, visit_date: str, use_filename_date: bool,
                         dest: str = "") -> list[dict]:
    """ذخیره فایل‌های آپلودی (رایانه یا گوشی) و افزودن به صف؛ مدل هم از همین حالا آماده می‌شود."""
    vd = _check_visit_date(visit_date or format_jalali(today_jalali()))
    dest = _check_dest(dest)
    batch = db().create_batch(batch_name, vd)
    results = []
    for f in files:
        name = Path(f.filename or "audio").name
        if not is_supported(name):
            results.append({"name": name, "result": "error", "message": "قالب این فایل پشتیبانی نمی‌شود."})
            continue
        try:
            results.append(_register_file(f.file, name, batch, vd, use_filename_date, dest))
        except Exception as e:
            results.append({"name": name, "result": "error", "message": f"ذخیره فایل ناموفق بود: {e}"})
        finally:
            await f.close()
    if any(r["result"] == "added" for r in results) and model_available(load_settings().model_name):
        worker().warmup()
    return results


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...), visit_date: str = Form(""), use_filename_date: bool = Form(True),
                 dest: str = Form("")):
    return {"results": await _store_uploads(files, f"آپلود {datetime.now():%H:%M}", visit_date, use_filename_date, dest)}


# ---------- آپلود از گوشی (شبکه محلی) ----------
_PHONE_BATCH = "گوشی: "


@app.get("/m")
def mobile_page():
    return FileResponse(WEB_DIR / "m.html")


def _sender(request: Request, given: str = "") -> str:
    """نام فرستنده: نام ثبت‌شده همان گوشی (از روی خود رایانه، نام نوشته‌شده در صفحه)."""
    device = getattr(request.state, "device", None)
    return device["name"] if device else ((given or "").strip()[:40] or "بدون نام")


class DeviceLogin(BaseModel):
    name: str


@app.post("/api/m/login")
def mobile_login(body: DeviceLogin, request: Request):
    """رمز در میان‌افزار بررسی شده است؛ گوشی کلید خودش را می‌گیرد و از این به بعد رمز لازم ندارد."""
    name = body.name.strip()[:40]
    if not name:
        err(400, "نام خود را بنویسید (تا ویس‌هایتان در رایانه با همین نام دیده شود).")
    token = lan.new_device_token()
    db().add_device(name, lan.token_hash(token), request.client.host if request.client else "")
    db().log_event(f"گوشی «{name}» برای ارسال ویس وصل شد.")
    return {"token": token, "name": name}


@app.post("/api/m/check")
def mobile_check(request: Request):
    """کلید گوشی در میان‌افزار بررسی شده است؛ اینجا فقط اطلاعات صفحه برگردانده می‌شود."""
    return {"ok": True, "name": _sender(request), "today": format_jalali(today_jalali()),
            "extensions": sorted(SUPPORTED_AUDIO_EXTENSIONS)}


@app.post("/api/m/upload")
async def mobile_upload(request: Request, files: list[UploadFile] = File(...), visit_date: str = Form(""),
                        sender: str = Form("")):
    sender = _sender(request, sender)
    results = await _store_uploads(files, _PHONE_BATCH + sender, visit_date, True)
    s = load_settings()
    if s.lan_auto_start and any(r["result"] == "added" for r in results) and model_available(s.model_name):
        worker().start()
    # فقط نتیجه افزودن به گوشی برمی‌گردد، نه شناسه داخلی یا مسیر فایل
    return {"results": [{"name": r["name"], "result": r["result"], "message": r.get("message", "")} for r in results]}


@app.get("/api/m/recent")
def mobile_recent(request: Request, sender: str = ""):
    """وضعیت آخرین ویس‌های فرستاده‌شده از همین گوشی (فقط نام فایل و وضعیت پردازش؛ نه ویس دیگران)."""
    rows = db().q("""SELECT a.original_name, a.status, a.created_at, a.error FROM audio_files a JOIN batches b ON b.id=a.batch_id
                     WHERE b.name=? ORDER BY a.id DESC LIMIT 20""", (_PHONE_BATCH + _sender(request, sender),))
    # راهنمای کیفیت ضبط (نویز، صدای ضعیف) فقط برای ویس پردازش‌شده؛ خطای داخلی برنامه به گوشی نمی‌رود
    return {"files": [{**{k: r[k] for k in ("original_name", "status", "created_at")},
                       "tip": r["error"] if r["status"] == "done" and r["error"] else ""} for r in rows]}


class LanIn(BaseModel):
    enabled: bool
    auto_start: bool = True
    idle_hours: int = 0


@app.get("/api/lan")
def lan_info():
    s = load_settings()
    bound = os.environ.get("V2X_BIND_HOST", s.host)
    return {
        "enabled": s.lan_enabled, "pin": s.lan_pin, "auto_start": s.lan_auto_start, "idle_hours": s.lan_idle_hours,
        "urls": [f"http://{ip}:{s.port}/m" for ip in lan.lan_addresses()],
        "restart_needed": s.lan_enabled != (bound == "0.0.0.0"),
        "devices": db().list_devices(),
    }


@app.put("/api/lan")
def lan_set(body: LanIn):
    s = load_settings()
    updates = {"lan_enabled": body.enabled, "lan_auto_start": body.auto_start, "lan_idle_hours": max(0, body.idle_hours)}
    if body.enabled and not s.lan_pin:
        updates["lan_pin"] = lan.generate_pin()
    if body.enabled and not s.lan_enabled:
        db().set_meta("lan_enabled_at", str(time.time()))
    save_settings(updates)
    return lan_info()


@app.post("/api/lan/new-pin")
def lan_new_pin():
    """رمز جدید: همه گوشی‌های وصل‌شده هم برداشته می‌شوند و باید با رمز تازه دوباره وصل شوند."""
    save_settings({"lan_pin": lan.generate_pin()})
    db().delete_devices()
    return lan_info()


@app.delete("/api/lan/devices/{device_id}")
def lan_remove_device(device_id: int):
    if not db().delete_devices(device_id):
        err(404, "این گوشی در فهرست نیست.")
    return lan_info()


def lan_auto_off() -> bool:
    """اگر «خاموش شدن خودکار» تنظیم شده و این مدت هیچ گوشی‌ای ویس نفرستاده، دسترسی شبکه بسته می‌شود."""
    s = load_settings()
    if not (s.lan_enabled and s.lan_idle_hours):
        return False
    seen = [datetime.fromisoformat(d["last_seen"]).timestamp() for d in db().list_devices() if d["last_seen"]]
    last = max(seen + [float(db().get_meta("lan_enabled_at") or 0)])
    if time.time() - last < s.lan_idle_hours * 3600:
        return False
    save_settings({"lan_enabled": False})
    db().log_event(f"ارسال از گوشی پس از {s.lan_idle_hours} ساعت بی‌استفاده خودکار خاموش شد.")
    return True


class FolderImport(BaseModel):
    path: str
    visit_date: str = ""
    use_filename_date: bool = True
    recursive: bool = False
    dest: str = ""


@app.post("/api/import-folder")
def import_folder(body: FolderImport):
    folder = Path(body.path)
    if not folder.is_dir():
        err(400, "پوشه پیدا نشد.")
    vd = _check_visit_date(body.visit_date or format_jalali(today_jalali()))
    dest = _check_dest(body.dest)
    it = folder.rglob("*") if body.recursive else folder.iterdir()
    files = sorted(p for p in it if p.is_file() and is_supported(p.name))
    if not files:
        err(400, "در این پوشه فایل صوتی پشتیبانی‌شده‌ای پیدا نشد.")
    batch = db().create_batch(f"پوشه {folder.name}", vd)
    results = []
    for p in files:
        try:
            with open(p, "rb") as fh:
                results.append(_register_file(fh, p.name, batch, vd, body.use_filename_date, dest))
        except OSError as e:
            results.append({"name": p.name, "result": "error", "message": f"خواندن فایل ناموفق بود: {e.strerror}"})
    if any(r["result"] == "added" for r in results) and model_available(load_settings().model_name):
        worker().warmup()
    return {"results": results}


@app.post("/api/samples/import")
def import_samples(dest: str = ""):
    """افزودن ویس‌های نمونه (گفتار مصنوعی با اطلاعات ساختگی) برای امتحان برنامه."""
    voices, _ = _sample_files()
    if not voices:
        err(404, "ویس نمونه‌ای همراه برنامه نیست.")
    return import_folder(FolderImport(path=str(SAMPLES_DIR), visit_date="", use_filename_date=False, dest=dest))


@app.get("/api/files")
def list_files(dest: str = ""):
    rows = db().q(
        """SELECT a.id, a.original_name, a.size, a.duration, a.visit_date, a.date_source, a.status, a.error,
                  a.attempts, a.model, a.processing_seconds, a.peak_rss_mb, a.audio_deleted, a.created_at, a.dest,
                  (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id) AS records,
                  (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id AND r.review_state='pending') AS pending,
                  (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id AND r.exported_at IS NOT NULL) AS exported
           FROM audio_files a WHERE ?='' OR a.dest=? ORDER BY a.id DESC""", (dest, dest))
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
        err(409, "ردیف‌های این ویس در اکسل ثبت شده‌اند و حذف آن مجاز نیست.")
    with db().tx() as c:
        c.execute("DELETE FROM records WHERE audio_id=?", (fid,))
        c.execute("DELETE FROM transcripts WHERE audio_id=?", (fid,))
        c.execute("DELETE FROM audio_files WHERE id=?", (fid,))
    if f["stored_name"]:
        (DATA_DIR / "uploads" / f["stored_name"]).unlink(missing_ok=True)
    return {"ok": True}


class FileMove(BaseModel):
    dest: str


@app.patch("/api/files/{fid}")
def move_file(fid: int, body: FileMove):
    """انتقال ویس (و ردیف‌های ثبت‌نشده‌اش) به فایل اکسل دیگر."""
    _get_file(fid)
    dest = _check_dest(body.dest)
    if db().one("SELECT COUNT(*) n FROM records WHERE audio_id=? AND exported_at IS NOT NULL", (fid,))["n"]:
        err(409, "ردیف‌های این ویس در اکسل ثبت شده‌اند؛ برای انتقال، اول آن ثبت را برگردانید.")
    db().set_audio(fid, dest=dest)
    return {"ok": True, "dest": dest}


@app.post("/api/files/{fid}/retry")
def retry_file(fid: int):
    f = _get_file(fid)
    if f["status"] == "processing":
        err(409, "این فایل در حال پردازش است.")
    if f["status"] == "done" and _protected_records(fid):
        err(409, "ردیف‌های این ویس اصلاح، تأیید یا ثبت شده‌اند؛ پردازش دوباره آن‌ها را بازنویسی نمی‌کند. "
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
def list_records(filter: str = "review", audio_id: int | None = None, dest: str = ""):
    where = _FILTERS.get(filter, "1=1")
    args: tuple = ()
    if audio_id:
        where += " AND r.audio_id=?"
        args = (audio_id,)
    if dest:
        where += " AND a.dest=?"
        args = (*args, dest)
    return {"records": [_record_out(r) for r in db().list_records(where, args)]}


def _get_record(rid: int) -> dict:
    r = db().list_records("r.id=?", (rid,))
    if not r:
        err(404, "ردیف پیدا نشد.")
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
        err(409, "این ردیف در اکسل ثبت شده است؛ برای ویرایش، اول آن ثبت را از «تاریخچه ثبت‌ها» برگردانید.")
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
            if not _is_map_revert(r, k, v):
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
        err(409, "این ردیف در اکسل ثبت شده است.")
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


def _is_map_revert(r: dict, field: str, value: str) -> bool:
    """برگرداندن حدسِ نقشه به آنچه شنیده شد، تصمیم همان آدرس است؛ «اصلاح همیشگی» یاد گرفته نمی‌شود."""
    fix = r["extracted"].get("meta", {}).get("map_fix")
    return bool(fix) and field == "address" and value == fix["from"]


class AcceptSuggestion(BaseModel):
    field: str
    value: str


@app.post("/api/records/{rid}/accept")
def accept_suggestion(rid: int, body: AcceptSuggestion):
    r = _get_record(rid)
    if r["exported_at"]:
        err(409, "این ردیف در اکسل ثبت شده است.")
    values = dict(r["values"])
    db().log_edit(rid, body.field, values.get(body.field, ""), body.value, "accept")
    if not _is_map_revert(r, body.field, body.value):
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
        err(409, "این ردیف در اکسل ثبت شده است؛ اول آن ثبت را از «تاریخچه ثبت‌ها» برگردانید.")
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


@app.post("/api/dictionary/export")
def dictionary_export():
    """واژه‌نامه و اصلاحات برای رایانه دیگر (بدون رکورد و ویس)؛ با رمزگذاری روشن، قفل با گذرواژه تنظیمات."""
    import json
    raw = json.dumps(dictionary.export_data(db()), ensure_ascii=False).encode("utf-8")
    try:
        data, encrypted = backup.seal(raw)
    except backup.BackupError as e:
        err(400, str(e))
    name = f"vazhenameh-{datetime.now():%Y%m%d}" + (".v2xdict" if encrypted else ".json")
    return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/dictionary/import")
async def dictionary_import(file: UploadFile = File(...), password: str = Form("")):
    import json
    try:
        data = json.loads(backup.unseal(await _read_upload(file, 100 * 1024 * 1024), password).decode("utf-8"))
    except backup.BackupError as e:
        err(400, str(e))
    except (json.JSONDecodeError, UnicodeDecodeError):
        err(400, "این فایل، واژه‌نامه «DataVox» نیست.")
    try:
        res = dictionary.import_data(db(), data)
    except ValueError as e:
        err(400, str(e))
    db().log_event(f"واژه‌نامه از فایل وارد شد: {res['entities']} نام، {res['aliases']} شکل دیگر، {res['corrections']} اصلاح.")
    return {**_after_knowledge_change(), "added": res}


@app.post("/api/dictionary/seed-from-excel")
def dict_seed(name: str = ""):
    """یادگیری از یک فایل اکسل موجود فهرست (همان «آموزش از اکسل» با ستون‌های تأییدشده آن)."""
    prof = excel_mapping.load_profile(name or excel_mapping.COMPANY)
    if not prof or prof.get("mode") == "new":
        err(400, "اول از «فایل‌های من» فایل اکسل را اضافه و ستون‌هایش را تأیید کنید.")
    roles = {c: _PROFILE_ROLES[f] for c, f in prof["columns"].items() if f in _PROFILE_ROLES}
    if not roles:
        err(400, "در ستون‌های این فایل، ستون نام یا آدرس مشخص نشده است.")
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
            check_package(path)
            info = knowledge.analyze_workbook(path)
        except ValueError as e:
            path.unlink(missing_ok=True)
            out.append({"name": name, "error": str(e)})
            continue
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


class InspectIn(BaseModel):
    path: str
    name: str = ""  # فایلی از فهرست که فایل اکسلش عوض می‌شود؛ خالی = فایل تازه در فهرست


def _append_profiles() -> list[dict]:
    return [p for n in excel_mapping.list_profiles() if (p := excel_mapping.load_profile(n)) and p.get("mode") != "new"]


def _same_path(a: str, b: str) -> bool:
    try:
        return bool(a and b) and Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def _name_for_file(path: Path) -> str:
    """نام فایل در فهرست برای یک فایل اکسل موجود: همان قبلی اگر این فایل در فهرست هست، وگرنه نام تازه."""
    for prof in _append_profiles():
        if _same_path(prof.get("excel_path", ""), str(path)):
            return prof["name"]
    if not excel_mapping.load_profile(excel_mapping.COMPANY):
        return excel_mapping.COMPANY
    return "f_" + uuid.uuid4().hex[:8]


@app.post("/api/excel/inspect")
def excel_inspect(body: InspectIn):
    p = Path(body.path.strip().strip('"'))
    if not body.path.strip() or not p.is_file():
        err(404, "فایل پیدا نشد.")
    rep = inspect_workbook(p)
    name = body.name.strip() or _name_for_file(p)
    prof = excel_mapping.load_profile(name)
    if prof and prof.get("mode") != "new" and _same_path(prof.get("excel_path", ""), str(p)):
        suggested = prof
    else:
        sheets = rep.get("sheets", [])
        main = max(sheets, key=lambda s: s["data_rows"]) if sheets else None
        suggested = excel_mapping.new_profile(name, str(p), main["name"], main["header_row"],
                                              main["headers"]) if main else None
    return {"report": rep, "profile": suggested}


@app.get("/api/excel/profile")
def excel_profile(name: str = ""):
    prof = excel_mapping.load_profile(name or excel_mapping.COMPANY)
    return {"profile": prof if prof and prof.get("mode") != "new" else None}


_APPEND_NAME = re.compile(r"f_[0-9a-f]{8}")


@app.put("/api/excel/profile")
def excel_profile_save(profile: dict):
    name = str(profile.get("name") or excel_mapping.COMPANY)
    existing = excel_mapping.load_profile(name)
    if (existing and existing.get("mode") == "new") or (
            not existing and name != excel_mapping.COMPANY and not _APPEND_NAME.fullmatch(name)):
        err(400, "این فایل در فهرست فایل‌ها نیست.")
    p = Path(profile.get("excel_path", ""))
    if not p.exists():
        err(400, "فایل اکسل پیدا نشد.")
    if any(o["name"] != name and _same_path(o.get("excel_path", ""), str(p)) for o in _append_profiles()):
        err(409, f"«{p.name}» قبلاً در فهرست فایل‌ها هست؛ همان را باز کنید.")
    rep = inspect_workbook(p)
    sheet = next((s for s in rep.get("sheets", []) if s["name"] == profile.get("sheet")), None)
    if not sheet:
        err(400, next((r["message"] for r in rep["risks"] if r["level"] == "block"), "شیت انتخاب‌شده در فایل نیست."))
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
        err(400, "دست‌کم یک ستون باید اطلاعاتی بگیرد.")
    if len(set(columns.values())) != len(columns):
        err(400, "یک اطلاعات به بیش از یک ستون داده شده است.")
    clean = {
        "name": name,
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
    if "highlights" in clean["policy"]:
        clean["policy"]["highlights"] = excel_template.clean_highlights(clean["policy"]["highlights"])
    if not clean["policy"].get("text_style"):
        # سبک نوشتن (جداکننده، نوع رقم) از ردیف‌های موجود همان فایل استخراج می‌شود
        style_cols = {c: f for c, f in columns.items() if f in ("address", "notes_composed", "technical_summary")}
        rows = read_rows(p, sheet["name"], hr, style_cols, raw=True) if style_cols else []
        samples = [r.get(f, "") for r in rows for f in style_cols.values()]
        clean["policy"]["text_style"] = infer_style(samples)
    first = not excel_mapping.load_profile(load_settings().active_profile)
    excel_mapping.save_profile(clean)
    # اولین فایل فهرست، فایل ویس‌های خودکار (پوشه ورودی و گوشی) هم می‌شود
    save_settings({"last_excel_path": str(p), **({"active_profile": name} if first else {})})
    _excel_cache["key"] = None
    _rows_cache.clear()
    return {"profile": clean}


def _approved_records(dest: str) -> list[dict]:
    rows = db().list_records("r.review_state='approved' AND r.exported_at IS NULL AND a.dest=?", (dest,))
    for r in rows:
        t = db().one("SELECT processed_text FROM transcripts WHERE audio_id=?", (r["audio_id"],))
        r["transcript"] = (t or {}).get("processed_text", "")
    return rows


class DestIn(BaseModel):
    dest: str = ""


@app.post("/api/excel/preview")
def excel_preview(body: DestIn | None = None):
    dest = _check_dest(body.dest if body else "")
    prof = _confirmed_profile(dest)
    recs = _approved_records(dest)
    pending = db().one("""SELECT COUNT(*) n FROM records r JOIN audio_files a ON a.id=r.audio_id
                          WHERE r.review_state='pending' AND r.exported_at IS NULL AND a.dest=?""", (dest,))["n"]
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
    dest: str = ""


_export_lock = threading.Lock()


def _confirmed_profile(dest: str) -> dict:
    prof = _write_profile(create=True, name=dest)
    if not prof or not prof.get("confirmed"):
        err(400, "ستون‌های این فایل هنوز تأیید نشده‌اند؛ از «تنظیمات فایل» تأییدشان کنید.")
    return prof


def _export(prof: dict, dest: str, record_ids: list[int] | None = None) -> dict:
    """ساخت خروجی (روی کپی) و ثبت آن؛ باید زیر _export_lock صدا زده شود."""
    import json
    recs = _approved_records(dest)
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
    dest = _check_dest(body.dest)
    prof = _confirmed_profile(dest)
    with _export_lock:
        return _export(prof, dest, body.record_ids)


@app.post("/api/excel/commit")
def excel_commit(body: ExportIn):
    """ثبت یک‌مرحله‌ای: نوشتن روی کپی، بررسی، و جایگزینی فایل اصلی (با پشتیبانی که پیش از نوشتن گرفته شده).

    اگر جایگزینی ممکن نباشد (مثلاً فایل در Excel باز شد)، خروجی ساخته‌شده می‌ماند و بعداً قابل اعمال است.
    با گزینه «اول در کپی» (review_copy_first) فایل اصلی دست نمی‌خورد تا کاربر کپی را ببیند و از تاریخچه اعمالش کند.
    """
    copy_first = load_settings().review_copy_first
    dest = _check_dest(body.dest)
    tpl = excel_mapping.load_profile(dest)
    recs = [r for r in _approved_records(dest) if not body.record_ids or r["id"] in set(body.record_ids)]
    if not recs:
        err(400, "ردیف تأییدشده‌ای برای ثبت نیست.")
    # قالبی که فایل یا شیت هر روز/ماه را جدا می‌کند، چند مقصد دارد؛ هر مقصد ثبت (و پشتیبان) جداگانه دارد
    groups = excel_template.group_records(tpl, recs) if tpl and tpl.get("mode") == "new" else [(None, recs)]
    targets = [(_write_profile(create=True, visit_date=vd, name=dest) if vd is not None else _confirmed_profile(dest), grp)
               for vd, grp in groups]
    for prof, _ in targets:
        if not prof or not prof.get("confirmed"):
            err(400, "ستون‌های این فایل هنوز تأیید نشده‌اند؛ از «تنظیمات فایل» تأییدشان کنید.")
        lock = lock_status(Path(prof["excel_path"]))
        if not copy_first and (lock["write_blocked"] or lock["owner_file"]):
            err(409, lock["message"] or "فایل اکسل باز است؛ آن را ببندید و دوباره تلاش کنید.")
    done: list[dict] = []
    _rows_cache.clear()
    with _export_lock:
        for prof, grp in targets:
            rep = _export(prof, dest, [r["id"] for r in grp])
            if copy_first:
                rep["applied"], rep["copy_only"] = False, True
                rep["message"] = (f"ردیف‌ها در یک کپی از «{Path(rep['target_path']).name}» نوشته شدند و فایل اصلی دست نخورد. "
                                  "کپی را ببینید و اگر درست بود، از «تاریخچه ثبت‌ها» «اعمال روی فایل اصلی» را بزنید.")
                done.append(rep)
                continue
            try:
                replace_original(rep["output_path"], rep["target_path"], rep["target_sha"], backup_path=rep["backup_path"])
            except ExcelWriteError as e:
                rep["applied"] = False
                rep["message"] = f"ردیف‌ها در یک کپی ثبت شدند ولی فایل «{Path(rep['target_path']).name}» به‌روز نشد: {e}"
            else:
                with db().tx() as c:
                    c.execute("UPDATE exports SET replaced_original_at=?, status='applied' WHERE id=?", (now(), rep["export_id"]))
                rep["applied"] = True
            done.append(rep)
    first = done[0]
    return {**first, "applied": all(r["applied"] for r in done), "copy_only": copy_first,
            "message": " ".join(r.get("message", "") for r in done if not copy_first or r is first).strip(),
            "rows": [x for r in done for x in r["rows"]], "export_ids": [r["export_id"] for r in done],
            "files": sorted({Path(r["target_path"]).name for r in done})}


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
    out = prof.get("output") or {}
    return {"name": name, "title": prof.get("title") or ("فایل شرکت" if not new else name), "mode": prof.get("mode", "append"),
            "active": name == active, "target": excel_template.target_path(prof).name if new else Path(prof.get("excel_path", "")).name,
            # برای کارت مقصد: یک جمله ساده درباره اینکه ردیف‌ها کجا نوشته می‌شوند
            "confirmed": bool(prof.get("confirmed")), "sheet": prof.get("sheet", ""),
            "folder": out.get("folder", ""), "file": out.get("file", ""), "split": out.get("split", "none")}


def _sample_records() -> list[dict]:
    """چند رکورد واقعی اخیر برای پیش‌نمایش (اگر نباشد، نمونه ساختگی)."""
    rows = db().list_records("r.review_state!='rejected'")[-4:]
    return [{"id": r["id"], "values": r["values"], "original_name": r["original_name"], "transcript": "",
             "validation": r["validation"], "status": r["status"]} for r in rows] or \
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
            "fonts": excel_template.installed_fonts(), "aligns": excel_template.ALIGNS, "splits": excel_template.SPLITS,
            "highlight_defaults": excel_template.DEFAULT_HIGHLIGHTS}


@app.get("/api/templates/{name}")
def template_get(name: str):
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "این فایل در فهرست نیست.")
    return {"template": prof, "target": str(excel_template.target_path(prof)) if prof.get("mode") == "new" else prof.get("excel_path", "")}


class TemplateNew(BaseModel):
    title: str


@app.post("/api/templates")
def template_create(body: TemplateNew):
    title = body.title.strip()[:60]
    if not title:
        err(400, "نام فایل را بنویسید.")
    name = "t_" + uuid.uuid4().hex[:8]
    folder = Path.home() / "Documents"
    tpl = excel_template.new_template(name, title, str(folder if folder.is_dir() else Path.home()))
    _save_new_dest(tpl)
    return {"name": name}


def _save_new_dest(tpl: dict) -> None:
    """اولین فایل فهرست، فایل ویس‌های خودکار (پوشه ورودی و گوشی) هم می‌شود."""
    first = not excel_mapping.load_profile(load_settings().active_profile)
    excel_mapping.save_profile(tpl)
    if first:
        save_settings({"active_profile": tpl["name"]})


@app.put("/api/templates/{name}")
def template_save(name: str, body: dict):
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "این فایل در فهرست نیست.")
    if prof.get("mode") != "new":
        # فایل شرکت: فقط قالب مقادیر؛ ستون‌ها و ظاهر فایل موجود دست نمی‌خورد
        prof["policy"] = {**prof.get("policy", {}), **{k: v for k, v in (body.get("policy") or {}).items()
                                                      if k in excel_mapping.VALUE_FORMAT_KEYS}}
        if "highlights" in prof["policy"]:
            prof["policy"]["highlights"] = excel_template.clean_highlights(prof["policy"]["highlights"])
        excel_mapping.save_profile(prof)
        return {"template": prof}
    tpl = _clean_template({**body, "name": name})
    if not Path(tpl["output"]["folder"]).is_dir():
        err(400, "پوشه فایل پیدا نشد.")
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


async def _read_upload(file: UploadFile, limit: int = 20 * 1024 * 1024) -> bytes:
    data = await file.read(limit + 1)
    if len(data) > limit:
        err(400, "حجم فایل زیاد است.")
    return data


@app.post("/api/templates/from-file")
async def template_from_file(file: UploadFile = File(...)):
    """«مثل این فایل»: ستون‌ها و ظاهر از یک فایل اکسل نمونه خوانده می‌شود (چیزی ذخیره نمی‌شود)."""
    if Path(file.filename or "").suffix.lower() not in (".xlsx", ".xlsm"):
        err(400, "فقط فایل XLSX یا XLSM.")
    KB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = KB_DIR / f"style_{uuid.uuid4().hex}.xlsx"
    tmp.write_bytes(await _read_upload(file))
    try:
        check_package(tmp)
        return excel_template.from_file(tmp)
    except ValueError as e:
        err(400, str(e))
    except Exception:
        log.exception("template from file failed")
        err(400, "فایل اکسل باز نشد (خراب یا رمزدار است).")
    finally:
        tmp.unlink(missing_ok=True)


@app.get("/api/templates/{name}/export")
def template_export(name: str):
    prof = excel_mapping.load_profile(name)
    if not prof or prof.get("mode") != "new":
        err(404, "فقط تنظیمات «فایل تازه» به رایانه دیگر منتقل می‌شود.")
    import json
    data = json.dumps(excel_template.to_export(prof), ensure_ascii=False, indent=1).encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="application/json",
                             headers={"Content-Disposition": "attachment; filename=template.v2x.json"})


@app.post("/api/templates/import")
async def template_import(file: UploadFile = File(...)):
    import json
    try:
        data = json.loads((await _read_upload(file, 1024 * 1024)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        err(400, "این فایل، تنظیمات فایل «DataVox» نیست.")
    name = "t_" + uuid.uuid4().hex[:8]
    folder = Path.home() / "Documents"
    try:
        tpl = excel_template.from_export(data, name, str(folder if folder.is_dir() else Path.home()))
    except ValueError as e:
        err(400, str(e))
    _save_new_dest(tpl)
    return {"name": name}


@app.delete("/api/templates/{name}")
def template_delete(name: str):
    if not excel_mapping.load_profile(name):
        err(404, "این فایل در فهرست نیست.")
    if name == load_settings().active_profile:
        err(400, "ویس‌های گوشی و پوشه ورودی به این فایل می‌آیند؛ اول فایل دیگری را برای آن‌ها انتخاب کنید.")
    busy = db().one("""SELECT COUNT(*) n FROM audio_files a WHERE a.dest=? AND (a.status IN ('queued','processing')
                       OR EXISTS(SELECT 1 FROM records r WHERE r.audio_id=a.id AND r.exported_at IS NULL
                                 AND r.review_state!='rejected'))""", (name,))["n"]
    if busy:
        err(409, f"{busy} ویس این فایل هنوز ثبت نشده است؛ اول آن‌ها را ثبت، رد یا به فایل دیگری منتقل کنید.")
    excel_mapping.delete_profile(name)
    return {"ok": True}


_rows_cache: dict = {}


def _file_rows(prof: dict) -> dict | None:
    """تعداد ردیف‌های داده و آخرین ردیف فایل (با حافظه تا وقتی فایل تغییر نکرده)."""
    try:
        wp = excel_template.writer_profile(prof, create=False) if prof.get("mode") == "new" else prof
        path = Path(wp.get("excel_path") or "")
        if not path.is_file():
            return {"rows": 0, "last_row": 0, "exists": False}
        key = (str(path), path.stat().st_mtime, wp.get("sheet"), wp.get("header_row"), tuple(wp.get("headers") or {}))
        if key not in _rows_cache:
            from .excel_reader import data_summary
            _rows_cache[key] = {**data_summary(path, wp["sheet"], int(wp.get("header_row") or 1), list(wp.get("headers") or {})),
                                "exists": True}
        return _rows_cache[key]
    except Exception:
        log.exception("reading row count failed")
        return None


_STAT_KEYS = ("voices", "converting", "failed", "no_rows", "review", "ready", "written", "rejected")


def _dest_stats() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in db().q("""SELECT a.dest d, COUNT(*) voices, SUM(a.status IN ('queued','processing')) converting,
                              SUM(a.status='failed') failed,
                              SUM(a.status='done' AND NOT EXISTS(SELECT 1 FROM records r WHERE r.audio_id=a.id)) no_rows
                       FROM audio_files a GROUP BY a.dest"""):
        out[r["d"] or ""] = {k: r[k] or 0 for k in ("voices", "converting", "failed", "no_rows")}
    for r in db().q("""SELECT a.dest d, CASE WHEN r.exported_at IS NOT NULL THEN 'written'
                              WHEN r.review_state='rejected' THEN 'rejected' WHEN r.review_state='approved' THEN 'ready'
                              ELSE 'review' END k, COUNT(*) n
                       FROM records r JOIN audio_files a ON a.id=r.audio_id GROUP BY d, k"""):
        out.setdefault(r["d"] or "", {})[r["k"]] = r["n"]
    return {d: {k: v.get(k, 0) for k in _STAT_KEYS} for d, v in out.items()}


def _dest_info(name: str, prof: dict, active: str, stats: dict) -> dict:
    new = prof.get("mode") == "new"
    path = str(excel_template.target_path(prof)) if new else prof.get("excel_path", "")
    folder_ok = Path(path).parent.is_dir() if path else False
    last = db().one("""SELECT created_at, rows_written, first_row, last_row, status FROM exports
                       WHERE profile=? AND status!='undone' ORDER BY id DESC LIMIT 1""", (name,))
    return {"name": name, "mode": prof.get("mode", "append"), "title": prof.get("title") or Path(path).name,
            "file": Path(path).name, "path": path, "split": (prof.get("output") or {}).get("split", "none"),
            "confirmed": bool(prof.get("confirmed")), "configured": bool(prof.get("confirmed")) and folder_ok
            and (new or Path(path).is_file()), "missing": not new and bool(path) and not Path(path).is_file(),
            "auto": name == active, "file_rows": _file_rows(prof), "last_commit": last,
            "pending_apply": db().one("SELECT COUNT(*) n FROM exports WHERE profile=? AND status='created'", (name,))["n"],
            **stats.get(name, dict.fromkeys(_STAT_KEYS, 0))}


@app.get("/api/dests")
def dests_list():
    """فایل‌های اکسل فهرست، هرکدام با وضعیت ویس‌ها و ردیف‌هایش. orphans: ویس‌هایی که فایلشان در فهرست نیست."""
    active = load_settings().active_profile
    stats = _dest_stats()
    names = [n for n in excel_mapping.list_profiles() if excel_mapping.load_profile(n)]
    items = [_dest_info(n, excel_mapping.load_profile(n), active, stats) for n in names]
    orphans = [{"dest": d, **v} for d, v in stats.items() if d not in names and (v["converting"] or v["review"] or v["ready"]
                                                                               or v["failed"] or v["no_rows"])]
    return {"dests": items, "active": active, "orphans": orphans}


@app.get("/api/dests/{name}")
def dest_get(name: str):
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "این فایل در فهرست نیست.")
    return _dest_info(name, prof, load_settings().active_profile, _dest_stats())


def _voice_stage(f: dict, recs: list[dict]) -> str:
    """سرنوشت یک ویس: در حال تبدیل، ناموفق، بدون ردیف، نیاز به بررسی، آماده ثبت، ثبت‌شده یا ردشده."""
    if f["status"] in ("queued", "processing"):
        return f["status"]
    if f["status"] == "failed":
        return "failed"
    if not recs:
        return "no_rows"
    open_recs = [r for r in recs if not r["exported_at"]]
    if any(r["review_state"] == "pending" for r in open_recs):
        return "review"
    if any(r["review_state"] == "approved" for r in open_recs):
        return "ready"
    if any(r["exported_at"] for r in recs):
        return "written"
    return "rejected"


@app.get("/api/dests/{name}/voices")
def dest_voices(name: str):
    """ویس‌های یک فایل، هر ویس با سرنوشتش و ردیف‌هایی که از آن ساخته یا در اکسل ثبت شده است."""
    import json
    files = db().q("""SELECT a.id, a.original_name, a.visit_date, a.date_source, a.status, a.error, a.duration,
                             a.audio_deleted, a.created_at FROM audio_files a WHERE a.dest=? ORDER BY a.id DESC""", (name,))
    recs: dict[int, list[dict]] = {}
    for r in db().q("""SELECT r.id, r.audio_id, r.building_index, r.review_state, r.status, r.exported_at, r.export_row,
                              r.export_id, r.values_json, e.target_path
                       FROM records r JOIN audio_files a ON a.id=r.audio_id LEFT JOIN exports e ON e.id=r.export_id
                       WHERE a.dest=? ORDER BY r.audio_id, r.building_index""", (name,)):
        v = json.loads(r.pop("values_json") or "{}")
        r["name"] = v.get("engineer_name", "")
        r["file"] = Path(r.pop("target_path")).name if r["target_path"] else ""
        recs.setdefault(r["audio_id"], []).append(r)
    out = []
    for f in files:
        rs = recs.get(f["id"], [])
        f["records"] = rs
        f["stage"] = _voice_stage(f, rs)
        out.append(f)
    current = worker().state().get("current_id")
    return {"voices": out, "current_id": current}


@app.get("/api/dests/{name}/cells")
def dest_cells(name: str, filter: str = "review"):
    """ردیف‌های یک فایل به شکل خود اکسل: ستون‌های فایل به ترتیب واقعی و مقدار هر خانه، همان‌طور که نوشته می‌شود."""
    from openpyxl.utils import column_index_from_string
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "این فایل در فهرست نیست.")
    wp = excel_template.writer_profile(prof, create=False) if prof.get("mode") == "new" else prof
    headers = wp.get("headers") or {}
    letters = sorted(headers, key=column_index_from_string)
    prot = set(wp.get("protected") or [])
    columns = [{"letter": c, "title": str(headers[c] or "").replace("\n", " "), "field": (wp.get("columns") or {}).get(c, ""),
                "protected": c in prot} for c in letters]
    recs = db().list_records(_FILTERS.get(filter, "1=1") + " AND a.dest=?", (name,))
    rows = {}
    for r in recs:
        t = db().one("SELECT processed_text FROM transcripts WHERE audio_id=?", (r["audio_id"],))
        cells = excel_mapping.cell_values(wp, {**r, "transcript": (t or {}).get("processed_text", "")})
        rows[r["id"]] = {c: cells.get(c, "") for c in letters}
    info = _file_rows(prof) or {}
    return {"columns": columns, "rows": rows, "next_row": (info.get("last_row") or wp.get("header_row") or 1) + 1}


_check_cache: dict = {}


def _sheet_headers(path: Path, sheet: str, header_row: int) -> dict[str, str] | None:
    """عنوان ستون‌های ردیف عنوان (خواندن سریع، با حافظه تا وقتی فایل تغییر نکرده). None: شیت نیست."""
    import openpyxl
    from openpyxl.utils import get_column_letter
    key = (str(path), path.stat().st_mtime, sheet, header_row)
    if key not in _check_cache:
        wb = openpyxl.load_workbook(path, read_only=True)
        try:
            if sheet not in wb.sheetnames:
                _check_cache[key] = None
            else:
                row = next(wb[sheet].iter_rows(min_row=header_row, max_row=header_row, values_only=True), ())
                _check_cache[key] = {get_column_letter(i): str(v) for i, v in enumerate(row, 1) if v not in (None, "")}
        finally:
            wb.close()
    return _check_cache[key]


@app.get("/api/dests/{name}/check")
def dest_check(name: str):
    """وضعیت فایل پیش از ثبت، با جمله‌های ساده: [{level: ok|warn|block, text, fix}]؛ fix: columns یا file."""
    from .normalizer import normalize_text
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "این فایل در فهرست نیست.")
    new = prof.get("mode") == "new"
    out: list[dict] = []
    add = lambda level, text, fix=None: out.append({"level": level, "text": text, "fix": fix})  # noqa: E731
    if not prof.get("confirmed"):
        add("block", "ستون‌های این فایل هنوز تأیید نشده‌اند.", "columns")
        return {"items": out, "blocked": True}
    wp = excel_template.writer_profile(prof, create=False) if new else prof
    path = Path(wp.get("excel_path") or "")
    if new and not path.parent.is_dir():
        add("block", f"پوشه‌ای که فایل باید در آن ساخته شود («{path.parent}») پیدا نشد.", "columns")
    elif not path.is_file():
        if new:
            add("ok", f"«{path.name}» در اولین ثبت با ستون‌های خودش ساخته می‌شود.")
        else:
            add("block", f"فایل «{path.name}» در مسیرش پیدا نشد؛ اگر جابه‌جا شده، از «تنظیمات فایل» دوباره انتخابش کنید.", "file")
    else:
        lock = lock_status(path)
        if lock["write_blocked"] or lock["owner_file"]:
            if load_settings().review_copy_first:
                add("warn", "فایل در Excel باز است؛ ثبت در کپی انجام می‌شود، ولی برای اعمال روی فایل اصلی باید آن را ببندید.")
            else:
                add("block", "فایل در Excel باز است. تغییراتش را ذخیره کنید و Excel را ببندید، بعد «ثبت» را بزنید.")
        try:
            heads = _sheet_headers(path, wp["sheet"], int(wp.get("header_row") or 1))
        except Exception:
            heads = None
            add("block", "فایل باز نشد؛ ممکن است خراب یا رمزدار باشد.", "file")
        else:
            if heads is None:
                add("block", f"شیت «{wp['sheet']}» در فایل پیدا نشد؛ ستون‌ها را دوباره تأیید کنید.", "columns")
            elif not new:
                changed = [(c, h, heads.get(c, "")) for c, h in (wp.get("headers") or {}).items()
                           if normalize_text(str(h or "")) != normalize_text(heads.get(c, ""))]
                if changed:
                    c, was, now_ = changed[0]
                    add("block", f"ستون‌های فایل از زمان تأیید عوض شده‌اند (مثلاً ستون {c} قبلاً «{was}» بود و حالا «{now_ or 'خالی'}» است). "
                                 "ستون‌ها را دوباره تأیید کنید تا ردیف‌ها در ستون اشتباه نوشته نشوند.", "columns")
                extra = [f"«{h}»" for c, h in heads.items() if c not in (wp.get("headers") or {})]
                if extra:
                    add("warn", f"ستون تازه {'، '.join(extra[:3])} به فایل اضافه شده و برنامه چیزی در آن نمی‌نویسد. "
                                "اگر باید پر شود، ستون‌ها را دوباره تأیید کنید.", "columns")
        try:
            key = ("risks", str(path), path.stat().st_mtime)
            if key not in _check_cache:
                _check_cache[key] = inspect_workbook(path)["risks"]
            for r in _check_cache[key]:
                add("block" if r["level"] == "block" else "warn", r["message"])
        except Exception:
            log.exception("inspect for check failed")
    if not any(x["level"] == "block" for x in out):
        rows = _file_rows(prof) or {}
        if path.is_file():
            from .normalizer import to_persian_digits
            add("ok", f"فایل آماده ثبت است؛ ردیف‌های تازه زیر آخرین ردیف (ردیف {to_persian_digits(str(rows.get('last_row', '؟')))}) نوشته می‌شوند"
                      " و پیش از ثبت از فایل پشتیبان گرفته می‌شود.")
    return {"items": out, "blocked": any(x["level"] == "block" for x in out)}


@app.get("/api/files/{fid}/why")
def file_why(fid: int):
    """چرا از این ویس ردیفی ساخته نشد: متن ویس و راهنمای کیفیت ضبط."""
    f = _get_file(fid)
    t = db().transcript(fid) or {}
    return {"status": f["status"], "error": f["error"] or "", "text": t.get("processed_text") or t.get("raw_text") or "",
            "audio": not f["audio_deleted"]}


@app.post("/api/dests/{name}/open")
def dest_open(name: str):
    """باز کردن خود فایل اکسل (یا پوشه‌اش اگر هنوز ساخته نشده)؛ فقط فایل‌های همین فهرست."""
    prof = excel_mapping.load_profile(name)
    if not prof:
        err(404, "این فایل در فهرست نیست.")
    path = excel_template.target_path(prof) if prof.get("mode") == "new" else Path(prof.get("excel_path") or "")
    target = path if path.is_file() else path.parent
    if not str(path) or not target.exists():
        err(404, "فایل یا پوشه‌اش پیدا نشد.")
    if hasattr(os, "startfile"):
        os.startfile(str(target))  # noqa: S606 - فقط فایل‌های فهرست
    return {"opened": str(target), "file": path.is_file()}


class AdoptIn(BaseModel):
    source: str  # نام فایلی که دیگر در فهرست نیست


@app.post("/api/dests/{name}/adopt")
def dest_adopt(name: str, body: AdoptIn):
    """ویس‌های ثبت‌نشده‌ای که فایلشان از فهرست حذف شده، به این فایل منتقل می‌شوند."""
    if not excel_mapping.load_profile(name):
        err(404, "این فایل در فهرست نیست.")
    if excel_mapping.load_profile(body.source):
        err(400, "آن فایل هنوز در فهرست هست؛ ویس‌ها را از خود آن منتقل کنید.")
    with db().tx() as c:
        n = c.execute("""UPDATE audio_files SET dest=? WHERE COALESCE(dest,'')=? AND NOT EXISTS(
                           SELECT 1 FROM records r WHERE r.audio_id=audio_files.id AND r.exported_at IS NOT NULL)""",
                      (name, body.source)).rowcount
    return {"moved": n}


@app.post("/api/templates/{name}/activate")
def template_activate(name: str):
    if not excel_mapping.load_profile(name):
        err(404, "این فایل در فهرست نیست.")
    save_settings({"active_profile": name})
    _excel_cache["key"] = None
    return {"ok": True}


def _template_rows(body: dict) -> tuple[dict, list[list[str]], list[str]]:
    """مقدار ستون‌ها و رنگ ردیف برای چند رکورد نمونه، با همان قواعدی که در ثبت به کار می‌رود."""
    tpl = _clean_template(body)
    prof = excel_template.writer_profile(tpl, create=False)
    cols = list(prof["headers"])
    today = format_jalali(today_jalali())
    rows, colors = [], []
    for i, rec in enumerate(_sample_records(), start=1):
        cells = excel_mapping.cell_values(prof, rec)
        rows.append([str(i) if prof["columns"][c] == "row_number" else cells.get(c, "") for c in cols])
        colors.append(excel_template.highlight(prof["policy"], rec, today))
    return tpl, rows, colors


def _company_preview(body: dict) -> dict:
    """پیش‌نمایش «فایل موجود»: ستون‌های خود فایل به ترتیب واقعی، با ستون‌ها و قالب مقادیرِ (ذخیره‌نشده) صفحه."""
    from openpyxl.utils import column_index_from_string

    name = str(body.get("name") or "")
    saved = excel_mapping.load_profile(name) or {}
    if (name != excel_mapping.COMPANY and not saved) or saved.get("mode") == "new":
        err(404, "این فایل در فهرست نیست.")
    headers = body.get("headers") if isinstance(body.get("headers"), dict) else saved.get("headers")
    if not headers:
        err(400, "اول فایل اکسل موجود را انتخاب کنید.")
    headers = {str(c): str(h or "") for c, h in headers.items() if re.fullmatch(r"[A-Z]{1,3}", str(c))}
    allowed = {k for k, _, _ in FIELD_DEFS} | set(COMPUTED_FIELDS) | {"followup"}
    cols = body.get("columns") if isinstance(body.get("columns"), dict) else saved.get("columns") or {}
    columns = {c: f for c, f in cols.items() if c in headers and f in allowed}
    prot = body.get("protected") if isinstance(body.get("protected"), list) else saved.get("protected") or []
    policy = {**saved.get("policy", excel_mapping.DEFAULT_POLICY), **{k: v for k, v in (body.get("policy") or {}).items()
                                                                     if k in excel_mapping.VALUE_FORMAT_KEYS}}
    if "highlights" in policy:
        policy["highlights"] = excel_template.clean_highlights(policy["highlights"])
    prof = {**saved, "headers": headers, "columns": columns, "policy": policy}
    letters = sorted(headers, key=column_index_from_string)
    today = format_jalali(today_jalali())
    rows, colors = [], []
    for i, rec in enumerate(_sample_records(), start=1):
        cells = excel_mapping.cell_values(prof, rec)
        rows.append([str(i) if columns.get(c) == "row_number" else cells.get(c, "") for c in letters])
        colors.append(excel_template.highlight(policy, rec, today))
    return {"headers": [headers[c] for c in letters], "letters": letters, "fields": [columns.get(c, "") for c in letters],
            "protected": [c for c in prot if c in headers and c not in columns], "rows": rows, "colors": colors,
            "target": Path(saved.get("excel_path") or "").name, "demo": not _has_records()}


def _has_records() -> bool:
    return db().one("SELECT COUNT(*) n FROM records WHERE review_state!='rejected'")["n"] > 0


@app.post("/api/templates/preview")
def template_preview(body: dict):
    if body.get("mode") != "new":
        return _company_preview(body)
    from openpyxl.utils import get_column_letter

    tpl, rows, colors = _template_rows(body)
    return {"headers": [c["title"] for c in tpl["columns_list"]], "rows": rows, "colors": colors,
            "letters": [get_column_letter(i) for i in range(1, len(tpl["columns_list"]) + 1)],
            "target": excel_template.target_path(tpl).name, "demo": not _has_records()}


@app.post("/api/templates/sample")
def template_sample(body: dict):
    tpl, rows, _ = _template_rows(body)
    data = excel_template.build_sample(tpl, rows)
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=sample.xlsx"})


@app.get("/api/exports")
def exports(dest: str = "", limit: int = 300):
    """تاریخچه ثبت‌ها: هر ثبت با تاریخ شمسی، فایل، ردیف‌ها و نام ساختمان‌های هر ردیف."""
    import json
    rows = db().q("""SELECT id, created_at, target_path, output_path, backup_path, profile, rows_written, first_row,
                            last_row, status, replaced_original_at, report_json FROM exports
                     WHERE ?='' OR profile=? ORDER BY id DESC LIMIT ?""", (dest, dest, max(1, min(limit, 2000))))
    for e in rows:
        rep = json.loads(e.pop("report_json") or "{}")
        ids = [x["record_id"] for x in rep.get("rows", [])]
        names = {r["id"]: (r["values"].get("engineer_name", ""), r["original_name"])
                 for r in db().list_records(f"r.id IN ({','.join('?' * len(ids))})", tuple(ids))} if ids else {}
        e["items"] = [{"row": x["row"], "name": names.get(x["record_id"], ("", ""))[0], "voice": names.get(x["record_id"], ("", ""))[1]}
                      for x in rep.get("rows", [])]
        e["file"] = Path(e["target_path"]).name
        prof = excel_mapping.load_profile(e["profile"] or "")
        e["dest_listed"] = bool(prof)
        try:
            dt = datetime.fromisoformat(e["created_at"])
            e["date_jalali"], e["time"] = format_jalali(from_gregorian(dt.date())), dt.strftime("%H:%M")
        except (TypeError, ValueError):
            e["date_jalali"], e["time"] = "", ""
    return {"exports": rows}


@app.post("/api/exports/{eid}/open")
def export_open(eid: int):
    """باز کردن فایلی که این ثبت در آن نوشته شده (یا فایل کپی، اگر هنوز روی فایل اصلی اعمال نشده)."""
    e = _get_export(eid)
    p = Path(e["output_path"] if e["status"] == "created" else e["target_path"])
    if not p.is_file():
        err(404, "فایل پیدا نشد؛ ممکن است جابه‌جا یا پاک شده باشد.")
    # مسیر از سابقه خود برنامه می‌آید، نه از درخواست؛ کپی ثبت‌نشده فقط از پوشه داده‌های برنامه
    if e["status"] == "created" and not p.resolve().is_relative_to(DATA_DIR.resolve()):
        err(403, "باز کردن این مسیر مجاز نیست.")
    if hasattr(os, "startfile"):
        os.startfile(str(p))  # noqa: S606 - فایلی که خود برنامه در آن ثبت کرده
    return {"opened": str(p)}


def _get_export(eid: int) -> dict:
    e = db().one("SELECT * FROM exports WHERE id=?", (eid,))
    if not e:
        err(404, "این ثبت پیدا نشد.")
    return e


@app.post("/api/exports/{eid}/replace-original")
def export_replace(eid: int):
    import json
    e = _get_export(eid)
    if e["status"] != "created":
        err(409, "این ثبت قبلاً روی فایل اعمال یا برگردانده شده است.")
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
        err(409, "این ثبت قبلاً برگردانده شده است.")
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
    msg = "ردیف‌ها به حالت «آماده ثبت» برگشتند."
    if restored:
        msg = "ثبت برگشت: فایل اکسل به حالت پیش از ثبت برگشت و ردیف‌ها دوباره آماده ثبت‌اند."
    elif e["replaced_original_at"]:
        msg += " فایل اصلی پس از ثبت تغییر کرده بود و دست نخورد؛ نسخه پیش از ثبت در پوشه backups هست."
    return {"ok": True, "restored": restored, "message": msg}


@app.get("/api/exports/{eid}/download")
def export_download(eid: int):
    e = _get_export(eid)
    p = Path(e["output_path"])
    if not p.exists():
        err(404, "فایل این ثبت پیدا نشد.")
    return FileResponse(p, filename=p.name)


class OpenIn(BaseModel):
    path: str


@app.post("/api/open-folder")
def open_folder(body: OpenIn):
    p = Path(body.path)
    target = p if p.is_dir() else p.parent
    allowed = [DATA_DIR.resolve()]
    for n in excel_mapping.list_profiles():
        prof = _write_profile(name=n)
        if prof and prof.get("excel_path"):
            allowed.append(Path(prof["excel_path"]).resolve().parent)
    if not target.is_dir() or not any(target.resolve().is_relative_to(a) for a in allowed):  # نه «data-دیگر»
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
        "license": _license_out(),
        "performance": perf,
    }


@app.put("/api/settings")
def put_settings(updates: dict):
    allowed = {"model_name", "compute_type", "cpu_threads", "beam_size", "vad_filter", "initial_prompt",
               "use_dictionary_hotwords", "hotwords_limit", "review_spoken_phones", "learn_auto_threshold", "kb_auto_spelling","model_idle_minutes", "required_fields", "default_area_code", "default_city",
               "similarity_suggest", "min_duration_sec", "open_browser", "inbox_dir", "review_copy_first"}
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


WIPE_PHRASE = "پاک شود"


class WipeIn(BaseModel):
    confirm: str


@app.post("/api/maintenance/wipe")
def wipe_all(body: WipeIn):
    """پاک‌کردن کامل اطلاعات (مثلاً پیش از تحویل رایانه به دیگری): رکوردها، متن و فایل ویس‌ها، واژه‌نامه
    آموخته، پشتیبان‌ها، نسخه‌های اکسل داخل پوشه برنامه و گزارش‌ها. تنظیمات و قالب‌های اکسل می‌مانند؛
    فایل اکسل اصلی و فایل‌های ساخته‌شده در پوشه‌های کاربر دست نمی‌خورند."""
    if body.confirm.strip() != WIPE_PHRASE:
        err(400, f"برای پاک‌کردن، عبارت «{WIPE_PHRASE}» را دقیقاً بنویسید.")
    worker().cancel()
    worker().join(20)
    if worker().running:
        err(409, "پردازش هنوز در جریان است؛ چند ثانیه دیگر دوباره امتحان کنید.")
    db().wipe_all()
    for sub in ("uploads", "tmp", "outputs", "backups", "reports", "auto-backups"):
        shutil.rmtree(DATA_DIR / sub, ignore_errors=True)
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    for p in (DATA_DIR / "logs").glob("*.log*"):
        try:
            p.unlink()
        except OSError:  # فایل گزارشی که الان باز است فقط خالی می‌شود
            p.write_bytes(b"")
    log.warning("همه اطلاعات برنامه به درخواست کاربر پاک شد.")
    return {"ok": True}


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
    db().bind_unassigned(load_settings().active_profile)
    db().log_event(f"اطلاعات از پشتیبان «{name}» بازگردانده شد (پشتیبان وضعیت قبلی: {res['safety_backup']}).", "warning")
    return res


class BackupEncryptionIn(BaseModel):
    enabled: bool
    password: str = ""


@app.get("/api/backups/encryption")
def backups_encryption():
    return backup.encryption_status()


@app.put("/api/backups/encryption")
def backups_encryption_set(body: BackupEncryptionIn):
    try:
        return backup.set_encryption(body.enabled, body.password)
    except backup.BackupError as e:
        err(400, str(e))


@app.post("/api/backups/{name}/export")
def backups_export(name: str):
    """دریافت پشتیبان؛ اگر رمزگذاری در تنظیمات روشن باشد با گذرواژه همان‌جا قفل می‌شود."""
    try:
        data, encrypted = backup.export_backup(name)
    except backup.BackupError as e:
        err(400, str(e))
    filename = f"{Path(name).stem}.v2xbak" if encrypted else name
    return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/backups/import")
async def backups_import(file: UploadFile = File(...), password: str = Form("")):
    try:
        return backup.import_backup(await _read_upload(file, 1024 ** 3), password)
    except backup.BackupError as e:
        err(400, str(e))


# DataVox.exe نسخه جدید این متغیر را می‌گذارد و با دیدن کد خروج RESTART_FOR_UPDATE، به‌روزرسانی را اعمال و
# موتور را دوباره راه‌اندازی می‌کند (پنجره برنامه باز می‌ماند و خودش دوباره بارگذاری می‌شود)
RESTART_FOR_UPDATE = 75


def _one_click_update() -> bool:
    return os.environ.get("V2X_LAUNCHER") == "2"


@app.get("/api/update")
def update_info():
    return {"version": __version__, "supported": updater.current_runtime_id() is not None,
            "staged": updater.staged_info(), "one_click": _one_click_update()}


@app.post("/api/update/apply")
def update_apply():
    """نصب بسته آماده بدون بستن دستی: موتور خاموش می‌شود و اجراکننده نسخه جدید را جایگزین و روشن می‌کند."""
    if not updater.staged_info():
        err(409, "بسته به‌روزرسانی آماده‌ای نیست.")
    if not _one_click_update():
        err(409, "این نسخه از برنامه نصب خودکار ندارد؛ برنامه را با «خروج از برنامه» ببندید و دوباره باز کنید.")
    db().log_event("نصب به‌روزرسانی شروع شد؛ برنامه چند ثانیه دیگر با نسخه جدید باز می‌شود.")
    worker().cancel()

    def restart():
        worker().join(20)  # ویس در حال پردازش به صف برمی‌گردد
        os._exit(RESTART_FOR_UPDATE)

    threading.Timer(0.5, restart).start()
    return {"restarting": True, "from": __version__, "to": updater.staged_info()["version"]}


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
    """صفحه اصلی با کلید محرمانه همین اجرا (فقط این صفحه آن را دارد)."""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    meta = f'<meta name="v2x-token" content="{API_TOKEN}">'
    return HTMLResponse(html.replace("</head>", f"  {meta}\n</head>", 1),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # pragma: no cover
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": f"خطای داخلی: {type(exc).__name__}"})
