"""پنل فروشنده: صدور، تمدید و پیگیری مجوز مشتری‌ها؛ فقط روی همین رایانه (127.0.0.1)."""
from __future__ import annotations

import json
import secrets
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from voice2excel import __version__
from voice2excel.dates_fa import format_jalali, from_gregorian

from .store import KEYS_DIR, SellerError, Store, load_key

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
CONTACT_FILE = ROOT / "voice2excel" / "assets" / "contact.json"
LICENSES_DIR = ROOT / "licenses"
TOKEN = secrets.token_urlsafe(32)
_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "voice2excel" / "web"), name="static")
_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
        if LICENSES_DIR.exists():
            _store.import_folder(LICENSES_DIR)
    return _store


@app.middleware("http")
async def _guard(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
    if host not in ("127.0.0.1", "localhost"):
        return JSONResponse(status_code=403, content={"detail": "درخواست نامعتبر."})
    if request.headers.get("sec-fetch-site") in ("cross-site", "same-site") and request.url.path != "/":
        return JSONResponse(status_code=403, content={"detail": "درخواست از صفحه دیگری پذیرفته نمی‌شود."})
    if request.method not in ("GET", "HEAD") and not secrets.compare_digest(request.headers.get("x-token", ""), TOKEN):
        return JSONResponse(status_code=403, content={"detail": "صفحه را دوباره باز کنید (F5)."})
    response = await call_next(request)
    response.headers.update({"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff",
                             "Referrer-Policy": "no-referrer", "Content-Security-Policy": _CSP})
    return response


def err(status: int, msg: str):
    raise HTTPException(status_code=status, detail=msg)


def _j(iso: str | None) -> str:
    return format_jalali(from_gregorian(date.fromisoformat(iso[:10]))) if iso else ""


def _out(lic: dict) -> dict:
    return {**lic, "issued_j": _j(lic.get("issued")), "expires_j": _j(lic.get("expires")),
            "file": f"{lic['machine'][:4]}-{lic['id']}.v2x"}


@app.get("/")
def index():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("</head>", f'  <meta name="x-token" content="{TOKEN}">\n</head>', 1),
                        headers={"Cache-Control": "no-store"})


@app.get("/panel.js")
def panel_js():
    return FileResponse(WEB / "panel.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/api/overview")
def overview():
    try:
        load_key()
        key_ok, key_error = True, ""
    except SellerError as e:
        key_ok, key_error = False, str(e)
    latest = store().latest_per_machine()
    count = lambda s: sum(1 for r in latest if r["state"] == s)  # noqa: E731
    return {"version": __version__, "keys_dir": str(KEYS_DIR), "key_ok": key_ok, "key_error": key_error,
            "customers": len(store().q("SELECT id FROM customers")), "active": count("active") + count("soon"),
            "forever": count("forever"), "soon": count("soon"), "lapsed": count("lapsed"),
            "paid": store().q("SELECT COALESCE(SUM(amount),0) s FROM licenses")[0]["s"], "contact": _contact()}


@app.get("/api/customers")
def customers(q: str = ""):
    return {"customers": [{**c, "machines": [_out(m) for m in c["machines"]], "licenses": [_out(x) for x in c["licenses"]]}
                          for c in store().customers(q)]}


class CustomerIn(BaseModel):
    name: str
    phone: str = ""
    notes: str = ""


@app.put("/api/customers/{cid}")
def customer_update(cid: int, body: CustomerIn):
    try:
        store().update_customer(cid, body.name, body.phone, body.notes)
    except SellerError as e:
        err(400, str(e))
    return {"ok": True}


class IssueIn(BaseModel):
    name: str
    phone: str = ""
    machine: str
    kind: str = "year"
    amount: int = 0
    note: str = ""


def _save_file(lic: dict) -> None:
    """نسخه فایلی هر مجوز هم در پوشه licenses (مثل ابزار خط فرمان) می‌ماند."""
    LICENSES_DIR.mkdir(exist_ok=True)
    (LICENSES_DIR / _out(lic)["file"]).write_text(lic["text"], encoding="utf-8")


@app.post("/api/issue")
def issue(body: IssueIn):
    try:
        cid = store().find_or_create(body.name, body.phone)
        lic = store().issue(cid, body.machine, body.kind, body.amount, body.note)
    except SellerError as e:
        err(400, str(e))
    _save_file(lic)
    return _out(lic)


class RenewIn(BaseModel):
    kind: str = "year"
    amount: int = 0
    note: str = ""


@app.post("/api/licenses/{lid}/renew")
def renew(lid: int, body: RenewIn):
    try:
        lic = store().renew(lid, body.kind, body.amount, body.note)
    except SellerError as e:
        err(400, str(e))
    _save_file(lic)
    return _out(lic)


@app.get("/api/licenses/{lid}/file")
def license_file(lid: int):
    try:
        lic = _out(store().license(lid))
    except SellerError as e:
        err(404, str(e))
    return Response(lic["text"], media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{lic["file"]}"'})


@app.get("/api/due")
def due():
    return {"licenses": [_out(x) for x in store().due()]}


def _contact() -> dict:
    try:
        data = json.loads(CONTACT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {k: str(data.get(k) or "") for k in ("name", "phone", "telegram", "whatsapp")}


class ContactIn(BaseModel):
    name: str = ""
    phone: str = ""
    telegram: str = ""
    whatsapp: str = ""


@app.put("/api/contact")
def contact_save(body: ContactIn):
    data = {k: v.strip()[:80] for k, v in body.model_dump().items()}
    data["telegram"] = data["telegram"].lstrip("@").replace("https://t.me/", "")
    CONTACT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return _contact()
