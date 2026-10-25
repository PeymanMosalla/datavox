"""ورودی صوت: بررسی قابلیت خواندن، استانداردسازی به ۱۶ کیلوهرتز تک‌کاناله و کنترل کیفیت.

از PyAV استفاده می‌شود که کتابخانه‌های FFmpeg را با خودش دارد؛ نصب جداگانه FFmpeg لازم نیست.
هر فایل جداگانه خوانده و پس از پردازش از حافظه آزاد می‌شود.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import SUPPORTED_AUDIO_EXTENSIONS, Settings

SAMPLE_RATE = 16000
MAX_AUDIO_BYTES = 1024 ** 3  # یک گیگابایت؛ ویس یک‌ساعته معمولی چند ده مگابایت است

# امضای آغاز فایل‌هایی که صوت نیستند (برنامه، فایل فشرده، سند، صفحه وب) ولی پسوند صوتی گرفته‌اند
_NOT_AUDIO = (b"MZ", b"PK\x03\x04", b"%PDF", b"\x7fELF", b"Rar!", b"7z\xbc\xaf",
              b"\xd0\xcf\x11\xe0", b"{\\rtf", b"#!", b"<")


class AudioError(Exception):
    """خطای قابل فهم برای کاربر."""


@dataclass
class AudioInfo:
    duration: float
    rms: float


def is_supported(name: str) -> bool:
    return Path(name).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def looks_like_audio(head: bytes) -> bool:
    """فایلی که با امضای یک برنامه یا سند شروع شده، فقط تغییر نام داده شده و صوت نیست."""
    return not head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(_NOT_AUDIO)


def _decode(path: Path, warnings: list[str] | None = None) -> np.ndarray:
    """رمزگشایی تکه‌تکه با PyAV و تبدیل به ۱۶ کیلوهرتز تک‌کاناله (بدون بارگذاری کل فایل خام در حافظه).

    اگر انتهای فایل خراب باشد (رایج در ویس‌های ناقص منتقل‌شده)، بخش سالم نگه داشته و هشدار ثبت می‌شود.
    """
    import av

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        if not container.streams.audio:
            raise AudioError("این فایل هیچ بخش صوتی ندارد.")
        stream = container.streams.audio[0]
        try:
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1))
        except av.error.FFmpegError:
            if not chunks:
                raise
            if warnings is not None:
                done = sum(len(c) for c in chunks) / SAMPLE_RATE
                warnings.append(f"بخشی از انتهای فایل خراب بود؛ {done:.0f} ثانیه سالم آن پردازش شد. ویس را برای کامل بودن بررسی کنید.")
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return (np.concatenate(chunks).astype(np.float32) / 32768.0)


def load_audio(path: Path, warnings: list[str] | None = None) -> np.ndarray:
    """خواندن و تبدیل به آرایه float32 تک‌کاناله ۱۶ کیلوهرتز."""
    try:
        import av  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise AudioError("کتابخانه پردازش صوت نصب نیست؛ install.bat را دوباره اجرا کنید.") from e
    if not path.exists():
        raise AudioError("فایل صوتی پیدا نشد (ممکن است حذف شده باشد).")
    if path.stat().st_size == 0:
        raise AudioError("فایل صوتی خالی است (حجم صفر).")
    try:
        audio = _decode(path, warnings)
    except AudioError:
        raise
    except Exception as e:  # PyAV خطاهای گوناگون می‌دهد
        raise AudioError(f"فایل صوتی خراب است یا قالب آن قابل خواندن نیست ({type(e).__name__}).") from e
    if len(audio) == 0:
        raise AudioError("فایل صوتی هیچ داده صوتی ندارد.")
    return audio


def check_audio(audio: np.ndarray, settings: Settings) -> AudioInfo:
    duration = len(audio) / SAMPLE_RATE
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))) if len(audio) else 0.0
    if duration < settings.min_duration_sec:
        raise AudioError(f"ویس بسیار کوتاه است ({duration:.1f} ثانیه).")
    if duration > settings.max_duration_sec:
        raise AudioError(f"ویس بیش از حد طولانی است ({duration / 60:.1f} دقیقه).")
    if rms < settings.silence_rms_threshold:
        raise AudioError("ویس بی‌صدا است یا صدای آن بسیار ضعیف است.")
    return AudioInfo(duration=duration, rms=rms)
