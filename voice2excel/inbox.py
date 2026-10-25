"""پوشه ورودی خودکار: ویس‌هایی که در یک پوشه ذخیره می‌شوند (مثلاً دانلودهای تلگرام یا واتساپ دسکتاپ)
خودکار برداشته و به صف پردازش اضافه می‌شوند.

- فقط فایل‌هایی که پس از تنظیم پوشه آمده‌اند برداشته می‌شوند (ویس‌های قدیمی پوشه دست نمی‌خورند).
- فایلی که هنوز در حال دانلود است برداشته نمی‌شود: اندازه‌اش باید در دو بررسی پیاپی ثابت بماند.
- فایل تکراری با بررسی محتوا (sha256) هنگام ثبت کنار گذاشته می‌شود.
"""
from __future__ import annotations

import os
from pathlib import Path

from .audio_processor import is_supported


class Inbox:
    def __init__(self) -> None:
        self._sizes: dict[str, int] = {}
        self._taken: set[tuple[str, int, float]] = set()

    def poll(self, folder: str | Path, since: float) -> list[Path]:
        """فایل‌های صوتی تازه‌ای که نوشتنشان تمام شده است."""
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return []
        ready: list[Path] = []
        sizes: dict[str, int] = {}
        for e in entries:
            if e.name.startswith((".", "~")) or not is_supported(e.name):
                continue
            try:
                if not e.is_file():
                    continue
                st = e.stat()
            except OSError:
                continue
            key = (e.path, st.st_size, st.st_mtime)
            if st.st_mtime < since or st.st_size == 0 or key in self._taken:
                continue
            sizes[e.path] = st.st_size
            if self._sizes.get(e.path) == st.st_size:
                ready.append(Path(e.path))
                self._taken.add(key)
        self._sizes = sizes
        return ready
