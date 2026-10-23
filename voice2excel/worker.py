"""پردازشگر صف در پس‌زمینه.

فایل‌ها یکی‌یکی پردازش می‌شوند (کنترل مصرف RAM)، نتیجه هر فایل بلافاصله در SQLite
ذخیره می‌شود، خرابی یک فایل صف را متوقف نمی‌کند و پس از بسته‌شدن ناگهانی برنامه،
فایل نیمه‌کاره دوباره به صف برمی‌گردد.
"""
from __future__ import annotations

import gc
import threading
import time
import traceback

from . import dictionary
from .audio_processor import AudioError, check_audio, load_audio
from .config import DATA_DIR, load_settings
from .database import Database
from .logger import get_logger
from .normalizer import normalize_text
from .pipeline import build_records
from .transcriber import ModelMissingError, Transcriber, TranscriptionCancelled

log = get_logger("worker")


def _rss_mb() -> tuple[float, float]:
    try:
        import psutil

        mi = psutil.Process().memory_info()
        peak = getattr(mi, "peak_wset", mi.rss)
        return mi.rss / 1e6, peak / 1e6
    except Exception:
        return 0.0, 0.0


class Worker:
    def __init__(self, db: Database, transcriber=None):
        self.db = db
        self.transcriber = transcriber or Transcriber(load_settings())
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.current_id: int | None = None
        self.current_name: str = ""
        self.current_started: float | None = None
        self.last_error: str = ""
        self.run_started: float | None = None
        self.run_done = 0
        self._idle_timer: threading.Timer | None = None
        self._warm_thread: threading.Thread | None = None

    # ---------- کنترل ----------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self._cancel_idle_unload()
            self._stop.clear()
            self.last_error = ""
            self.run_started = time.time()
            self.run_done = 0
            self._thread = threading.Thread(target=self._loop, name="voice-worker", daemon=True)
            self._thread.start()
            return True

    def cancel(self) -> None:
        """توقف پردازش؛ فایل در حال پردازش به صف برمی‌گردد و نتایج قبلی حفظ می‌شوند."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def state(self) -> dict:
        return {
            "running": self.running,
            "stopping": self.running and self._stop.is_set(),
            "current_id": self.current_id,
            "current_name": self.current_name,
            "current_elapsed": round(time.time() - self.current_started, 1) if self.current_started else None,
            "last_error": self.last_error,
            "run_done": self.run_done,
            "model_state": getattr(self.transcriber, "state", "unloaded"),
        }

    # ---------- آماده نگه داشتن مدل ----------
    def warmup(self) -> bool:
        """بارگذاری مدل در پس‌زمینه (مثلاً هنگام باز شدن صفحه ویس‌ها یا افزودن ویس) تا اولین ویس منتظر نماند."""
        load = getattr(self.transcriber, "load", None)
        if load is None or getattr(self.transcriber, "state", "") in ("ready", "loading"):
            self._schedule_idle_unload()
            return False
        if self._warm_thread and self._warm_thread.is_alive():
            return False
        self.transcriber.settings = load_settings()

        def run():
            try:
                load()
            except Exception as e:  # نبود مدل در شروع صف با پیام روشن گزارش می‌شود
                log.info("پیش‌بارگذاری مدل انجام نشد: %s", e)
            finally:
                if not self.running:
                    self._schedule_idle_unload()

        self._warm_thread = threading.Thread(target=run, name="model-warmup", daemon=True)
        self._warm_thread.start()
        return True

    def _cancel_idle_unload(self) -> None:
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _schedule_idle_unload(self) -> None:
        """مدل (~۲ گیگ RAM) پس از چند دقیقه بی‌کاری آزاد می‌شود؛ هر کار تازه زمان‌سنج را از نو شروع می‌کند."""
        self._cancel_idle_unload()
        minutes = max(0.0, float(load_settings().model_idle_minutes))
        self._idle_timer = threading.Timer(minutes * 60, self._unload_if_idle)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _unload_if_idle(self) -> None:
        if self.running:
            return
        unload = getattr(self.transcriber, "unload", None)
        if unload:
            unload()
            log.info("مدل پس از بی‌کاری از حافظه آزاد شد")
        gc.collect()

    # ---------- حلقه ----------
    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                item = self.db.next_queued()
                if item is None:
                    break
                if not self.db.claim(item["id"]):
                    continue
                stop_all = self._process(item)
                self.run_done += 1
                if stop_all:
                    break
        except Exception as e:  # pragma: no cover - نباید رخ دهد
            self.last_error = f"خطای پردازشگر: {e}"
            log.exception("worker loop failed")
        finally:
            self.current_id = None
            self.current_name = ""
            self.current_started = None
            gc.collect()
            self._schedule_idle_unload()

    def _process(self, item: dict) -> bool:
        """پردازش یک فایل. خروجی True یعنی کل صف باید متوقف شود (مثلاً نبود مدل)."""
        aid = item["id"]
        self.current_id, self.current_name, self.current_started = aid, item["original_name"], time.time()
        settings = load_settings()
        self.transcriber.settings = settings
        t0 = time.time()
        path = DATA_DIR / "uploads" / (item["stored_name"] or "")
        try:
            audio_warnings: list[str] = []
            audio = load_audio(path, audio_warnings)
            info = check_audio(audio, settings)
            self.db.set_audio(aid, duration=round(info.duration, 2))
            hot = dictionary.hotwords(self.db, settings.hotwords_limit) if settings.use_dictionary_hotwords else None
            tr = self.transcriber.transcribe(audio, hotwords=hot or None, should_stop=self._stop.is_set)
            del audio
            gc.collect()
            if not tr.text.strip():
                raise AudioError("در ویس گفتاری تشخیص داده نشد.")
            normalized = normalize_text(tr.text)
            processed, clauses, records = build_records(self.db, settings, normalized, item["visit_date"], aid,
                                                        words=tr.words)
            self.db.save_results(aid, {
                "raw_text": tr.text, "normalized_text": normalized, "processed_text": processed,
                "segments": tr.segments, "words": tr.words, "clauses": clauses,
                "language": tr.language, "language_prob": tr.language_prob,
                "avg_logprob": tr.avg_logprob, "model": tr.model,
            }, records)
            _, peak = _rss_mb()
            for w in audio_warnings:
                self.db.log_event(w, "warning", aid)
            self.db.set_audio(aid, status="done", error=" ".join(audio_warnings) or None, model=tr.model,
                              processing_seconds=round(time.time() - t0, 1), peak_rss_mb=round(peak, 1))
            log.info("فایل %s پردازش شد (%.1f ثانیه)", aid, time.time() - t0)
            return False
        except TranscriptionCancelled:
            self.db.set_audio(aid, status="queued", error="پردازش توسط کاربر متوقف شد؛ با شروع دوباره ادامه می‌یابد.")
            return True
        except ModelMissingError as e:
            self.db.set_audio(aid, status="queued", error=str(e))
            self.last_error = str(e)
            return True
        except AudioError as e:
            self.db.set_audio(aid, status="failed", error=str(e), processing_seconds=round(time.time() - t0, 1))
            self.db.log_event(str(e), "warning", aid)
            return False
        except MemoryError:
            gc.collect()
            msg = "حافظه کافی نبود؛ مدل کوچک‌تری را در تنظیمات انتخاب کنید."
            self.db.set_audio(aid, status="failed", error=msg)
            self.db.log_event(msg, "error", aid)
            return False
        except Exception as e:
            msg = f"خطای غیرمنتظره: {type(e).__name__}: {e}"
            self.db.set_audio(aid, status="failed", error=msg, processing_seconds=round(time.time() - t0, 1))
            self.db.log_event(msg + "\n" + traceback.format_exc(limit=5), "error", aid)
            log.exception("processing failed for %s", aid)
            return False
        finally:
            gc.collect()
