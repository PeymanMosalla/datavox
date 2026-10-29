"""بررسی ایستای سازگاری بسته با ویندوز ۷: هر DLL/PYD/EXE نباید تابع یا کتابخانه‌ای از ویندوز ۸ به بعد بخواهد.

ویندوز ۷ تابعی را که وجود ندارد هنگام بارگذاری DLL پیدا نمی‌کند و برنامه با «DLL load failed» بالا نمی‌آید؛
این بررسی جدول importهای همه فایل‌ها را با فهرست توابع غایب در ویندوز ۷ (packaging/win7/missing_api.json،
برگرفته از YY-Thunks) و فهرست API Setهای موجود در ویندوز ۷ SP1 مقایسه می‌کند.

استفاده:  .venv/Scripts/python.exe scripts/win7_check.py <پوشه>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parent.parent
MISSING = json.loads((ROOT / "packaging" / "win7" / "missing_api.json").read_text(encoding="utf-8"))["functions"]
# API Setهای ویندوز ۷ SP1 (apisetschema)؛ api-ms-win-crt-* با به‌روزرسانی KB2999226 (Universal CRT) می‌آید
APISET7 = {f"api-ms-win-core-{x}-l1-1-0.dll" for x in (
    "console datetime debug delayload errorhandling fibers file handle heap interlocked io libraryloader localization "
    "localregistry memory misc namedpipe processenvironment processthreads profile rtlsupport string synch sysinfo "
    "threadpool util xstate").split()} | {
    "api-ms-win-security-base-l1-1-0.dll", "api-ms-win-security-lsalookup-l1-1-0.dll", "api-ms-win-security-sddl-l1-1-0.dll",
    "api-ms-win-service-core-l1-1-0.dll", "api-ms-win-service-management-l1-1-0.dll",
    "api-ms-win-service-management-l2-1-0.dll", "api-ms-win-service-winsvc-l1-1-0.dll"}
SYSTEM7 = set("""kernel32 user32 gdi32 advapi32 shell32 shlwapi ole32 oleaut32 ws2_32 wsock32 mswsock bcrypt crypt32 secur32
iphlpapi psapi pdh powrprof ntdll version winmm setupapi dbghelp imagehlp userenv netapi32 rpcrt4 comdlg32 imm32 uxtheme
dwmapi wtsapi32 mpr cfgmgr32 winhttp wininet ncrypt normaliz dnsapi msvcrt comctl32 msimg32 usp10 gdiplus d3d9 d3d11 dxgi
d2d1 dwrite opengl32 glu32 avrt avicap32 mfplat mf mfreadwrite propsys urlmon wintrust msi authz credui cryptbase cryptsp
bcryptprimitives oleacc hid wlanapi wldap32 odbc32 winspool.drv sspicli kernelbase mscoree cabinet""".split())
# روی ویندوز ۷ بارگذاری نمی‌شوند: DataVox.exe آنجا WebView2 را کنار می‌گذارد و پنجره را با مرورگر می‌سازد
NOT_LOADED_ON_WIN7 = {"webview2loader.dll"}


def _dll_problem(name: str, local: set[str]) -> str | None:
    n = name.lower()
    if n in local or n.startswith("api-ms-win-crt-") or n == "ucrtbase.dll":
        return None
    if n.startswith("api-ms-win-"):
        return None if n in APISET7 else f"API Set نیست در ویندوز ۷: {name}"
    return None if n.removesuffix(".dll") in SYSTEM7 or n in SYSTEM7 else f"کتابخانه ناشناخته: {name}"


def scan(root: Path) -> dict[str, list[str]]:
    files = [p for p in root.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe") and p.is_file()]
    local = {p.name.lower() for p in files}
    problems: dict[str, list[str]] = {}
    for p in files:
        try:
            pe = pefile.PE(str(p), fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                                   pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        except pefile.PEFormatError:
            continue
        if p.name.lower() in NOT_LOADED_ON_WIN7:
            continue
        found = []
        managed = pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].VirtualAddress != 0  # اسمبلی .NET (فقط mscoree)
        if pe.FILE_HEADER.Machine != 0x8664 and not managed:
            found.append("۶۴ بیتی نیست")
        for attr, kind in (("DIRECTORY_ENTRY_IMPORT", ""), ("DIRECTORY_ENTRY_DELAY_IMPORT", "(تأخیری) ")):
            for entry in getattr(pe, attr, []):
                dll = entry.dll.decode(errors="replace")
                bad = _dll_problem(dll, local)
                if bad:
                    found.append(kind + bad)
                if dll.lower() in local:
                    continue  # کتابخانه همراه بسته (مثل api-ms-win-core-path-l1-1-0.dll در Python سازگار با ویندوز ۷)
                for imp in entry.imports:
                    fn = imp.name.decode(errors="replace") if imp.name else None
                    if fn in MISSING:
                        found.append(f"{kind}{dll}!{fn} (از ویندوز {MISSING[fn]})")
        pe.close()
        if found:
            problems[str(p.relative_to(root))] = sorted(set(found))
    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    root = Path(sys.argv[1])
    problems = scan(root)
    for f, items in sorted(problems.items()):
        print(f)
        for x in items:
            print("    ", x)
    print("سازگار با ویندوز ۷" if not problems else f"{len(problems)} فایل با ویندوز ۷ سازگار نیست")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
