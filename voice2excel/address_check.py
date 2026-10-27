"""بررسی آدرس با نقشه: خیابان فرعیِ شنیده‌شده با خیابان اصلی جور است؟

هشدار فقط وقتی هر دو شرط برقرار باشد: خیابان دوم بیش از FAR_KM از خیابان اول دور است، و در فاصله NEAR_KM
از خیابان اول خیابانی واقعی با تلفظ مشابه خیابان دوم هست (یعنی احتمالاً همان گفته شده و اشتباه شنیده شده).
صرف وجود خیابان هم‌نام در جای دیگر شهر هشدار نمی‌دهد. آدرس خودکار عوض نمی‌شود؛ فقط پیشنهاد داده می‌شود.

تنظیم با داده: روی ۹۵ آدرس دوخیابانی درست از اکسل شرکت و ۹۲۱ جفت خیابان درست از نقشه، هیچ هشدار بی‌جا؛
روی ۵۷۵ اشتباه شنیدن شبیه‌سازی‌شده (با شباهت تلفظ هم‌اندازه اشتباه‌های واقعی مدل گفتار) ۹۹٪ علامت خورد و در ۹۵٪
خیابان درست پیشنهاد شد.
"""
from __future__ import annotations

import difflib
import re
from functools import lru_cache

import numpy as np

from .geo import base_points
from .knowledge import streets_from_address
from .normalizer import normalize_text, sound_key, to_ascii_digits

FAR_KM = 2.0
NEAR_KM = 0.5
SIMILAR = 0.75
_EARTH_KM = 6371.0


@lru_cache(maxsize=1)
def _index():
    """(کلیدها، نام هر کلید، نقطه‌ها به رادیان، شماره کلید هر نقطه)."""
    groups: dict[str, list] = {}
    names: dict[str, str] = {}
    for name, pts in base_points():
        k = sound_key(name)
        if len(k) >= 3 and pts:
            groups.setdefault(k, []).extend(pts)
            names.setdefault(k, name)
    keys = sorted(groups)
    if not keys:
        return [], {}, np.zeros((0, 2)), np.zeros(0, dtype=int)
    pts = np.radians(np.array([p for k in keys for p in groups[k]], dtype=np.float64))
    owner = np.array([i for i, k in enumerate(keys) for _ in groups[k]])
    return keys, names, pts, owner


def _dist_to_all(points: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """کمترین فاصله (کیلومتر) هر نقطه نقشه از نزدیک‌ترین نقطه points."""
    best = np.full(len(pts), np.inf)
    for lat, lon in points:
        h = np.sin((pts[:, 0] - lat) / 2) ** 2 + np.cos(lat) * np.cos(pts[:, 0]) * np.sin((pts[:, 1] - lon) / 2) ** 2
        np.minimum(best, 2 * _EARTH_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1))), out=best)
    return best


@lru_cache(maxsize=256)
def _distances_from(key: str) -> dict[str, float]:
    """فاصله هر خیابان نقشه از خیابان key (کمترین فاصله میان نقطه‌هایشان)."""
    keys, _, pts, owner = _index()
    i = keys.index(key)
    d = _dist_to_all(pts[owner == i], pts)
    out = np.full(len(keys), np.inf)
    np.minimum.at(out, owner, d)
    return dict(zip(keys, out.tolist()))


def _surface(address: str, key: str) -> str | None:
    """همان بخش از متن آدرس که این خیابان است (برای جایگزینی در پیشنهاد)."""
    words = [w.strip("،,.") for w in address.split()]
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            part = words[i:i + n]
            if all(p and not re.search(r"[\d۰-۹]", p) for p in part) and sound_key(" ".join(part)) == key:
                return " ".join(part)  # فقط نام، بدون شماره: «فاطمیه ۵» ← «فاطمی ۵»
    return None


def check(address: str) -> list[dict]:
    """[{heard, suggestion, main, km}]: خیابانی که با خیابان اصلی جور نیست و پیشنهاد نزدیکِ هم‌آوا."""
    keys, names, _, _ = _index()
    if not keys or not address:
        return []
    text = to_ascii_digits(normalize_text(address))
    found: list[str] = []
    for st in streets_from_address(text):
        k = sound_key(st.canonical)
        if k in names and k not in found:
            found.append(k)
    if len(found) < 2:
        return []
    main = found[0]
    dist = _distances_from(main)
    out = []
    for k in found[1:]:
        if dist[k] <= FAR_KM:
            continue
        near = [c for c in keys if c not in (main, k) and dist[c] <= NEAR_KM
                and difflib.SequenceMatcher(None, c, k).ratio() >= SIMILAR]
        if not near:
            continue
        best = max(near, key=lambda c: difflib.SequenceMatcher(None, c, k).ratio())
        out.append({"heard": _surface(address, k) or names[k], "suggestion": names[best],
                    "main": names[main], "km": round(dist[k], 1)})
    return out
