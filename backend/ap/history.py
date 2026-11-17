"""Seeded operating history for the demo company: 60 days of invoices from vendors that the five demo
documents never touch, so the overview has a real period to summarise. Deterministic (fixed seed)."""
import random
from datetime import datetime, timedelta

from . import db
from .gst import make_gstin

VENDORS = [
    ("V005", "Saraswati Fasteners", "27", "small", 30, ["Hex bolt M10", "Spring washer 10mm", "Anchor fastener 12mm"]),
    ("V006", "Nilgiri Chemicals", "33", "", 45, ["Degreasing solvent 20L", "Industrial adhesive 5kg"]),
    ("V007", "Orbit Freight Movers", "07", "", 15, ["Freight Delhi to Pune", "Loading charges"]),
    ("V008", "Deccan Office Supplies", "29", "micro", 15, ["Printer paper A4", "Toner cartridge", "Files and folders"]),
    ("V009", "Rathi Tools", "06", "small", 30, ["Carbide drill bit set", "Torque wrench 3/8in"]),
    ("V010", "Aravali Castings", "08", "", 45, ["Grey iron casting GC-12", "Machined bracket housing"]),
    ("V011", "Pune Precision Parts", "27", "small", 30, ["CNC turned shaft", "Bushing 25mm"]),
    ("V012", "Coastal Courier Services", "27", "", 15, ["Express courier", "Document pickup"]),
    ("V013", "Lakshmi Lubricants", "33", "micro", 21, ["Hydraulic oil 68", "Grease EP2 18kg"]),
    ("V014", "Indus Safety Gear", "07", "", 30, ["Safety shoes", "Hard hat", "Nitrile gloves box"]),
    ("V015", "Zenith IT Solutions", "29", "", 30, ["Laptop rental", "Annual software support"]),
    ("V016", "Mehta Packaging Works", "09", "small", 21, ["Stretch film roll", "Corrugated box 5-ply"]),
]
PANS = ["AAFCS1023K", "AAGCN4411L", "AABCO7782M", "AAECD3390P", "AAKFR5521Q", "AAICA6610R", "AAJCP2207S", "AACCC9184T",
        "AAPFL3346U", "AAHCI8825V", "AAOCZ1478W", "AANFM6639X"]

# exception type -> (rule, title, severity, owner, weight, ask template)
HOLDS = [
    ("R13", "Unit prices within tolerance", "hold", "procurement", 30, "Unit price {p} against PO {po} on {item}. Confirm the new rate or ask for a credit note."),
    ("R14", "Billed quantity has been received", "hold", "stores", 22, "Billed {q} of {item}; receipts show {r}. Confirm what arrived."),
    ("R11", "PO found", "hold", "procurement", 15, "No PO quoted and no clear match among open POs. Link the right PO."),
    ("R17", "GST type fits the place of supply", "hold", "vendor", 12, "Inter-state supply billed with CGST + SGST. Revised invoice with IGST needed."),
    ("R15", "Billed so far stays within the PO", "hold", "procurement", 8, "Billing would exceed {po_no} by {x} units. Amend the PO or ask for a revised invoice."),
    ("R23", "Money and ID fields read with high confidence", "confirm", "ap", 8, "Total read with confidence 0.7{d} from a phone photo. Confirm the amount."),
    ("R02", "Required fields present", "hold", "vendor", 5, "Invoice number missing. Ask the vendor to reissue."),
]


def _amount(rng):
    return round(min(max(rng.lognormvariate(10.6, 0.9), 3000), 600000), -1)


def seed(today=None):
    rng = random.Random(42)
    today = today or datetime.now(db.IST).replace(microsecond=0)
    for (vid, name, st, msme, terms, _), pan in zip(VENDORS, PANS):
        db.insert("vendors", dict(vendor_id=vid, name=name, gstin=make_gstin(st, pan), state=st, msme=msme,
                                  bank_account=str(rng.randint(10**11, 10**12 - 1)), ifsc="HDFC000" + str(rng.randint(1000, 9999)),
                                  email_domains=name.split()[0].lower() + ".in", contact_email="accounts@" + name.split()[0].lower() + ".in",
                                  phone=f"+91 9{rng.randint(100000000, 999999999)}", payment_terms_days=terms, addr=""))
    weights = [h[4] for h in HOLDS]
    seq = {}
    for day in range(60, 0, -1):
        date = (today - timedelta(days=day)).replace(hour=9, minute=0, second=0)
        n = 0 if date.weekday() == 6 else rng.choice([2, 3, 4, 4, 5, 5, 6, 7]) if date.weekday() < 5 else rng.choice([0, 1, 2])
        for _ in range(n):
            vid, vname, st, msme, terms, items = rng.choice(VENDORS)
            seq[vid] = seq.get(vid, 100) + rng.randint(1, 4)
            inv_date = date - timedelta(days=rng.randint(0, 3))
            received = date + timedelta(hours=rng.randint(0, 8), minutes=rng.randint(0, 59))
            decided = received + timedelta(seconds=rng.randint(18, 75))
            total = _amount(rng)
            sub = round(total / 1.18, 2)
            r = rng.random()
            stp = 0.62 + 0.16 * (1 - day / 60)  # corrections feed back into rules and vendor templates, so fewer exceptions over time
            hold_end = stp + (1 - stp) * 0.66
            path = "auto" if r < stp else "hold" if r < hold_end else "signoff" if r < hold_end + 0.05 else "security" if r < hold_end + 0.065 else "duplicate"
            age_days = (today - decided).total_seconds() / 86400
            outcome, title, touched, resolved = "approved", "Approved", 0, None
            rule = None
            if path == "hold":
                rule = rng.choices(HOLDS, weights)[0]
                open_now = rng.random() < (0.5 if age_days < 7 else 0.08)
                if open_now:
                    outcome, title = "hold", "On hold: " + rule[1].lower()
                else:
                    resolved = decided + timedelta(hours=max(2, rng.expovariate(1 / 53)))
                    outcome, title, touched = ("approved", "Approved after review", 1) if rng.random() < 0.9 else ("rejected", "Rejected after review", 1)
            elif path == "signoff":
                if age_days < 1.5 and rng.random() < 0.6:
                    outcome, title = "signoff", "Needs sign-off"
                else:
                    resolved = decided + timedelta(hours=rng.uniform(1, 20))
                    outcome, title, touched = "approved", "Approved after sign-off", 1
            elif path == "security":
                if age_days < 5:
                    outcome, title = "security", "On hold, security: payment blocked"
                else:
                    resolved = decided + timedelta(hours=rng.uniform(3, 30))
                    outcome, title, touched = "rejected", "Rejected: bank change not confirmed by vendor", 1
            elif path == "duplicate":
                outcome, title = "rejected", "Rejected: duplicate"
            if resolved and resolved > today:
                resolved = None
                outcome, title, touched = ("hold", "On hold: " + rule[1].lower(), 0) if rule else ("signoff", "Needs sign-off", 0)
            due = inv_date + timedelta(days=min(terms, 45) if msme else terms)
            inv_id = db.insert("invoices", dict(
                vendor_id=vid, invoice_no=f"{vname[:2].upper()}/{inv_date:%y}/{seq[vid]:04d}", invoice_no_norm=f"H{vid}{seq[vid]}",
                invoice_date=inv_date.date().isoformat(), subtotal=sub, tax_total=round(total - sub, 2), total=total,
                outcome=outcome, outcome_title=title, decided_at=decided.isoformat(), received_at=received.isoformat(),
                resolved_at=resolved.isoformat() if resolved else None, touched=touched, due_date=due.date().isoformat(),
                paid=1 if outcome == "approved" and due < today else 0, exported=1 if outcome == "approved" else 0,
                rules_version="v1", extractor="history", source="history"))
            item = rng.choice(items)
            if rule:
                p = rng.randint(400, 9000)
                ask = rule[5].format(p=f"₹{p:,}", po=f"₹{round(p / rng.uniform(1.03, 1.09)):,}", item=item, q=rng.randint(20, 90),
                                     r=rng.randint(5, 19), po_no=f"PO-{rng.randint(3900, 4400)}", x=rng.randint(2, 15), d=rng.randint(0, 9))
                db.insert("rule_results", dict(invoice_id=inv_id, rule_id=rule[0], question=0, title=rule[1], outcome="fail" if rule[2] != "confirm" else "warn",
                                               severity=rule[2], owner=rule[3], detail=ask))
                db.insert("tasks", dict(invoice_id=inv_id, owner_role=rule[3], kind="message" if rule[3] != "ap" else "confirm", ask=ask,
                                        status="open" if outcome == "hold" else "done", created_at=decided.isoformat(),
                                        resolved_at=resolved.isoformat() if resolved else None))
            elif path == "security":
                ask = "Bank account on the invoice differs from the vendor master. Call the number on file before any payment."
                db.insert("rule_results", dict(invoice_id=inv_id, rule_id="R08", question=6, title="Bank details match the vendor master", outcome="fail",
                                               severity="security", owner="ap_manager", detail=ask))
                db.insert("tasks", dict(invoice_id=inv_id, owner_role="ap_manager", kind="call", ask=ask, status="open" if outcome == "security" else "done",
                                        created_at=decided.isoformat(), resolved_at=resolved.isoformat() if resolved else None))
            elif path == "duplicate":
                db.insert("rule_results", dict(invoice_id=inv_id, rule_id="R09", question=5, title="Not already processed", outcome="fail",
                                               severity="reject", owner="vendor", detail="Same invoice number as one already processed."))
            elif path == "signoff":
                db.insert("rule_results", dict(invoice_id=inv_id, rule_id="R22", question=0, title="Can be approved without sign-off", outcome="warn",
                                               severity="signoff", owner="ap_manager", detail=f"₹{total:,.0f} is above the automatic approval limit."))
                db.insert("tasks", dict(invoice_id=inv_id, owner_role="ap_manager", kind="signoff", ask=f"Sign off ₹{total:,.0f} for {vname}.",
                                        status="open" if outcome == "signoff" else "done", created_at=decided.isoformat(),
                                        resolved_at=resolved.isoformat() if resolved else None))
