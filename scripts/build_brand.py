"""ساخت نشان‌های DataVox از تصویر اصلی (packaging/brand/datavox-source.png).

خروجی‌ها در مخزن ثبت می‌شوند و در اجرای برنامه به این ابزار نیازی نیست:
- packaging/brand/icon.ico: آیکون فایل اجرایی و میان‌بر (نماد روی کاشی سفید گوشه‌گرد، خوانا روی نوار وظیفه تیره)
- voice2excel/web/brand/mark.png: نماد بدون متن (منو، نوار عنوان، آیکون زبانه)
- voice2excel/web/brand/logo.png: نشان کامل با نام (صفحه شروع)

استفاده (Pillow لازم است؛ فقط برای ساخت):  python scripts/build_brand.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "packaging" / "brand" / "datavox-source.png"
WEB = ROOT / "voice2excel" / "web" / "brand"
GAP_ROW = 740  # ردیف خالی میان نماد و نام در تصویر اصلی


def transparent(img: Image.Image) -> Image.Image:
    """زمینه سفید بیرونی شفاف می‌شود؛ خانه‌های سفید درون جدول (که به لبه تصویر راه ندارند) سفید می‌مانند."""
    rgb = img.convert("RGB")
    marker = (255, 0, 255)
    flood = rgb.copy()
    w, h = flood.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if flood.getpixel(xy) != marker:
            ImageDraw.floodfill(flood, xy, marker, thresh=40)
    bg = ImageChops.difference(flood, Image.new("RGB", flood.size, marker)).convert("L").point(lambda v: 255 if v < 8 else 0)
    # لبه نرم: پیکسل‌های روشنِ مرز، نیمه‌شفاف
    soft = bg.filter(ImageFilter.GaussianBlur(1.2))
    alpha = ImageChops.invert(soft)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def crop(img: Image.Image, pad: float = 0.04) -> Image.Image:
    box = img.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    c = img.crop(box)
    p = int(max(c.size) * pad)
    canvas = Image.new("RGBA", (c.width + 2 * p, c.height + 2 * p), (0, 0, 0, 0))
    canvas.paste(c, (p, p), c)
    return canvas


def square(img: Image.Image, size: int, scale: float = 1.0) -> Image.Image:
    s = int(size * scale)
    r = min(s / img.width, s / img.height)
    im = img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return out


def tile(mark: Image.Image, size: int) -> Image.Image:
    """کاشی سفید گوشه‌گرد با نماد در میانه (آیکون ویندوز)."""
    big = size * 4
    t = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(t)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=(255, 255, 255, 255))
    m = square(mark, big, 0.80)
    t.alpha_composite(m)
    return t.resize((size, size), Image.LANCZOS)


def main() -> int:
    src = Image.open(SRC)
    clean = transparent(src)
    mark = crop(clean.crop((0, 0, clean.width, GAP_ROW)))
    logo = crop(clean)
    WEB.mkdir(parents=True, exist_ok=True)
    square(mark, 256).save(WEB / "mark.png", optimize=True)
    logo.thumbnail((640, 640), Image.LANCZOS)
    logo.save(WEB / "logo.png", optimize=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    icons = [tile(mark, s) for s in sizes]
    icons[-1].save(ROOT / "packaging" / "brand" / "icon.ico", sizes=[(s, s) for s in sizes], append_images=icons[:-1])
    icons[-1].save(ROOT / "packaging" / "brand" / "icon-preview.png")
    print("brand assets:", WEB / "mark.png", WEB / "logo.png", ROOT / "packaging" / "brand" / "icon.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
