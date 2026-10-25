"""آزمون ثبت در اکسل روی فایل آزمایشی با همان ساختار فایل شرکت (با داده ساختگی)."""
from pathlib import Path

import openpyxl
import pytest
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from voice2excel.excel_mapping import new_profile
from voice2excel.excel_reader import inspect_workbook, lock_status
from voice2excel.excel_writer import ExcelWriteError, replace_original, write_export

HEADERS = ["تاریخ بازدید اول آقای صالحی ", "آدرس پروژه", "نام کارفرما", "همراه کارفرما", "توضیحات آقای صالحی",
           "تاریخ\nتماس", "پیگیری خانم شاکری پور", "تاریخ\nپیگیری"]


def make_company_like(path: Path, with_formula: bool = False) -> Path:
    wb = openpyxl.Workbook()
    wb.active.title = "Sheet2"  # شیت خالی، مثل فایل شرکت
    ws = wb.create_sheet("Sheet1")
    ws.sheet_view.rightToLeft = True
    thin = Side(style="thin")
    for i, h in enumerate(HEADERS, 1):
        c = ws.cell(1, i, h)
        c.font = Font(name="B Nazanin", bold=True)
        c.fill = PatternFill("solid", fgColor="FFD966")
    rows = [
        ("1405/7/20", "خواجه ربیع ، یوسف زاده 6/7", "مهندس آزمون‌یک", 9150000001, "تعداد 5 سقف ، سازه فلز"),
        (None, "امامت 60 ، پلاک 8", "مهندس آزمون‌دو", 9150000002, "تعداد 6 سقف"),
        None,
        ("1405/7/21", "سجادیه 10", "مهندس آزمون‌سه", "09150000003", "سازه بتون"),
    ]
    r = 2
    for row in rows:
        if row:
            for i, v in enumerate(row, 1):
                c = ws.cell(r, i, v)
                c.font = Font(name="B Nazanin", size=12)
                c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
                c.alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(r, 1).number_format = "@"
        ws.row_dimensions[r].height = 39.95
        r += 1
    ws.auto_filter.ref = "A1:H3"
    ws.column_dimensions["B"].width = 54
    dv = DataValidation(type="list", formula1='"بله,خیر"')
    ws.add_data_validation(dv)
    dv.add("G2:G100")
    ws.conditional_formatting.add("H2:H100", CellIsRule(operator="equal", formula=['"فوری"'], fill=PatternFill("solid", fgColor="FF0000")))
    if with_formula:
        s3 = wb.create_sheet("خلاصه")
        s3["A1"] = "تعداد"
        s3["B1"] = "=COUNTA(Sheet1!C2:C1000)"
    wb.active = 1
    wb.save(path)
    return path


def profile_for(path: Path) -> dict:
    rep = inspect_workbook(path)
    sheet = next(s for s in rep["sheets"] if s["name"] == "Sheet1")
    p = new_profile("t", str(path), "Sheet1", sheet["header_row"], sheet["headers"])
    p["confirmed"] = True
    return p


def rec(i, values, audio_id=1, b=0):
    return {"id": i, "audio_id": audio_id, "building_index": b, "values": values, "original_name": f"v{i}.ogg"}


V1 = {"visit_date": "1405/07/28", "engineer_name": "مهندس رجبی", "phone": "09373451255", "address": "سجادیه 58 ، قطعه دوم",
      "floors": "7", "structure_type": "بتون", "executed": "3 سقف اجرا شده"}
V2 = {"visit_date": "1405/07/28", "engineer_name": "مهندس نصیری", "phone": "09151112233\n09357654321", "address": "فلاحی 34",
      "notes": "=HYPERLINK(\"http://x\")", "project_name": "آراز"}


def test_inspect_detects_structure(tmp_path):
    p = make_company_like(tmp_path / "co.xlsx")
    rep = inspect_workbook(p)
    s = next(s for s in rep["sheets"] if s["name"] == "Sheet1")
    assert s["header_row"] == 1 and s["last_data_row"] == 5 and s["right_to_left"]
    assert s["auto_filter_stale"]
    assert not rep["blocking"]


def test_mapping_suggestion_matches_company_headers(tmp_path):
    p = profile_for(make_company_like(tmp_path / "co.xlsx"))
    assert p["columns"] == {"A": "visit_date", "B": "address", "C": "engineer_name", "D": "phone", "E": "notes_composed"}
    assert set(p["protected"]) == {"F", "G", "H"}


def test_export_writes_copy_and_preserves_original(tmp_path, monkeypatch):
    src = make_company_like(tmp_path / "co.xlsx", with_formula=True)
    before = src.read_bytes()
    rep = write_export(profile_for(src), [rec(1, V1), rec(2, V2, audio_id=2)])
    assert src.read_bytes() == before  # فایل اصلی دست نخورده
    assert Path(rep["backup_path"]).read_bytes() == before
    out = Path(rep["output_path"])
    assert out.exists() and out != src

    wb = openpyxl.load_workbook(out)
    ws = wb["Sheet1"]
    assert wb.sheetnames == ["Sheet2", "Sheet1", "خلاصه"]
    assert [ws.cell(1, i).value for i in range(1, 9)] == HEADERS
    # ردیف خالی میان روزها: آخرین داده ردیف 5 است، تاریخ جدید ← ردیف 6 خالی، داده از 7
    assert rep["first_row"] == 7
    assert all(ws.cell(6, c).value is None for c in range(1, 9))
    # تاریخ فقط در اولین ردیف روز، به همان شکل ردیف‌های قبلی فایل («1405/7/20»)
    assert ws["A7"].value == "1405/7/28" and ws["A8"].value is None
    assert ws["C7"].value == "مهندس رجبی"
    assert ws["D7"].value == "09373451255" and ws["D7"].data_type == "s"  # متن با صفر اول
    assert ws["D8"].value == "09151112233\n09357654321" and ws["D8"].alignment.wrap_text
    assert ws["E7"].value == "تعداد 7 سقف ، سازه بتون ، 3 سقف اجرا شده"
    # متن شبیه فرمول به‌صورت متن ثبت شده
    assert ws["E8"].data_type == "s" and "HYPERLINK" in ws["E8"].value and ws["E8"].value.startswith("پروژه: آراز")
    # ستون‌های محافظت‌شده دست نخورده‌اند
    assert all(ws.cell(r, c).value is None for r in (7, 8) for c in (6, 7, 8))
    # داده‌ها و قالب‌بندی قبلی
    assert ws["D2"].value == 9150000001 and ws["C5"].value == "مهندس آزمون‌سه"
    assert ws["C7"].font.name == "B Nazanin" and ws["C7"].border.top.style == "thin"
    assert ws.row_dimensions[7].height >= 39.95  # ارتفاع ردیف قبلی حفظ یا برای محتوای بیشتر بلندتر
    assert ws.sheet_view.rightToLeft
    assert ws.auto_filter.ref == "A1:H8"  # فیلتر قدیمی (A1:H3) ردیف‌های تازه را هم می‌پوشاند
    assert len(ws.data_validations.dataValidation) == 1 and len(ws.conditional_formatting) == 1
    assert ws.column_dimensions["B"].width == 54
    assert wb["خلاصه"]["B1"].value == "=COUNTA(Sheet1!C2:C1000)"  # فرمول حفظ شد


def test_same_day_continues_group_without_blank_row(tmp_path):
    src = make_company_like(tmp_path / "co.xlsx")
    rep = write_export(profile_for(src), [rec(1, {**V1, "visit_date": "1405/07/21"})])
    assert rep["first_row"] == 6
    ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
    assert ws["A6"].value is None  # همان روزِ ردیف قبلی


def test_phone_policy_like_existing(tmp_path):
    src = make_company_like(tmp_path / "co.xlsx")
    p = profile_for(src)
    p["policy"]["phone_format"] = "as_number_like_existing"
    rep = write_export(p, [rec(1, V1)])
    ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
    assert ws.cell(rep["first_row"], 4).value == "9373451255"


def test_header_change_blocks_write(tmp_path):
    src = make_company_like(tmp_path / "co.xlsx")
    p = profile_for(src)
    wb = openpyxl.load_workbook(src)
    wb["Sheet1"]["C1"] = "نام مشتری"
    wb.save(src)
    with pytest.raises(ExcelWriteError, match="عنوان ستون"):
        write_export(p, [rec(1, V1)])


def test_chart_file_blocked(tmp_path):
    from openpyxl.chart import BarChart, Reference
    src = make_company_like(tmp_path / "co.xlsx")
    wb = openpyxl.load_workbook(src)
    ws = wb["Sheet1"]
    ch = BarChart()
    ch.add_data(Reference(ws, min_col=4, min_row=1, max_row=3))
    ws.add_chart(ch, "J2")
    wb.save(src)
    rep = inspect_workbook(src)
    assert rep["blocking"]
    with pytest.raises(ExcelWriteError, match="نمودار"):
        write_export(profile_for(src), [rec(1, V1)])


def test_locked_original_reported_and_replace_refused(tmp_path):
    src = make_company_like(tmp_path / "co.xlsx")
    rep = write_export(profile_for(src), [rec(1, V1)])
    fh = open(src, "rb")  # شبیه باز بودن فایل در برنامه دیگر
    owner = src.with_name("~$" + src.name)
    owner.write_bytes(b"x")
    try:
        st = lock_status(src)
        assert st["locked"] and st["message"]
        with pytest.raises(ExcelWriteError):
            replace_original(rep["output_path"], str(src), rep["target_sha"])
    finally:
        fh.close()
        owner.unlink()
    res = replace_original(rep["output_path"], str(src), rep["target_sha"])
    assert Path(res["backup_path"]).exists()
    assert openpyxl.load_workbook(src)["Sheet1"].cell(rep["first_row"], 3).value == "مهندس رجبی"


def test_replace_refused_if_original_changed_after_export(tmp_path):
    src = make_company_like(tmp_path / "co.xlsx")
    rep = write_export(profile_for(src), [rec(1, V1)])
    wb = openpyxl.load_workbook(src)
    wb["Sheet1"]["C3"] = "مهندس ویرایش‌شده"
    wb.save(src)
    with pytest.raises(ExcelWriteError, match="تغییر کرده"):
        replace_original(rep["output_path"], str(src), rep["target_sha"])


def test_real_company_file_inspect_if_present():
    """فقط بررسی (بدون نوشتن) فایل واقعی شرکت در صورت وجود."""
    src = Path(__file__).resolve().parents[2] / "source"
    files = list(src.glob("*.xlsx")) if src.exists() else []
    if not files:
        pytest.skip("فایل واقعی شرکت در دسترس نیست")
    before = files[0].read_bytes()
    rep = inspect_workbook(files[0])
    assert files[0].read_bytes() == before
    s = next(s for s in rep["sheets"] if s["data_rows"] > 0)
    assert s["name"] == "Sheet1" and s["header_row"] == 1
    assert not rep["blocking"]


def test_text_style_inferred_and_applied():
    from voice2excel.text_style import apply_style, infer_style
    company = ["خواجه ربیع ، یوسف زاده 6/7", "امامت 60 ، پلاک 8", "سجادیه 58 ، قطعه دوم", "فلاحی 34 فاطمیه 5"]
    style = infer_style(company)
    assert style == {"sep": " ، ", "digits": "ascii"}
    assert apply_style("سجادیه ۵۸، قطعه دوم", style) == "سجادیه 58 ، قطعه دوم"
    persian = infer_style(["امامت ۶۰، پلاک ۸", "آزادی ۷۳، پلاک ۷"])
    assert persian == {"sep": "، ", "digits": "persian"}
    assert apply_style("امامت 60 , پلاک 8", persian) == "امامت ۶۰، پلاک ۸"


def test_export_uses_company_style(tmp_path):
    src = make_company_like(tmp_path / "co.xlsx")
    p = profile_for(src)
    p["policy"]["text_style"] = {"sep": " ، ", "digits": "ascii"}
    rep = write_export(p, [rec(1, {**V1, "address": "سجادیه ۵۸،قطعه دوم"})])
    ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
    assert ws.cell(rep["first_row"], 2).value == "سجادیه 58 ، قطعه دوم"
    assert ws.cell(rep["first_row"], 4).value == "09373451255"  # شماره دست نمی‌خورد


def test_export_autofits_columns_rows_and_extends_filter(tmp_path):
    """خروجی بدون ویرایش دستی مرتب است: ستون‌ها پهن، متن بلند چندخطی، ارتفاع ردیف به اندازه خط‌ها."""
    src = make_company_like(tmp_path / "co.xlsx")
    wb = openpyxl.load_workbook(src)
    wb["Sheet1"].auto_filter.ref = "A1:H3"  # فیلتر قدیمی که ردیف‌های تازه را نمی‌پوشاند
    wb.save(src)
    long_note = {**V1, "notes": "توضیح بسیار بلندی درباره این ساختمان که از عرض معمول یک ستون خیلی بیشتر است و باید چند خط شود"}
    prof = profile_for(src)
    widths_before = {c: openpyxl.load_workbook(src)["Sheet1"].column_dimensions[c].width for c in "ABCDE"}
    rep = write_export(prof, [rec(1, long_note)])
    ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
    r = rep["first_row"]
    notes_col = next(c for c, f in prof["columns"].items() if f == "notes_composed")
    assert ws.column_dimensions[notes_col].width > (widths_before[notes_col] or 8.43)  # پهن‌تر شد
    assert ws.column_dimensions[notes_col].width <= 60  # ولی نه بی‌نهایت
    assert ws[f"{notes_col}{r}"].alignment.wrap_text  # متن بلند چند خط
    assert ws.row_dimensions[r].height and ws.row_dimensions[r].height >= 30  # ارتفاع برای چند خط
    assert all(ws.column_dimensions[c].width >= (widths_before[c] or 0) for c in "ABCDE")  # هرگز باریک‌تر نمی‌شود
    assert ws.auto_filter.ref == f"A1:H{r}"
    prof["policy"]["autofit"] = False
    rep = write_export(prof, [rec(1, long_note)])
    ws = openpyxl.load_workbook(rep["output_path"])["Sheet1"]
    assert ws.column_dimensions[notes_col].width == widths_before[notes_col]


def test_date_format_follows_existing_rows():
    from voice2excel.excel_writer import _infer_date_format
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, v in enumerate(["1405/7/20", "1405/7/21", "1405/07/22"], start=2):
        ws.cell(i, 1, v)
    assert _infer_date_format(ws, 1, 2, 4) == "compact"
    ws.cell(5, 1, "1405/07/23"); ws.cell(6, 1, "1405/07/24")
    assert _infer_date_format(ws, 1, 2, 6) == ""
    assert _infer_date_format(ws, None, 2, 6) == "" and _infer_date_format(openpyxl.Workbook().active, 1, 2, 1) == ""
