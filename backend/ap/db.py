"""Storage. One connection per call keeps threads (pipeline runs) and the API safe.

Locally this is one SQLite file. When DATABASE_URL is set (the hosted version on Vercel), the same queries run on
Postgres instead, because hosted containers forget their disk. There, every visitor gets their own copy of the demo
data (a Postgres schema named after a browser cookie), so two reviewers never see each other's runs, and uploaded
files are kept in the database as well as on local disk."""
import contextvars
import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("AP_DB", APP / "backend" / "ap.db"))
STORAGE = Path(os.environ.get("AP_STORAGE", APP / "backend" / "storage"))
DATA = APP / "data"
IST = timezone(timedelta(hours=5, minutes=30))

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
PG = bool(DATABASE_URL)
_workspace = contextvars.ContextVar("workspace", default="default")
_sqlite_override = contextvars.ContextVar("sqlite_override", default=None)  # seeding always runs on SQLite
_PK = {"documents": "doc_id", "invoices": "invoice_id", "tasks": "task_id", "events": "event_id"}

SCHEMA = """
CREATE TABLE vendors(vendor_id TEXT PRIMARY KEY, name TEXT, gstin TEXT, state TEXT, msme TEXT, bank_account TEXT, ifsc TEXT,
  email_domains TEXT, contact_email TEXT, phone TEXT, payment_terms_days INTEGER, addr TEXT);
CREATE TABLE purchase_orders(po_no TEXT PRIMARY KEY, vendor_id TEXT, po_date TEXT, status TEXT DEFAULT 'open');
CREATE TABLE po_lines(po_no TEXT, line_no INTEGER, item_code TEXT, description TEXT, hsn TEXT, qty REAL, unit_price REAL, gst_rate REAL);
CREATE TABLE receipts(grn_no TEXT, po_no TEXT, line_no INTEGER, qty_received REAL, received_date TEXT);
CREATE TABLE documents(doc_id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, sender TEXT, subject TEXT, received_at TEXT,
  message_id TEXT, filename TEXT, sha256 TEXT, kind TEXT, stored_path TEXT, preview_path TEXT, classified_as TEXT, created_at TEXT);
CREATE TABLE runs(run_id TEXT PRIMARY KEY, doc_id INTEGER, invoice_id INTEGER, status TEXT, route TEXT, started_at TEXT, finished_at TEXT);
CREATE TABLE invoices(invoice_id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, run_id TEXT, vendor_id TEXT, invoice_no TEXT,
  invoice_no_norm TEXT, invoice_date TEXT, po_no TEXT, po_suggested TEXT, subtotal REAL, tax_total REAL, total REAL, tax_type TEXT,
  outcome TEXT, outcome_title TEXT, outcome_reason TEXT, next_step TEXT, due_date TEXT, decided_at TEXT, rules_version TEXT,
  extractor TEXT, source TEXT, exported INTEGER DEFAULT 0, received_at TEXT, resolved_at TEXT, touched INTEGER DEFAULT 0,
  paid INTEGER DEFAULT 0);
CREATE TABLE invoice_lines(invoice_id INTEGER, line_no INTEGER, description TEXT, hsn TEXT, qty REAL, unit_price REAL, amount REAL,
  po_no TEXT, po_line INTEGER, match_score REAL);
CREATE TABLE fields(invoice_id INTEGER, name TEXT, value TEXT, source TEXT, confidence REAL, found_in_source INTEGER, bbox TEXT);
CREATE TABLE rule_results(invoice_id INTEGER, rule_id TEXT, question INTEGER, title TEXT, outcome TEXT, severity TEXT, owner TEXT, detail TEXT);
CREATE TABLE tasks(task_id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER, owner_role TEXT, kind TEXT, ask TEXT,
  draft_to TEXT, draft_subject TEXT, draft_body TEXT, status TEXT, created_at TEXT, resolved_at TEXT);
CREATE TABLE events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, invoice_id INTEGER, ts TEXT, stage_no INTEGER,
  stage TEXT, status TEXT, summary TEXT, detail TEXT, prev_hash TEXT, hash TEXT);
"""


def now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def connect():
    con = sqlite3.connect(_sqlite_override.get() or DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _use_pg():
    return PG and _sqlite_override.get() is None


def q(sql, params=()):
    if _use_pg():
        return _pg(sql, params, "all")
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def one(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def x(sql, params=()):
    if _use_pg():
        return _pg(sql, params, "none")
    con = connect()
    try:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def x_count(sql, params=()) -> int:
    """Run a write and return how many rows it changed (used to claim a run exactly once)."""
    if _use_pg():
        return _pg(sql, params, "count")
    con = connect()
    try:
        cur = con.execute(sql, params)
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def insert(table, row: dict):
    cols = ",".join(row)
    sql = f"INSERT INTO {table}({cols}) VALUES({','.join('?' * len(row))})"
    if _use_pg():
        return _pg(sql + (f" RETURNING {_PK[table]}" if table in _PK else ""), tuple(row.values()), "id" if table in _PK else "none")
    return x(sql, tuple(row.values()))


def _event_row(prev, run_id, invoice_id, stage_no, stage, status, summary, detail):
    ts = now()
    body = json.dumps([run_id, invoice_id, ts, stage_no, stage, status, summary, detail], sort_keys=True, default=str)
    h = hashlib.sha256((prev + body).encode()).hexdigest()
    return dict(run_id=run_id, invoice_id=invoice_id, ts=ts, stage_no=stage_no, stage=stage, status=status,
                summary=summary, detail=json.dumps(detail, default=str) if detail is not None else None, prev_hash=prev, hash=h)


_local_event_lock = threading.Lock()


def add_event(run_id, invoice_id, stage_no, stage, status, summary, detail=None):
    """Two writers adding events at once (a run and a click) could both chain onto the same previous entry and break
    the log, so reading the last hash and writing the new entry happen under one lock."""
    args = (run_id, invoice_id, stage_no, stage, status, summary, detail)
    if not _use_pg():
        with _local_event_lock:
            last = one("SELECT hash FROM events ORDER BY event_id DESC LIMIT 1")
            insert("events", _event_row(last["hash"] if last else "genesis", *args))
        return
    with _pool().connection() as con, con.transaction():
        _set_path(con)
        con.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("events:" + schema(),))
        last = con.execute("SELECT hash FROM events ORDER BY event_id DESC LIMIT 1").fetchone()
        row = _event_row(last["hash"] if last else "genesis", *args)
        con.execute(f"INSERT INTO events({','.join(row)}) VALUES({','.join(['%s'] * len(row))})", _pg_params(row.values()))


def verify_chain() -> bool:
    prev = "genesis"
    for e in q("SELECT * FROM events ORDER BY event_id"):
        detail = json.loads(e["detail"]) if e["detail"] else None
        body = json.dumps([e["run_id"], e["invoice_id"], e["ts"], e["stage_no"], e["stage"], e["status"], e["summary"], detail],
                          sort_keys=True, default=str)
        if e["prev_hash"] != prev or hashlib.sha256((prev + body).encode()).hexdigest() != e["hash"]:
            return False
        prev = e["hash"]
    return True


def norm_invoice_no(s: str) -> str:
    """'INV/2026/042' and 'INV-2026-42' both become 'INV202642'."""
    import re
    parts = re.findall(r"[A-Za-z]+|\d+", s or "")
    return "".join(p.upper() if p.isalpha() else str(int(p)) for p in parts)


def reset():
    """Restore the starting data. Hosted, this resets only the current visitor's copy."""
    if _use_pg():
        _pg_reset_workspace()
        return
    STORAGE.mkdir(parents=True, exist_ok=True)
    for f in STORAGE.glob("*"):
        f.unlink(missing_ok=True)
    _create_and_seed()


def _create_and_seed():
    con = connect()
    try:  # drop and recreate tables rather than deleting the file (Windows keeps open files locked)
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
            con.execute(f"DROP TABLE {name}")
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()
    load = lambda name: list(csv.DictReader(open(DATA / name, encoding="utf-8")))
    for r in load("vendors.csv"):
        insert("vendors", r)
    for r in load("purchase_orders.csv"):
        insert("purchase_orders", r)
    for r in load("po_lines.csv"):
        insert("po_lines", r)
    for r in load("receipts.csv"):
        insert("receipts", r)
    for h in json.loads((DATA / "history.json").read_text()):
        inv_id = insert("invoices", dict(vendor_id=h["vendor_id"], invoice_no=h["invoice_no"],
                                         invoice_no_norm=norm_invoice_no(h["invoice_no"]), invoice_date=h["invoice_date"],
                                         po_no=h["po_no"], subtotal=h["subtotal"], tax_total=h["tax"], total=h["total"],
                                         outcome="approved", outcome_title="Approved", decided_at=h["decided_at"],
                                         source="history", rules_version="v1", exported=1))
        for i, ln in enumerate(h["lines"], 1):
            insert("invoice_lines", dict(invoice_id=inv_id, line_no=i, qty=ln["qty"], unit_price=ln["unit_price"],
                                         amount=ln["amount"], po_no=h["po_no"], po_line=ln["po_line"], match_score=1.0))
    if os.environ.get("AP_HISTORY", "1") == "1":
        from . import history
        history.seed()


def buyer():
    return json.loads((DATA / "buyer.json").read_text())


# ---------- files (hosted: a container's disk is temporary, so keep a copy in the database) ----------

def save_file(path):
    if path and _use_pg():
        _pg("INSERT INTO files(name, data) VALUES(?, ?) ON CONFLICT (name) DO UPDATE SET data=EXCLUDED.data",
            (Path(path).name, Path(path).read_bytes()), "none")


def ensure_file(path):
    """Bring a stored file back onto this machine's disk if this copy of the app has not seen it yet."""
    if not path or not _use_pg() or Path(path).exists():
        return
    row = one("SELECT data FROM files WHERE name=?", (Path(path).name,))
    if row:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(bytes(row["data"]))


# ---------- Postgres (hosted) ----------

_WS_RE = re.compile(r"^[a-f0-9]{12}$")
_pool_obj = None
_pool_guard = threading.Lock()
_ws_guard = threading.Lock()
_ready = set()        # workspaces this process knows exist
_seed_cache = {}      # date -> seeded SQLite file, built with the exact same code as the local reset


def use_workspace(ws):
    """Set the visitor's workspace for this request. Anything that isn't a 12-character hex id uses the shared one."""
    return _workspace.set(ws if ws and _WS_RE.match(ws) else "default")


def reset_workspace_var(token):
    _workspace.reset(token)


def schema():
    return "ws_" + _workspace.get()  # validated above, so it is safe to put in SQL


def _pool():
    global _pool_obj
    with _pool_guard:
        if _pool_obj is None:
            from psycopg.rows import dict_row
            from psycopg.types.numeric import FloatLoader
            from psycopg_pool import ConnectionPool

            def configure(con):
                con.adapters.register_loader("numeric", FloatLoader)  # SUM() of integers comes back as float, as in SQLite

            url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("POSTGRES_URL_NON_POOLING") or DATABASE_URL
            _pool_obj = ConnectionPool(url, min_size=1, max_size=8, open=True, configure=configure,
                                       check=ConnectionPool.check_connection, max_idle=120,
                                       kwargs=dict(row_factory=dict_row, prepare_threshold=None, autocommit=False))
    return _pool_obj


def _real_text(v: float) -> str:
    """A float written the way SQLite writes one ('84960.0', '0.3'), so stored text and numbers match the local app."""
    s = "%.15g" % v
    return s if any(c in s for c in ".eEn") else s + ".0"


def _pg_val(v):
    # Numbers go as text and Postgres reads them by column type, the same loose typing SQLite uses.
    if v is None or isinstance(v, (str, bytes, bytearray, memoryview)):
        return v
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _real_text(v)
    return v


def _pg_params(params):
    return tuple(_pg_val(v) for v in params)


def _set_path(con):
    con.execute(f"SET LOCAL search_path TO {schema()}")


def _pg(sql, params, mode):
    ensure_workspace()
    with _pool().connection() as con, con.transaction():
        _set_path(con)
        cur = con.execute(sql.replace("%", "%%").replace("?", "%s"), _pg_params(params))
        if mode == "all":
            return cur.fetchall()
        if mode == "id":
            return next(iter(cur.fetchone().values()))
        if mode == "count":
            return cur.rowcount
        return None


def _pg_schema_sql():
    s = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    s = re.sub(r"\bINTEGER\b", "BIGINT", s)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)  # Postgres REAL is single precision and would round rupee amounts
    s += "\nCREATE TABLE files(name TEXT PRIMARY KEY, data BYTEA);"
    return [stmt.strip() for stmt in s.split(";") if stmt.strip()]


def _seed_file():
    key = datetime.now(IST).date().isoformat()
    path = _seed_cache.get(key)
    if path and os.path.exists(path):
        return path
    path = os.path.join(tempfile.gettempdir(), f"vouch_seed_{key}_{os.getpid()}.db")
    token = _sqlite_override.set(path)
    try:
        _create_and_seed()
    finally:
        _sqlite_override.reset(token)
    _seed_cache[key] = path
    return path


def _pg_seed(con, name):
    """Create the visitor's schema and copy in today's starting data, inside the caller's transaction."""
    src = sqlite3.connect(_seed_file())
    src.row_factory = sqlite3.Row
    try:
        con.execute(f"CREATE SCHEMA {name}")
        con.execute(f"SET LOCAL search_path TO {name}")
        for stmt in _pg_schema_sql():
            con.execute(stmt)
        for table in re.findall(r"CREATE TABLE (\w+)", SCHEMA):
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            with con.cursor().copy(f"COPY {table} ({','.join(rows[0].keys())}) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row([_pg_val(v) for v in r])
        for table, pk in _PK.items():
            con.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), COALESCE((SELECT MAX({pk}) FROM {table}), 0) + 1, false)")
    finally:
        src.close()


def ensure_workspace():
    name = schema()
    if name in _ready:
        return
    with _ws_guard:
        if name in _ready:
            return
        with _pool().connection() as con, con.transaction():
            con.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("ws:" + name,))
            if not con.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (name,)).fetchone():
                _pg_seed(con, name)
        _ready.add(name)


def _pg_reset_workspace():
    name = schema()
    with _ws_guard:
        with _pool().connection() as con, con.transaction():
            con.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("ws:" + name,))
            con.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")
            _pg_seed(con, name)
        _ready.add(name)
