"""ساخت موتور whisper.cpp برای ویندوز روی پردازنده‌های قدیمی (Core 2 / Pentium Dual: SSSE3، بدون SSE4.1 و AVX).

    pcenv\\Scripts\\python.exe build_win_old.py
خروجی: build\\win-core2\\bin\\whisper-cli.exe (ایستا، بدون DLL جانبی)
"""
import os
import subprocess
from pathlib import Path

import cmake
import ninja

ROOT = Path(__file__).resolve().parent
TC = ROOT / "toolchains" / "llvm-mingw-20261020-msvcrt-x86_64" / "bin"
SRC = ROOT / "third_party" / "whisper.cpp-1.9.5"
OUT = ROOT / "build" / "win-core2"
CMAKE = Path(cmake.CMAKE_BIN_DIR) / "cmake.exe"
NINJA = Path(ninja.BIN_DIR) / "ninja.exe"
# ویندوز ۷ (0x0601): تابع‌های ویندوز ۸ به بعد (مثل SetThreadInformation) در ggml کامپایل نمی‌شوند
FLAGS = "-march=core2 -mtune=generic -D_WIN32_WINNT=0x0601 -DWINVER=0x0601"


def run(cmd):
    print(">", " ".join(map(str, cmd))[:250], flush=True)
    env = dict(os.environ, PATH=str(TC) + os.pathsep + os.environ["PATH"])
    subprocess.run([str(c) for c in cmd], check=True, env=env)


run([CMAKE, "-S", SRC, "-B", OUT, "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={NINJA}",
     "-DCMAKE_C_COMPILER=x86_64-w64-mingw32-clang", "-DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-clang++",
     "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF",
     "-DGGML_NATIVE=OFF", "-DGGML_SSE42=OFF", "-DGGML_AVX=OFF", "-DGGML_AVX2=OFF", "-DGGML_FMA=OFF",
     "-DGGML_F16C=OFF", "-DGGML_BMI2=OFF", "-DGGML_OPENMP=OFF",
     "-DWHISPER_BUILD_TESTS=OFF", "-DWHISPER_BUILD_SERVER=OFF", "-DWHISPER_BUILD_EXAMPLES=ON",
     f"-DCMAKE_C_FLAGS={FLAGS}", f"-DCMAKE_CXX_FLAGS={FLAGS} -include algorithm", "-DCMAKE_EXE_LINKER_FLAGS=-static"])
run([CMAKE, "--build", OUT, "--target", "whisper-cli", "-j", str(os.cpu_count() or 4)])
print("OK:", OUT / "bin" / "whisper-cli.exe")
