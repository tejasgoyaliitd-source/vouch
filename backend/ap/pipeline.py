"""The 12-stage run. Each stage writes one event (hash-chained) so the live view and the audit log show
exactly what happened and why."""
import contextvars
import json
import os
import re
import threading
import time
import uuid
from datetime import timedelta

import httpx

from . import db, extract, models, privacy, rules
from .intake import kind_of, parse_eml, store

STAGES = ["Receive", "Route", "Read", "Classify", "Protect", "Extract", "Check extraction", "Identify vendor",
          "Match PO and receipt", "Apply rules", "Decide", "Act"]
DELAY = float(os.environ.get("STAGE_DELAY", "0.35"))  # pacing so people can follow the live view; 0 in tests


def ingest(data: bytes, filename: str, channel_hint=None) -> int:
    """Store the file (or the email and its first invoice-like attachment) and return a document id."""
    kind = kind_of(data, filename)
    meta = dict(channel=channel_hint or "upload", sender="", subject="", received_at=db.now(), message_id="", filename=filename)
    if kind == "eml":
        m = parse_eml(data)
        att = next(((n, b) for n, b in m["attachments"] if kind_of(b, n) in ("pdf", "jpg", "png", "docx")), None)
        meta.update(channel="email", sender=m["sender"], subject=m["subject"], received_at=m["received_at"], message_id=m["message_id"])
        if not att:
            sha, path = store(data, "eml")
            return db.insert("documents", dict(meta, sha256=sha, kind="eml", stored_path=path, created_at=db.now()))
        filename, data = att
        meta["filename"] = filename
        kind = kind_of(data, filename)
    sha, path = store(data, kind)
    return db.insert("documents", dict(meta, sha256=sha, kind=kind, stored_path=path, created_at=db.now()))


# Hosted (Vercel), work that continues after a response is sent may be paused, and the next request may reach another
# copy of the app. So there a run waits as "queued" and is started by the live view's stream, which stays open for the
# whole run. Locally a run starts straight away, as before.
IN_STREAM = os.environ.get("RUN_IN_STREAM") == "1"


def _thread(run_id):
    ctx = contextvars.copy_context()  # carries the visitor's workspace into the thread
    threading.Thread(target=ctx.run, args=(_run_safe, run_id), daemon=True).start()


def start(data: bytes, filename: str, channel_hint=None, background=True) -> str:
    doc_id = ingest(data, filename, channel_hint)
    run_id = "R-" + uuid.uuid4().hex[:6].upper()
    queued = background and IN_STREAM
    db.insert("runs", dict(run_id=run_id, doc_id=doc_id, status="queued" if queued else "running", started_at=db.now()))
    if not background:
        _run_safe(run_id)
    elif not queued:
        _thread(run_id)
    return run_id


def claim(run_id) -> bool:
    """Start a queued run. Only the first caller wins, so a run never executes twice."""
    if db.x_count("UPDATE runs SET status='running' WHERE run_id=? AND status='queued'", (run_id,)) != 1:
        return False
    _thread(run_id)
    return True


def run_sync(data, filename, channel_hint=None) -> str:
    return start(data, filename, channel_hint, background=False)


def _run_safe(run_id):
    try:
        run(run_id)
    except Exception as e:  # never approve on failure: record it and leave the invoice for a person
        db.add_event(run_id, None, 99, "Error", "fail", f"Run stopped: {type(e).__name__}: {e}. Nothing was approved.")
        db.x("UPDATE runs SET status='error', finished_at=? WHERE run_id=?", (db.now(), run_id))


def run(run_id):
    rec = db.one("SELECT * FROM runs WHERE run_id=?", (run_id,))
    doc = db.one("SELECT * FROM documents WHERE doc_id=?", (rec["doc_id"],))
    db.ensure_file(doc["stored_path"])  # hosted: the upload may have landed on another copy of the app
    buyer = db.buyer()
    inv_id = None
    n = 0

    def ev(status, summary, detail=None, stage_inc=True):
        nonlocal n
        if stage_inc:
            n += 1
        t0 = time.time()
        db.add_event(run_id, inv_id, n, STAGES[n - 1], status, summary, detail)
        time.sleep(max(0.0, DELAY - (time.time() - t0)))

    # 1 Receive
    seen = db.one("SELECT doc_id FROM documents WHERE sha256=? AND doc_id<>?", (doc["sha256"], doc["doc_id"]))
    src = f"Email from {doc['sender']}, subject \"{doc['subject']}\"." if doc["channel"] == "email" else "Uploaded from this desk."
    ev("ok", f"{src} Attachment {doc['filename']}. " + ("This exact file was seen before." if seen else "New file."),
       dict(message_id=doc["message_id"], sha256=doc["sha256"][:16], received_at=doc["received_at"]))

    # 2 Route + 3 Read
    t = time.time()
    r = extract.route_and_read(doc["stored_path"], doc["kind"])
    secs = time.time() - t
    preview = None
    if r["preview"] is not None:
        preview = doc["stored_path"].rsplit(".", 1)[0] + "_preview.png"
        img = r["preview"].copy()
        img.thumbnail((1100, 1600))
        img.save(preview)
        db.save_file(preview)
    db.x("UPDATE documents SET preview_path=? WHERE doc_id=?", (preview, doc["doc_id"]))
    db.x("UPDATE runs SET route=? WHERE run_id=?", (r["route"], run_id))
    ev("ok" if r["route"] != "unsupported" else "fail", r["reason"], dict(route=r["route"], cleanup=r["steps"]))
    if r["route"] == "unsupported":
        _finish(run_id, None, "rejected")
        return
    conf = round(sum(x["conf"] for x in r["rows"]) / max(len(r["rows"]), 1), 2)
    reader = {"text": "PDF text layer", "einvoice": "PDF text layer + signed QR", "scan": "Tesseract OCR", "photo": "Tesseract OCR", "docx": "Word reader"}[r["route"]]
    ev("ok" if conf >= 0.85 else "warn", f"{reader} read {len(r['rows'])} lines of text in {secs:.1f} s, average confidence {conf:.2f}."
       + (" Signed e-invoice QR decoded." if r["qr"] else ""), dict(rows=[x["text"] for x in r["rows"]][:60]))

    # 4 Classify
    text = "\n".join(x["text"] for x in r["rows"])
    is_inv = ("invoice" in text.lower() or "bill no" in text.lower()) and "total" in text.lower()
    db.x("UPDATE documents SET classified_as=? WHERE doc_id=?", ("tax invoice" if is_inv else "not an invoice", doc["doc_id"]))
    misleading = re.search(r"reminder|statement|payment due|bank|overdue", doc["subject"] or "", re.I)
    hint = f" (subject says \"{doc['subject']}\", but the attachment itself is an invoice)" if misleading and is_inv else ""
    ev("ok" if is_inv else "fail", ("Tax invoice" + hint) if is_inv else "Not an invoice: no invoice title or total found. Ignored.")
    if not is_inv:
        _finish(run_id, None, "rejected")
        return

    # 5 Protect
    masked, mapping = privacy.mask(text)
    kinds = sorted({k.split("_")[0].strip("[") for k in mapping})
    model_out, model_err = None, None
    try:
        model_out = models.read_invoice(masked)
    except (models.ModelError, httpx.HTTPError) as e:  # a failed model call never blocks or approves: the parser and the rules still run
        model_err = str(e)[:160]
    sent = (f"Sent the masked text to {model_out['provider'].title()} ({model_out['model']}), answered in {model_out['seconds']} s."
            if model_out else f"Model call failed ({model_err}); the local parser reads alone." if model_err
            else "No model connected, so nothing left this machine.")
    ev("ok" if not model_err else "warn", f"Masked {len(mapping)} sensitive values ({', '.join(kinds).lower() or 'none'}). {sent}",
       dict(masked_text=masked[:3000], masked_items=kinds, model=model_out and model_out["model"], tokens=model_out and model_out["usage"]))

    # 6 Extract
    F, lines = extract.parse_fields(r["rows"], buyer["gstin"], {"einvoice": "text layer", "text": "text layer", "scan": "OCR", "photo": "OCR", "docx": "Word"}[r["route"]])
    merge = None
    if model_out:
        F, lines, merge = extract.merge_model(F, lines, model_out["data"], text)
    qr_print = []
    if r["qr"]:
        for name, f in extract.qr_fields(r["qr"]).items():
            printed = F.get(name, {}).get("value")
            if name in ("invoice_no", "supplier_gstin", "total"):
                qr_print.append((name, f["value"], printed))
            f["bbox"] = F.get(name, {}).get("bbox")
            F[name] = f
    tax_type = "IGST" if "tax_igst" in F else "CGST+SGST" if "tax_cgst" in F else ""
    inv_date = rules.parse_date(F.get("invoice_date", {}).get("value"))
    inv_id = db.insert("invoices", dict(doc_id=doc["doc_id"], run_id=run_id, invoice_no=F.get("invoice_no", {}).get("value"),
                                        invoice_no_norm=db.norm_invoice_no(F.get("invoice_no", {}).get("value", "")),
                                        invoice_date=inv_date.isoformat() if inv_date else None, po_no=F.get("po_no", {}).get("value"),
                                        subtotal=F.get("subtotal", {}).get("value"), total=F.get("total", {}).get("value"),
                                        tax_total=sum(F[k]["value"] for k in ("tax_igst", "tax_cgst", "tax_sgst") if k in F),
                                        tax_type=tax_type, outcome="running", rules_version=rules.RULES_VERSION, received_at=rec["started_at"],
                                        extractor=f"{model_out['provider'].title()} and the local parser" if model_out else "local parser", source="pipeline"))
    db.x("UPDATE runs SET invoice_id=? WHERE run_id=?", (inv_id, run_id))
    for name, f in F.items():
        db.insert("fields", dict(invoice_id=inv_id, name=name, value=str(f["value"]), source=f["source"], confidence=f["confidence"],
                                 found_in_source=1, bbox=json.dumps(f.get("bbox"))))
    lowest = min([(f["confidence"], k) for k, f in F.items()] + [(l["confidence"], f"line {i}") for i, l in enumerate(lines, 1)], default=(1, ""))
    if merge:
        two = f"Two readers: {len(merge['agree'])} fields agree"
        two += f", {len(merge['disagree'])} differ ({', '.join(d['field'].replace('_', ' ') for d in merge['disagree'])})" if merge["disagree"] else ""
        two += f", {len(merge['not_on_page'])} model values not found on the page and dropped" if merge["not_on_page"] else ""
        two += f"; {merge['lines']}." if merge.get("lines") else "."
    else:
        two = f"Read {len(F)} fields and {len(lines)} line items with the local parser."
    ev("ok" if lowest[0] >= 0.85 else "warn", f"{two} Lowest confidence {lowest[0]:.2f} ({lowest[1].replace('_', ' ')}).",
       dict(fields={k: (v["value"], v["confidence"], v["source"]) for k, v in F.items()}, readers=merge))

    # 7 Check extraction
    results = rules.check_extraction(F, lines, qr_print)
    ev(_status(results), _summ(results, "Values found on the page, arithmetic and confidence"), _det(results))

    # 8 Identify vendor
    vendor, vr = rules.identify_vendor(F, doc)
    results += vr
    if vendor:
        db.x("UPDATE invoices SET vendor_id=? WHERE invoice_id=?", (vendor["vendor_id"], inv_id))
    ev(_status(vr), (f"{vendor['name']}. " if vendor else "Vendor not identified. ") + _summ(vr, "Vendor checks"), _det(vr))

    po_no, suggested, matched, due = None, None, [], None
    if vendor:
        # 9 Match PO and receipt
        po_no, suggested, matched, mr = rules.match_po(F, lines, vendor, inv_id)
        results += mr
        for i, (l, p, s) in enumerate(matched or [(l, None, 0) for l in lines], 1):
            db.insert("invoice_lines", dict(invoice_id=inv_id, line_no=i, description=l["description"], hsn=l["hsn"], qty=l["qty"],
                                            unit_price=l["unit_price"], amount=l["amount"], po_no=po_no if p else None,
                                            po_line=p["line_no"] if p else None, match_score=s))
        db.x("UPDATE invoices SET po_no=COALESCE(po_no, ?), po_suggested=? WHERE invoice_id=?", (po_no, suggested, inv_id))
        ev(_status(mr), (f"{po_no}{' (suggested)' if suggested else ''}. " if po_no else "") + _summ(mr, "PO and receipt checks"), _det(mr))
        # 10 Apply rules
        br, due = rules.business_rules(F, lines, vendor, matched, doc, inv_id, buyer)
        results += br
        ev(_status(br), _summ(br, "Duplicates, tax, dates, payment limits, approval limit"), _det(br))
    else:
        ev("warn", "Skipped: no vendor, so there is nothing to match against.")
        ev("warn", "Skipped: business rules need a known vendor.")

    for res in results:
        db.insert("rule_results", dict(invoice_id=inv_id, **res))

    # 11 Decide
    total = F.get("total", {}).get("value") or 0
    d = rules.decide(results, due, vendor, total)
    db.x("""UPDATE invoices SET outcome=?, outcome_title=?, outcome_reason=?, next_step=?, due_date=?, decided_at=?, exported=?
            WHERE invoice_id=?""", (d["outcome"], d["title"], d["reason"], d["next"], due.isoformat() if due else None, db.now(),
                                   1 if d["outcome"] == "approved" else 0, inv_id))
    ev({"approved": "ok", "signoff": "warn", "hold": "warn", "security": "fail", "rejected": "fail"}[d["outcome"]], d["title"],
       dict(reason=d["reason"], rules_version=rules.RULES_VERSION, decided_by="rules (code), not the model"))

    # 12 Act
    inv = db.one("SELECT * FROM invoices WHERE invoice_id=?", (inv_id,))
    tasks = rules.build_tasks(inv, results, d, vendor, doc)
    for tk in tasks:
        db.insert("tasks", dict(invoice_id=inv_id, status="open", created_at=db.now(), **tk))
    if d["outcome"] == "approved":
        act = d["next"]
    else:
        verb = {"message": "message drafted", "call": "call the vendor", "confirm": "confirm details", "signoff": "sign off"}
        act = "Assigned: " + "; ".join(f"{rules.OWNERS[t['owner_role']]}, {verb.get(t['kind'], t['kind'])}" for t in tasks) + "." if tasks else "No follow-up needed."
    ev("ok", act, dict(tasks=len(tasks)))
    _finish(run_id, inv_id, d["outcome"])


def _finish(run_id, inv_id, outcome):
    db.x("UPDATE runs SET status='done', finished_at=? WHERE run_id=?", (db.now(), run_id))


def _status(rs):
    if any(r["outcome"] == "fail" and r["severity"] in ("security", "reject") for r in rs):
        return "fail"
    if any(r["outcome"] == "fail" for r in rs):
        return "fail"
    if any(r["outcome"] == "warn" for r in rs):
        return "warn"
    return "ok"


def _summ(rs, label):
    checked = [r for r in rs if r["outcome"] != "info"]
    bad = [r for r in rs if r["outcome"] in ("fail", "warn")]
    if not bad:
        return f"{label}: all {len(checked)} passed."
    return " ".join(r["detail"] for r in bad)


def _det(rs):
    return [dict(rule=r["rule_id"], title=r["title"], outcome=r["outcome"], detail=r["detail"]) for r in rs]
