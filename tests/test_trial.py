"""دوره آزمایشی: ۱۰ روز یا ۱۰ ویس؛ بازنشانی با نصب دوباره، ساعت یا ویرایش فایل ممکن نیست."""
from datetime import date, timedelta

import pytest

from voice2excel import licensing, trial


@pytest.fixture()
def required(monkeypatch, tmp_path):
    monkeypatch.setattr(licensing, "REQUIRED", True)
    monkeypatch.setattr(licensing, "LICENSE_FILE", tmp_path / "none.v2x")
    licensing._cache["key"] = None
    yield
    licensing._cache["key"] = None


def _set(started: date, seen: date, voices: int) -> None:
    trial._write_all({"m": licensing.machine_code(), "s": started.isoformat(), "d": seen.isoformat(), "v": voices})


def test_fresh_trial_is_full(required):
    i = trial.info()
    assert i["active"] and i["days_left"] == 10 and i["voices_left"] == 10 and licensing.can_process()


def test_ten_voices_end_trial_and_only_processing_stops(required):
    for _ in range(9):
        licensing.note_processed()
    assert trial.info()["voices_left"] == 1 and licensing.can_process()
    licensing.note_processed()
    i = trial.info()
    assert not i["active"] and i["reason"] == "ویس" and not licensing.can_process()


def test_ten_days_end_trial(required):
    today = date.today()
    _set(today - timedelta(days=9), today, 0)
    assert trial.info()["days_left"] == 1
    _set(today - timedelta(days=10), today, 0)
    i = trial.info()
    assert not i["active"] and i["reason"] == "روز"


def test_clock_rollback_does_not_extend(required):
    """ساعت رایانه به عقب برده شد: بیشترین تاریخ دیده‌شده ملاک است، نه ساعت فعلی."""
    today = date.today()
    _set(today - timedelta(days=3), today + timedelta(days=6), 0)  # قبلاً ۶ روز جلوتر دیده شده
    i = trial.info()
    assert i["days_left"] == 1 and i["clock_back"]


def test_reinstall_does_not_reset(required, _isolated_trial):
    """پاک کردن پوشه برنامه (و حتی چند مکان دیگر) دوره را از نو شروع نمی‌کند؛ مکان‌های پاک‌شده دوباره پر می‌شوند."""
    stores, reg = _isolated_trial
    _set(date.today() - timedelta(days=4), date.today(), 6)
    for p in stores[:3]:
        p.unlink()
    reg.clear()  # فقط ProgramData مانده
    i = trial.info()
    assert i["voices_used"] == 6 and i["days_left"] == 6
    assert all(p.exists() for p in stores) and "s" in reg


def test_registry_alone_keeps_state(required, _isolated_trial):
    stores, reg = _isolated_trial
    _set(date.today() - timedelta(days=2), date.today(), 8)
    for p in stores:
        p.unlink()
    assert trial.info()["voices_used"] == 8


def test_edited_or_foreign_state_is_ignored(required, _isolated_trial):
    """ویرایش دستی فایل (مثلاً شمار به صفر) یا فایل رایانه دیگر پذیرفته نمی‌شود؛ مقدار درست از بقیه مکان‌ها می‌آید."""
    import base64
    import json
    stores, _ = _isolated_trial
    _set(date.today(), date.today(), 7)
    body, tag = stores[0].read_text(encoding="utf-8").split(".")
    rec = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    rec["v"] = 0
    forged = base64.urlsafe_b64encode(json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
    for p in stores:
        p.write_text(f"{forged}.{tag}", encoding="utf-8")
    assert trial.info()["voices_used"] == 7  # از رجیستری
    other = trial._encode({"m": "AAAA-BBBB-CCCC-DDDD", "s": date.today().isoformat(), "d": date.today().isoformat(), "v": 0})
    assert trial._decode(other) is None


def test_licensed_user_is_not_counted(required, tmp_path, monkeypatch):
    monkeypatch.setattr(licensing, "_license", lambda: {"licensed": True})
    for _ in range(15):
        licensing.note_processed()
    assert licensing.can_process() and trial.info()["voices_used"] == 0
