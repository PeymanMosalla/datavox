"""نگاشت بخش‌های متن پردازش‌شده به زمان در ویس.

متن پردازش‌شده با متن خام (واژه‌های زمان‌دار Whisper) یکی نیست: عددها به رقم تبدیل و
املای آوایی اصلاح شده‌اند. پس واژه‌هایی که در هر دو یکسان مانده‌اند («مهندس»، «سجادیه»)
لنگر می‌شوند و زمانِ بخش‌های تغییرکرده (مثل رقم‌های شماره) از فاصله میان لنگرها به دست می‌آید.
"""
from __future__ import annotations

import difflib
import re

from .normalizer import normalize_text

_PUNCT = "،,.:؛;!?؟«»\"'()"
# حاشیه پخش، تا ابتدا و انتهای واژه بریده نشود
PAD = 0.25
# واژه‌هایی با احتمال کمتر از این مقدار فقط «برای اطلاع» به کاربر نشان داده می‌شوند (در تصمیم‌گیری نقشی ندارند)
LOW_PROB = 0.5


def _key(word: str) -> str:
    return normalize_text(word).strip(_PUNCT).replace("‌", "")


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(_key(m.group(0)), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


class TimeMap:
    """زمان هر بازه از متن پردازش‌شده را بر اساس واژه‌های زمان‌دار ویس برمی‌گرداند."""

    def __init__(self, processed_text: str, words: list[dict]):
        self.words = [w for w in words if w.get("word", "").strip()]
        self.tokens = _tokens(processed_text)
        raw_keys = [_key(w["word"]) for w in self.words]
        proc_keys = [t[0] for t in self.tokens]
        self.proc_to_raw: dict[int, int] = {}
        sm = difflib.SequenceMatcher(None, raw_keys, proc_keys, autojunk=False)
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                if proc_keys[b + k]:
                    self.proc_to_raw[b + k] = a + k
        self.duration = self.words[-1]["end"] if self.words else 0.0

    def _token_range(self, start: int, end: int) -> tuple[int, int] | None:
        idx = [i for i, (_, s, e) in enumerate(self.tokens) if s < end and e > start]
        return (idx[0], idx[-1]) if idx else None

    def span_time(self, start: int, end: int) -> tuple[float, float] | None:
        """زمان (ثانیه) بازه [start, end) از متن پردازش‌شده؛ None اگر ویس واژه زمان‌دار نداشته باشد."""
        if not self.words:
            return None
        rng = self._token_range(start, end)
        if rng is None:
            return None
        a, b = rng
        inside = [self.proc_to_raw[i] for i in range(a, b + 1) if i in self.proc_to_raw]
        before = next((self.proc_to_raw[i] for i in range(a - 1, -1, -1) if i in self.proc_to_raw), None)
        after = next((self.proc_to_raw[i] for i in range(b + 1, len(self.tokens)) if i in self.proc_to_raw), None)
        # ابتدا: اگر اولین توکنِ بازه لنگر است، زمان آغاز همان واژه؛ وگرنه پایانِ لنگرِ قبلی
        if a in self.proc_to_raw:
            t0 = self.words[self.proc_to_raw[a]]["start"]
        elif before is not None:
            t0 = self.words[before]["end"]
        elif inside:
            t0 = self.words[0]["start"]
        else:
            t0 = 0.0
        if b in self.proc_to_raw:
            t1 = self.words[self.proc_to_raw[b]]["end"]
        elif after is not None:
            t1 = self.words[after]["start"]
        else:
            t1 = self.duration
        if t1 <= t0:
            return None
        return round(max(0.0, t0 - PAD), 2), round(min(self.duration + PAD, t1 + PAD), 2)

    def low_confidence_words(self, t0: float, t1: float) -> list[tuple[str, list[float]]]:
        """واژه‌هایی از ویس که در این بازه با اطمینان کم شنیده شده‌اند، با زمان پخش هر کدام (فقط برای نمایش)."""
        return [(w["word"].strip(_PUNCT), [round(max(0.0, w["start"] - PAD), 2), round(w["end"] + PAD, 2)])
                for w in self.words
                if w["start"] >= t0 - 0.05 and w["end"] <= t1 + 0.05 and w.get("prob", 1.0) < LOW_PROB]


def field_times(processed_text: str, words: list[dict], spans: dict[str, list[int]]) -> tuple[dict, dict, dict]:
    """خروجی: ({فیلد: [شروع، پایان]}، {فیلد: [واژه‌های کم‌اطمینان]}، {فیلد: [زمان هر واژه کم‌اطمینان]})."""
    tm = TimeMap(processed_text, words)
    times, low, low_times = {}, {}, {}
    for field, (s, e) in spans.items():
        t = tm.span_time(s, e)
        if t:
            times[field] = list(t)
            lc = tm.low_confidence_words(*t)
            if lc:
                low[field] = [w for w, _ in lc]
                low_times[field] = [span for _, span in lc]
    return times, low, low_times
