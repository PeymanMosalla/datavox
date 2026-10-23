"""ثبت کنترل‌شده رکوردها در فایل اکسل شرکت.

اصول:
- فایل اصلی هرگز مستقیم ویرایش نمی‌شود؛ خروجی در یک کپی جداگانه ساخته می‌شود.
- پیش از هر کاری از فایل اصلی نسخه پشتیبان گرفته می‌شود.
- عنوان ستون‌ها با قالب نگاشت مقایسه می‌شود؛ هر تغییری کار را متوقف می‌کند.
- فقط ردیف‌های بعد از آخرین داده و فقط ستون‌های نگاشت‌شده نوشته می‌شوند.
- پس از ذخیره، خروجی دوباره خوانده و بررسی می‌شود که داده‌های قبلی دست نخورده باشند.
- جایگزینی فایل اصلی فقط با تأیید جداگانه کاربر انجام می‌شود.
"""
from __future__ import annotations

import copy
import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment
from openpyxl.utils import column_index_from_string

from .config import DATA_DIR
from .deduplicator import file_sha256
from .excel_mapping import cell_values
from .excel_reader import inspect_workbook, last_data_row, lock_status, zip_parts
from .normalizer import normalize_text

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ExcelWriteError(Exception):
    """خطای قابل فهم برای کاربر؛ هیچ تغییری در فایل اصلی ایجاد نشده است."""


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _header_mismatches(ws, profile: dict) -> list[str]:
    bad = []
    hr = profile["header_row"]
    for col, expected in profile["headers"].items():
        actual = ws.cell(hr, column_index_from_string(col)).value
        if normalize_text(str(actual or "")) != normalize_text(str(expected or "")):
            bad.append(f"ستون {col}: انتظار «{expected}» ولی «{actual or ''}» دیده شد")
    return bad


def _sheet_fingerprint(ws, max_row: int | None = None) -> str:
    """هش همه مقادیر یک شیت (تا ردیف مشخص) برای اطمینان از دست‌نخوردن داده‌های قبلی."""
    h = hashlib.sha256()
    for row in ws.iter_rows(max_row=max_row or ws.max_row):
        for c in row:
            if c.value is not None:
                h.update(f"{c.coordinate}={c.value!r};".encode("utf-8"))
    return h.hexdigest()


def safe_set(cell, value) -> None:
    """نوشتن مقدار به‌صورت متن؛ متن‌هایی که شبیه فرمول‌اند هرگز فرمول نمی‌شوند."""
    if value is None or value == "":
        cell.value = None
        return
    s = str(value)
    cell.value = s
    if s.startswith(FORMULA_PREFIXES):
        cell.data_type = "s"
        cell.quotePrefix = True
    else:
        cell.data_type = "s"


def _copy_style(src, dst) -> None:
    if src.has_style:
        dst.font = copy.copy(src.font)
        dst.border = copy.copy(src.border)
        dst.fill = copy.copy(src.fill)
        dst.number_format = src.number_format
        dst.protection = copy.copy(src.protection)
        dst.alignment = copy.copy(src.alignment)


def _group_date(ws, date_col: int | None, last_row: int, start_row: int) -> str:
    if not date_col:
        return ""
    for r in range(last_row, start_row - 1, -1):
        v = ws.cell(r, date_col).value
        if v not in (None, ""):
            return normalize_text(str(v))
    return ""


def _same_date(a: str, b: str) -> bool:
    from .dates_fa import parse_jalali

    da, db_ = parse_jalali(a), parse_jalali(b)
    if da and db_:
        return da == db_
    return normalize_text(a) == normalize_text(b)


def plan_rows(profile: dict, ws, records: list[dict]) -> dict:
    """محاسبه دقیق اینکه هر رکورد در کدام ردیف و با چه مقادیری نوشته می‌شود."""
    cols = [column_index_from_string(c) for c in list(profile["headers"].keys())]
    start = profile["header_row"] + 1
    last = last_data_row(ws, cols, start)
    policy = profile.get("policy", {})
    date_col_letter = next((c for c, f in profile["columns"].items() if f == "visit_date"), None)
    date_col = column_index_from_string(date_col_letter) if date_col_letter else None
    current_group = _group_date(ws, date_col, last, start)
    row = last + 1
    plan = []
    for rec in sorted(records, key=lambda r: (r["values"].get("visit_date", ""), r["audio_id"], r["building_index"])):
        values = cell_values(profile, rec)
        vdate = rec["values"].get("visit_date", "")
        new_group = not current_group or not _same_date(vdate, current_group)
        if new_group and policy.get("blank_row_between_dates") and (plan or last >= start):
            row += 1  # ردیف خالی میان گروه‌های روزانه (قرارداد فایل شرکت)
        if date_col_letter and policy.get("date_first_row_only") and not new_group:
            values[date_col_letter] = ""
        plan.append({"record_id": rec["id"], "row": row, "cells": values, "visit_date": vdate})
        current_group = vdate
        row += 1
    return {"last_existing_row": last, "rows": plan}


def preview(profile: dict, records: list[dict]) -> dict:
    path = Path(profile["excel_path"])
    if not path.exists():
        raise ExcelWriteError("فایل اکسل مقصد پیدا نشد.")
    wb = openpyxl.load_workbook(path, keep_vba=path.suffix.lower() == ".xlsm")
    try:
        if profile["sheet"] not in wb.sheetnames:
            raise ExcelWriteError(f"شیت «{profile['sheet']}» در فایل پیدا نشد.")
        ws = wb[profile["sheet"]]
        mism = _header_mismatches(ws, profile)
        plan = plan_rows(profile, ws, records)
        plan["header_mismatches"] = mism
        return plan
    finally:
        wb.close()


def write_export(profile: dict, records: list[dict], allow_warnings: bool = True) -> dict:
    """ساخت کپی جدید از فایل مقصد با ردیف‌های اضافه‌شده. فایل اصلی تغییر نمی‌کند."""
    target = Path(profile["excel_path"])
    if not target.exists():
        raise ExcelWriteError("فایل اکسل مقصد پیدا نشد.")
    if not records:
        raise ExcelWriteError("هیچ رکورد تأییدشده‌ای برای ثبت وجود ندارد.")
    report = inspect_workbook(target)
    blocking = [r["message"] for r in report["risks"] if r["level"] == "block"]
    if blocking:
        raise ExcelWriteError("ثبت متوقف شد: " + " ؛ ".join(blocking))

    out_dir = DATA_DIR / "outputs"
    bak_dir = DATA_DIR / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    bak_dir.mkdir(parents=True, exist_ok=True)
    stamp = _ts()
    ext = target.suffix.lower()

    # ۱) پشتیبان از فایل اصلی و بررسی سلامت آن
    backup = bak_dir / f"{target.stem}__پشتیبان_{stamp}{ext}"
    shutil.copy2(target, backup)
    target_sha = file_sha256(target)
    if file_sha256(backup) != target_sha:
        raise ExcelWriteError("ساخت نسخه پشتیبان ناموفق بود؛ هیچ تغییری انجام نشد.")

    # ۲) بارگذاری از روی نسخه پشتیبان (فایل اصلی حتی برای خواندن قفل نمی‌شود)
    wb = openpyxl.load_workbook(backup, keep_vba=ext == ".xlsm", rich_text=True)
    if profile["sheet"] not in wb.sheetnames:
        raise ExcelWriteError(f"شیت «{profile['sheet']}» در فایل پیدا نشد.")
    ws = wb[profile["sheet"]]
    mism = _header_mismatches(ws, profile)
    if mism:
        raise ExcelWriteError("عنوان ستون‌های فایل با قالب نگاشت یکسان نیست؛ نگاشت را دوباره بررسی کنید: "
                              + " ؛ ".join(mism))
    sheetnames_before = list(wb.sheetnames)
    plan = plan_rows(profile, ws, records)
    last = plan["last_existing_row"]
    fp_target_before = _sheet_fingerprint(ws, max_row=last)
    fp_others_before = {s.title: _sheet_fingerprint(s) for s in wb.worksheets if s.title != ws.title}
    policy = profile.get("policy", {})
    protected = {column_index_from_string(c) for c in profile.get("protected", [])}
    max_col = max(column_index_from_string(c) for c in profile["headers"]) if profile["headers"] else ws.max_column
    phone_cols = {c for c, f in profile["columns"].items() if f == "phone"}
    style_row = last if last > profile["header_row"] else None

    # ۳) نوشتن ردیف‌ها
    for item in plan["rows"]:
        r = item["row"]
        if style_row and policy.get("copy_style_from_last_row", True):
            for c in range(1, max_col + 1):
                _copy_style(ws.cell(style_row, c), ws.cell(r, c))
            h = ws.row_dimensions[style_row].height
            if h:
                ws.row_dimensions[r].height = h
        for col_letter, value in item["cells"].items():
            ci = column_index_from_string(col_letter)
            if ci in protected:
                continue
            cell = ws.cell(r, ci)
            safe_set(cell, value)
            if col_letter in phone_cols:
                cell.number_format = "@"
            if value and "\n" in str(value):
                al = copy.copy(cell.alignment) if cell.has_style else Alignment()
                cell.alignment = Alignment(horizontal=al.horizontal, vertical=al.vertical or "center",
                                           wrap_text=True, readingOrder=al.readingOrder)

    # ۴) ذخیره در فایل موقت و سپس انتقال اتمیک به مسیر خروجی
    output = out_dir / f"{target.stem}__ثبت_{stamp}{ext}"
    tmp = out_dir / f".tmp_{stamp}{ext}"
    try:
        wb.save(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise ExcelWriteError(f"ذخیره فایل خروجی ناموفق بود ({type(e).__name__}). داده‌های پردازش‌شده حفظ شده‌اند.") from e
    finally:
        wb.close()
    os.replace(tmp, output)

    # ۵) بررسی پس از ذخیره
    verify = verify_output(output, profile, plan, sheetnames_before, fp_target_before, fp_others_before, last)
    try:
        dropped = sorted(set(zip_parts(target)) - set(zip_parts(output)))
    except Exception:
        dropped = []
    if verify["errors"]:
        bad = output.with_name(output.stem + "__نامعتبر" + output.suffix)
        os.replace(output, bad)
        raise ExcelWriteError("بررسی فایل خروجی ناموفق بود و خروجی کنار گذاشته شد: " + " ؛ ".join(verify["errors"]))
    return {
        "output_path": str(output),
        "backup_path": str(backup),
        "target_path": str(target),
        "target_sha": target_sha,
        "first_row": plan["rows"][0]["row"],
        "last_row": plan["rows"][-1]["row"],
        "rows": [{"record_id": p["record_id"], "row": p["row"]} for p in plan["rows"]],
        "dropped_parts": dropped,
        "warnings": [r["message"] for r in report["risks"] if r["level"] != "block"] + verify["warnings"],
    }


def verify_output(output: Path, profile: dict, plan: dict, sheetnames_before, fp_target_before, fp_others_before,
                  last: int) -> dict:
    errors, warnings = [], []
    wb = openpyxl.load_workbook(output, keep_vba=output.suffix.lower() == ".xlsm", rich_text=True)
    try:
        if list(wb.sheetnames) != sheetnames_before:
            errors.append("فهرست شیت‌ها تغییر کرده است.")
        ws = wb[profile["sheet"]]
        if _header_mismatches(ws, profile):
            errors.append("عنوان ستون‌ها تغییر کرده است.")
        if _sheet_fingerprint(ws, max_row=last) != fp_target_before:
            errors.append("داده‌های قبلی شیت مقصد تغییر کرده‌اند.")
        for s in wb.worksheets:
            if s.title != ws.title and _sheet_fingerprint(s) != fp_others_before.get(s.title):
                errors.append(f"داده‌های شیت «{s.title}» تغییر کرده‌اند.")
        protected = {column_index_from_string(c) for c in profile.get("protected", [])}
        for item in plan["rows"]:
            for col, val in item["cells"].items():
                ci = column_index_from_string(col)
                if ci in protected:
                    continue
                got = ws.cell(item["row"], ci).value
                if (got or "") != (val or ""):
                    errors.append(f"مقدار سلول {col}{item['row']} درست ذخیره نشد.")
                if got and ws.cell(item["row"], ci).data_type == "f":
                    errors.append(f"سلول {col}{item['row']} به‌اشتباه فرمول شده است.")
    finally:
        wb.close()
    return {"errors": errors, "warnings": warnings}


def replace_original(output_path: str, target_path: str, expected_target_sha: str) -> dict:
    """جایگزینی فایل اصلی با خروجی تأییدشده (فقط با دستور صریح کاربر)."""
    output, target = Path(output_path), Path(target_path)
    if not output.exists():
        raise ExcelWriteError("فایل خروجی پیدا نشد.")
    if not target.exists():
        raise ExcelWriteError("فایل اصلی پیدا نشد.")
    lock = lock_status(target)
    if lock["write_blocked"] or lock["owner_file"]:
        raise ExcelWriteError(lock["message"] or "فایل اصلی باز است.")
    if file_sha256(target) != expected_target_sha:
        raise ExcelWriteError("فایل اصلی پس از ساخت خروجی تغییر کرده است (احتمالاً کسی آن را ویرایش کرده). "
                              "برای جلوگیری از ازدست‌رفتن آن تغییرات، دوباره خروجی بگیرید.")
    backup = DATA_DIR / "backups" / f"{target.stem}__پیش-از-جایگزینی_{_ts()}{target.suffix}"
    shutil.copy2(target, backup)
    tmp = target.with_name(f".~v2x_{_ts()}{target.suffix}")
    shutil.copy2(output, tmp)
    try:
        os.replace(tmp, target)
    except PermissionError as e:
        tmp.unlink(missing_ok=True)
        raise ExcelWriteError("فایل اصلی در Excel یا برنامه دیگری باز است؛ آن را ببندید و دوباره تلاش کنید.") from e
    return {"target_path": str(target), "backup_path": str(backup)}
