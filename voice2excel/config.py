"""تنظیمات برنامه: مسیرها، مدل گفتار و قواعد اعتبارسنجی.

تنظیمات کاربر در data/settings.json ذخیره می‌شود و مقادیر پیش‌فرض این فایل را
بازنویسی می‌کند. هیچ تنظیمی نیاز به اینترنت ندارد.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("V2X_DATA_DIR", ROOT_DIR / "data"))
MODELS_DIR = Path(os.environ.get("V2X_MODELS_DIR", ROOT_DIR / "models"))
WEB_DIR = Path(__file__).resolve().parent / "web"
# ویس‌ها و فایل اکسل نمونه (در نسخه قابل‌حمل) برای امتحان سریع برنامه
SAMPLES_DIR = Path(os.environ.get(
    "V2X_SAMPLES_DIR",
    ROOT_DIR / "samples" if (ROOT_DIR / "samples").is_dir() else ROOT_DIR / "packaging" / "samples",
))

SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".ogg", ".oga", ".opus", ".amr", ".aac", ".flac",
    ".wma", ".webm", ".mp4", ".3gp", ".mpeg", ".mpga", ".aiff", ".aif",
}

# مدل‌های قابل انتخاب faster-whisper (همگی محلی و رایگان)
AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


@dataclass
class Settings:
    # --- گفتار ---
    # انتخاب بر اساس آزمون (data/reports و README): turbo تنها مدلی بود که شماره‌ها را درست شنید؛
    # حدود ۱٫۹ گیگ RAM و ۱۲ ثانیه برای ویس ۱۵ ثانیه‌ای. small گزینه پشتیبان رایانه‌های ضعیف‌تر است.
    model_name: str = "large-v3-turbo"
    compute_type: str = "int8"
    cpu_threads: int = 0  # 0 = خودکار
    # روی ۹ ویس واقعی: ۲ همان دقت ۵ را داشت با حدود نصف زمان (۱۷ ثانیه به‌جای ۳۲)؛ ۱ دقت شماره را کم کرد
    beam_size: int = 2
    language: str = "fa"
    vad_filter: bool = True
    # متن راهنمای سبک برای Whisper. آزمون نشان داد:
    # - رقم در متن راهنما مدل small را به حلقه تولید رقم‌های بی‌معنی می‌اندازد؛
    # - نام شخص در متن راهنما به خروجی نشت می‌کند.
    # پس فقط واژه‌های عمومی حوزه، بدون رقم و بدون نام.
    initial_prompt: str = (
        "سلام، مهندس، شماره تماس، آدرس خیابان، کوچه، پلاک، قطعه دوم، نبش، سازه فلز، سازه بتن، "
        "تعداد سقف، سقف‌ها اجرا شده، تازه استارت خورده، دیوارچینی، زنگ بزنین."
    )
    # ارسال پرکاربردترین نام‌های واژه‌نامه به مدل گفتار (hotwords). خاموش، چون آزمون A/B روی ۸ ویس
    # (۲۰۲۶-۱۰-۲۳، large-v3-turbo، واژه‌نامه پرشده از فایل شرکت) نشان داد: تکرار ساختگی «مهندس»،
    # نام ساختگی، از دست رفتن شماره یا آدرس در ۳ ویس و ۲ تا ۴ برابر کندی. نام درست از راه پیشنهاد
    # واژه‌نامه پس از تشخیص گفتار به دست می‌آید.
    use_dictionary_hotwords: bool = False
    hotwords_limit: int = 40

    # مدل پس از این چند دقیقه بی‌کاری از حافظه آزاد می‌شود (بارگذاری دوباره حدود ۱۵ تا ۶۰ ثانیه طول می‌کشد)
    model_idle_minutes: float = 10.0

    # --- صوت ---
    min_duration_sec: float = 0.6
    max_duration_sec: float = 600.0
    silence_rms_threshold: float = 0.003

    # --- اعتبارسنجی ---
    required_fields: list[str] = field(
        default_factory=lambda: ["engineer_name", "phone", "address"]
    )
    # هر شماره تلفنِ تشخیص‌داده‌شده تا کالیبره‌شدن با ویس واقعی به بازبینی برود.
    # دلیل: در آزمون، مدل «سه» را «سی» شنید و شماره‌ای با قالب درست ولی رقم غلط ساخت
    # (هم وقتی عدد را با حروف نوشت، هم وقتی با رقم).
    review_spoken_phones: bool = True
    # پیش‌شماره شهر برای شماره‌های ثابت هشت‌رقمی؛ فقط پیشنهاد داده می‌شود (خالی = بدون پیشنهاد). مشهد: 051
    default_area_code: str = "051"
    default_city: str = ""
    # کمینه شباهت برای پیشنهاد «نام مشابه» (فقط پیشنهاد؛ هرگز ادغام خودکار نیست)
    similarity_suggest: float = 0.78
    # اصلاحی که کاربر دست‌کم این تعداد بار تکرار کرده، در ویس‌های بعدی خودکار اعمال می‌شود (کمتر: فقط پیشنهاد)
    learn_auto_threshold: int = 2
    # املای هم‌آوای نام مهندس و خیابان («فلاهی»، «کازمی») به املای واژه‌نامه برگردد (فقط اگر یک گزینه باشد)
    kb_auto_spelling: bool = True
    # داده پایه نشانی‌های شهر در کنار واژه‌نامه (در رابط کاربری نمایش داده نمی‌شود)
    kb_base_pack: bool = True

    # --- اکسل ---
    active_profile: str = "default"
    last_excel_path: str = ""

    # --- آپلود از گوشی در شبکه محلی ---
    # خاموش: برنامه فقط روی همین رایانه در دسترس است. روشن: فقط صفحه آپلود (/m) با رمز از شبکه محلی باز می‌شود
    lan_enabled: bool = False
    lan_pin: str = ""
    lan_auto_start: bool = True  # پردازش ویس‌های رسیده از گوشی خودکار شروع شود
    lan_idle_hours: int = 0  # خاموش شدن خودکار پس از این مدت بی‌استفاده (۰ = هرگز)

    # --- پوشه ورودی خودکار (خالی = خاموش) ---
    inbox_dir: str = ""

    # --- سرور ---
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True

    @property
    def model_path(self) -> Path:
        return MODELS_DIR / self.model_name

    def effective_threads(self) -> int:
        if self.cpu_threads > 0:
            return self.cpu_threads
        return max(1, min(8, (os.cpu_count() or 2) - 1))


_lock = threading.Lock()
_settings: Settings | None = None


def settings_path() -> Path:
    return DATA_DIR / "settings.json"


def ensure_dirs() -> None:
    for sub in ("", "uploads", "outputs", "backups", "logs", "profiles", "reports", "tmp"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    global _settings
    with _lock:
        if _settings is None:
            s = Settings()
            p = settings_path()
            if p.exists():
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    known = {f.name for f in fields(Settings)}
                    for k, v in raw.items():
                        if k in known:
                            setattr(s, k, v)
                except (OSError, ValueError):
                    pass  # فایل خراب: پیش‌فرض‌ها استفاده می‌شوند
            _settings = s
        return _settings


def save_settings(updates: dict) -> Settings:
    """فقط مقادیری که کاربر تغییر داده ذخیره می‌شوند؛ بقیه از پیش‌فرض نسخه فعلی برنامه می‌آیند."""
    s = load_settings()
    known = {f.name for f in fields(Settings)}
    with _lock:
        ensure_dirs()
        stored: dict = {}
        if settings_path().exists():
            try:
                stored = json.loads(settings_path().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                stored = {}
        for k, v in updates.items():
            if k in known:
                setattr(s, k, v)
                stored[k] = v
        tmp = settings_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, settings_path())
    return s


def reset_settings_cache() -> None:
    global _settings
    with _lock:
        _settings = None
