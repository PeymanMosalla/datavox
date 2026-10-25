"""کنترل کیفیت و اعتبارسنجی، مستقل از موتور استخراج.

هر فیلد وضعیت مستقل دارد (valid / review / missing / invalid) و دلیل آن به فارسی
ثبت می‌شود. وضعیت رکورد فقط از فیلدهای الزامی، ابهام‌ها و تکرار قوی محاسبه می‌شود؛
فیلد اختیاریِ غایب یا مشکوک مانع ثبت نیست، فقط هشدار می‌دهد.
"""
from __future__ import annotations

import re

from . import dictionary
from .config import Settings
from .database import Database
from .dates_fa import parse_jalali
from .phone import classify
from .schema import FIELD_LABELS, FieldCheck, ValidationResult


def _check_phone(value: str, meta: dict, edited: bool, settings: Settings) -> FieldCheck:
    lines = [ln.strip() for ln in str(value).replace("\r", "\n").split("\n") if ln.strip()]
    if not lines:
        return FieldCheck(status="missing", reasons=["شماره تماس در ویس پیدا نشد."])
    status = "valid"
    reasons: list[str] = []
    suggestions: list[str] = []
    phones_meta = {p.get("normalized"): p for p in meta.get("phones", [])}

    def worsen(s: str):
        nonlocal status
        order = ["valid", "review", "invalid"]
        if order.index(s) > order.index(status):
            status = s

    for ln in lines:
        if re.search(r"[^\d+\s\-]", ln):
            worsen("invalid")
            reasons.append(f"«{ln}» به‌جز رقم، نویسه دیگری دارد.")
            continue
        kind, norm, notes = classify(ln)
        pm = phones_meta.get(norm) if not edited else None
        for n in (pm or {}).get("notes", []) if pm else notes:
            if n not in reasons:
                reasons.append(n)
        if kind == "incomplete":
            worsen("invalid")
            reasons.append(f"شماره {norm} ناقص یا نامعتبر است ({len(norm)} رقم)؛ رقمی حدس زده نشد.")
            continue
        if kind == "local":
            worsen("review")
            if settings.default_area_code:
                suggestions.append(f"0{settings.default_area_code.lstrip('0')}{norm}")
            continue
        if pm and pm.get("ambiguous"):
            worsen("review")
            reasons.append("مرز گروه‌های عددی در گفتار روشن نبود (مثلاً «نهصد پانزده» بدون «و»)؛ ترتیب رقم‌ها را با ویس بررسی کنید.")
        if not edited and settings.review_spoken_phones:
            worsen("review")
            reasons.append("شماره را با شنیدن ویس تأیید کنید (مدل گفتار گاهی رقمی مثل «سه» و «سی» را اشتباه می‌شنود).")
        if pm and not pm.get("explicit") and kind != "mobile":
            worsen("review")
            reasons.append("پیش از این شماره واژه‌ای مثل «شماره» یا «تلفن» نیامده و فقط از الگوی رقم‌ها برداشت شد.")
    if meta.get("phone_inherited") and not edited:
        worsen("review")
        reasons.append("شماره از ساختمان دیگرِ همین ویس برداشته شده؛ تعلق آن را تأیید کنید.")
    if edited and status == "valid":
        reasons.append("اصلاح یا تأییدشده توسط کاربر.")
    if status == "valid" and not reasons:
        reasons.append("قالب شماره معتبر است.")
    return FieldCheck(status=status, reasons=reasons, suggestions=suggestions)


def _check_name(db: Database, value: str, etype: str, meta_notes: list[str], inherited: bool, edited: bool,
                settings: Settings, required: bool) -> FieldCheck:
    if not value.strip():
        return FieldCheck(status="missing", reasons=["در ویس گفته نشده است."])
    if re.search(r"\d", value):
        return FieldCheck(status="invalid", reasons=["نام نباید رقم داشته باشد."])
    reasons = list(meta_notes)
    status = "valid"
    suggestions: list[str] = []
    if inherited and not edited:
        status = "review"
        reasons.append("از ساختمان دیگرِ همین ویس برداشته شده؛ تعلق آن را تأیید کنید.")
    matches = dictionary.lookup(db, value, etype, settings.similarity_suggest)
    exact = [m for m in matches if m.exact]
    if exact:
        reasons.append("در واژه‌نامه وجود دارد.")
    elif matches:
        title = ""
        if etype == "engineer":
            from .normalizer import strip_title
            title = strip_title(value)[0]
        suggestions = [f"{title} {m.canonical}".strip() for m in matches]
        if not edited:
            status = "review"
            reasons.append("املای مشابهی در واژه‌نامه هست؛ ممکن است همان شخص با املای دیگر باشد.")
        else:
            reasons.append("املای مشابهی در واژه‌نامه هست؛ فقط برای اطلاع.")
    else:
        if edited:
            reasons.append("نام جدید با تأیید کاربر.")
        else:
            status = "review" if status == "valid" else status
            reasons.append("نام جدید است و در واژه‌نامه نیست؛ املای آن را با ویس تأیید کنید.")
    if any("گفته نشده" in n for n in meta_notes) and not edited:
        status = "review"
    return FieldCheck(status=status, reasons=reasons, suggestions=suggestions)


def _check_address(db: Database, value: str, street: str, edited: bool, settings: Settings) -> FieldCheck:
    if not value.strip():
        return FieldCheck(status="missing", reasons=["آدرس در ویس پیدا نشد."])
    reasons = []
    suggestions = []
    status = "valid"
    has_detail = bool(re.search(r"\d", value)) or bool(re.search(r"پلاک|کوچه|نبش|قطعه|بلوار|خیابان|میدان|جنب|روبروی", value))
    if not has_detail and not edited:
        status = "review"
        reasons.append("آدرس جزئیات کافی (شماره خیابان، پلاک یا نشانه) ندارد.")
    if street and not edited:
        name_only = re.sub(r"^(?:خیابان|خیابون|بلوار|بولوار)\s+", "", re.sub(r"\s*\d+.*$", "", street)).strip()
        if name_only:
            matches = dictionary.lookup(db, name_only, "street", settings.similarity_suggest)
            if matches and not any(m.exact for m in matches):
                suggestions = [value.replace(name_only, m.canonical, 1) for m in matches[:3]]
                status = "review"
                reasons.append(f"نام خیابان «{name_only}» در واژه‌نامه نیست ولی املای مشابه دارد.")
    if status == "valid":
        reasons.append("اصلاح یا تأییدشده توسط کاربر." if edited else "آدرس ثبت شد؛ اعتبار جغرافیایی آن بررسی نشده است.")
    return FieldCheck(status=status, reasons=reasons, suggestions=suggestions)


def validate(db: Database, values: dict, meta: dict, settings: Settings, edited: set[str] | None = None,
             duplicates: list[dict] | None = None) -> ValidationResult:
    """values: مقدار فعلی فیلدها؛ meta: اطلاعات استخراج (شماره‌ها، ارث‌بری، ابهام‌ها)."""
    edited = edited or set()
    fields: dict[str, FieldCheck] = {}
    notes_meta = meta.get("field_notes", {})
    inherited = set(meta.get("inherited", []))

    fields["engineer_name"] = _check_name(
        db, values.get("engineer_name", ""), "engineer", notes_meta.get("engineer_name", []),
        "engineer_name" in inherited, "engineer_name" in edited, settings,
        "engineer_name" in settings.required_fields)
    fields["phone"] = _check_phone(values.get("phone", ""), {**meta, "phone_inherited": "phone" in inherited},
                                   "phone" in edited, settings)
    fields["address"] = _check_address(db, values.get("address", ""), values.get("street", ""),
                                       "address" in edited, settings)
    vd = values.get("visit_date", "")
    if not vd:
        fields["visit_date"] = FieldCheck(status="missing", reasons=["تاریخ بازدید مشخص نیست."])
    elif parse_jalali(vd) is None:
        fields["visit_date"] = FieldCheck(status="invalid", reasons=["قالب تاریخ شمسی باید مانند 1405/07/28 باشد."])
    else:
        fields["visit_date"] = FieldCheck(status="valid", reasons=["تاریخ دسته ویس‌ها."])

    if values.get("project_name"):
        fields["project_name"] = _check_name(db, values["project_name"], "project", [], False,
                                             "project_name" in edited, settings,
                                             "project_name" in settings.required_fields)
        if fields["project_name"].status == "review" and "project_name" not in settings.required_fields:
            # نام پروژه اختیاری است: نام جدید پروژه فقط اطلاع‌رسانی است
            if not fields["project_name"].suggestions:
                fields["project_name"].status = "valid"
    elif "project_name" in settings.required_fields:
        fields["project_name"] = FieldCheck(status="missing", reasons=["نام پروژه گفته نشده است."])

    if values.get("followup_time_text") and not values.get("followup_date"):
        reason = (notes_meta.get("followup_date") or notes_meta.get("followup_time_text") or
                  ["تاریخ دقیق پیگیری قابل محاسبه نبود."])
        fields["followup_date"] = FieldCheck(status="review", reasons=reason)
    elif values.get("followup_date"):
        if parse_jalali(values["followup_date"]) is None:
            fields["followup_date"] = FieldCheck(status="invalid", reasons=["قالب تاریخ پیگیری نامعتبر است."])
        else:
            fields["followup_date"] = FieldCheck(
                status="valid" if "followup_date" in edited else "review",
                reasons=(notes_meta.get("followup_date") or []) + ["تاریخ پیشنهادی است؛ تأیید کنید."]
                if "followup_date" not in edited else ["تأییدشده توسط کاربر."])

    for k in ("floors", "units"):
        if values.get(k) and not str(values[k]).isdigit():
            fields[k] = FieldCheck(status="invalid", reasons=["باید عدد باشد."])

    # وضعیت رکورد
    reasons: list[str] = []
    required = list(settings.required_fields)
    req_checks = {k: fields.get(k) or FieldCheck(status="missing", reasons=["گفته نشده است."]) for k in required}
    for k, fc in req_checks.items():
        fields.setdefault(k, fc)
    if all(fc.status == "missing" for fc in req_checks.values()):
        status = "invalid"
        reasons.append("هیچ‌یک از اطلاعات اصلی (نام، شماره، آدرس) در ویس پیدا نشد.")
    else:
        status = "ready"
        for k, fc in req_checks.items():
            if fc.status != "valid":
                status = "review"
                label = FIELD_LABELS.get(k, k)
                reasons.append(f"{label}: " + {"missing": "پیدا نشد", "invalid": "نامعتبر",
                                                "review": "نیاز به بررسی"}[fc.status])
    for a in meta.get("ambiguities", []):
        if "ambiguities" not in edited:
            status = "review" if status == "ready" else status
            reasons.append(a)
    dups = duplicates or []
    if any(d["level"] == "strong" for d in dups):
        status = "review" if status == "ready" else status
        reasons.append("احتمال تکراری بودن این رکورد زیاد است؛ رکوردهای مشابه را ببینید.")
    elif dups:
        reasons.append("رکورد مشابهی وجود دارد (برای اطلاع؛ ممکن است ساختمان دیگری از همان مهندس باشد).")
    if status == "ready":
        reasons.append("همه فیلدهای الزامی معتبرند.")
    # پیشنهاد از اصلاحات قبلی کاربر (هنوز به حد اعمال خودکار نرسیده)؛ وضعیت فیلد را تغییر نمی‌دهد
    for field, sugs in (meta.get("learned_suggestions") or {}).items():
        if field in edited:
            continue
        fc = fields.setdefault(field, FieldCheck(status="valid"))
        for sg in sugs:
            if sg not in fc.suggestions and sg != values.get(field):
                fc.suggestions.append(sg)
        fc.reasons.append("پیش‌تر اصلاح مشابهی در این فیلد انجام داده‌اید؛ پیشنهاد آن نمایش داده شده است.")
    return ValidationResult(status=status, fields=fields, reasons=reasons, duplicates=dups)
