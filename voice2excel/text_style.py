"""یکدست کردن ظاهر متن با سبک ردیف‌های موجود فایل اکسل شرکت.

سبک (نوع جداکننده و رقم فارسی/انگلیسی) از آدرس‌های همان فایل استخراج و هنگام نوشتن
اعمال می‌شود؛ مقدار ذخیره‌شده در برنامه تغییر نمی‌کند.
"""
from __future__ import annotations

import re
from collections import Counter

from .normalizer import to_ascii_digits, to_persian_digits

DEFAULT_STYLE = {"sep": " ، ", "digits": "ascii"}
_SEP_RE = re.compile(r"\s*[،,]\s*")
_SEP_FORMS = {" ، ": re.compile(r" [،,] "), "، ": re.compile(r"(?<! )[،,] "), " ،": re.compile(r" [،,](?! )"),
              "،": re.compile(r"(?<! )[،,](?! )")}


def infer_style(samples: list[str]) -> dict:
    """سبک غالب از نمونه متن‌ها (مثلاً ستون آدرس فایل شرکت)."""
    seps: Counter = Counter()
    ascii_d = persian_d = 0
    for s in samples:
        s = str(s or "")
        for form, pat in _SEP_FORMS.items():
            seps[form] += len(pat.findall(s))
        ascii_d += len(re.findall(r"[0-9]", s))
        persian_d += len(re.findall(r"[۰-۹٠-٩]", s))
    sep = seps.most_common(1)[0][0] if seps and seps.most_common(1)[0][1] > 0 else DEFAULT_STYLE["sep"]
    digits = "persian" if persian_d > ascii_d else "ascii"
    return {"sep": sep, "digits": digits}


def apply_style(text: str, style: dict | None) -> str:
    """جداکننده‌ها و رقم‌ها را به سبک داده‌شده درمی‌آورد."""
    if not text:
        return text
    style = {**DEFAULT_STYLE, **(style or {})}
    out = _SEP_RE.sub(style["sep"], str(text)).strip()
    out = to_persian_digits(out) if style["digits"] == "persian" else to_ascii_digits(out)
    return out


def join(parts: list[str], style: dict | None) -> str:
    style = {**DEFAULT_STYLE, **(style or {})}
    return style["sep"].join(p for p in parts if p)
