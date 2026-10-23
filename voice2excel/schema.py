"""ساختار داده‌های استخراج و اعتبارسنجی (قابل اعتبارسنجی با Pydantic)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FieldStatus = Literal["valid", "review", "missing", "invalid"]
RecordStatus = Literal["ready", "review", "invalid"]

# فهرست فیلدها: کلید، عنوان فارسی، گروه
FIELD_DEFS: list[tuple[str, str, str]] = [
    ("visit_date", "تاریخ بازدید", "main"),
    ("engineer_name", "نام مهندس / شخص تماس", "main"),
    ("phone", "شماره تماس", "main"),
    ("project_name", "نام پروژه / ساختمان", "main"),
    ("address", "آدرس", "main"),
    ("building_type", "نوع ساختمان", "tech"),
    ("structure_type", "نوع سازه", "tech"),
    ("floors", "تعداد سقف", "tech"),
    ("executed", "سقف‌های اجراشده", "tech"),
    ("units", "تعداد واحد", "tech"),
    ("stage", "مرحله ساخت", "tech"),
    ("permit_status", "وضعیت نقشه / مجوز", "tech"),
    ("customer_need", "نیاز اعلام‌شده", "notes"),
    ("notes", "توضیحات تکمیلی", "notes"),
    ("followup_action", "اقدام بعدی", "followup"),
    ("followup_time_text", "زمان پیگیری (گفته‌شده)", "followup"),
    ("followup_date", "تاریخ پیگیری پیشنهادی", "followup"),
    ("city", "شهر", "address"),
    ("neighborhood", "محله", "address"),
    ("street", "خیابان", "address"),
    ("alley", "کوچه / فرعی", "address"),
    ("plate", "پلاک / قطعه", "address"),
]
FIELD_LABELS = {k: label for k, label, _ in FIELD_DEFS}

# فیلدهای ترکیبی که فقط برای نگاشت به اکسل ساخته می‌شوند
COMPUTED_FIELDS = {
    "technical_summary": "خلاصه فنی (سبک ستون توضیحات)",
    "notes_composed": "توضیحات ترکیبی (فنی + توضیحات + پیگیری)",
    "source_file": "نام فایل ویس",
    "transcript": "متن کامل ویس",
    "validation_summary": "وضعیت اعتبارسنجی",
}


class FieldValue(BaseModel):
    value: str = ""
    evidence: str = ""  # بخشی از متن که مقدار از آن آمده
    span: list[int] | None = None  # [آغاز، پایان] بخش مبدأ در متن پردازش‌شده (برای پخش همان تکه از ویس)
    inherited: bool = False  # از ساختمان قبلی همان ویس به ارث رسیده
    notes: list[str] = Field(default_factory=list)


class PhoneInfo(BaseModel):
    heard: str
    normalized: str
    kind: str
    explicit: bool
    ambiguous: bool
    notes: list[str] = Field(default_factory=list)
    from_words: bool = False


class Segment(BaseModel):
    text: str
    category: str
    block: int


class ExtractedRecord(BaseModel):
    building_index: int = 0
    building_count: int = 1
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    phones: list[PhoneInfo] = Field(default_factory=list)
    title: str = ""  # «مهندس»، «آقای»، ...
    ambiguities: list[str] = Field(default_factory=list)
    # پیشنهادهایی از اصلاحات قبلی کاربر که هنوز به حد اعمال خودکار نرسیده‌اند: {فیلد: [مقدار پیشنهادی]}
    learned_suggestions: dict[str, list[str]] = Field(default_factory=dict)

    def get(self, key: str) -> str:
        fv = self.fields.get(key)
        return fv.value if fv else ""


class ExtractionResult(BaseModel):
    records: list[ExtractedRecord]
    segments: list[Segment] = Field(default_factory=list)
    text: str = ""  # متن پردازش‌شده‌ای که استخراج روی آن انجام شد


class FieldCheck(BaseModel):
    status: FieldStatus
    reasons: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    status: RecordStatus
    fields: dict[str, FieldCheck] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    duplicates: list[dict] = Field(default_factory=list)
