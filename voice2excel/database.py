"""پایگاه داده SQLite: وضعیت پردازش، متن‌ها، رکوردها، واژه‌نامه و سوابق.

هر نتیجه بلافاصله پس از پردازش هر فایل ذخیره می‌شود تا بسته‌شدن ناگهانی برنامه
چیزی را از بین نبرد. حالت WAL برای خواندن هم‌زمان رابط کاربری و نوشتن پردازشگر است.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .config import DATA_DIR
from .logger import mask_sensitive

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches(
    id INTEGER PRIMARY KEY, name TEXT, visit_date TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS audio_files(
    id INTEGER PRIMARY KEY,
    batch_id INTEGER REFERENCES batches(id),
    original_name TEXT NOT NULL,
    stored_name TEXT,
    sha256 TEXT,
    size INTEGER,
    duration REAL,
    visit_date TEXT,
    date_source TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    processing_seconds REAL,
    peak_rss_mb REAL,
    audio_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_audio_status ON audio_files(status);
CREATE INDEX IF NOT EXISTS ix_audio_sha ON audio_files(sha256);
CREATE TABLE IF NOT EXISTS transcripts(
    audio_id INTEGER PRIMARY KEY REFERENCES audio_files(id) ON DELETE CASCADE,
    raw_text TEXT, normalized_text TEXT, processed_text TEXT,
    segments_json TEXT, words_json TEXT, clauses_json TEXT,
    language TEXT, language_prob REAL, avg_logprob REAL, model TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS records(
    id INTEGER PRIMARY KEY,
    audio_id INTEGER REFERENCES audio_files(id) ON DELETE CASCADE,
    building_index INTEGER, building_count INTEGER,
    extracted_json TEXT,
    values_json TEXT,
    validation_json TEXT,
    status TEXT,
    review_state TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT,
    duplicate_decision TEXT,
    manually_edited INTEGER NOT NULL DEFAULT 0,
    export_id INTEGER, export_row INTEGER, exported_at TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_records_audio ON records(audio_id);
CREATE TABLE IF NOT EXISTS record_edits(
    id INTEGER PRIMARY KEY, record_id INTEGER, field TEXT, old_value TEXT, new_value TEXT,
    action TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS entities(
    id INTEGER PRIMARY KEY, canonical TEXT NOT NULL, type TEXT NOT NULL,
    created_at TEXT, last_confirmed_at TEXT, source TEXT, notes TEXT, use_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(type, canonical)
);
CREATE TABLE IF NOT EXISTS aliases(
    id INTEGER PRIMARY KEY, entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    alias TEXT NOT NULL, match_key TEXT NOT NULL, source TEXT, created_at TEXT,
    UNIQUE(entity_id, alias)
);
CREATE INDEX IF NOT EXISTS ix_alias_key ON aliases(match_key);
CREATE TABLE IF NOT EXISTS entity_changes(
    id INTEGER PRIMARY KEY, entity_id INTEGER, action TEXT, old_value TEXT, new_value TEXT, source TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS exports(
    id INTEGER PRIMARY KEY, created_at TEXT, target_path TEXT, output_path TEXT, backup_path TEXT,
    profile TEXT, rows_written INTEGER, first_row INTEGER, last_row INTEGER, record_ids_json TEXT,
    status TEXT, error TEXT, report_json TEXT, replaced_original_at TEXT
);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY, at TEXT, level TEXT, audio_id INTEGER, message TEXT
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS corrections(
    id INTEGER PRIMARY KEY, field_group TEXT NOT NULL, wrong TEXT NOT NULL, right TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT, last_at TEXT,
    UNIQUE(field_group, wrong, right)
);
CREATE TABLE IF NOT EXISTS knowledge_sources(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, label TEXT, sha256 TEXT, sheet TEXT, columns_json TEXT,
    rows INTEGER, engineers INTEGER, streets INTEGER, projects INTEGER, new_entities INTEGER, imported_at TEXT
);
CREATE TABLE IF NOT EXISTS entity_sources(
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    count INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(entity_id, source_id)
);
CREATE TABLE IF NOT EXISTS lan_devices(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, last_seen TEXT, last_ip TEXT
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or DATA_DIR / "voice2excel.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.write_lock = threading.RLock()
        with self.write_lock:
            self.conn().executescript(SCHEMA)  # executescript تراکنش خودش را مدیریت می‌کند
            self._migrate()

    # ستون‌هایی که پس از نسخه اول اضافه شده‌اند: (جدول، ستون، تعریف)
    _MIGRATIONS = [
        ("record_edits", "undone", "INTEGER NOT NULL DEFAULT 0"),
        ("audio_files", "dest", "TEXT"),  # فایل اکسلی که ردیف‌های این ویس در آن ثبت می‌شوند (نام قالب)
    ]

    def _migrate(self) -> None:
        """افزودن ستون‌های تازه به پایگاه داده‌های قدیمی، بدون از دست رفتن اطلاعات."""
        c = self.conn()
        for table, column, ddl in self._MIGRATIONS:
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self._drop_unique_sha()

    _AUDIO_COLUMNS = ("id", "batch_id", "original_name", "stored_name", "sha256", "size", "duration", "visit_date",
                      "date_source", "status", "error", "attempts", "model", "processing_seconds", "peak_rss_mb",
                      "audio_deleted", "created_at", "updated_at", "dest")

    def _drop_unique_sha(self) -> None:
        """نسخه‌های پیش از ۲.۷.۱: sha256 یکتا بود (هر ویس فقط یک بار در کل برنامه). حالا یک ویس می‌تواند در چند
        فایل اکسل باشد؛ جدول با همان داده و بدون آن قید دوباره ساخته می‌شود."""
        c = self.conn()
        unique = False
        for idx in c.execute("PRAGMA index_list(audio_files)").fetchall():
            if idx[2] and [r[2] for r in c.execute(f"PRAGMA index_info('{idx[1]}')")] == ["sha256"]:
                unique = True
        if not unique:
            return
        have = [r[1] for r in c.execute("PRAGMA table_info(audio_files)")]
        cols = [x for x in self._AUDIO_COLUMNS if x in have]
        ddl = SCHEMA.split("CREATE TABLE IF NOT EXISTS audio_files(")[1].split(");")[0]
        c.execute("PRAGMA foreign_keys=OFF")
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(f"CREATE TABLE audio_files_v2({ddl}, dest TEXT)" if "dest" not in ddl else f"CREATE TABLE audio_files_v2({ddl})")
            c.execute(f"INSERT INTO audio_files_v2({','.join(cols)}) SELECT {','.join(cols)} FROM audio_files")
            c.execute("DROP TABLE audio_files")
            c.execute("ALTER TABLE audio_files_v2 RENAME TO audio_files")
            c.execute("CREATE INDEX IF NOT EXISTS ix_audio_status ON audio_files(status)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_audio_sha ON audio_files(sha256)")
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.execute("PRAGMA foreign_keys=ON")

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.write_lock:
            c = self.conn()
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute("COMMIT")
            except BaseException:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                raise

    def q(self, sql: str, args: tuple | list = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn().execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple | list = ()) -> dict[str, Any] | None:
        r = self.conn().execute(sql, args).fetchone()
        return dict(r) if r else None

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    # ---------- رخدادها ----------
    def log_event(self, message: str, level: str = "info", audio_id: int | None = None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO events(at, level, audio_id, message) VALUES(?,?,?,?)",
                      (now(), level, audio_id, mask_sensitive(message)))

    # ---------- فایل‌ها ----------
    def create_batch(self, name: str, visit_date: str) -> int:
        with self.tx() as c:
            cur = c.execute("INSERT INTO batches(name, visit_date, created_at) VALUES(?,?,?)",
                            (name, visit_date, now()))
            return cur.lastrowid

    def find_audio_by_hash(self, sha: str, dest: str | None = None) -> dict | None:
        """ویسی با همین محتوا؛ با dest فقط در همان فایل اکسل."""
        if dest is None:
            return self.one("SELECT * FROM audio_files WHERE sha256=? ORDER BY id DESC", (sha,))
        return self.one("SELECT * FROM audio_files WHERE sha256=? AND dest=? ORDER BY id DESC", (sha, dest))

    def audio_by_hashes(self, hashes: list[str]) -> list[dict]:
        if not hashes:
            return []
        marks = ",".join("?" * len(hashes))
        return self.q(f"""SELECT a.*, (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id) n_rows,
                          (SELECT COUNT(*) FROM records r WHERE r.audio_id=a.id AND r.exported_at IS NOT NULL) n_written
                          FROM audio_files a WHERE a.sha256 IN ({marks}) ORDER BY a.id DESC""", tuple(hashes))

    def stored_in_use(self, stored_name: str, exclude_ids: tuple[int, ...] = ()) -> bool:
        """آیا ویس دیگری (رونوشت همان ویس در فایل دیگر) هنوز از همین فایل صوتی استفاده می‌کند؟"""
        skip = f" AND id NOT IN ({','.join('?' * len(exclude_ids))})" if exclude_ids else ""
        return bool(self.one(f"SELECT 1 x FROM audio_files WHERE stored_name=? AND audio_deleted=0{skip} LIMIT 1",
                             (stored_name, *exclude_ids)))

    def copy_audio(self, src_id: int, dest: str, batch_id: int) -> int:
        """رونوشت ویس پردازش‌شده برای فایل اکسل دیگر: همان متن و ردیف‌ها، بی‌آنکه دوباره به متن تبدیل شود.
        ردیفی که در فایل مبدأ تأیید یا ثبت شده بود، اینجا هم تأییدشده است (همان بررسی کاربر)؛ ثبت در اکسل نه."""
        with self.tx() as c:
            a = c.execute("SELECT * FROM audio_files WHERE id=?", (src_id,)).fetchone()
            cur = c.execute(
                """INSERT INTO audio_files(batch_id, original_name, stored_name, sha256, size, duration, visit_date,
                   date_source, status, error, model, processing_seconds, audio_deleted, dest, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?, 'done', ?, ?, 0, ?, ?, ?, ?)""",
                (batch_id, a["original_name"], a["stored_name"], a["sha256"], a["size"], a["duration"], a["visit_date"],
                 a["date_source"], a["error"], a["model"], a["audio_deleted"], dest, now(), now()))
            new_id = cur.lastrowid
            c.execute("""INSERT INTO transcripts(audio_id, raw_text, normalized_text, processed_text, segments_json, words_json,
                         clauses_json, language, language_prob, avg_logprob, model, created_at)
                         SELECT ?, raw_text, normalized_text, processed_text, segments_json, words_json, clauses_json,
                         language, language_prob, avg_logprob, model, ? FROM transcripts WHERE audio_id=?""",
                      (new_id, now(), src_id))
            for r in c.execute("SELECT * FROM records WHERE audio_id=? ORDER BY building_index, id", (src_id,)).fetchall():
                approved = r["review_state"] == "approved" or r["exported_at"]
                state = "approved" if approved else ("rejected" if r["review_state"] == "rejected" else "pending")
                c.execute("""INSERT INTO records(audio_id, building_index, building_count, extracted_json, values_json,
                             validation_json, status, review_state, approved_by, duplicate_decision, manually_edited,
                             created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (new_id, r["building_index"], r["building_count"], r["extracted_json"], r["values_json"],
                           r["validation_json"], r["status"], state, "copy" if approved else r["approved_by"],
                           r["duplicate_decision"], r["manually_edited"], now(), now()))
            return new_id

    def add_audio(self, batch_id: int, original_name: str, stored_name: str, sha: str, size: int,
                  visit_date: str, date_source: str, dest: str | None = None) -> int:
        with self.tx() as c:
            cur = c.execute(
                """INSERT INTO audio_files(batch_id, original_name, stored_name, sha256, size, visit_date,
                   date_source, status, dest, created_at, updated_at) VALUES(?,?,?,?,?,?,?, 'queued', ?, ?, ?)""",
                (batch_id, original_name, stored_name, sha, size, visit_date, date_source, dest, now(), now()),
            )
            return cur.lastrowid

    def bind_unassigned(self, dest: str) -> int:
        """ویس‌هایی که هنوز به فایلی وصل نیستند (پایگاه داده نسخه‌های قبل) به فایل dest وصل می‌شوند."""
        with self.tx() as c:
            return c.execute("UPDATE audio_files SET dest=? WHERE dest IS NULL OR dest=''", (dest,)).rowcount

    def set_audio(self, audio_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE audio_files SET {cols} WHERE id=?", (*fields.values(), audio_id))

    def next_queued(self) -> dict | None:
        return self.one("SELECT * FROM audio_files WHERE status='queued' ORDER BY id LIMIT 1")

    def claim(self, audio_id: int) -> bool:
        """علامت‌گذاری اتمیک برای جلوگیری از پردازش دوباره هم‌زمان."""
        with self.tx() as c:
            cur = c.execute(
                "UPDATE audio_files SET status='processing', attempts=attempts+1, updated_at=? "
                "WHERE id=? AND status='queued'", (now(), audio_id))
            return cur.rowcount == 1

    def recover_interrupted(self) -> int:
        """فایل‌هایی که هنگام بسته‌شدن برنامه در حال پردازش بودند به صف برمی‌گردند."""
        with self.tx() as c:
            cur = c.execute(
                "UPDATE audio_files SET status='queued', error=?, updated_at=? WHERE status='processing'",
                ("پردازش قبلی ناتمام ماند (بسته‌شدن برنامه)؛ دوباره در صف قرار گرفت.", now()))
            return cur.rowcount

    def counts(self) -> dict[str, int]:
        rows = self.q("SELECT status, COUNT(*) n FROM audio_files GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    # ---------- متن و رکورد ----------
    def save_results(self, audio_id: int, transcript: dict, records: list[dict]) -> list[int]:
        """ذخیره متن و رکوردها در یک تراکنش. رکوردهای اصلاح‌شده دستی یا ثبت‌شده دست نمی‌خورند."""
        with self.tx() as c:
            protected = c.execute(
                "SELECT COUNT(*) FROM records WHERE audio_id=? AND (manually_edited=1 OR exported_at IS NOT NULL "
                "OR (review_state!='pending' AND approved_by='user'))", (audio_id,)).fetchone()[0]
            c.execute(
                """INSERT OR REPLACE INTO transcripts(audio_id, raw_text, normalized_text, processed_text,
                   segments_json, words_json, clauses_json, language, language_prob, avg_logprob, model, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (audio_id, transcript["raw_text"], transcript["normalized_text"], transcript["processed_text"],
                 json.dumps(transcript.get("segments", []), ensure_ascii=False),
                 json.dumps(transcript.get("words", []), ensure_ascii=False),
                 json.dumps(transcript.get("clauses", []), ensure_ascii=False),
                 transcript.get("language"), transcript.get("language_prob"), transcript.get("avg_logprob"),
                 transcript.get("model"), now()))
            if protected:
                return []
            c.execute("DELETE FROM records WHERE audio_id=?", (audio_id,))
            ids = []
            for r in records:
                cur = c.execute(
                    """INSERT INTO records(audio_id, building_index, building_count, extracted_json, values_json,
                       validation_json, status, review_state, approved_by, created_at, updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (audio_id, r["building_index"], r["building_count"], json.dumps(r["extracted"], ensure_ascii=False),
                     json.dumps(r["values"], ensure_ascii=False), json.dumps(r["validation"], ensure_ascii=False),
                     r["status"], r.get("review_state", "pending"), r.get("approved_by"), now(), now()))
                ids.append(cur.lastrowid)
            return ids

    def get_record(self, record_id: int) -> dict | None:
        r = self.one("SELECT * FROM records WHERE id=?", (record_id,))
        return _decode_record(r) if r else None

    def list_records(self, where: str = "1=1", args: tuple = ()) -> list[dict]:
        rows = self.q(
            f"""SELECT r.*, a.original_name, a.visit_date AS audio_visit_date, a.status AS audio_status,
                a.audio_deleted FROM records r JOIN audio_files a ON a.id=r.audio_id WHERE {where}
                ORDER BY r.audio_id, r.building_index""", args)
        return [_decode_record(r) for r in rows]

    def update_record(self, record_id: int, **fields: Any) -> None:
        for k in ("values_json", "validation_json", "extracted_json"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k], ensure_ascii=False)
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE records SET {cols} WHERE id=?", (*fields.values(), record_id))

    def log_edit(self, record_id: int, field: str, old: str, new: str, action: str = "edit") -> None:
        with self.tx() as c:
            c.execute("INSERT INTO record_edits(record_id, field, old_value, new_value, action, at) VALUES(?,?,?,?,?,?)",
                      (record_id, field, old, new, action, now()))

    def transcript(self, audio_id: int) -> dict | None:
        t = self.one("SELECT * FROM transcripts WHERE audio_id=?", (audio_id,))
        if t:
            for k in ("segments_json", "words_json", "clauses_json"):
                t[k[:-5]] = json.loads(t.pop(k) or "[]")
        return t

    # ---------- متا ----------
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        r = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, value))

    # ---------- گوشی‌های شبکه محلی ----------
    def add_device(self, name: str, token_hash: str, ip: str) -> int:
        with self.tx() as c:
            return c.execute("INSERT INTO lan_devices(name, token_hash, created_at, last_seen, last_ip) VALUES(?,?,?,?,?)",
                             (name, token_hash, now(), now(), ip)).lastrowid

    def device_by_token(self, token_hash: str) -> dict | None:
        return self.one("SELECT * FROM lan_devices WHERE token_hash=?", (token_hash,))

    def touch_device(self, device_id: int, ip: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE lan_devices SET last_seen=?, last_ip=? WHERE id=?", (now(), ip, device_id))

    def list_devices(self) -> list[dict]:
        return self.q("SELECT id, name, created_at, last_seen, last_ip FROM lan_devices ORDER BY last_seen DESC")

    def delete_devices(self, device_id: int | None = None) -> int:
        with self.tx() as c:
            if device_id is None:
                return c.execute("DELETE FROM lan_devices").rowcount
            return c.execute("DELETE FROM lan_devices WHERE id=?", (device_id,)).rowcount

    def wipe_all(self) -> None:
        """پاک‌کردن همه اطلاعات کاربران (رکورد، متن ویس، واژه‌نامه، اصلاحات، رخدادها)؛ فقط متای فنی می‌ماند.
        فایل پایگاه داده بازنویسی می‌شود تا داده پاک‌شده در فضای خالی فایل باقی نماند."""
        with self.write_lock:
            conn = self.conn()
            conn.execute("PRAGMA foreign_keys=OFF")  # بیرون از تراکنش؛ ترتیب پاک‌کردن جدول‌ها مهم نباشد
            try:
                with self.tx() as c:
                    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='meta'").fetchall():
                        c.execute(f'DELETE FROM "{t}"')  # sqlite_sequence هم: شماره‌ها از ۱ شروع شوند
            finally:
                conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _decode_record(r: dict) -> dict:
    for k in ("extracted_json", "values_json", "validation_json"):
        r[k[:-5]] = json.loads(r.pop(k) or "{}")
    return r


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    with _db_lock:
        if _db is None:
            _db = Database()
        return _db


def set_db(db: Database | None) -> None:
    """برای آزمون‌ها: جایگزینی پایگاه داده سراسری."""
    global _db
    with _db_lock:
        _db = db
