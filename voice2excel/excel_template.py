"""قالب‌های خروجی اکسل.

دو حالت:
- append: افزودن ردیف به فایل موجود شرکت (نگاشت ستون‌ها در excel_mapping)؛ ظاهر فایل حفظ می‌شود.
- new: فایل خروجی را خود برنامه از روی قالب می‌سازد: ستون‌ها، ترتیب، عنوان، عرض و ظاهر را کاربر تعیین می‌کند.

قالب «new» به یک نگاشت معمولی (excel_mapping) تبدیل می‌شود تا ثبت، پشتیبان‌گیری، بررسی پس از ذخیره
و بازگشت دقیقاً همان مسیر حالت append را طی کنند.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .schema import COMPUTED_FIELDS, FIELD_LABELS

EXTRA_FIELDS = {"row_number": "شماره ردیف", "constant": "مقدار ثابت (دلخواه)"}
ALIGNS = {"right": "راست", "center": "وسط", "left": "چپ"}
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")

DEFAULT_STYLE = {
    "header": {"font": "Tahoma", "size": 11, "bold": True, "color": "#FFFFFF", "fill": "#3355D6", "height": 28},
    "body": {"font": "Tahoma", "size": 10, "color": "#1B2236", "align": "right", "wrap": True, "height": 0},
    "border": True, "zebra": "#EEF2FC", "rtl": True, "freeze": True, "filter": True,
}
# قالب‌های رنگی آماده: (پس‌زمینه سرستون، متن سرستون، ردیف‌های راه‌راه)
PRESETS = {
    "blue": ("آبی", "#3355D6", "#FFFFFF", "#EEF2FC"),
    "green": ("سبز", "#138A52", "#FFFFFF", "#E8F6EF"),
    "teal": ("فیروزه‌ای", "#0F7891", "#FFFFFF", "#E4F4F7"),
    "gray": ("خاکستری", "#3A4256", "#FFFFFF", "#F1F2F5"),
    "gold": ("طلایی", "#B26A00", "#FFFFFF", "#FFF6E5"),
    "plain": ("ساده (بدون رنگ)", "#FFFFFF", "#000000", ""),
}
# فونت‌های رایج فارسی و ویندوز: (نام، بخشی از نام فایل فونت برای تشخیص نصب بودن)
FONTS = [("Tahoma", "tahoma"), ("Arial", "arial"), ("Calibri", "calibri"), ("Segoe UI", "segoeui"),
         ("Times New Roman", "times"), ("B Nazanin", "bnazanin"), ("B Yekan", "byekan"), ("B Titr", "btitr"),
         ("B Mitra", "bmitra"), ("B Lotus", "blotus"), ("IRANSans", "iransans"), ("Vazirmatn", "vazirmatn"),
         ("Sahel", "sahel")]
DEFAULT_FIELDS = [("visit_date", 14), ("engineer_name", 22), ("phone", 16), ("address", 36),
                  ("technical_summary", 34), ("notes", 30)]


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field) or COMPUTED_FIELDS.get(field) or EXTRA_FIELDS.get(field, field)


def new_template(name: str, title: str, folder: str) -> dict:
    return {
        "name": name, "title": title, "mode": "new", "confirmed": True,
        "columns_list": [{"field": f, "title": field_label(f), "width": w, "align": "right"} for f, w in DEFAULT_FIELDS],
        "style": _deep_copy(DEFAULT_STYLE),
        "output": {"folder": folder, "file": title},
        # برخلاف فایل شرکت، در فایل تازه هر ردیف تاریخ خودش را دارد و ردیف خالی میان روزها نیست (قابل تغییر)
        "policy": {"text_style": {"sep": " ، ", "digits": "ascii"}, "blank_row_between_dates": False,
                   "date_first_row_only": False},
    }


def _deep_copy(d: dict) -> dict:
    return {k: dict(v) if isinstance(v, dict) else v for k, v in d.items()}


def _color(v, default: str) -> str:
    v = str(v or "").strip()
    return ("#" + v.lstrip("#")).upper() if _HEX.match(v) else default


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def clean(tpl: dict) -> dict:
    """یکدست و ایمن کردن قالب دریافتی از رابط کاربری (مقادیر نامعتبر به پیش‌فرض برمی‌گردند)."""
    allowed = set(FIELD_LABELS) | set(COMPUTED_FIELDS) | set(EXTRA_FIELDS) | {"followup"}
    cols = []
    for c in tpl.get("columns_list") or []:
        f = c.get("field")
        if f not in allowed:
            continue
        cols.append({"field": f, "title": str(c.get("title") or field_label(f)).strip()[:80] or field_label(f),
                     "width": _num(c.get("width"), 4, 120, 18), "align": c.get("align") if c.get("align") in ALIGNS else "right",
                     **({"value": str(c.get("value") or "")[:200]} if f == "constant" else {})})
    if not cols:
        raise ValueError("دست‌کم یک ستون لازم است.")
    titles = [c["title"] for c in cols]
    if len(set(titles)) != len(titles):
        raise ValueError("عنوان ستون‌ها نباید تکراری باشد.")
    s, d = tpl.get("style") or {}, DEFAULT_STYLE
    h, b = s.get("header") or {}, s.get("body") or {}
    style = {
        "header": {"font": str(h.get("font") or d["header"]["font"])[:40], "size": _num(h.get("size"), 6, 36, 11),
                   "bold": bool(h.get("bold", True)), "color": _color(h.get("color"), "#000000"),
                   "fill": _color(h.get("fill"), "#FFFFFF"), "height": _num(h.get("height"), 0, 120, 28)},
        "body": {"font": str(b.get("font") or d["body"]["font"])[:40], "size": _num(b.get("size"), 6, 36, 10),
                 "color": _color(b.get("color"), "#000000"), "align": b.get("align") if b.get("align") in ALIGNS else "right",
                 "wrap": bool(b.get("wrap", True)), "height": _num(b.get("height"), 0, 200, 0)},
        "border": bool(s.get("border", True)), "zebra": _color(s.get("zebra"), "") if s.get("zebra") else "",
        "rtl": bool(s.get("rtl", True)), "freeze": bool(s.get("freeze", True)), "filter": bool(s.get("filter", True)),
    }
    out = tpl.get("output") or {}
    file = re.sub(r'[\\/:*?"<>|]+', " ", str(out.get("file") or tpl.get("title") or "ثبت ویس")).strip()[:80] or "ثبت ویس"
    return {**tpl, "mode": "new", "confirmed": True, "columns_list": cols, "style": style,
            "output": {"folder": str(out.get("folder") or "").strip().strip('"'), "file": file}}


def target_path(tpl: dict) -> Path:
    return Path(tpl["output"]["folder"]) / f"{tpl['output']['file']}.xlsx"


def writer_profile(tpl: dict, create: bool = True) -> dict:
    """نگاشت معادل قالب «new» برای موتور ثبت؛ create: اگر فایل خروجی نیست، با سرستون ساخته شود."""
    path = target_path(tpl)
    if create and not path.exists():
        if not path.parent.is_dir():
            raise FileNotFoundError(f"پوشه خروجی «{path.parent}» پیدا نشد؛ در «قالب اکسل» پوشه را انتخاب کنید.")
        create_workbook(tpl, path)
    letters = [get_column_letter(i) for i in range(1, len(tpl["columns_list"]) + 1)]
    columns = {}
    for col, c in zip(letters, tpl["columns_list"]):
        columns[col] = f"const:{c.get('value', '')}" if c["field"] == "constant" else c["field"]
    return {
        **tpl, "excel_path": str(path), "sheet": "Sheet1", "header_row": 1,
        "headers": {col: c["title"] for col, c in zip(letters, tpl["columns_list"])},
        "columns": columns, "protected": [],
        "policy": {"blank_row_between_dates": False, "date_first_row_only": False, **(tpl.get("policy") or {}),
                   "copy_style_from_last_row": False},
    }


# ---------- ساخت و قالب‌بندی فایل ----------
def _font(spec: dict, bold: bool | None = None) -> Font:
    return Font(name=spec["font"], size=spec["size"], bold=spec.get("bold") if bold is None else bold,
                color="FF" + spec["color"].lstrip("#"))


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor="FF" + color.lstrip("#")) if color else PatternFill()


_THIN = Side(style="thin", color="FFC9CFDB")


def create_workbook(tpl: dict, path: Path) -> None:
    """فایل تازه با سرستون، عرض ستون‌ها، جهت راست‌به‌چپ، سرستون ثابت و فیلتر."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    write_header(ws, tpl)
    tmp = path.with_name(f".~v2x_new_{os.getpid()}.xlsx")
    wb.save(tmp)
    os.replace(tmp, path)


def write_header(ws, tpl: dict) -> None:
    s = tpl["style"]
    ws.sheet_view.rightToLeft = s["rtl"]
    for i, c in enumerate(tpl["columns_list"], start=1):
        cell = ws.cell(1, i, c["title"])
        cell.font = _font(s["header"])
        cell.fill = _fill(s["header"]["fill"])
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if s["border"]:
            cell.border = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
        ws.column_dimensions[get_column_letter(i)].width = c["width"]
    if s["header"]["height"]:
        ws.row_dimensions[1].height = s["header"]["height"]
    if s["freeze"]:
        ws.freeze_panes = "A2"
    if s["filter"]:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(tpl['columns_list']))}1"


def style_row(ws, row: int, tpl: dict, ordinal: int) -> None:
    """ظاهر یک ردیف داده؛ ordinal برای ردیف‌های راه‌راه."""
    s = tpl["style"]
    fill = _fill(s["zebra"] if s["zebra"] and ordinal % 2 == 0 else "")
    for i, c in enumerate(tpl["columns_list"], start=1):
        cell = ws.cell(row, i)
        cell.font = _font(s["body"], bold=False)
        cell.fill = fill
        # شماره تلفن چپ‌به‌راست خوانده شود تا «0915 123 4567» در شیت راست‌به‌چپ وارونه نشود (۱ = چپ‌به‌راست)
        cell.alignment = Alignment(horizontal=c["align"], vertical="center", wrap_text=s["body"]["wrap"],
                                   readingOrder=1 if c["field"] == "phone" else 0)
        if s["border"]:
            cell.border = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
    if s["body"]["height"]:
        ws.row_dimensions[row].height = s["body"]["height"]


def finish_sheet(ws, tpl: dict, last_row: int) -> None:
    """پس از نوشتن ردیف‌ها: محدوده فیلتر همه داده‌ها را بپوشاند."""
    if tpl["style"]["filter"]:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(tpl['columns_list']))}{max(1, last_row)}"


def build_sample(tpl: dict, rows: list[list[str]]) -> bytes:
    """فایل نمونه با همین قالب و چند ردیف، برای دیدن نتیجه در خود Excel."""
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    write_header(ws, tpl)
    for r, values in enumerate(rows, start=2):
        for i, v in enumerate(values, start=1):
            ws.cell(r, i, v or None)
        style_row(ws, r, tpl, r - 1)
    finish_sheet(ws, tpl, len(rows) + 1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- فونت‌های نصب‌شده ----------
def installed_fonts() -> list[dict]:
    """فونت‌های رایج و اینکه روی این رایانه نصب‌اند یا نه (اکسل فقط نام فونت را نگه می‌دارد)."""
    stems: set[str] = set()
    for d in (Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"):
        try:
            stems |= {re.sub(r"[\s_\-]", "", p.stem.lower()) for p in d.iterdir()}
        except OSError:
            continue
    return [{"name": n, "installed": any(s.startswith(key) for s in stems)} for n, key in FONTS]
