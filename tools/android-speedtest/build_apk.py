"""ساخت APK آزمایش سرعت DataVox بدون Gradle (ابزارهای build-tools و NDK مستقیم).

    pcenv\\Scripts\\python.exe build_apk.py [--native] [--models turbo=...,small=...]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SDK = ROOT / "sdk"
BT = SDK / "build-tools"
ANDROID_JAR = SDK / "android-34" / "android.jar"
JDK = Path(r"C:\Program Files\Android\Android Studio\jbr")
NDK = ROOT / "ndk" / "android-ndk-r28c"
BUILD = ROOT / "build"
APP = ROOT / "app"
ABI = "arm64-v8a"


def run(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd)[:300], flush=True)
    env = dict(os.environ, JAVA_HOME=str(JDK), PATH=str(JDK / "bin") + os.pathsep + os.environ["PATH"])
    subprocess.run([str(c) for c in cmd], check=True, env=env, **kw)


def build_native():
    import cmake
    import ninja
    cmake_exe = Path(cmake.CMAKE_BIN_DIR) / "cmake.exe"
    ninja_exe = Path(ninja.BIN_DIR) / "ninja.exe"
    out = BUILD / "native"
    run([cmake_exe, "-S", ROOT / "native", "-B", out, "-G", "Ninja",
         f"-DCMAKE_MAKE_PROGRAM={ninja_exe}",
         f"-DCMAKE_TOOLCHAIN_FILE={NDK / 'build/cmake/android.toolchain.cmake'}",
         f"-DANDROID_ABI={ABI}", "-DANDROID_PLATFORM=android-24", "-DCMAKE_BUILD_TYPE=Release",
         # Snapdragon 732G (Cortex-A76/A55): ARMv8.2 با dotprod و fp16
         "-DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16"])
    run([cmake_exe, "--build", out, "--target", "dvwhisper", "-j", str(os.cpu_count() or 4)])
    so = out / "libdvwhisper.so"
    strip = NDK / "toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-strip.exe"
    dst = BUILD / "lib" / ABI
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(so, dst / so.name)
    run([strip, "--strip-unneeded", dst / so.name])
    print("native:", (dst / so.name).stat().st_size // 1024, "KB")


def build_java():
    cls = BUILD / "classes"
    dex = BUILD / "dex"
    for d in (cls, dex):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    srcs = sorted((APP / "src").rglob("*.java"))
    run([JDK / "bin/javac.exe", "-encoding", "UTF-8", "-source", "8", "-target", "8", "-Xlint:-options",
         "-bootclasspath", ANDROID_JAR, "-classpath", BT / "core-lambda-stubs.jar", "-d", cls, *srcs])
    classes = sorted(cls.rglob("*.class"))
    run([BT / "d8.bat", "--release", "--min-api", "24", "--lib", ANDROID_JAR,
         "--output", dex, *classes])


def package(models: dict[str, Path]):
    assets = BUILD / "assets"
    shutil.rmtree(assets, ignore_errors=True)
    shutil.copytree(APP / "assets", assets)
    (assets / "models").mkdir(exist_ok=True)
    for name, src in models.items():
        dst = assets / "models" / f"{name}.bin"
        try:
            os.link(src, dst)  # بدون کپی دوباره فایل‌های بزرگ
        except OSError:
            shutil.copy2(src, dst)
    base = BUILD / "base.apk"
    run([BT / "aapt2.exe", "link", "-o", base, "-I", ANDROID_JAR, "--manifest", APP / "AndroidManifest.xml",
         "-A", assets, "--min-sdk-version", "24", "--target-sdk-version", "34",
         "-0", "bin", "-0", "wav"])
    unaligned = BUILD / "unaligned.apk"
    shutil.copy2(base, unaligned)
    with zipfile.ZipFile(unaligned, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(BUILD / "dex" / "classes.dex", "classes.dex")
        so = BUILD / "lib" / ABI / "libdvwhisper.so"
        z.write(so, f"lib/{ABI}/libdvwhisper.so")
    aligned = BUILD / "aligned.apk"
    run([BT / "zipalign.exe", "-p", "-f", "4", unaligned, aligned])
    ks = ROOT / "speechtest.keystore"
    if not ks.exists():
        run([JDK / "bin/keytool.exe", "-genkeypair", "-keystore", ks, "-alias", "speechtest", "-keyalg", "RSA",
             "-keysize", "2048", "-validity", "10000", "-storepass", "speechtest", "-keypass", "speechtest",
             "-dname", "CN=DataVox Speech Test"])
    out = ROOT / "out" / "DataVox-SpeechTest.apk"
    out.parent.mkdir(exist_ok=True)
    run([BT / "apksigner.bat", "sign", "--ks", ks, "--ks-pass", "pass:speechtest",
         "--out", out, aligned])
    run([BT / "apksigner.bat", "verify", "--min-sdk-version", "24", out])
    for p in (base, unaligned, aligned):
        p.unlink(missing_ok=True)
    print("APK:", out, round(out.stat().st_size / 1e6), "MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", action="store_true")
    ap.add_argument("--models", default="turbo-q8=cache/ggml-large-v3-turbo-q8_0.bin,turbo-q5=cache/ggml-large-v3-turbo-q5_0.bin")
    a = ap.parse_args()
    models = {k: ROOT / v for k, v in (x.split("=", 1) for x in a.models.split(","))}
    if a.native or not (BUILD / "lib" / ABI / "libdvwhisper.so").exists():
        build_native()
    build_java()
    package(models)


if __name__ == "__main__":
    sys.exit(main())
