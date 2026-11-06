"""موتورهای گفتار نسخه oldcpu، برای رایانه‌هایی که پردازنده‌شان SSE4.1 ندارد (Pentium Dual-Core، Core 2 قدیمی).

موتور اصلی faster-whisper/CTranslate2 روی این پردازنده‌ها اجرا نمی‌شود؛ به‌جای آن دو موتور با همان مدل
large-v3-turbo داریم:
- آنلاین (Cloudflare Workers AI): چند ثانیه برای هر ویس. ویس فقط برای تبدیل به متن فرستاده می‌شود.
- روی همین رایانه (whisper.cpp ساخته‌شده برای Core 2، فایل engine/dvwhisper.dll): بدون اینترنت ولی کند،
  حدود چند دقیقه برای هر ویس. هر وقت موتور آنلاین در دسترس نباشد، خودکار به کار می‌افتد.
"""
from __future__ import annotations

import base64
import ctypes
import io
import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from .config import MODELS_DIR, ROOT_DIR
from .logger import get_logger

log = get_logger("engines")

ENGINE_DIR = Path(os.environ.get("V2X_ENGINE_DIR", ROOT_DIR / "engine"))
CLOUD_CRED = Path(os.environ.get("V2X_CLOUD_CRED", ROOT_DIR / "cloud.json"))
LOCAL_MODEL_FILE = "ggml-large-v3-turbo-q8_0.bin"
CLOUD_MODEL = "@cf/openai/whisper-large-v3-turbo"
CLOUD_CHUNK_SEC = 240  # ویس بلندتر در چند تکه فرستاده می‌شود
SR = 16000


class CloudUnavailable(Exception):
    def __init__(self, reason: str, message: str, retry_after: float):
        super().__init__(message)
        self.reason = reason
        self.retry_after = retry_after


class EngineCancelled(Exception):
    pass


# ---------- ساخت کلمه‌ها و بخش‌ها ----------
def _words_from_tokens(tokens: list[dict]) -> list[dict]:
    """نشانه‌های whisper (بایت UTF-8) به کلمه؛ نشانه‌ای که با فاصله شروع شود، کلمه تازه است."""
    words, cur, cur_tokens = [], b"", []

    def flush():
        if cur_tokens:
            text = cur.decode("utf-8", "replace").strip()
            if text:
                ps = [t["p"] for t in cur_tokens]
                words.append({"word": text, "start": round(cur_tokens[0]["t0"] / 100, 2),
                              "end": round(cur_tokens[-1]["t1"] / 100, 2), "prob": round(sum(ps) / len(ps), 3)})

    for t in tokens:
        b = bytes.fromhex(t["h"])
        if b.startswith(b" ") and cur_tokens:
            flush()
            cur, cur_tokens = b"", []
        cur += b
        cur_tokens.append(t)
    flush()
    return words


def parse_local_result(raw: str) -> dict:
    d = json.loads(raw)
    segments, words, texts, logprobs = [], [], [], []
    for s in d.get("segments", []):
        text = bytes.fromhex(s["text"]).decode("utf-8", "replace").strip()
        toks = s.get("tokens", [])
        lp = [t["plog"] for t in toks]
        avg = sum(lp) / len(lp) if lp else None
        segments.append({"start": round(s["t0"] / 100, 2), "end": round(s["t1"] / 100, 2), "text": text,
                         "avg_logprob": round(avg, 3) if avg is not None else None,
                         "no_speech_prob": round(s.get("nsp", 0.0), 3)})
        words.extend(_words_from_tokens(toks))
        if text:
            texts.append(text)
        if avg is not None:
            logprobs.append(avg)
    return {"text": " ".join(texts), "segments": segments, "words": words, "language": "fa", "language_prob": 1.0,
            "avg_logprob": round(sum(logprobs) / len(logprobs), 3) if logprobs else None}


# ---------- موتور روی همین رایانه ----------
class LocalEngine:
    """whisper.cpp برای پردازنده‌های قدیمی (SSSE3)؛ مدل فقط هنگام نیاز بارگذاری می‌شود (~۱ گیگ RAM)."""

    def __init__(self):
        self._lib = None
        self._ctx = None
        self._lock = threading.Lock()

    @staticmethod
    def dll_path() -> Path:
        return ENGINE_DIR / "dvwhisper.dll"

    @staticmethod
    def model_path() -> Path:
        return MODELS_DIR / LOCAL_MODEL_FILE

    @classmethod
    def available(cls) -> bool:
        return cls.dll_path().exists() and cls.model_path().exists()

    @property
    def loaded(self) -> bool:
        return self._ctx is not None

    def _load_lib(self):
        if self._lib is None:
            lib = ctypes.CDLL(str(self.dll_path()))
            lib.dvw_init.restype = ctypes.c_void_p
            lib.dvw_init.argtypes = [ctypes.c_char_p]
            lib.dvw_free.argtypes = [ctypes.c_void_p]
            lib.dvw_free_str.argtypes = [ctypes.c_void_p]
            lib.dvw_system_info.restype = ctypes.c_char_p
            lib.dvw_transcribe.restype = ctypes.c_void_p
            lib.dvw_transcribe.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p,
                                           ctypes.POINTER(ctypes.c_int)]
            self._lib = lib
        return self._lib

    def load(self):
        with self._lock:
            if self._ctx is None:
                lib = self._load_lib()
                t0 = time.time()
                ctx = lib.dvw_init(str(self.model_path()).encode("utf-8"))
                if not ctx:
                    raise RuntimeError("بارگذاری مدل گفتار روی این رایانه ناموفق بود (فایل مدل خراب است یا RAM کافی نیست).")
                self._ctx = ctx
                log.info("موتور روی رایانه آماده شد (%.1f ثانیه)", time.time() - t0)

    def unload(self):
        with self._lock:
            if self._ctx is not None:
                self._lib.dvw_free(self._ctx)
                self._ctx = None

    def transcribe(self, audio: np.ndarray, threads: int, beam: int, language: str, prompt: str | None,
                   should_stop: Callable[[], bool] | None = None) -> dict:
        self.load()
        pcm = np.ascontiguousarray(audio, dtype=np.float32)
        flag = ctypes.c_int(0)
        done = threading.Event()

        def watch():  # درخواست توقف کاربر به موتور می‌رسد
            while not done.wait(0.3):
                if should_stop and should_stop():
                    flag.value = 1
                    return

        threading.Thread(target=watch, daemon=True).start()
        try:
            with self._lock:
                ptr = self._lib.dvw_transcribe(self._ctx, pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), len(pcm),
                                               threads, beam, (language or "fa").encode(),
                                               (prompt or "").encode("utf-8"), ctypes.byref(flag))
        finally:
            done.set()
        if not ptr:
            raise RuntimeError("موتور گفتار روی این رایانه پاسخی نداد.")
        try:
            raw = ctypes.string_at(ptr).decode("ascii")
        finally:
            self._lib.dvw_free_str(ptr)
        if flag.value:
            raise EngineCancelled()
        d = json.loads(raw)
        if "error" in d:
            raise RuntimeError(f"تبدیل ویس روی این رایانه ناموفق بود (کد {d['error']}).")
        return parse_local_result(raw)


# ---------- موتور آنلاین ----------
def _load_cred() -> tuple[str, str] | None:
    try:
        d = json.loads(CLOUD_CRED.read_text(encoding="utf-8"))
        token = base64.b64decode(d["t"]).decode()[::-1] if "t" in d else d["token"]
        return d.get("a") or d["account"], token
    except (OSError, ValueError, KeyError):
        return None


def _wav_bytes(audio: np.ndarray) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _ssl_context() -> ssl.SSLContext:
    # ریشه‌های گواهی ویندوز ۷ بدون به‌روزرسانی ممکن است قدیمی باشند؛ فهرست certifi همراه بسته است
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _seconds_to_utc_midnight() -> float:
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return (nxt - now).total_seconds()


def _split_points(audio: np.ndarray) -> list[int]:
    """مرز تکه‌ها: نزدیک هر ۲۴۰ ثانیه، در کم‌صداترین لحظه ±۵ ثانیه تا کلمه‌ای نصف نشود."""
    n, step, win = len(audio), CLOUD_CHUNK_SEC * SR, 5 * SR
    points, pos = [0], 0
    while n - pos > step:
        lo, hi = pos + step - win, min(n, pos + step + win)
        seg = audio[lo:hi]
        frame = 800
        k = len(seg) // frame
        if k > 0:
            energy = (seg[:k * frame].reshape(k, frame) ** 2).mean(axis=1)
            cut = lo + int(energy.argmin()) * frame + frame // 2
        else:
            cut = pos + step
        points.append(cut)
        pos = cut
    points.append(n)
    return points


class CloudEngine:
    def __init__(self):
        self.cred = _load_cred()

    @property
    def configured(self) -> bool:
        return self.cred is not None

    def _post(self, body: dict, timeout: float) -> dict:
        acc, token = self.cred
        url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{CLOUD_MODEL}"
        req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            code = e.code
            if code == 429:
                raise CloudUnavailable("quota", "سهمیه رایگان امروز موتور آنلاین تمام شد.", _seconds_to_utc_midnight())
            if code in (401, 403):
                raise CloudUnavailable("auth", "حساب موتور آنلاین پذیرفته نشد.", 3600)
            if code == 413:
                raise CloudUnavailable("size", "ویس برای موتور آنلاین بیش از حد بزرگ است.", 0)
            raise CloudUnavailable("server", f"موتور آنلاین خطا داد ({code}).", 300)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as e:
            raise CloudUnavailable("network", f"اتصال به موتور آنلاین برقرار نشد ({type(e).__name__}).", 300)
        except ValueError:
            raise CloudUnavailable("server", "پاسخ موتور آنلاین قابل خواندن نبود.", 300)
        if not d.get("success"):
            errs = d.get("errors") or []
            if any("limit" in str(x.get("message", "")).lower() or x.get("code") == 4006 for x in errs):
                raise CloudUnavailable("quota", "سهمیه رایگان امروز موتور آنلاین تمام شد.", _seconds_to_utc_midnight())
            raise CloudUnavailable("server", "موتور آنلاین پاسخ ناموفق داد.", 300)
        return d["result"]

    def transcribe(self, audio: np.ndarray, language: str, prompt: str | None, vad: bool,
                   should_stop: Callable[[], bool] | None = None) -> dict:
        points = _split_points(audio)
        segments, words, texts, logprobs = [], [], [], []
        lang_prob = 1.0
        for a, b in zip(points, points[1:]):
            if should_stop and should_stop():
                raise EngineCancelled()
            chunk = audio[a:b]
            off = a / SR
            body = {"audio": base64.b64encode(_wav_bytes(chunk)).decode(), "task": "transcribe",
                    "language": language or "fa", "vad_filter": bool(vad)}
            if prompt:
                body["initial_prompt"] = prompt
            r = self._post(body, timeout=60 + len(chunk) / SR)
            lang_prob = min(lang_prob, float((r.get("transcription_info") or {}).get("language_probability") or 1.0))
            for s in r.get("segments") or []:
                text = (s.get("text") or "").strip()
                segments.append({"start": round(off + float(s.get("start", 0)), 2),
                                 "end": round(off + float(s.get("end", 0)), 2), "text": text,
                                 "avg_logprob": round(float(s["avg_logprob"]), 3) if s.get("avg_logprob") is not None else None,
                                 "no_speech_prob": round(float(s.get("no_speech_prob") or 0), 3)})
                for w in s.get("words") or []:
                    wt = (w.get("word") or "").strip()
                    if wt:
                        words.append({"word": wt, "start": round(off + float(w.get("start", 0)), 2),
                                      "end": round(off + float(w.get("end", 0)), 2), "prob": 1.0})
                if text:
                    texts.append(text)
                if s.get("avg_logprob") is not None:
                    logprobs.append(float(s["avg_logprob"]))
        return {"text": " ".join(texts), "segments": segments, "words": words, "language": language or "fa",
                "language_prob": round(lang_prob, 3),
                "avg_logprob": round(sum(logprobs) / len(logprobs), 3) if logprobs else None}


# ---------- وضعیت (برای صفحه تنظیمات) ----------
class EngineStatus:
    def __init__(self):
        self.cloud_down_until = 0.0
        self.cloud_reason = ""
        self.cloud_message = ""
        self.last_engine = ""
        self.last_at = 0.0

    def as_dict(self, mode: str, cloud: CloudEngine, local: LocalEngine) -> dict:
        now = time.time()
        return {"mode": mode, "cloud_configured": cloud.configured, "local_available": local.available(),
                "local_loaded": local.loaded,
                "cloud_paused_minutes": round(max(0.0, self.cloud_down_until - now) / 60),
                "cloud_reason": self.cloud_reason if self.cloud_down_until > now else "",
                "cloud_message": self.cloud_message if self.cloud_down_until > now else "",
                "last_engine": self.last_engine, "last_at": self.last_at}
