"""اطلاعات پنل فروشنده: مشتری‌ها و مجوزهای صادرشده (SQLite کنار کلیدهای امضا، نه در مخزن یا بسته).

این برنامه فقط روی رایانه فروشنده اجرا می‌شود و هرگز همراه بسته مشتری نمی‌رود.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from voice2excel import ed25519, licensing

KEYS_DIR = Path(os.environ.get("V2X_SELLER_DIR") or Path.home() / ".voice2excel-keys")
CODE_RE = re.compile(r"^[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$")
YEAR_DAYS = 365
SOON_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses(
    id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
    machine TEXT NOT NULL, kind TEXT NOT NULL, issued TEXT NOT NULL, expires TEXT,
    amount INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', text TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lic_machine ON licenses(machine);
"""


class SellerError(Exception):
    """پیام قابل فهم برای فروشنده."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_key() -> bytes:
    p = KEYS_DIR / "license-signing.key"
    if not p.exists():
        raise SellerError(f"کلید امضای مجوز پیدا نشد: {p}")
    key = bytes.fromhex(p.read_text().strip())
    if ed25519.public_key(key) != licensing.LICENSE_PUBLIC_KEY:
        raise SellerError("کلید امضای مجوز با کلید داخل برنامه نمی‌خواند.")
    return key


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or KEYS_DIR / "seller.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, args)]

    def run(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            return self.conn.execute(sql, args).lastrowid

    # ---------- مشتری ----------
    def find_or_create(self, name: str, phone: str) -> int:
        name, phone = name.strip()[:120], _digits(phone)
        if not name:
            raise SellerError("نام مشتری را بنویسید.")
        row = (self.q("SELECT id FROM customers WHERE phone=? AND phone!=''", (phone,)) if phone else []) \
            or self.q("SELECT id FROM customers WHERE name=?", (name,))
        if row:
            if phone:
                self.run("UPDATE customers SET phone=? WHERE id=? AND phone=''", (phone, row[0]["id"]))
            return row[0]["id"]
        return self.run("INSERT INTO customers(name, phone, created_at) VALUES(?,?,?)", (name, phone, _now()))

    def update_customer(self, cid: int, name: str, phone: str, notes: str) -> None:
        if not name.strip():
            raise SellerError("نام مشتری خالی است.")
        self.run("UPDATE customers SET name=?, phone=?, notes=? WHERE id=?",
                 (name.strip()[:120], _digits(phone), notes.strip()[:2000], cid))

    # ---------- مجوز ----------
    def issue(self, customer_id: int, machine: str, kind: str, amount: int = 0, note: str = "",
              start: date | None = None) -> dict:
        machine = machine.strip().upper()
        if not CODE_RE.match(machine):
            raise SellerError("کد رایانه باید مانند ABCD-EFGH-IJKL-MNOP باشد.")
        if kind not in ("year", "forever"):
            raise SellerError("مدت اشتراک نامعتبر است.")
        cust = self.q("SELECT name FROM customers WHERE id=?", (customer_id,))
        if not cust:
            raise SellerError("مشتری پیدا نشد.")
        today = date.today()
        expires = None if kind == "forever" else ((start or today) + timedelta(days=YEAR_DAYS)).isoformat()
        data = {"customer": cust[0]["name"], "machine": machine, "issued": today.isoformat()}
        if expires:
            data["expires"] = expires
        text = licensing.encode(data, load_key())
        if licensing.decode(text) != data:
            raise SellerError("مجوز ساخته‌شده بررسی نشد.")
        lid = self.run("INSERT INTO licenses(customer_id, machine, kind, issued, expires, amount, note, text, created_at) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (customer_id, machine, kind, today.isoformat(), expires, max(0, int(amount or 0)),
                        note.strip()[:500], text, _now()))
        return self.license(lid)

    def renew(self, license_id: int, kind: str = "year", amount: int = 0, note: str = "") -> dict:
        """تمدید زودهنگام روزی را از دست نمی‌دهد: یک سال از پایان اشتراک فعلی (یا امروز اگر گذشته)."""
        old = self.license(license_id)
        start = max(date.today(), date.fromisoformat(old["expires"])) if old["expires"] else None
        return self.issue(old["customer_id"], old["machine"], kind, amount, note or "تمدید", start)

    def license(self, lid: int) -> dict:
        rows = self.q("SELECT l.*, c.name AS customer, c.phone FROM licenses l JOIN customers c ON c.id=l.customer_id "
                      "WHERE l.id=?", (lid,))
        if not rows:
            raise SellerError("این مجوز پیدا نشد.")
        return _with_state(rows[0])

    def latest_per_machine(self) -> list[dict]:
        rows = self.q("""SELECT l.*, c.name AS customer, c.phone FROM licenses l JOIN customers c ON c.id=l.customer_id
                         WHERE l.id = (SELECT MAX(id) FROM licenses x WHERE x.machine=l.machine)""")
        return [_with_state(r) for r in rows]

    def customers(self, query: str = "") -> list[dict]:
        like = f"%{query.strip()}%"
        custs = self.q("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY id DESC", (like, like))
        latest: dict[int, list[dict]] = {}
        for lic in self.latest_per_machine():
            latest.setdefault(lic["customer_id"], []).append(lic)
        paid = {r["customer_id"]: r["s"] for r in self.q("SELECT customer_id, SUM(amount) s FROM licenses GROUP BY customer_id")}
        lic_rows = self.q("SELECT l.*, c.name AS customer, c.phone FROM licenses l JOIN customers c ON c.id=l.customer_id "
                          "ORDER BY l.id DESC")
        by_cust: dict[int, list[dict]] = {}
        for r in lic_rows:
            by_cust.setdefault(r["customer_id"], []).append(_with_state(r))
        return [{**c, "machines": latest.get(c["id"], []), "licenses": by_cust.get(c["id"], []),
                 "paid": paid.get(c["id"]) or 0} for c in custs]

    def due(self) -> list[dict]:
        """اشتراک‌هایی که تا ۳۰ روز دیگر تمام می‌شوند یا تمام شده‌اند (آخرین مجوز هر رایانه)."""
        rows = [r for r in self.latest_per_machine() if r["state"] in ("soon", "lapsed")]
        return sorted(rows, key=lambda r: r["expires"])

    def import_folder(self, folder: Path) -> int:
        """مجوزهای پیشین (scripts/issue_license.py) یک بار به پنل آورده می‌شوند."""
        added = 0
        known = {r["text"] for r in self.q("SELECT text FROM licenses")}
        for f in sorted(folder.glob("*.v2x")):
            text = "".join(f.read_text(encoding="utf-8").split())
            if text in known:
                continue
            try:
                data = licensing.decode(text)
            except licensing.LicenseError:
                continue
            cid = self.find_or_create(data.get("customer") or f.stem, "")
            self.run("INSERT INTO licenses(customer_id, machine, kind, issued, expires, amount, note, text, created_at) "
                     "VALUES(?,?,?,?,?,0,?,?,?)",
                     (cid, data["machine"], "year" if data.get("expires") else "forever", data.get("issued") or "",
                      data.get("expires"), "از فایل‌های قبلی", text, _now()))
            added += 1
        return added


def _digits(phone: str) -> str:
    s = str(phone or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    return re.sub(r"[^\d+]", "", s)[:20]


def _with_state(r: dict) -> dict:
    if not r.get("expires"):
        return {**r, "state": "forever", "days_left": None}
    left = (date.fromisoformat(r["expires"]) - date.today()).days
    return {**r, "state": "lapsed" if left < 0 else "soon" if left <= SOON_DAYS else "active", "days_left": left}
