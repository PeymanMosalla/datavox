"""بررسی ساختار فایل اکسل مقصد پیش از هر ویرایش (گزارش پیش‌پرواز).

ویژگی‌هایی که openpyxl نمی‌تواند با اطمینان حفظ کند، پیش از نوشتن شناسایی و گزارش می‌شوند.
این ماژول هرگز فایل را تغییر نمی‌دهد.
"""
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from .normalizer import normalize_text

# بخش‌هایی از بسته xlsx و میزان خطرشان هنگام ذخیره با openpyxl
_PART_RISKS = [
    (r"^xl/vbaProject\.bin$", "warn", "فایل ماکرو (VBA) دارد؛ با حالت حفظ ماکرو باز می‌شود، ولی پس از ثبت، اجرای ماکروها را در Excel بررسی کنید."),
    (r"^xl/charts/", "block", "فایل نمودار دارد؛ openpyxl نمودارها را حفظ نمی‌کند."),
    (r"^xl/pivotTables/|^xl/pivotCache/", "block", "فایل جدول محوری (Pivot) دارد؛ ممکن است آسیب ببیند."),
    (r"^xl/slicers/|^xl/slicerCaches/|^xl/timelines/", "block", "فایل Slicer یا Timeline دارد که حفظ نمی‌شود."),
    (r"^xl/ctrlProps/|^xl/activeX/", "block", "فایل کنترل فرم یا ActiveX دارد که حفظ نمی‌شود."),
    (r"^xl/media/|^xl/drawings/", "warn", "فایل تصویر یا شکل دارد؛ تصاویر ساده حفظ می‌شوند ولی شکل‌ها ممکن است حذف شوند."),
    (r"^xl/externalLinks/", "warn", "فایل به فایل‌های دیگر لینک دارد؛ لینک‌ها حفظ می‌شوند ولی مقادیرشان به‌روز نمی‌شود."),
    (r"^xl/threadedComments/", "warn", "فایل کامنت‌های رشته‌ای دارد که ممکن است به یادداشت ساده تبدیل شوند."),
    (r"^xl/connections\.xml$|^xl/queryTables/", "warn", "فایل اتصال داده یا Power Query دارد که ممکن است حذف شود."),
    (r"^customXml/", "info", "فایل داده XML سفارشی دارد که ممکن است حذف شود."),
]


def lock_status(path: Path) -> dict:
    """آیا فایل در Excel یا برنامه دیگری باز است؟"""
    path = Path(path)
    owner = path.with_name("~$" + path.name)
    owner_exists = owner.exists()
    write_blocked = False
    if path.exists():
        try:
            with open(path, "r+b"):
                pass
        except PermissionError:
            write_blocked = True
        except OSError:
            write_blocked = True
    locked = write_blocked or owner_exists
    msg = ""
    if write_blocked:
        msg = "فایل در Excel یا برنامه دیگری باز است. لطفاً آن را ببندید و دوباره تلاش کنید."
    elif owner_exists:
        msg = "نشانه باز بودن فایل در Excel دیده شد (فایل ~$). اگر فایل باز است، آن را ببندید."
    return {"locked": locked, "write_blocked": write_blocked, "owner_file": owner_exists, "message": msg}


MAX_UNPACKED_BYTES = 300 * 1024 * 1024
MAX_PARTS = 5000


def check_package(path: Path) -> None:
    """پیش از باز کردن با openpyxl: فایلی که پس از باز شدن بسیار بزرگ می‌شود (بمب فشرده) حافظه را پر نکند.
    اندازه اعلام‌شده هر بخش هنگام خواندن هم رعایت می‌شود (zipfile بیش از آن نمی‌خواند)."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
    except (zipfile.BadZipFile, OSError):
        raise ValueError("فایل اکسل خراب است یا رمزگذاری شده است.") from None
    if len(infos) > MAX_PARTS or sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        raise ValueError("ساختار این فایل اکسل غیرعادی است (پس از باز شدن بسیار بزرگ می‌شود) و باز نمی‌شود.")


def zip_parts(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return sorted(n for n in z.namelist() if not n.endswith("/"))  # مدخل پوشه، بخش واقعی فایل نیست


def detect_header_row(ws, max_scan: int = 10) -> int:
    best_row, best_count = 1, 0
    for r in range(1, min(ws.max_row, max_scan) + 1):
        count = sum(1 for c in range(1, min(ws.max_column, 60) + 1)
                    if isinstance(ws.cell(r, c).value, str) and ws.cell(r, c).value.strip())
        if count > best_count:
            best_row, best_count = r, count
    return best_row if best_count >= 2 else 1


def header_map(ws, header_row: int) -> dict[str, str]:
    out = {}
    for c in range(1, min(ws.max_column, 200) + 1):
        v = ws.cell(header_row, c).value
        if v not in (None, ""):
            out[get_column_letter(c)] = str(v)
    return out


def last_data_row(ws, columns: list[int], start_row: int) -> int:
    """آخرین ردیفی که در یکی از ستون‌های داده مقدار دارد (۰ یعنی هیچ داده‌ای نیست)."""
    for r in range(ws.max_row, start_row - 1, -1):
        for c in columns:
            v = ws.cell(r, c).value
            if v is not None and str(v).strip() != "":
                return r
    return start_row - 1


def inspect_workbook(path: str | Path) -> dict:
    path = Path(path)
    report: dict = {"path": str(path), "name": path.name, "exists": path.exists(), "risks": [], "sheets": []}
    if not path.exists():
        report["risks"].append({"level": "block", "message": "فایل پیدا نشد."})
        return report
    ext = path.suffix.lower()
    report["type"] = ext.lstrip(".").upper()
    report["size"] = path.stat().st_size
    report["modified"] = os.path.getmtime(path)
    report["lock"] = lock_status(path)
    if ext not in (".xlsx", ".xlsm"):
        report["risks"].append({"level": "block", "message": "فقط فایل‌های XLSX و XLSM پشتیبانی می‌شوند (فایل XLS قدیمی را در Excel با قالب XLSX ذخیره کنید)."})
        return report
    try:
        check_package(path)
        parts = zip_parts(path)
    except ValueError as e:
        report["risks"].append({"level": "block", "message": str(e)})
        return report
    report["parts"] = parts
    report["has_macros"] = "xl/vbaProject.bin" in parts
    if report["has_macros"] and ext == ".xlsx":
        report["risks"].append({"level": "warn", "message": "فایل XLSX شامل ماکرو است که Excel آن را اجرا نمی‌کند."})
    seen = set()
    for pat, level, msg in _PART_RISKS:
        if any(re.search(pat, p) for p in parts) and msg not in seen:
            seen.add(msg)
            report["risks"].append({"level": level, "message": msg})
    try:
        wb = openpyxl.load_workbook(path, keep_vba=ext == ".xlsm", rich_text=True)
    except Exception as e:
        report["risks"].append({"level": "block", "message": f"فایل با openpyxl باز نشد: {type(e).__name__}"})
        return report
    report["defined_names"] = list(wb.defined_names.keys()) if hasattr(wb.defined_names, "keys") else []
    report["active_sheet"] = wb.active.title if wb.active else ""
    for ws in wb.worksheets:
        hr = detect_header_row(ws)
        headers = header_map(ws, hr)
        cols = [openpyxl.utils.column_index_from_string(c) for c in headers] or list(range(1, ws.max_column + 1))
        ldr = last_data_row(ws, cols, hr + 1)
        formulas = []
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    formulas.append(cell.coordinate)
        info = {
            "name": ws.title,
            "state": ws.sheet_state,
            "dimensions": ws.dimensions,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "right_to_left": bool(ws.sheet_view.rightToLeft),
            "freeze_panes": ws.freeze_panes,
            "auto_filter": ws.auto_filter.ref,
            "merged_cells": [str(r) for r in ws.merged_cells.ranges][:50],
            "data_validations": len(ws.data_validations.dataValidation),
            "conditional_formats": len(ws.conditional_formatting),
            "tables": list(ws.tables.keys()),
            "formula_count": len(formulas),
            "formula_samples": formulas[:10],
            "header_row": hr,
            "headers": headers,
            "data_start_row": hr + 1,
            "last_data_row": ldr,
            "data_rows": max(0, ldr - hr),
            "images": len(getattr(ws, "_images", [])),
        }
        if info["auto_filter"] and ldr:
            m = re.search(r"(\d+)$", info["auto_filter"])
            if m and int(m.group(1)) < ldr:
                info["auto_filter_stale"] = True
        report["sheets"].append(info)
        if info["tables"]:
            report["risks"].append({"level": "warn", "message": f"شیت «{ws.title}» جدول اکسل (Table) دارد؛ ردیف‌های جدید باید داخل محدوده جدول باشند."})
    wb.close()
    report["blocking"] = any(r["level"] == "block" for r in report["risks"])
    return report


def data_summary(path: Path, sheet: str, header_row: int, columns: list[str]) -> dict:
    """تعداد ردیف‌های داده و آخرین ردیف داده در ستون‌های داده‌شده (خواندن سریع، بدون باز کردن کامل فایل)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet not in wb.sheetnames:
            return {"rows": 0, "last_row": 0}
        ws = wb[sheet]
        idx = [openpyxl.utils.column_index_from_string(c) - 1 for c in columns]
        rows, last = 0, header_row
        for i, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
            if any(ci < len(row) and row[ci] is not None and str(row[ci]).strip() != "" for ci in idx):
                rows, last = rows + 1, i
        return {"rows": rows, "last_row": last}
    finally:
        wb.close()


def read_rows(path: Path, sheet: str, header_row: int, columns: dict[str, str], raw: bool = False) -> list[dict]:
    """خواندن ردیف‌های موجود (فقط مقدار). columns: {حرف ستون: کلید فیلد}.

    raw=False متن را برای مقایسه نرمال می‌کند (تشخیص تکرار)؛ raw=True متن را دست‌نخورده برمی‌گرداند (تشخیص سبک).
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        idx = {openpyxl.utils.column_index_from_string(c) - 1: f for c, f in columns.items()}
        out = []
        for i, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
            rec = {}
            for ci, f in idx.items():
                if ci < len(row) and row[ci] not in (None, ""):
                    rec[f] = str(row[ci]) if raw else normalize_text(str(row[ci]))
            if rec:
                rec["ref"] = f"ردیف {i} اکسل"
                out.append(rec)
        return out
    finally:
        wb.close()
