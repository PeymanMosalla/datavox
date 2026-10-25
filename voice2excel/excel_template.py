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
# تقسیم خروجی: یک فایل، فایل جدا برای هر ماه یا روز، یا شیت جدا برای هر ماه در یک فایل
SPLITS = {"none": "یک فایل", "month_file": "فایل جدا برای هر ماه", "day_file": "فایل جدا برای هر روز",
          "month_sheet": "شیت جدا برای هر ماه (در یک فایل)"}
# رنگ‌گذاری هوشمند ردیف‌ها (خالی = خاموش)
DEFAULT_HIGHLIGHTS = {"warn": "#FFF3DC", "today": "", "followup": "#FDE8EA", "followup_days": 3}
DEFAULT_FIELDS = [("visit_date", 14), ("engineer_name", 22), ("phone", 16), ("address", 36),
                  ("technical_summary", 34), ("notes", 30)]


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field) or COMPUTED_FIELDS.get(field) or EXTRA_FIELDS.get(field, field)


def new_template(name: str, title: str, folder: str) -> dict:
    return {
        "name": name, "title": title, "mode": "new", "confirmed": True,
        "columns_list": [{"field": f, "title": field_label(f), "width": w, "align": "right"} for f, w in DEFAULT_FIELDS],
        "style": _deep_copy(DEFAULT_STYLE),
        "output": {"folder": folder, "file": title, "split": "none"},
        # برخلاف فایل شرکت، در فایل تازه هر ردیف تاریخ خودش را دارد و ردیف خالی میان روزها نیست (قابل تغییر)
        "policy": {"text_style": {"sep": " ، ", "digits": "ascii"}, "blank_row_between_dates": False,
                   "date_first_row_only": False, "highlights": dict(DEFAULT_HIGHLIGHTS)},
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
    policy = dict(tpl.get("policy") or {})
    if "highlights" in policy:
        policy["highlights"] = clean_highlights(policy["highlights"])
    return {**tpl, "mode": "new", "confirmed": True, "columns_list": cols, "style": style, "policy": policy,
            "output": {"folder": str(out.get("folder") or "").strip().strip('"'), "file": file,
                       "split": out.get("split") if out.get("split") in SPLITS else "none"}}


def clean_highlights(h) -> dict:
    h = h if isinstance(h, dict) else {}
    out = {k: _color(h.get(k), "") if h.get(k) else "" for k in ("warn", "today", "followup")}
    out["followup_days"] = int(_num(h.get("followup_days"), 0, 60, DEFAULT_HIGHLIGHTS["followup_days"]))
    return out


def period(visit_date: str, kind: str) -> str:
    """«1405/07/28» ← ماه «1405-07» یا روز «1405-07-28» (برای نام فایل یا شیت)."""
    from .dates_fa import parse_jalali

    d = parse_jalali(visit_date or "")
    if not d:
        return "بدون تاریخ"
    return f"{d.year}-{d.month:02d}" + (f"-{d.day:02d}" if kind == "day" else "")


def target(tpl: dict, visit_date: str | None = None) -> tuple[Path, str]:
    """(مسیر فایل، نام شیت) برای رکوردی با این تاریخ بازدید؛ بدون تاریخ = امروز."""
    from .dates_fa import format_jalali, today_jalali

    out = tpl["output"]
    split = out.get("split", "none")
    vd = visit_date or format_jalali(today_jalali())
    name, sheet = out["file"], "Sheet1"
    if split == "month_file":
        name = f"{name} {period(vd, 'month')}"
    elif split == "day_file":
        name = f"{name} {period(vd, 'day')}"
    elif split == "month_sheet":
        sheet = period(vd, "month")
    return Path(out["folder"]) / f"{name}.xlsx", sheet


def target_path(tpl: dict, visit_date: str | None = None) -> Path:
    return target(tpl, visit_date)[0]


def group_records(tpl: dict, records: list[dict]) -> list[tuple[str, list[dict]]]:
    """رکوردها بر اساس فایل/شیت مقصد گروه‌بندی می‌شوند؛ خروجی: [(تاریخ نماینده گروه، رکوردها)]."""
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault(target(tpl, r["values"].get("visit_date", "")), []).append(r)
    return [(g[0]["values"].get("visit_date", ""), g) for g in groups.values()]


def writer_profile(tpl: dict, create: bool = True, visit_date: str | None = None) -> dict:
    """نگاشت معادل قالب «new» برای موتور ثبت؛ create: اگر فایل خروجی نیست، با سرستون ساخته شود."""
    path, sheet = target(tpl, visit_date)
    if create and not path.exists():
        if not path.parent.is_dir():
            raise FileNotFoundError(f"پوشه خروجی «{path.parent}» پیدا نشد؛ در «قالب اکسل» پوشه را انتخاب کنید.")
        create_workbook(tpl, path, sheet)
    letters = [get_column_letter(i) for i in range(1, len(tpl["columns_list"]) + 1)]
    columns = {}
    for col, c in zip(letters, tpl["columns_list"]):
        columns[col] = f"const:{c.get('value', '')}" if c["field"] == "constant" else c["field"]
    return {
        **tpl, "excel_path": str(path), "sheet": sheet, "header_row": 1,
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


def create_workbook(tpl: dict, path: Path, sheet: str = "Sheet1") -> None:
    """فایل تازه با سرستون، عرض ستون‌ها، جهت راست‌به‌چپ، سرستون ثابت و فیلتر."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
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


def highlight(policy: dict, rec: dict, today: str) -> str:
    """رنگ ردیف بر اساس وضعیت رکورد؛ اولویت: پیگیری نزدیک، ردیف ناقص، بازدید امروز."""
    from .dates_fa import parse_jalali

    h = policy.get("highlights") or {}
    v = rec.get("values", {})
    if h.get("followup") and v.get("followup_date"):
        d, t = parse_jalali(v["followup_date"]), parse_jalali(today)
        if d and t and 0 <= (d.togregorian() - t.togregorian()).days <= h.get("followup_days", 3):
            return h["followup"]
    checks = (rec.get("validation") or {}).get("fields") or {}
    if h.get("warn") and any((checks.get(k) or {}).get("status") in ("missing", "invalid")
                             for k in ("engineer_name", "phone", "address")):
        return h["warn"]  # ردیف ناقص: نام، شماره یا آدرس ندارد یا نامعتبر است
    if h.get("today") and v.get("visit_date") == today:
        return h["today"]
    return ""


def paint_row(ws, row: int, ncols: int, color: str) -> None:
    for i in range(1, ncols + 1):
        ws.cell(row, i).fill = _fill(color)


def finish_sheet(ws, tpl: dict, last_row: int) -> None:
    """پس از نوشتن ردیف‌ها: محدوده فیلتر همه داده‌ها را بپوشاند."""
    if tpl["style"]["filter"]:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(tpl['columns_list']))}{max(1, last_row)}"


def _rgb(color, default: str) -> str:
    """رنگ openpyxl ← «#RRGGBB»؛ رنگ‌های پوسته (theme) که مقدار ثابت ندارند، پیش‌فرض می‌گیرند."""
    rgb = getattr(color, "rgb", None) if color is not None and getattr(color, "type", "") == "rgb" else None
    return "#" + rgb[-6:].upper() if isinstance(rgb, str) and len(rgb) >= 6 and rgb != "00000000" else default


def from_file(path: Path) -> dict:
    """«مثل این فایل»: ستون‌ها (فیلد هر ستون از روی عنوانش حدس زده می‌شود) و ظاهر سرستون و ردیف‌ها.

    ستونی که فیلدش شناخته نشد، خالی می‌ماند (ستون «مقدار ثابت» بدون مقدار) تا چیدمان فایل حفظ شود.
    """
    from .excel_mapping import suggest_mapping
    from .excel_reader import detect_header_row, header_map

    wb = openpyxl.load_workbook(path)
    try:
        ws = max(wb.worksheets, key=lambda w: w.max_row)
        hr = detect_header_row(ws)
        headers = header_map(ws, hr)
        if not headers:
            raise ValueError("سرستونی در این فایل پیدا نشد.")
        mapping, _ = suggest_mapping(headers)
        cols, titles = [], set()
        for col, title in headers.items():
            base = t = re.sub(r"\s+", " ", str(title)).strip()[:76] or col
            n = 2
            while t in titles:  # عنوان تکراری در فایل
                t, n = f"{base} {n}", n + 1
            titles.add(t)
            data = ws[f"{col}{hr + 1}"]
            field = mapping.get(col, "constant")
            cols.append({"field": field, "title": t,
                         "width": ws.column_dimensions[col].width or 14,
                         "align": data.alignment.horizontal if data.alignment.horizontal in ALIGNS else "right",
                         **({"value": ""} if field == "constant" else {})})
        first = next(iter(headers))
        h, d1, d2 = ws[f"{first}{hr}"], ws[f"{first}{hr + 1}"], ws[f"{first}{hr + 2}"]
        z1, z2 = _rgb(d1.fill.fgColor, ""), _rgb(d2.fill.fgColor, "")
        style = {
            "header": {"font": h.font.name or "Tahoma", "size": h.font.sz or 11, "bold": bool(h.font.b),
                       "color": _rgb(h.font.color, "#000000"), "fill": _rgb(h.fill.fgColor, "#FFFFFF") if h.fill.fill_type else "#FFFFFF",
                       "height": ws.row_dimensions[hr].height or 0},
            "body": {"font": d1.font.name or h.font.name or "Tahoma", "size": d1.font.sz or 10,
                     "color": _rgb(d1.font.color, "#000000"), "wrap": bool(d1.alignment.wrap_text),
                     "height": ws.row_dimensions[hr + 1].height or 0},
            "border": bool(h.border.left.style or d1.border.left.style),
            "zebra": (z2 or z1) if z1 != z2 else "",
            "rtl": bool(ws.sheet_view.rightToLeft), "freeze": bool(ws.freeze_panes), "filter": bool(ws.auto_filter.ref),
        }
        return {"columns_list": cols, "style": style}
    finally:
        wb.close()


EXPORT_KEYS = ("title", "columns_list", "style", "policy")


def to_export(tpl: dict) -> dict:
    """قالب برای انتقال به رایانه یا مشتری دیگر؛ پوشه خروجی (مخصوص این رایانه) همراهش نیست."""
    return {"v2x_template": 1, **{k: tpl[k] for k in EXPORT_KEYS if k in tpl},
            "output": {"file": tpl["output"]["file"], "split": tpl["output"].get("split", "none")}}


def from_export(data: dict, name: str, folder: str) -> dict:
    if not isinstance(data, dict) or data.get("v2x_template") != 1:
        raise ValueError("این فایل، قالب «ثبت ویس» نیست.")
    tpl = {k: data[k] for k in EXPORT_KEYS if k in data}
    return clean({**tpl, "name": name, "title": str(tpl.get("title") or "قالب واردشده")[:60],
                  "output": {**(data.get("output") or {}), "folder": folder}})


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
