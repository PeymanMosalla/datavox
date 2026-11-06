"""ساخت dvwhisper.dll: موتور گفتار whisper.cpp برای رایانه‌های قدیمی (نسخه oldcpu).

پردازنده هدف: Core 2 / Pentium Dual-Core (SSSE3؛ بدون SSE4.1، AVX و POPCNT)، ویندوز ۷ به بعد.
ابزارها بیرون از مخزن‌اند (کد whisper.cpp 1.9.5، کامپایلر llvm-mingw msvcrt، cmake و ninja از pip):

    python scripts/build_engine_oldcpu.py --whisper <پوشه whisper.cpp> --toolchain <پوشه bin کامپایلر>

خروجی: packaging/oldcpu/dvwhisper.dll (در git نمی‌رود). پس از ساخت بررسی می‌شود که هیچ دستور SSE4.1 به بعد
و هیچ تابع ویندوز ۸ به بعد در DLL نباشد.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "oldcpu"
DEFAULT_TOOLS = ROOT.parent / "datavox-android"
# Core 2 (SSSE3) و ویندوز ۷ (0x0601): ggml تابع ویندوز ۸ (SetThreadInformation) را کامپایل نمی‌کند
FLAGS = "-march=core2 -mtune=generic -D_WIN32_WINNT=0x0601 -DWINVER=0x0601"
# دستورهای SSE4.1، SSE4.2، POPCNT و AVX که E5300/E2180 ندارند
FORBIDDEN = re.compile(r"^(v[a-z]\w*|pmulld|pminsd|pmaxsd|pminud|pmaxud|pminsb|pmaxsb|pminuw|pmaxuw|blendps|blendpd|"
                       r"blendvps|blendvpd|pblendvb|pblendw|roundps|roundpd|roundss|roundsd|dpps|dppd|ptest|pinsrd|"
                       r"pinsrq|pinsrb|pextrd|pextrq|pextrb|insertps|extractps|pmovzx\w+|pmovsx\w+|pcmpeqq|pcmpgtq|"
                       r"packusdw|mpsadbw|phminposuw|movntdqa|crc32\w*|popcnt\w*|lzcnt\w*|pcmp[ei]str[im])$")


def run(cmd, env):
    print(">", " ".join(map(str, cmd))[:240], flush=True)
    subprocess.run([str(c) for c in cmd], check=True, env=env)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", type=Path, default=DEFAULT_TOOLS / "third_party" / "whisper.cpp-1.9.5")
    ap.add_argument("--toolchain", type=Path,
                    default=DEFAULT_TOOLS / "toolchains" / "llvm-mingw-20261020-msvcrt-x86_64" / "bin")
    a = ap.parse_args()
    import cmake
    import ninja

    env = dict(os.environ, PATH=str(a.toolchain) + os.pathsep + os.environ["PATH"])
    build = ROOT / "build" / "dvwhisper-core2"
    cm = Path(cmake.CMAKE_BIN_DIR) / "cmake.exe"
    run([cm, "-S", ROOT / "native" / "dvwhisper", "-B", build, "-G", "Ninja",
         f"-DCMAKE_MAKE_PROGRAM={Path(ninja.BIN_DIR) / 'ninja.exe'}", f"-DWHISPER_SRC={a.whisper}",
         "-DCMAKE_C_COMPILER=x86_64-w64-mingw32-clang", "-DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-clang++",
         "-DCMAKE_BUILD_TYPE=Release", "-DGGML_NATIVE=OFF", "-DGGML_SSE42=OFF", "-DGGML_AVX=OFF", "-DGGML_AVX2=OFF",
         "-DGGML_FMA=OFF", "-DGGML_F16C=OFF", "-DGGML_BMI2=OFF", "-DGGML_OPENMP=OFF",
         f"-DCMAKE_C_FLAGS={FLAGS}", f"-DCMAKE_CXX_FLAGS={FLAGS} -include algorithm"], env)
    run([cm, "--build", build, "--target", "dvwhisper", "-j", str(os.cpu_count() or 4)], env)
    dll = build / "libdvwhisper.dll"
    if not dll.exists():
        dll = build / "dvwhisper.dll"
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "dvwhisper.dll"
    shutil.copy2(dll, dst)
    run([a.toolchain / "llvm-strip.exe", "--strip-unneeded", dst], env)

    # بررسی: هیچ دستور پردازنده جدیدتر
    asm = subprocess.run([str(a.toolchain / "llvm-objdump.exe"), "-d", "--no-show-raw-insn", str(dst)],
                         capture_output=True, text=True, errors="replace").stdout
    bad = {}
    for line in asm.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            m = parts[1].split()[0] if parts[1].split() else ""
            if FORBIDDEN.match(m):
                bad[m] = bad.get(m, 0) + 1
    if bad:
        raise SystemExit(f"دستورهای ناسازگار با پردازنده قدیمی در DLL: {bad}")
    # بررسی: هیچ تابع ویندوز ۸ به بعد
    sys.path.insert(0, str(ROOT / "scripts"))
    from win7_check import scan

    problems = scan(OUT)
    if problems:
        raise SystemExit(f"ناسازگار با ویندوز ۷: {problems}")
    print(f"OK: {dst} ({dst.stat().st_size // 1024} KB) — بدون SSE4.1/AVX و سازگار با ویندوز ۷")
    return 0


if __name__ == "__main__":
    sys.exit(main())
