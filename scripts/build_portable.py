"""ساخت نسخه قابل‌حمل ویندوز: یک پوشه/zip که بدون نصب Python و بدون اینترنت اجرا می‌شود.

خروجی: dist/DataVox/  و  dist/DataVox-<نسخه>.zip
ساختار:
    DataVox.exe          اجراکننده (بدون پنجره کنسول)
    Guide.html           راهنمای فارسی
    python/              Python جاسازی‌شده + کتابخانه‌ها + کتابخانه‌های زمان‌اجرای VC++
    app/voice2excel/     کد برنامه
    models/<مدل>/        مدل گفتار
    samples/             ویس‌ها و فایل اکسل نمونه (داده ساختگی)
    data/                (در اولین اجرا ساخته می‌شود؛ اطلاعات کاربر)

استفاده (روی رایانه سازنده، یک بار با اینترنت برای دریافت Python جاسازی‌شده):
    .venv\\Scripts\\python.exe scripts\\build_portable.py [--model large-v3-turbo] [--no-zip] [--win7]

--win7: بسته جداگانه ویندوز ۷ (dist/DataVox-win7/ و dist/DataVox-<نسخه>-win7.zip): همان کد و همان موتور و مدل
گفتار، با Python 3.12 سازگار با ویندوز ۷ (پروژه PythonVista)، کتابخانه‌های requirements-win7.txt، Visual C++ 14.44،
VAD با numpy به‌جای onnxruntime و پوشه Windows7 (پیش‌نیازهای رسمی مایکروسافت، Firefox ESR و راهنما).
هر DLL بسته پیش از zip با scripts/win7_check.py بررسی می‌شود و در صورت ناسازگاری، ساخت متوقف می‌شود.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PKG = ROOT / "packaging"
DIST = ROOT / "dist"
PY_VERSION = "3.12.10"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
VC_DLLS = ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll",
           "concrt140.dll", "vcomp140.dll"]
RUNTIME_REQS = ["faster-whisper", "ctranslate2", "av", "numpy", "fastapi", "uvicorn", "python-multipart",
                "pydantic", "pydantic-core", "tokenizers", "openpyxl", "jdatetime", "psutil"]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")

# ---------- ویندوز ۷ ----------
# همان Python 3.12 که برای اجرا روی ویندوز ۷ وصله شده است (https://github.com/adang1345/PythonVista)
WIN7_EMBED_URL = (f"https://github.com/adang1345/PythonVista/releases/download/v{PY_VERSION}/"
                  f"python-{PY_VERSION}-embed-amd64.zip")
WIN7_EMBED_SHA256 = "6f4e1a6c607aaac0b052c9f8962a863ae23ddeab4502619dc0a151cf1bca1a60"
# Visual C++ 14.44 (آخرین نسخه سازگار با ویندوز ۷)؛ نسخه 14.5x سیستم به توابع ویندوز ۸ به بعد نیاز دارد.
# vcruntime140 همان نسخه همراه PythonVista می‌ماند.
WIN7_VC_RUNTIME = "msvc-runtime==14.44.35112"
WIN7_VC_DLLS = ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll", "vcomp140.dll"]
# روی ویندوز ۷ بارگذاری نمی‌شوند و لازم هم نیستند (VAD با numpy: voice2excel/vad_numpy.py؛ hf_xet فقط برای دانلود)
WIN7_DROP = ["onnxruntime", "hf_xet"]
WIN7_PREREQS = {  # نام فایل: (نشانی رسمی، sha256)
    "Windows6.1-KB3063858-x64.msu": (
        "https://download.microsoft.com/download/0/8/E/08E0386B-F6AF-4651-8D1B-C0A95D2731F0/Windows6.1-KB3063858-x64.msu",
        "6fec4e38cdcbdaa334937a2ef38bad6800e9c80cb513183451b4049e84479a85"),
    "Windows6.1-KB2999226-x64.msu": (  # بسته مایکروسافت که python.org برای نصب‌کننده‌های Python نگه داشته است
        "https://www.python.org/ftp/python/3.6.6/amd64rc1/Windows6.1-KB2999226-x64.msu",
        "f2619b122c818e2d026e6826541b800d0b764c05aa014d9a13002f259e6e816e"),
    "ndp48-x86-x64-allos-enu.exe": (
        "https://download.visualstudio.microsoft.com/download/pr/2d6bb6b2-226a-4baa-bdec-798822606ff1/"
        "8494001c276a4b96804cde7829c04d7f/ndp48-x86-x64-allos-enu.exe",
        "68c9986a8dcc0214d909aa1f31bee9fb5461bb839edca996a75b08ddffc1483f"),
    "Firefox-Setup-115.44.0esr-fa.exe": (
        "https://archive.mozilla.org/pub/firefox/releases/115.44.0esr/win64/fa/Firefox%20Setup%20115.44.0esr.exe",
        "4edf7418cf29a47348c7e46edd6469a2766a143017c26acb2fc0d0457f92e5d6"),
}


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def runtime_requirements(win7: bool = False) -> list[str]:
    reqs = []
    for line in (ROOT / ("requirements-win7.txt" if win7 else "requirements.txt")).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.split("==")[0].lower() in RUNTIME_REQS:
            reqs.append(line)
    return reqs


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_verified(url: str, sha256: str, dest: Path) -> Path:
    """دریافت یک بار (نگه‌داری در packaging/cache) با بررسی sha256؛ فایل دست‌کاری‌شده هرگز وارد بسته نمی‌شود."""
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"دریافت {url}")
        urllib.request.urlretrieve(url, dest)
    if _sha256(dest) != sha256:
        dest.unlink()
        raise SystemExit(f"چکیده فایل {dest.name} با مقدار ثبت‌شده نمی‌خواند؛ ساخت متوقف شد.")
    return dest


# ---------- مراحل ساخت ----------
def get_embed_python(dest: Path, win7: bool = False) -> None:
    if win7:
        cache = fetch_verified(WIN7_EMBED_URL, WIN7_EMBED_SHA256,
                               PKG / "cache" / "win7" / f"python-{PY_VERSION}-embed-amd64.zip")
    else:
        cache = PKG / "cache" / f"python-{PY_VERSION}-embed-amd64.zip"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        print(f"دریافت {EMBED_URL}")
        urllib.request.urlretrieve(EMBED_URL, cache)
    with zipfile.ZipFile(cache) as z:
        z.extractall(dest)
    pth = dest / f"python{PY_VERSION.split('.')[0]}{PY_VERSION.split('.')[1]}._pth"
    pth.write_text(f"python{PY_VERSION.split('.')[0]}{PY_VERSION.split('.')[1]}.zip\n.\nLib\\site-packages\n..\\app\nimport site\n",
                   encoding="ascii")


def install_packages(site: Path, win7: bool = False) -> None:
    site.mkdir(parents=True, exist_ok=True)
    reqs = runtime_requirements(win7)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-warn-script-location", "--disable-pip-version-check",
                           "--only-binary=:all:", "--target", str(site), *reqs])
    # حذف بخش‌های غیرلازم برای کاهش حجم
    for pat in ("*.dist-info/RECORD",):
        for p in site.glob(pat):
            p.unlink(missing_ok=True)
    shutil.rmtree(site / "bin", ignore_errors=True)
    # ابزارهای توسعه onnxruntime در زمان اجرا استفاده نمی‌شوند (faster-whisper فقط InferenceSession را برای VAD
    # می‌خواهد)؛ حذفشان مسیرهای بسیار طولانی را هم برمی‌دارد تا از سقف ۲۶۰ نویسه ویندوز دور بمانیم
    for sub in ("tools", "transformers", "quantization"):
        shutil.rmtree(site / "onnxruntime" / sub, ignore_errors=True)
    if win7:
        for name in WIN7_DROP:
            shutil.rmtree(site / name, ignore_errors=True)
            for p in site.glob(f"{name}-*.dist-info"):
                shutil.rmtree(p, ignore_errors=True)
    for p in list(site.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)


def copy_vc_runtime(dest: Path, win7: bool = False) -> list[str]:
    if win7:
        cache = PKG / "cache" / "win7" / "vc"
        if not all((cache / n).exists() for n in WIN7_VC_DLLS):
            cache.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="v2x-vc-") as work:
                subprocess.check_call([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
                                       "--disable-pip-version-check", "--python-version", "3.12",
                                       "--platform", "win_amd64", "-d", work, WIN7_VC_RUNTIME])
                with zipfile.ZipFile(next(Path(work).glob("*.whl"))) as z:
                    for info in z.infolist():
                        parts = info.filename.split("/")
                        if len(parts) == 3 and parts[1] == "data" and parts[2] in WIN7_VC_DLLS:
                            (cache / parts[2]).write_bytes(z.read(info))
        for name in WIN7_VC_DLLS:
            shutil.copy2(cache / name, dest / name)
        return list(WIN7_VC_DLLS)
    copied = []
    for name in VC_DLLS:
        src = Path(r"C:\Windows\System32") / name
        if src.exists():
            shutil.copy2(src, dest / name)
            copied.append(name)
    return copied


def copy_app(dest: Path, compiled: bool = True) -> None:
    """کد برنامه؛ به‌طور پیش‌فرض کامپایل‌شده (.pyd) تا کد خوانا همراه بسته نرود."""
    if compiled:
        from compile_app import compile_package
        compile_package(ROOT / "voice2excel", dest / "voice2excel")
    else:
        shutil.copytree(ROOT / "voice2excel", dest / "voice2excel",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyd"))


def make_samples(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    src = PKG / "samples"
    for p in sorted(src.glob("*")) if src.exists() else []:
        shutil.copy2(p, dest / p.name)
    sys.path.insert(0, str(ROOT))
    from tests.test_excel import make_company_like

    make_company_like(dest / "sample-company.xlsx")


WEBVIEW2_VERSION = "1.0.4314.35"  # کتابخانه رسمی مایکروسافت (مجوز BSD) برای پنجره اختصاصی برنامه
WEBVIEW2_FILES = {"Microsoft.Web.WebView2.Core.dll": "lib/net462/", "Microsoft.Web.WebView2.WinForms.dll": "lib/net462/",
                  "WebView2Loader.dll": "runtimes/win-x64/native/"}


def webview2_sdk() -> Path:
    """کتابخانه WebView2 (یک بار از nuget.org دریافت و در packaging/cache نگه داشته می‌شود)."""
    d = PKG / "cache" / f"webview2-{WEBVIEW2_VERSION}"
    if all((d / f).exists() for f in WEBVIEW2_FILES):
        return d
    d.mkdir(parents=True, exist_ok=True)
    url = f"https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{WEBVIEW2_VERSION}/microsoft.web.webview2.{WEBVIEW2_VERSION}.nupkg"
    pkg = d / "pkg.zip"
    urllib.request.urlretrieve(url, pkg)
    with zipfile.ZipFile(pkg) as z:
        for name, folder in WEBVIEW2_FILES.items():
            (d / name).write_bytes(z.read(folder + name))
    pkg.unlink()
    return d


def build_launcher(dest_exe: Path, icon: Path) -> None:
    """DataVox.exe و کتابخانه‌های WebView2 کنار آن."""
    if not CSC.exists():
        raise SystemExit("کامپایلر C# (.NET Framework 4) پیدا نشد.")
    sdk = webview2_sdk()
    subprocess.check_call([str(CSC), "/nologo", "/target:winexe", "/optimize+", "/codepage:65001", "/platform:x64",
                           f"/win32icon:{icon}", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
                           "/r:Microsoft.CSharp.dll", "/r:System.Core.dll",
                           f"/r:{sdk / 'Microsoft.Web.WebView2.Core.dll'}", f"/r:{sdk / 'Microsoft.Web.WebView2.WinForms.dll'}",
                           f"/out:{dest_exe}", str(PKG / "Launcher.cs")])
    for name in WEBVIEW2_FILES:
        shutil.copy2(sdk / name, dest_exe.parent / name)


def smoke_test(dist: Path, win7: bool = False) -> None:
    code = ("import sys, voice2excel, faster_whisper, ctranslate2, av, numpy, fastapi, uvicorn, openpyxl, jdatetime;"
            "from voice2excel import server;"
            "print('OK', sys.version.split()[0], sys.executable)")
    if win7:  # VAD باید بدون onnxruntime و با همان وزن‌های مدل کار کند
        code += (";import pydantic_core, tokenizers;from voice2excel.vad_numpy import install_fallback;"
                 "assert install_fallback();from faster_whisper import vad;"
                 "assert vad.get_vad_model()(numpy.zeros(16384, 'float32')).max() < 0.5;print('VAD-OK')")
    env = {"V2X_DATA_DIR": str(dist / "data-smoketest"), "V2X_MODELS_DIR": str(dist / "models"),
           "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1", "SystemRoot": r"C:\Windows",
           "PATH": r"C:\Windows\System32;C:\Windows"}
    out = subprocess.run([str(dist / "python" / "python.exe"), "-c", code], cwd=dist / "app", env=env,
                         capture_output=True, text=True, encoding="utf-8")
    print(out.stdout.strip(), out.stderr.strip()[-2000:])
    shutil.rmtree(dist / "data-smoketest", ignore_errors=True)
    for p in list((dist / "app").rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)
    if out.returncode != 0 or "OK" not in out.stdout or (win7 and "VAD-OK" not in out.stdout):
        raise SystemExit("آزمون دود نسخه قابل‌حمل ناموفق بود.")


def add_win7_files(out: Path) -> None:
    """پوشه Windows7: پیش‌نیازهای رسمی (بدون نیاز به اینترنت روی رایانه مشتری)، نصب‌کننده و راهنما."""
    folder = out / "Windows7"
    folder.mkdir()
    for name, (url, sha) in WIN7_PREREQS.items():
        shutil.copy2(fetch_verified(url, sha, PKG / "cache" / "win7" / "prereq" / name), folder / name)
    for name in ("Install-Prerequisites.bat", "Windows7-Guide.html"):
        shutil.copy2(PKG / "win7" / name, folder / name)
    shutil.copy2(PKG / "win7" / "Windows7-Guide.html", out / "Windows7-Guide.html")


def check_win7(out: Path) -> None:
    from win7_check import scan

    # پوشه Windows7 نصب‌کننده‌های رسمی مایکروسافت و Mozilla است که خودشان برای ویندوز ۷ ساخته شده‌اند
    problems = {f: p for f, p in scan(out).items() if Path(f).parts[0] not in ("data", "Windows7")}
    for f, items in sorted(problems.items()):
        print(f, *items, sep="\n    ")
    if problems:
        raise SystemExit(f"{len(problems)} فایل بسته با ویندوز ۷ سازگار نیست؛ ساخت متوقف شد.")
    # ابزار داخلی ویندوز ۷ هنگام باز کردن zip نام‌های غیرانگلیسی را خراب می‌کند
    odd = [str(p.relative_to(out)) for p in out.rglob("*")
           if p.relative_to(out).parts[0] != "data" and not str(p.relative_to(out)).isascii()]
    if odd:
        raise SystemExit("نام فایل غیرانگلیسی در بسته ویندوز ۷: " + ", ".join(odd[:5]))
    print("همه فایل‌های اجرایی بسته با ویندوز ۷ سازگارند.")


def make_zip(dist: Path, zip_path: Path) -> None:
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(dist.rglob("*")):
            if p.is_dir():
                continue
            if p.relative_to(dist).parts[0] == "data":
                continue  # اطلاعات کاربر هرگز داخل بسته ارسالی قرار نمی‌گیرد
            arc = Path(dist.name) / p.relative_to(dist)
            stored = p.suffix in (".bin", ".zip", ".woff2") or p.stat().st_size > 50_000_000
            z.write(p, arc, compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--no-zip", action="store_true")
    ap.add_argument("--no-compile", action="store_true", help="کد متنی (فقط برای آزمون سریع)")
    ap.add_argument("--win7", action="store_true", help="(در شاخه windows7-only همیشه فعال است)")
    ap.add_argument("--name", default="", help="بسته آزمایشی جدا: dist/DataVox-win7-<name> و DataVox-<نسخه>-win7-<name>.zip")
    a = ap.parse_args()
    win7 = True  # شاخه windows7-only فقط بسته ویندوز ۷ می‌سازد؛ بسته ویندوز ۱۰ و ۱۱ از شاخه main ساخته می‌شود
    from voice2excel import __version__

    model_dir = ROOT / "models" / a.model
    if not (model_dir / "model.bin").exists():
        raise SystemExit(f"مدل {a.model} در پوشه models نیست؛ ابتدا download_model.bat را اجرا کنید.")
    tag = ("win7" if win7 else "") + (f"-{a.name}" if a.name else "")
    tag = tag.lstrip("-")
    out = DIST / (f"DataVox-{tag}" if tag else "DataVox")
    # اطلاعات کاربری که با همین پوشه کار کرده حفظ می‌شود (ولی هرگز داخل zip نمی‌رود)
    kept_data = DIST / (f"_kept_user_data-{tag}" if tag else "_kept_user_data")
    legacy = DIST / "Voice2Excel"  # نام پیشین برنامه: اطلاعاتش یک بار به پوشه جدید می‌آید
    if not tag and not (out / "data").exists() and (legacy / "data").exists():
        step("انتقال اطلاعات کاربر از پوشه نام قبلی (Voice2Excel)")
        out.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy / "data"), str(out / "data"))
    if (out / "data").exists():
        step("نگه‌داشتن اطلاعات کاربر (data) در کنار ساخت")
        # فقط جابه‌جایی؛ هرگز کپی و پاک‌کردن (اگر پرونده‌ای قفل باشد، shutil.move نیمی از اطلاعات را پاک می‌کرد)
        if kept_data.exists():
            raise SystemExit(f"ناموفق: {kept_data} از ساخت ناتمام قبلی مانده و شاید تنها نسخه اطلاعات باشد؛ "
                             f"اول آن را بررسی و به {out / 'data'} برگردانید.")
        try:
            os.rename(out / "data", kept_data)
        except OSError as e:
            raise SystemExit(f"ناموفق: پوشه اطلاعات کاربر جابه‌جا نشد ({e}). برنامه یا پرونده‌ای از آن باز است؛ "
                             "آن را ببندید و دوباره بسازید. چیزی پاک نشد.")
    step(f"پاک‌سازی {out}")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    step(f"Python جاسازی‌شده {PY_VERSION}" + (" (سازگار با ویندوز ۷)" if win7 else ""))
    get_embed_python(out / "python", win7)
    step("نصب کتابخانه‌ها")
    install_packages(out / "python" / "Lib" / "site-packages", win7)
    step("کتابخانه‌های زمان‌اجرای Visual C++")
    print("کپی شد:", copy_vc_runtime(out / "python", win7))
    step("کد برنامه")
    copy_app(out / "app", compiled=not a.no_compile)
    # شناسه محیط اجرا: به‌روزرسانی سبک فقط وقتی پذیرفته می‌شود که Python و کتابخانه‌ها همین باشند
    from voice2excel.updater import compute_runtime_id
    (out / "app" / "runtime.json").write_text(json.dumps(
        {"runtime_id": compute_runtime_id(PY_VERSION, runtime_requirements(win7)), "python": PY_VERSION}),
        encoding="utf-8")
    step(f"مدل گفتار {a.model}")
    shutil.copytree(model_dir, out / "models" / a.model)
    step("نمونه‌ها")
    make_samples(out / "samples")
    step("آیکون و اجراکننده")
    icon = PKG / "brand" / "icon.ico"  # نشان DataVox (scripts/build_brand.py)
    build_launcher(out / "DataVox.exe", icon)
    shutil.copy2(ROOT / "voice2excel" / "web" / "guide.html", out / "Guide.html")
    shutil.copy2(PKG / "THIRD-PARTY-NOTICES.txt", out / "THIRD-PARTY-NOTICES.txt")
    shutil.copy2(ROOT / "voice2excel" / "web" / "recording-guide.html", out / "Recording-Guide.html")
    if win7:
        step("پیش‌نیازها و راهنمای ویندوز ۷")
        add_win7_files(out)
    step("آزمون دود (بدون Python سیستم)")
    smoke_test(out, win7)
    if win7:
        step("بررسی سازگاری همه DLLها با ویندوز ۷")
        check_win7(out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e9
    print(f"حجم پوشه: {size:.2f} گیگابایت")
    longest = max((str(p.relative_to(out.parent)) for p in out.rglob("*")), key=len)
    print(f"طولانی‌ترین مسیر داخلی: {len(longest)} نویسه ({longest})")
    if len(longest) > 150:
        raise SystemExit("مسیرهای داخلی بسته بیش از حد طولانی‌اند (سقف ۲۶۰ نویسه ویندوز).")
    if not a.no_zip:
        zp = DIST / (f"DataVox-{__version__}-{tag}.zip" if tag else f"DataVox-{__version__}.zip")
        step(f"ساخت {zp.name}")
        make_zip(out, zp)
        print(f"حجم zip: {zp.stat().st_size / 1e9:.2f} گیگابایت")
    if kept_data.exists():
        os.rename(kept_data, out / "data")
        print("اطلاعات کاربر به پوشه برنامه برگردانده شد.")
    print("\nانجام شد:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
