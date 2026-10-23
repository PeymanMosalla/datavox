"""گزارش رخدادها با پوشاندن اطلاعات حساس.

شماره‌های تلفن و رشته‌های عددی طولانی پیش از نوشتن در فایل گزارش پوشانده می‌شوند
و مسیر کامل فایل‌ها ثبت نمی‌شود.
"""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from .config import DATA_DIR

_LONG_DIGITS = re.compile(r"(?:\+?\d[\d\s\-]{6,}\d)")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def mask_sensitive(text: str) -> str:
    text = str(text).translate(_PERSIAN_DIGITS)
    return _LONG_DIGITS.sub(lambda m: m.group(0)[:3] + "***", text)


class _MaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive(record.getMessage())
        record.args = ()
        return True


_configured = False


def get_logger(name: str = "voice2excel") -> logging.Logger:
    global _configured
    logger = logging.getLogger("voice2excel")
    if not _configured:
        _configured = True
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        try:
            (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                DATA_DIR / "logs" / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            fh.setFormatter(fmt)
            fh.addFilter(_MaskFilter())
            logger.addHandler(fh)
        except OSError:
            pass
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.addFilter(_MaskFilter())
        logger.addHandler(sh)
        logger.propagate = False
    return logger if name == "voice2excel" else logger.getChild(name)
