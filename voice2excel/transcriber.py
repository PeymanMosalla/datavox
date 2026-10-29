"""تبدیل گفتار به متن با faster-whisper، کاملاً محلی و روی CPU.

مدل فقط از پوشه models خوانده می‌شود (local_files_only) و در زمان اجرا هیچ تماس
اینترنتی برقرار نمی‌شود. مدل قابل تعویض از طریق تنظیمات است.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .config import MODELS_DIR, Settings
from .logger import get_logger

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

log = get_logger("transcriber")


class ModelMissingError(Exception):
    pass


class TranscriptionCancelled(Exception):
    pass


@dataclass
class TranscriptResult:
    text: str
    segments: list[dict] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    language: str = "fa"
    language_prob: float = 0.0
    avg_logprob: float | None = None
    model: str = ""


def model_dir(name: str) -> Path:
    return MODELS_DIR / name


def model_available(name: str) -> bool:
    d = model_dir(name)
    return (d / "model.bin").exists() and (d / "config.json").exists()


def installed_models() -> list[str]:
    if not MODELS_DIR.exists():
        return []
    return sorted(p.name for p in MODELS_DIR.iterdir() if p.is_dir() and model_available(p.name))


class Transcriber:
    """نگه‌دارنده یک مدل بارگذاری‌شده؛ مدل فقط یک بار در حافظه بارگذاری می‌شود."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._model_key = None
        self._lock = threading.Lock()
        self.loading = False

    def _key(self):
        s = self.settings
        return (s.model_name, s.compute_type, s.effective_threads())

    @property
    def state(self) -> str:
        """unloaded / loading / ready"""
        if self.loading:
            return "loading"
        return "ready" if self._model is not None and self._model_key == self._key() else "unloaded"

    def load(self):
        with self._lock:
            if self._model is not None and self._model_key == self._key():
                return self._model
            self.loading = True
            try:
                return self._load_locked()
            finally:
                self.loading = False

    def _load_locked(self):
        """بارگذاری مدل؛ فقط با قفل _lock فراخوانی می‌شود."""
        name = self.settings.model_name
        if not model_available(name):
            raise ModelMissingError(
                f"مدل گفتار «{name}» در پوشه models پیدا نشد. یک بار با اینترنت فایل "
                f"download_model.bat را اجرا کنید (یا پوشه مدل را دستی کپی کنید)."
            )
        from faster_whisper import WhisperModel

        self._model = None  # آزادسازی مدل قبلی پیش از بارگذاری مدل جدید
        log.info("بارگذاری مدل %s", name)
        self._model = WhisperModel(
            str(model_dir(name)), device="cpu", compute_type=self.settings.compute_type,
            cpu_threads=self.settings.effective_threads(), local_files_only=True,
        )
        self._model_key = self._key()
        return self._model

    def unload(self):
        with self._lock:
            self._model = None
            self._model_key = None

    def transcribe(self, audio: np.ndarray, hotwords: str | None = None,
                   should_stop: Callable[[], bool] | None = None) -> TranscriptResult:
        model = self.load()
        s = self.settings
        kwargs = dict(
            language=s.language or None,
            beam_size=s.beam_size,
            vad_filter=s.vad_filter,
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=s.initial_prompt or None,
        )
        if hotwords:
            kwargs["hotwords"] = hotwords
        segments_iter, info = model.transcribe(audio, **kwargs)
        segments, words, texts, logprobs = [], [], [], []
        for seg in segments_iter:
            if should_stop and should_stop():
                raise TranscriptionCancelled()
            texts.append(seg.text.strip())
            logprobs.append(seg.avg_logprob)
            segments.append({
                "start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip(),
                "avg_logprob": round(seg.avg_logprob, 3), "no_speech_prob": round(seg.no_speech_prob, 3),
            })
            for w in seg.words or []:
                words.append({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2),
                              "prob": round(w.probability, 3)})
        return TranscriptResult(
            text=" ".join(t for t in texts if t),
            segments=segments, words=words,
            language=info.language, language_prob=round(info.language_probability, 3),
            avg_logprob=round(float(np.mean(logprobs)), 3) if logprobs else None,
            model=s.model_name,
        )
