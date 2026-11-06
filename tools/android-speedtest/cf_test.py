"""آزمایش Cloudflare Workers AI (whisper-large-v3-turbo) با حساب کاربر؛ کلید هرگز چاپ نمی‌شود.

    python cf_test.py verify
    python cf_test.py run [sample-01 ...]
"""
import base64
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CRED = ROOT.parent / "cloudflare.txt"
MODEL = "@cf/openai/whisper-large-v3-turbo"
PROMPT = ("سلام، مهندس، شماره تماس، آدرس خیابان، کوچه، پلاک، قطعه دوم، نبش، سازه فلز، سازه بتن، "
          "تعداد سقف، سقف‌ها اجرا شده، تازه استارت خورده، دیوارچینی، زنگ بزنین.")


def creds():
    t = CRED.read_text(encoding="utf-8-sig")
    acc = re.search(r"account\s*=\s*([0-9a-f]{32})", t).group(1)
    m = re.search(r'Bearer\s+([^\s"\\]+)', t) or re.search(r"token\s*=\s*([A-Za-z0-9_\-]{20,})", t)
    return acc, m.group(1)


BIND = os.environ.get("CF_BIND")  # آدرس کارت شبکه واقعی، تا درخواست بیرون از VPN برود


def call(method, url, token, body=None, timeout=120):
    if BIND:
        from urllib.parse import urlsplit
        u = urlsplit(url)
        c = http.client.HTTPSConnection(u.hostname, timeout=timeout, source_address=(BIND, 0))
        c.request(method, u.path, body=None if body is None else json.dumps(body).encode(),
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, {"raw": raw[:300].decode("utf-8", "replace")}
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300].decode("utf-8", "replace")}


def trace():
    if BIND:
        c = http.client.HTTPSConnection("www.cloudflare.com", timeout=15, source_address=(BIND, 0))
        c.request("GET", "/cdn-cgi/trace")
        t = c.getresponse().read().decode()
        return dict(l.split("=", 1) for l in t.splitlines() if "=" in l).get("loc")
    with urllib.request.urlopen("https://www.cloudflare.com/cdn-cgi/trace", timeout=15) as r:
        return dict(l.split("=", 1) for l in r.read().decode().splitlines() if "=" in l).get("loc")


def main():
    acc, tok = creds()
    print("loc:", trace())
    if sys.argv[1] == "verify":
        for url in (f"https://api.cloudflare.com/client/v4/accounts/{acc}/tokens/verify",
                    "https://api.cloudflare.com/client/v4/user/tokens/verify"):
            code, d = call("GET", url, tok)
            print(code, d.get("success"), (d.get("result") or {}).get("status"), d.get("errors"))
        return
    for name in sys.argv[2:] or ["sample-01"]:
        wav = (ROOT / "app" / "assets" / "samples" / f"{name}.wav").read_bytes()
        body = {"audio": base64.b64encode(wav).decode(), "task": "transcribe", "language": "fa",
                "initial_prompt": PROMPT, "vad_filter": True}
        t0 = time.time()
        code, d = call("POST", f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{MODEL}", tok, body)
        el = time.time() - t0
        if code == 200 and d.get("success"):
            r = d["result"]
            segs = r.get("segments") or []
            words = sum(len(s.get("words") or []) for s in segs)
            print(f"{name}: {el:.1f}s | segments {len(segs)} words-with-time {words}")
            print("   ", r.get("text", "").strip())
        else:
            print(f"{name}: HTTP {code} {el:.1f}s", json.dumps(d, ensure_ascii=False)[:500])


if __name__ == "__main__":
    main()
