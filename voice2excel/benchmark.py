"""مقایسه مدل‌های گفتار روی ویس‌های واقعی: سرعت، حافظه و دقت استخراج.

استفاده:
    python -m voice2excel.benchmark --audio "پوشه ویس‌ها" --models tiny,base,small [--labels labels.csv]

فایل برچسب (اختیاری، CSV با UTF-8) ستون‌های زیر را دارد؛ مقادیر درستی که در ویس گفته شده:
    file,engineer_name,phone,address
هر مدل در یک فرایند جداگانه اجرا می‌شود تا مصرف RAM آن دقیق اندازه‌گیری شود.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")


def _norm(s: str) -> str:
    from .normalizer import normalize_text, strip_title

    _, bare = strip_title(s or "")
    return normalize_text(bare).replace(" ", "").replace("‌", "").replace("،", "").replace(",", "")


def _phone_key(s: str) -> str:
    from .phone import compare_key

    return ",".join(sorted(compare_key(p) for p in str(s or "").replace("\n", ",").split(",") if p.strip()))


def run_one_model(model: str, files: list[Path], beam: int) -> dict:
    """درون فرایند جداگانه اجرا می‌شود."""
    import psutil

    from .audio_processor import load_audio
    from .config import load_settings
    from .extractor import extract
    from .transcriber import Transcriber

    s = load_settings()
    s.model_name = model
    s.beam_size = beam
    t = Transcriber(s)
    t0 = time.time()
    t.load()
    load_s = time.time() - t0
    out = []
    for f in files:
        try:
            audio = load_audio(f)
            dur = len(audio) / 16000
            t1 = time.time()
            tr = t.transcribe(audio)
            el = time.time() - t1
            rec = extract(tr.text).records[0]
            out.append({"file": f.name, "duration": round(dur, 2), "seconds": round(el, 2), "text": tr.text,
                        "engineer_name": rec.get("engineer_name"), "phone": rec.get("phone"), "address": rec.get("address")})
        except Exception as e:
            out.append({"file": f.name, "error": f"{type(e).__name__}: {e}"})
    mi = psutil.Process().memory_info()
    return {"model": model, "load_seconds": round(load_s, 1), "peak_mb": round(getattr(mi, "peak_wset", mi.rss) / 1e6),
            "results": out}


def score(run: dict, labels: dict[str, dict]) -> dict:
    ok = [r for r in run["results"] if "error" not in r]
    total_audio = sum(r["duration"] for r in ok) or 1
    total_time = sum(r["seconds"] for r in ok)
    summary = {
        "model": run["model"], "files": len(run["results"]), "errors": len(run["results"]) - len(ok),
        "avg_seconds_per_file": round(total_time / max(1, len(ok)), 2),
        "real_time_factor": round(total_time / total_audio, 2), "peak_ram_mb": run["peak_mb"],
        "load_seconds": run["load_seconds"],
    }
    labeled = [r for r in ok if r["file"] in labels]
    if labeled:
        for field, key in (("engineer_name", _norm), ("phone", _phone_key), ("address", _norm)):
            hits = sum(1 for r in labeled if labels[r["file"]].get(field) and key(r.get(field, "")) == key(labels[r["file"]][field]))
            n = sum(1 for r in labeled if labels[r["file"]].get(field))
            summary[f"{field}_accuracy"] = f"{hits}/{n}" if n else "-"
        summary["labeled_files"] = len(labeled)
    return summary


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="مقایسه مدل‌های گفتار")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--models", default="tiny,base,small")
    ap.add_argument("--labels", default="")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--worker", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)

    from .audio_processor import is_supported
    from .config import DATA_DIR
    from .transcriber import model_available

    folder = Path(a.audio)
    files = sorted(p for p in folder.iterdir() if p.is_file() and is_supported(p.name))
    if a.worker:
        print("@@RESULT@@" + json.dumps(run_one_model(a.worker, files, a.beam), ensure_ascii=False))
        return 0
    if not files:
        print("هیچ فایل صوتی در پوشه پیدا نشد.")
        return 1
    labels = {}
    if a.labels:
        with open(a.labels, encoding="utf-8-sig") as fh:
            labels = {row["file"]: row for row in csv.DictReader(fh)}
    runs, summaries = [], []
    for m in [x.strip() for x in a.models.split(",") if x.strip()]:
        if not model_available(m):
            print(f"مدل {m} نصب نیست؛ رد شد.")
            continue
        print(f"در حال اجرای مدل {m} روی {len(files)} فایل...")
        p = subprocess.run([sys.executable, "-m", "voice2excel.benchmark", "--audio", str(folder), "--worker", m,
                            "--beam", str(a.beam)], capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("@@RESULT@@")), None)
        if not line:
            print(f"اجرای مدل {m} ناموفق بود:\n{p.stderr[-2000:]}")
            continue
        run = json.loads(line[len("@@RESULT@@"):])
        runs.append(run)
        summaries.append(score(run, labels))
        print(json.dumps(summaries[-1], ensure_ascii=False))
    out = Path(a.out) if a.out else DATA_DIR / "reports" / f"benchmark-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summaries, "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"گزارش کامل: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
