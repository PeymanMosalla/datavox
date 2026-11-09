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
    .venv\\Scripts\\python.exe scripts\\build_portable.py [--model large-v3-turbo] [--no-zip]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
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
                "pydantic", "openpyxl", "jdatetime", "psutil"]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def runtime_requirements() -> list[str]:
    reqs = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.split("==")[0].lower() in RUNTIME_REQS:
            reqs.append(line)
    return reqs


# ---------- مراحل ساخت ----------
def get_embed_python(dest: Path) -> None:
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


def install_packages(site: Path) -> None:
    site.mkdir(parents=True, exist_ok=True)
    reqs = runtime_requirements()
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
    for p in list(site.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)


def copy_vc_runtime(dest: Path) -> list[str]:
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


def smoke_test(dist: Path) -> None:
    code = ("import sys, voice2excel, faster_whisper, ctranslate2, av, numpy, fastapi, uvicorn, openpyxl, jdatetime;"
            "from voice2excel import server;"
            "print('OK', sys.version.split()[0], sys.executable)")
    env = {"V2X_DATA_DIR": str(dist / "data-smoketest"), "V2X_MODELS_DIR": str(dist / "models"),
           "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1", "SystemRoot": r"C:\Windows",
           "PATH": r"C:\Windows\System32;C:\Windows"}
    out = subprocess.run([str(dist / "python" / "python.exe"), "-c", code], cwd=dist / "app", env=env,
                         capture_output=True, text=True, encoding="utf-8")
    print(out.stdout.strip(), out.stderr.strip()[-2000:])
    shutil.rmtree(dist / "data-smoketest", ignore_errors=True)
    for p in list((dist / "app").rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)
    if out.returncode != 0 or "OK" not in out.stdout:
        raise SystemExit("آزمون دود نسخه قابل‌حمل ناموفق بود.")


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
    ap.add_argument("--name", default="", help="بسته آزمایشی جدا: dist/DataVox-<name> و DataVox-<نسخه>-<name>.zip؛ "
                    "پوشه و اطلاعات برنامه اصلی (dist/DataVox) دست نمی‌خورد")
    a = ap.parse_args()
    from voice2excel import __version__

    model_dir = ROOT / "models" / a.model
    if not (model_dir / "model.bin").exists():
        raise SystemExit(f"مدل {a.model} در پوشه models نیست؛ ابتدا download_model.bat را اجرا کنید.")
    out = DIST / (f"DataVox-{a.name}" if a.name else "DataVox")
    # اطلاعات کاربری که با همین پوشه کار کرده حفظ می‌شود (ولی هرگز داخل zip نمی‌رود)
    kept_data = DIST / (f"_kept_user_data-{a.name}" if a.name else "_kept_user_data")
    legacy = DIST / "Voice2Excel"  # نام پیشین برنامه: اطلاعاتش یک بار به پوشه جدید می‌آید
    if not a.name and not (out / "data").exists() and (legacy / "data").exists():
        step("انتقال اطلاعات کاربر از پوشه نام قبلی (Voice2Excel)")
        out.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy / "data"), str(out / "data"))
    if (out / "data").exists():
        step("نگه‌داشتن اطلاعات کاربر (data) در کنار ساخت")
        shutil.rmtree(kept_data, ignore_errors=True)
        shutil.move(str(out / "data"), str(kept_data))
    step(f"پاک‌سازی {out}")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    step(f"Python جاسازی‌شده {PY_VERSION}")
    get_embed_python(out / "python")
    step("نصب کتابخانه‌ها")
    install_packages(out / "python" / "Lib" / "site-packages")
    step("کتابخانه‌های زمان‌اجرای Visual C++")
    print("کپی شد:", copy_vc_runtime(out / "python"))
    step("کد برنامه")
    copy_app(out / "app", compiled=not a.no_compile)
    # شناسه محیط اجرا: به‌روزرسانی سبک فقط وقتی پذیرفته می‌شود که Python و کتابخانه‌ها همین باشند
    from voice2excel.updater import compute_runtime_id
    (out / "app" / "runtime.json").write_text(json.dumps(
        {"runtime_id": compute_runtime_id(PY_VERSION, runtime_requirements()), "python": PY_VERSION}), encoding="utf-8")
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
    step("آزمون دود (بدون Python سیستم)")
    smoke_test(out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e9
    print(f"حجم پوشه: {size:.2f} گیگابایت")
    longest = max((str(p.relative_to(out.parent)) for p in out.rglob("*")), key=len)
    print(f"طولانی‌ترین مسیر داخلی: {len(longest)} نویسه ({longest})")
    if len(longest) > 150:
        raise SystemExit("مسیرهای داخلی بسته بیش از حد طولانی‌اند (سقف ۲۶۰ نویسه ویندوز).")
    if not a.no_zip:
        zp = DIST / (f"DataVox-{__version__}-{a.name}.zip" if a.name else f"DataVox-{__version__}.zip")
        step(f"ساخت {zp.name}")
        make_zip(out, zp)
        print(f"حجم zip: {zp.stat().st_size / 1e9:.2f} گیگابایت")
    if kept_data.exists():
        shutil.move(str(kept_data), str(out / "data"))
        print("اطلاعات کاربر به پوشه برنامه برگردانده شد.")
    print("\nانجام شد:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
