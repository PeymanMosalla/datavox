"""سنجش سرعت موتور whisper.cpp ساخته‌شده برای پردازنده قدیمی (بدون SSE4.1/AVX) روی همین رایانه.

    pcenv\\Scripts\\python.exe bench_old_cpu.py <model.bin> <threads> [beam] [samples...]
"""
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI = ROOT / "build" / "win-core2" / "bin" / "whisper-cli.exe"
model, threads = sys.argv[1], sys.argv[2]
beam = sys.argv[3] if len(sys.argv) > 3 else "2"
names = sys.argv[4:] or ["sample-01"]
tot_a = tot_t = 0.0
for n in names:
    f = ROOT / "app" / "assets" / "samples" / f"{n}.wav"
    with wave.open(str(f)) as w:
        dur = w.getnframes() / w.getframerate()
    t0 = time.time()
    p = subprocess.run([str(CLI), "-m", model, "-f", str(f), "-t", threads, "-l", "fa", "-bs", beam, "-nt", "-np"],
                       capture_output=True)
    el = time.time() - t0
    err = p.stderr.decode("utf-8", "replace")
    enc = re.search(r"encode time =\s*([\d.]+) ms", err)
    tot_a += dur
    tot_t += el
    print(f"{Path(model).stem} t={threads} beam={beam} {n}: voice {dur:.1f}s -> {el:.1f}s (x{el / dur:.2f})"
          f" encode={float(enc.group(1)) / 1000 if enc else -1:.1f}s", flush=True)
print(f"TOTAL voice {tot_a:.0f}s -> {tot_t:.0f}s | per minute of voice: {60 * tot_t / tot_a:.0f}s", flush=True)
