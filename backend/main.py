"""HTTP API. Run: .venv/Scripts/python -m uvicorn main:app --port 8000"""
import asyncio
import contextvars
import csv
import os
import io
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

import anyio
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ap import db, pipeline, rules

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
SAMPLE_INFO = {  # file: (case name, vendor, how it arrives, format, what the case is about, expected outcome)
    "happy_acme_einvoice.eml": ("Clean e-invoice", "Acme Supplies", "billing@acmesupplies.com", "E-invoice PDF", "Matches PO and receipts", "approved"),
    "e1_bank_change.eml": ("Changed bank details", "Acme Supplies", "billing@acme-supp1ies.com", "E-invoice PDF", "New account, lookalike sender", "security"),
    "e2_po_overbilled.eml": ("Billed past the PO", "Bharat Steel Traders", "billing@bharatsteel.co.in", "PDF", "Second invoice on one PO", "hold"),
    "e3_resent_scan.eml": ("Resent as a scan", "Northwind IT Services", "accounts@northwindit.in", "Scanned PDF", "Paid invoice sent again", "rejected"),
    "IMG_2041.jpg": ("Phone photo, no PO", "Kumar Packaging", "Uploaded from WhatsApp", "Photo", "No PO number, GST type", "hold"),
}
# Test files for evaluators (samples/test_pack, built by scripts/make_test_pack.py): file, what it tests, expected outcome
TEST_PACK = [
    ("01_clean_einvoice.pdf", "Signed e-invoice that matches the PO, goods receipts and price", "approved"),
    ("02_bank_details_changed.pdf", "Same vendor and amount, but a bank account the vendor master does not have", "security"),
    ("03_billed_past_po.pdf", "Second invoice on one PO that bills 10 units more than were ordered", "hold"),
    ("04_paid_invoice_resent_as_scan.pdf", "An invoice already paid, sent again as a scan with the number written differently", "rejected"),
    ("05_whatsapp_photo_no_po.jpg", "Tilted phone photo, no PO number, and the wrong type of GST charged", "hold"),
    ("06_vendor_not_onboarded.pdf", "A supplier nobody has onboarded, with no PO quoted", "hold"),
    ("07_known_vendor_new_layout.pdf", "A known vendor in a layout the samples do not use (Invoice #, Dated, Amount payable)", "approved"),
]
TEST_DIR = SAMPLES / "test_pack"
EXPECT_WORDS = {"approved": "approved", "security": "security hold", "hold": "on hold", "rejected": "rejected", "signoff": "needs sign-off"}
THUMBS = SAMPLES / "_thumbs"

app = FastAPI(title="AP Desk")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

if not db.PG and not db.DB_PATH.exists():
    db.reset()


class Workspace:
    """Hosted only: each browser carries a random id in the vouch_ws cookie, and its requests use that visitor's own
    copy of the demo data, created on the first request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not db.PG:
            return await self.app(scope, receive, send)
        cookies = dict(h for h in scope["headers"] if h[0] == b"cookie").get(b"cookie", b"").decode("latin-1")
        ws = next((c.split("=", 1)[1].strip() for c in cookies.split(";") if c.strip().startswith("vouch_ws=")), None)
        token = db.use_workspace(ws)
        try:
            if scope["path"].startswith("/api/"):
                ctx = contextvars.copy_context()
                await anyio.to_thread.run_sync(ctx.run, db.ensure_workspace)
            await self.app(scope, receive, send)
        finally:
            db.reset_workspace_var(token)


app.add_middleware(Workspace)


@app.get("/api/status")
def model_status():
    from ap import models
    # Vercel refuses request bodies over 4.5 MB before they reach the app, so the page warns before uploading.
    return dict(models.status(), max_upload_mb=4.5 if os.environ.get("VERCEL") else 15)


@app.post("/api/demo/reset")
def reset():
    db.reset()
    return {"ok": True}


@app.get("/api/samples")
def samples():
    from ap.intake import parse_eml
    out = []
    for f, (n, v, s, fm, a, x) in SAMPLE_INFO.items():
        p = SAMPLES / f
        if not p.exists():
            continue
        m = parse_eml(p.read_bytes()) if f.endswith(".eml") else None
        out.append(dict(file=f, name=n, vendor=v, source=s, format=fm, about=a, expect=x, channel="email" if m else "upload",
                        subject=m["subject"] if m else "Invoice photo shared on WhatsApp", received_at=m["received_at"] if m else "2026-11-14T11:34:00+05:30",
                        attachment=m["attachments"][0][0] if m else "IMG_2041.jpg", preview=(m["body"].strip().splitlines() or [""])[0] if m else "Photo shared on WhatsApp",
                        run_id=_sample_run(f)))
    return out


def _sample_run(name):
    """The run this inbox item already has, if any (matched on the invoice file's fingerprint)."""
    sha = pipeline.content_sha((SAMPLES / name).read_bytes(), name)
    row = db.one("""SELECT r.run_id FROM documents d JOIN runs r ON r.doc_id=d.doc_id
                    WHERE d.sha256=? AND r.status<>'error' ORDER BY r.started_at LIMIT 1""", (sha,))
    return row["run_id"] if row else None


_sample_lock = threading.Lock()


@app.get("/api/test-pack")
def test_pack():
    return [dict(file=f, tests=t, expect=x, kb=round((TEST_DIR / f).stat().st_size / 1024)) for f, t, x in TEST_PACK if (TEST_DIR / f).exists()]


@app.get("/api/test-pack.zip")
def test_pack_zip():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f, t, x in TEST_PACK:
            if (TEST_DIR / f).exists():
                z.write(TEST_DIR / f, f"vouch_test_files/{f}")
        notes = [f"{f}: {t}. Expected: {EXPECT_WORDS[x]}." for f, t, x in TEST_PACK]
        z.writestr("vouch_test_files/README.txt", "Upload any of these in the Vouch inbox. Expected results:\n\n" + "\n".join(notes) + "\n")
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/zip",
                             headers={"Content-Disposition": "attachment; filename=vouch_test_files.zip"})


@app.get("/api/test-pack/{name}")
def test_pack_file(name: str):
    if name not in {f for f, _, _ in TEST_PACK} or not (TEST_DIR / name).exists():
        raise HTTPException(404, "Unknown test file")
    return FileResponse(TEST_DIR / name, filename=name)


@app.get("/api/samples/{name}/thumb")
def sample_thumb(name: str):
    if name not in SAMPLE_INFO:
        raise HTTPException(404)
    THUMBS.mkdir(exist_ok=True)
    out = THUMBS / (name + ".png")
    if not out.exists():
        from PIL import Image
        from ap.extract import pdf_page_image
        from ap.intake import kind_of, parse_eml
        data, fname = (SAMPLES / name).read_bytes(), name
        if kind_of(data, name) == "eml":
            fname, data = parse_eml(data)["attachments"][0]
        tmp = THUMBS / ("_src_" + fname)
        tmp.write_bytes(data)
        img = pdf_page_image(str(tmp), 70) if kind_of(data, fname) == "pdf" else Image.open(tmp).convert("RGB")
        img = img.crop((0, 0, img.width, int(img.width * 0.62)))
        img.thumbnail((420, 420))
        img.save(out)
        tmp.unlink()
    return FileResponse(out, media_type="image/png")


@app.post("/api/runs/sample/{name}")
def run_sample(name: str):
    if name not in SAMPLE_INFO:
        raise HTTPException(404, "Unknown sample")
    with _sample_lock:  # an inbox email is processed once, even if two tabs (or Process all and a click) ask together
        return {"run_id": _sample_run(name) or pipeline.start((SAMPLES / name).read_bytes(), name)}


@app.post("/api/inbox/upload")
async def inbox_upload(file: UploadFile = File(...)):
    """A file arrives in the inbox. It is stored but not processed; the Inbox decides when (by hand or on arrival)."""
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (15 MB max)")
    return {"doc_id": pipeline.ingest(data, file.filename or "upload")}


@app.post("/api/runs/document/{doc_id}")
def run_document(doc_id: int):
    if not db.one("SELECT doc_id FROM documents WHERE doc_id=?", (doc_id,)):
        raise HTTPException(404, "Unknown document")
    return {"run_id": pipeline.start_doc(doc_id)}


@app.post("/api/runs/upload")
async def run_upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (15 MB max)")
    return {"run_id": pipeline.start(data, file.filename or "upload")}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = db.one("SELECT * FROM runs WHERE run_id=?", (run_id,))
    if not run:
        raise HTTPException(404)
    run["document"] = db.one("SELECT doc_id, channel, sender, subject, received_at, filename, kind, classified_as FROM documents WHERE doc_id=?", (run["doc_id"],))
    run["invoice"] = invoice_detail(run["invoice_id"]) if run["invoice_id"] else None
    return run


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str):
    async def stream():
        await asyncio.to_thread(contextvars.copy_context().run, pipeline.claim, run_id)  # hosted: the run starts here
        last = 0
        for _ in range(1200):  # up to ~4 minutes
            evs = db.q("SELECT event_id, stage_no, stage, status, summary, detail, ts FROM events WHERE run_id=? AND event_id>? ORDER BY event_id", (run_id, last))
            for e in evs:
                last = e["event_id"]
                e["detail"] = json.loads(e["detail"]) if e["detail"] else None
                yield f"data: {json.dumps(e)}\n\n"
            run = db.one("SELECT status FROM runs WHERE run_id=?", (run_id,))
            if run and run["status"] not in ("running", "queued") and not evs:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.2)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/documents")
def documents():
    docs = db.q("""SELECT d.doc_id, d.channel, d.sender, d.subject, d.received_at, d.filename, d.kind, d.classified_as,
                   r.run_id, r.status run_status, i.invoice_id, i.outcome, i.outcome_title FROM documents d LEFT JOIN runs r ON r.doc_id=d.doc_id
                   LEFT JOIN invoices i ON i.invoice_id=r.invoice_id ORDER BY d.doc_id DESC""")
    # each run's stage results (1 to 12) so the list can show where a document stopped, without opening it
    stages = {}
    for e in db.q("SELECT run_id, stage_no, status, summary FROM events WHERE run_id IS NOT NULL AND stage_no BETWEEN 1 AND 12 ORDER BY event_id"):
        skipped = e["status"] == "warn" and (e["summary"] or "").startswith("Skipped")  # not needed, not a problem
        stages.setdefault(e["run_id"], {})[e["stage_no"]] = "skip" if skipped else e["status"]
    for d in docs:
        d["stages"] = [stages.get(d["run_id"], {}).get(n) for n in range(1, 13)]
    return docs


@app.get("/api/documents/{doc_id}/preview")
def preview(doc_id: int):
    d = db.one("SELECT preview_path FROM documents WHERE doc_id=?", (doc_id,))
    if not d or not d["preview_path"]:
        raise HTTPException(404)
    db.ensure_file(d["preview_path"])
    return FileResponse(d["preview_path"], media_type="image/png")


def invoice_detail(invoice_id):
    inv = db.one("""SELECT i.*, v.name vendor_name, v.gstin vendor_gstin, v.msme, v.phone vendor_phone FROM invoices i
                    LEFT JOIN vendors v ON v.vendor_id=i.vendor_id WHERE i.invoice_id=?""", (invoice_id,))
    if not inv:
        return None
    inv["fields"] = db.q("SELECT name, value, source, confidence, bbox FROM fields WHERE invoice_id=?", (invoice_id,))
    for f in inv["fields"]:
        f["bbox"] = json.loads(f["bbox"]) if f["bbox"] else None
    lines = db.q("SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY line_no", (invoice_id,))
    for l in lines:
        if l["po_no"] and l["po_line"]:
            p = db.one("SELECT * FROM po_lines WHERE po_no=? AND line_no=?", (l["po_no"], l["po_line"]))
            l.update(po_description=p["description"], po_qty=p["qty"], po_price=p["unit_price"],
                     received=rules.received(l["po_no"], l["po_line"]), billed_before=rules.billed_before(l["po_no"], l["po_line"], invoice_id))
    inv["lines"] = lines
    inv["rules"] = db.q("SELECT * FROM rule_results WHERE invoice_id=? ORDER BY question, rule_id", (invoice_id,))
    inv["tasks"] = db.q("SELECT * FROM tasks WHERE invoice_id=?", (invoice_id,))
    inv["events"] = db.q("SELECT ts, stage, status, summary FROM events WHERE invoice_id=? OR run_id=? ORDER BY event_id", (invoice_id, inv["run_id"]))
    inv["document"] = db.one("SELECT * FROM documents WHERE doc_id=?", (inv["doc_id"],)) if inv["doc_id"] else None
    return inv


@app.get("/api/invoices")
def invoices():
    return db.q("""SELECT i.invoice_id, i.invoice_no, i.invoice_date, i.total, i.outcome, i.outcome_title, i.due_date, i.decided_at,
                   i.received_at, i.resolved_at, i.touched, i.paid, i.source, i.run_id, v.name vendor_name, v.msme
                   FROM invoices i LEFT JOIN vendors v ON v.vendor_id=i.vendor_id WHERE i.outcome<>'running'
                   ORDER BY COALESCE(i.received_at, i.decided_at) DESC""")


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int):
    inv = invoice_detail(invoice_id)
    if not inv:
        raise HTTPException(404)
    return inv


@app.get("/api/queue")
def queue():
    rows = db.q("""SELECT t.*, i.invoice_no, i.total, i.outcome, i.outcome_title, i.due_date, i.decided_at, i.source, v.name vendor_name, v.msme
                   FROM tasks t JOIN invoices i ON i.invoice_id=t.invoice_id LEFT JOIN vendors v ON v.vendor_id=i.vendor_id
                   WHERE t.status IN ('open','sent') AND i.outcome<>'rejected' ORDER BY t.created_at DESC""")
    for r in rows:
        r["type"] = next((rules.PROBLEM.get(x["rule_id"], x["title"]) for x in db.q(
            "SELECT rule_id, title FROM rule_results WHERE invoice_id=? AND outcome IN ('fail','warn') AND owner=?", (r["invoice_id"], r["owner_role"]))),
            {"call": "bank details changed", "signoff": "sign-off"}.get(r["kind"], "review"))
    return rows


@app.post("/api/tasks/{task_id}/sent")
def mark_sent(task_id: int):
    t = db.one("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    if not t:
        raise HTTPException(404)
    db.x("UPDATE tasks SET status='sent' WHERE task_id=?", (task_id,))
    db.add_event(None, t["invoice_id"], 0, "Follow-up", "ok", f"Message to {rules.OWNERS[t['owner_role']]} marked as sent by the clerk")
    return {"ok": True}


def _t(s):
    return datetime.fromisoformat(s) if s else None


def _bucket(i):
    if i["outcome"] == "approved":
        return "straight" if not i["touched"] else "reviewed"
    return "rejected" if i["outcome"] == "rejected" else "open"


@app.post("/api/tasks/{task_id}/resolve")
async def resolve(task_id: int, request: Request):
    body = await request.json()
    action, who = body.get("action"), body.get("by", "AP desk")
    t = db.one("SELECT * FROM tasks WHERE task_id=?", (task_id,))
    if not t or action not in ("approve", "reject"):
        raise HTTPException(400, "Unknown task or action")
    now = db.now()
    if action == "approve":
        # Approving one task only closes that task. The invoice is approved once every open question is answered,
        # so confirming the PO cannot approve an invoice whose GST the vendor still has to fix.
        db.x("UPDATE tasks SET status='done', resolved_at=? WHERE task_id=?", (now, task_id))
        left = db.q("SELECT owner_role FROM tasks WHERE invoice_id=? AND status IN ('open','sent')", (t["invoice_id"],))
        if left:
            names = ", ".join(sorted({rules.OWNERS[x["owner_role"]] for x in left}))
            db.x("UPDATE invoices SET touched=1, next_step=? WHERE invoice_id=?", (f"Waiting on: {names}.", t["invoice_id"]))
            db.add_event(None, t["invoice_id"], 0, "Review", "ok", f"{who} closed one question. Still waiting on {names}, so the invoice stays on hold.")
            return {"ok": True, "approved": False, "waiting_on": names}
    db.x("UPDATE tasks SET status='done', resolved_at=? WHERE invoice_id=? AND status IN ('open','sent')", (now, t["invoice_id"]))
    title = "Approved after review" if action == "approve" else "Rejected after review"
    db.x("UPDATE invoices SET outcome=?, outcome_title=?, resolved_at=?, touched=1, exported=? WHERE invoice_id=?",
         ("approved" if action == "approve" else "rejected", title, now, 1 if action == "approve" else 0, t["invoice_id"]))
    db.add_event(None, t["invoice_id"], 0, "Review", "ok" if action == "approve" else "fail", f"{title} by {who}.")
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(days: int = 30):
    now = datetime.now(db.IST)
    start, prev_start = now - timedelta(days=days), now - timedelta(days=2 * days)
    invs = db.q("""SELECT i.*, v.name vendor_name, v.msme FROM invoices i LEFT JOIN vendors v ON v.vendor_id=i.vendor_id
                   WHERE i.received_at IS NOT NULL AND i.outcome<>'running'""")
    cur = [i for i in invs if _t(i["received_at"]) >= start]
    prev = [i for i in invs if prev_start <= _t(i["received_at"]) < start]

    def kpis(rows):
        n = len(rows)
        straight = sum(1 for i in rows if _bucket(i) == "straight")
        human = sorted(((_t(i["resolved_at"]) - _t(i["received_at"])).total_seconds() / 3600 for i in rows if i["resolved_at"]))
        auto = sorted(((_t(i["decided_at"]) - _t(i["received_at"])).total_seconds() for i in rows if _bucket(i) == "straight"))
        protected = sum(i["total"] or 0 for i in rows if i["outcome"] in ("rejected", "security") and not i["touched"] or "bank change" in (i["outcome_title"] or ""))
        return dict(processed=n, value=sum(i["total"] or 0 for i in rows), stp=round(100 * straight / n, 1) if n else 0,
                    human_hours=round(human[len(human) // 2], 1) if human else None, auto_seconds=round(auto[len(auto) // 2]) if auto else None,
                    protected=protected)

    k, kp = kpis(cur), kpis(prev)
    open_inv = [i for i in invs if i["outcome"] in ("hold", "security", "signoff")]
    open_tasks = db.q("SELECT t.*, i.total FROM tasks t JOIN invoices i ON i.invoice_id=t.invoice_id WHERE t.status IN ('open','sent')")
    k.update(open_exceptions=len(open_inv), at_risk=sum(i["total"] or 0 for i in open_inv),
             stale=sum(1 for t in open_tasks if (now - _t(t["created_at"])).days >= 3))

    daily = []
    for d in range(days - 1, -1, -1):
        day = (now - timedelta(days=d)).date()
        rows = [i for i in cur if _t(i["received_at"]).date() == day]
        daily.append(dict(date=day.isoformat(), **{b: sum(1 for i in rows if _bucket(i) == b) for b in ("straight", "reviewed", "open", "rejected")}))

    edges = [(0, 2, "0 to 2 days"), (3, 7, "3 to 7 days"), (8, 15, "8 to 15 days"), (16, 10**6, "Over 15 days")]
    ageing = []
    for role in ("procurement", "stores", "vendor", "ap", "ap_manager"):
        ts = [t for t in open_tasks if t["owner_role"] == role]
        ageing.append(dict(owner=rules.OWNERS[role].split(" (")[0], total=len(ts),
                           buckets=[sum(1 for t in ts if lo <= (now - _t(t["created_at"])).days <= hi) for lo, hi, _ in edges]))

    ids = {i["invoice_id"] for i in cur}
    by_type = {}
    for r in db.q("SELECT r.*, i.total FROM rule_results r JOIN invoices i ON i.invoice_id=r.invoice_id WHERE r.outcome IN ('fail','warn')"):
        if r["invoice_id"] in ids and r["rule_id"] not in ("R22",):
            label = {"R07": "sender not on file", "R08": "bank details changed", "R09": "duplicate"}.get(r["rule_id"], rules.PROBLEM.get(r["rule_id"], r["title"].lower()))
            e = by_type.setdefault(label, dict(type=label[0].upper() + label[1:], n=0, value=0))
            e["n"] += 1
            e["value"] += r["total"] or 0
    by_type = sorted(by_type.values(), key=lambda e: -e["n"])

    unpaid = [i for i in invs if i["outcome"] == "approved" and not i["paid"] and i["due_date"]]
    weeks = []
    for w in range(5):
        lo, hi = now.date() + timedelta(days=7 * w), now.date() + timedelta(days=7 * w + 6)
        rows = [i for i in unpaid if lo <= datetime.fromisoformat(i["due_date"]).date() <= hi] if w < 4 else []
        if w < 4:
            weeks.append(dict(label=f"{lo:%d %b}", msme=sum(i["total"] for i in rows if i["msme"]), other=sum(i["total"] for i in rows if not i["msme"]),
                              count=len(rows)))
    overdue = [i for i in unpaid if datetime.fromisoformat(i["due_date"]).date() < now.date()]

    vend = {}
    for i in cur:
        v = vend.setdefault(i["vendor_name"] or "Unknown", dict(vendor=i["vendor_name"] or "Unknown", n=0, exceptions=0, open=0, open_value=0))
        v["n"] += 1
        if _bucket(i) != "straight":
            v["exceptions"] += 1
        if i["outcome"] in ("hold", "security", "signoff"):
            v["open"] += 1
            v["open_value"] += i["total"] or 0
    vendors = sorted([v for v in vend.values() if v["n"] >= 3], key=lambda v: (-v["exceptions"] / v["n"], -v["open"]))[:6]
    for v in vendors:
        v["rate"] = round(100 * v["exceptions"] / v["n"])

    return dict(days=days, kpi=k, prev=kp, daily=daily, ageing=ageing, age_labels=[e[2] for e in edges], by_type=by_type,
                payables=weeks, overdue=dict(n=len(overdue), value=sum(i["total"] for i in overdue)), vendors=vendors,
                audit_chain_ok=db.verify_chain())


@app.get("/api/records")
def records():
    pos = db.q("SELECT p.*, v.name vendor_name FROM purchase_orders p JOIN vendors v ON v.vendor_id=p.vendor_id ORDER BY p.po_no")
    for p in pos:
        p["lines"] = db.q("SELECT * FROM po_lines WHERE po_no=? ORDER BY line_no", (p["po_no"],))
        for l in p["lines"]:
            l["received"] = rules.received(p["po_no"], l["line_no"])
            l["billed"] = rules.billed_before(p["po_no"], l["line_no"], -1)
    return dict(vendors=db.q("SELECT * FROM vendors"), pos=pos, settings=rules.SETTINGS, rules_version=rules.RULES_VERSION)


@app.get("/api/audit")
def audit():
    return dict(chain_ok=db.verify_chain(), events=db.q("""SELECT e.event_id, e.ts, e.run_id, e.stage, e.status, e.summary, e.hash,
                i.invoice_no FROM events e LEFT JOIN invoices i ON i.invoice_id=e.invoice_id ORDER BY e.event_id DESC LIMIT 300"""))


@app.get("/api/export/erp.csv", response_class=PlainTextResponse)
def erp_export():
    rows = db.q("""SELECT i.invoice_no, i.invoice_date, v.name, v.gstin, i.po_no, i.subtotal, i.tax_total, i.total, i.due_date
                   FROM invoices i JOIN vendors v ON v.vendor_id=i.vendor_id WHERE i.outcome='approved' AND i.source='pipeline'""")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Bill Number", "Bill Date", "Vendor Name", "Vendor GSTIN", "PO Number", "Sub Total", "Tax Total", "Total", "Due Date"])
    for r in rows:
        w.writerow(r.values())
    return PlainTextResponse(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=erp_bills.csv"})


if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
