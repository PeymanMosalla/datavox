"""قالب نگاشت: کدام فیلد در کدام ستون اکسل نوشته شود.

قالب‌ها در data/profiles/*.json ذخیره می‌شوند. عنوان ستون‌ها به‌عنوان «اثر انگشت» نگه
داشته می‌شود تا اگر ساختار فایل تغییر کرد، پیش از نوشتن متوقف شویم.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import DATA_DIR
from .normalizer import normalize_text
from .text_style import apply_style

DEFAULT_POLICY = {
    "phone_format": "text_leading_zero",  # یا as_number_like_existing
    "blank_row_between_dates": True,
    "date_first_row_only": True,
    "copy_style_from_last_row": True,
    "multi_phone_separator": "\n",
    "notes_parts": ["technical_summary", "project_name", "building_type", "permit_status",
                    "customer_need", "notes", "followup"],
}

# پیشنهاد خودکار نگاشت بر اساس واژه‌های عنوان ستون (ترتیب مهم است)
_HEADER_RULES = [
    (r"تاریخ.*(بازدید|ثبت|ضبط)|^تاریخ$", "visit_date"),
    (r"آدرس|نشانی", "address"),
    (r"همراه|موبایل|تلفن|شماره", "phone"),
    (r"نام.*(کارفرما|مهندس|مشتری)|کارفرما|مهندس|^نام", "engineer_name"),
    (r"پروژه|ساختمان", "project_name"),
    (r"توضیح", "notes_composed"),
]
# ستون‌هایی که به پیگیری فروش (افراد دیگر) تعلق دارند و نباید پر شوند
_PROTECT_RULES = r"پیگیری|تاریخ\s*تماس|نتیجه|وضعیت"


# قالب «افزودن به فایل شرکت» (نگاشت ستون‌های فایل موجود)؛ قالب‌های دیگر «فایل جدید»اند
COMPANY = "default"
# تنظیمات «قالب مقادیر» که در صفحه «قالب اکسل» برای هر دو نوع قالب قابل تغییرند
VALUE_FORMAT_KEYS = {"date_format", "phone_format", "phone_group", "multi_phone_separator", "name_title",
                     "text_style", "notes_parts", "blank_row_between_dates", "date_first_row_only", "highlights"}


def profiles_dir() -> Path:
    d = DATA_DIR / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def suggest_mapping(headers: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    columns: dict[str, str] = {}
    protected: list[str] = []
    used = set()
    for col, h in headers.items():
        hn = normalize_text(h).replace("\n", " ")
        if re.search(_PROTECT_RULES, hn):
            protected.append(col)
            continue
        for pat, field in _HEADER_RULES:
            if field in used:
                continue
            if re.search(pat, hn):
                columns[col] = field
                used.add(field)
                break
    return columns, protected


def new_profile(name: str, excel_path: str, sheet: str, header_row: int, headers: dict[str, str]) -> dict:
    columns, protected = suggest_mapping(headers)
    return {
        "name": name,
        "excel_path": excel_path,
        "sheet": sheet,
        "header_row": header_row,
        "headers": headers,
        "columns": columns,
        "protected": protected,
        "policy": dict(DEFAULT_POLICY),
        "confirmed": False,
    }


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name) or "default"


def save_profile(profile: dict) -> None:
    p = profiles_dir() / f"{_safe_name(profile['name'])}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def load_profile(name: str) -> dict | None:
    p = profiles_dir() / f"{_safe_name(name)}.json"
    if not p.exists():
        return None
    prof = json.loads(p.read_text(encoding="utf-8"))
    prof.setdefault("policy", {})
    if prof.get("mode") != "new":  # پیش‌فرض‌های قرارداد فایل شرکت؛ قالب «فایل جدید» پیش‌فرض‌های خودش را دارد
        for k, v in DEFAULT_POLICY.items():
            prof["policy"].setdefault(k, v)
    return prof


def list_profiles() -> list[str]:
    return sorted(p.stem for p in profiles_dir().glob("*.json"))


def delete_profile(name: str) -> None:
    (profiles_dir() / f"{_safe_name(name)}.json").unlink(missing_ok=True)


# ---------- ساخت مقدار هر ستون ----------

def technical_summary(v: dict) -> str:
    parts = []
    if v.get("floors"):
        parts.append(f"تعداد {v['floors']} {v.get('floors_unit') or 'سقف'}")
    if v.get("structure_type"):
        parts.append(f"سازه {v['structure_type']}")
    if v.get("executed"):
        parts.append(v["executed"])
    if v.get("stage"):
        parts.append(v["stage"])
    if v.get("units"):
        parts.append(f"تعداد {v['units']} واحد")
    return " ، ".join(parts)


def followup_text(v: dict) -> str:
    action = v.get("followup_action", "")
    date = v.get("followup_date", "")
    if not action and not date:
        return ""
    s = f"پیگیری: {action}" if action else "پیگیری"
    if date:
        s += f" (تاریخ پیشنهادی {date})"
    return s


def notes_composed(v: dict, mapped_fields: set[str], parts: list[str]) -> str:
    out = []
    for p in parts:
        if p in mapped_fields:
            continue
        if p == "technical_summary":
            s = technical_summary(v)
        elif p == "followup":
            s = followup_text(v)
        elif p == "project_name":
            s = f"پروژه: {v['project_name']}" if v.get("project_name") else ""
        elif p == "building_type":
            s = v.get("building_type", "")
            if s and s in technical_summary(v):
                s = ""
        else:
            s = v.get(p, "")
        if s:
            out.append(s)
    return " ، ".join(out)


# فیلدهایی که با سبک فایل شرکت (جداکننده و نوع رقم) نوشته نمی‌شوند
_UNSTYLED = {"phone", "visit_date", "followup_date", "source_file", "transcript", "validation_summary", "row_number"}
_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def format_date(value: str, fmt: str | None) -> str:
    """«1405/07/28»؛ persian ← «۱۴۰۵/۰۷/۲۸»؛ long ← «۲۸ مهر ۱۴۰۵». تاریخ ناخوانا دست نمی‌خورد."""
    from .dates_fa import parse_jalali
    from .normalizer import to_persian_digits

    d = parse_jalali(value) if value and fmt in ("persian", "long") else None
    if not d:
        return value
    if fmt == "long":
        return to_persian_digits(f"{d.day} {_MONTHS[d.month - 1]} {d.year}")
    return to_persian_digits(f"{d.year}/{d.month:02d}/{d.day:02d}")


def format_phone(p: str, group: bool) -> str:
    if group and re.fullmatch(r"09\d{9}", p):
        return f"{p[:4]} {p[4:7]} {p[7:]}"
    return p


def cell_values(profile: dict, record: dict) -> dict[str, str]:
    """مقدار هر ستون برای یک رکورد. record: {values, original_name, transcript, validation}."""
    v = record["values"]
    mapped = set(profile["columns"].values())
    policy = profile.get("policy", DEFAULT_POLICY)
    style = policy.get("text_style")
    out: dict[str, str] = {}
    for col, field in profile["columns"].items():
        if field.startswith("const:"):
            out[col] = field[6:]
            continue
        if field == "row_number":
            out[col] = ""  # در plan_rows از روی جایگاه ردیف پر می‌شود
            continue
        if field == "notes_composed":
            val = notes_composed(v, mapped, policy.get("notes_parts", DEFAULT_POLICY["notes_parts"]))
        elif field == "technical_summary":
            val = technical_summary(v)
        elif field == "phone":
            phones = [p.strip() for p in str(v.get("phone", "")).split("\n") if p.strip()]
            if policy.get("phone_format") == "as_number_like_existing":
                phones = [p[1:] if p.startswith("09") else p for p in phones]
            phones = [format_phone(p, policy.get("phone_group", False)) for p in phones]
            val = policy.get("multi_phone_separator", "\n").join(phones)
        elif field in ("visit_date", "followup_date"):
            val = format_date(v.get(field, ""), policy.get("date_format"))
        elif field == "engineer_name" and policy.get("name_title") == "drop":
            from .normalizer import strip_title
            val = strip_title(v.get(field, ""))[1]
        elif field == "source_file":
            val = record.get("original_name", "")
        elif field == "transcript":
            val = record.get("transcript", "")
        elif field == "validation_summary":
            val = " ؛ ".join(record.get("validation", {}).get("reasons", []))
        elif field == "followup":
            val = followup_text(v)
        else:
            val = v.get(field, "")
        if style and val and field not in _UNSTYLED:
            val = apply_style(val, style)
        out[col] = val or ""
    return out
