"""Checks and the decision. Everything here is deterministic code: same input, same output.
Each check maps to one of the eight questions AP answers before paying (see design doc, section 2)."""
from datetime import date, datetime, timedelta

from rapidfuzz import fuzz

from . import db
from .gst import is_valid_gstin, pan_of, state_of, STATES

RULES_VERSION = "v1"
SETTINGS = dict(price_tol_pct=2.0, price_tol_abs=500.0, rounding=1.0, auto_approve_cap=100000.0, max_age_days=180,
                msme_max_days=45, min_conf=0.85, line_match_min=70)
OWNERS = {"vendor": "Vendor", "procurement": "Procurement (R. Mehta)", "stores": "Stores (S. Iyer)",
          "ap": "You (AP desk)", "ap_manager": "AP manager (N. Kapoor)"}
PROBLEM = {"R07": "sender not on file", "R08": "bank details changed", "R09": "duplicate", "R19": "QR does not match print",
           "R22": "sign-off", "R02": "missing fields", "R03": "totals don't add up", "R04": "date looks wrong", "R05": "vendor not onboarded",
           "R06": "invalid GSTIN", "R10": "possible duplicate", "R11": "PO to confirm", "R12": "PO closed or another vendor's",
           "R13": "price outside tolerance", "R14": "billed more than received", "R15": "billed beyond the PO",
           "R16": "line not on the PO", "R17": "wrong GST type", "R18": "wrong GST rate", "R23": "fields to confirm"}
INTERNAL_EMAIL = {"procurement": "procurement@sharmacomponents.in", "stores": "stores@sharmacomponents.in"}


def inr(x):
    s = f"{float(x):.2f}"
    whole, dec = s.split(".")
    neg = whole.startswith("-")
    whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        whole = f"{head},{tail}"
    out = f"₹{whole}" if dec == "00" else f"₹{whole}.{dec}"
    return "-" + out if neg else out


def parse_date(s):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def R(rule_id, q, title, outcome, severity, owner, detail):
    return dict(rule_id=rule_id, question=q, title=title, outcome=outcome, severity=severity, owner=owner, detail=detail)


def val(F, name):
    return F[name]["value"] if name in F else None


# ---------- stage: check extraction ----------

def check_extraction(F, lines, qr_print):
    out = []
    missing = [n for n, label in [("invoice_no", "invoice number"), ("invoice_date", "invoice date"), ("total", "total"),
                                  ("supplier_gstin", "supplier GSTIN")] if n not in F]
    out.append(R("R02", 4, "Required fields present", "fail" if missing else "pass", "hold", "vendor",
                 f"Missing: {', '.join(missing)}." if missing else "Invoice number, date, total and supplier GSTIN all found."))
    taxes = sum(F[k]["value"] for k in ("tax_igst", "tax_cgst", "tax_sgst") if k in F)
    sub, total, lsum = val(F, "subtotal"), val(F, "total"), sum(l["amount"] for l in lines)
    problems = []
    if lines and sub is not None and abs(lsum - sub) > SETTINGS["rounding"]:
        problems.append(f"lines add up to {inr(lsum)} but subtotal says {inr(sub)}")
    if sub is not None and total is not None and abs(sub + taxes - total) > SETTINGS["rounding"]:
        problems.append(f"subtotal {inr(sub)} + tax {inr(taxes)} = {inr(sub + taxes)}, but total says {inr(total)}")
    problems += [f"line {i}: {l['qty']:g} x {inr(l['unit_price'])} is not {inr(l['amount'])}" for i, l in enumerate(lines, 1) if not l["consistent"]]
    out.append(R("R03", 4, "Arithmetic adds up", "fail" if problems else "pass", "hold", "vendor",
                 "; ".join(problems).capitalize() + "." if problems else f"Lines {inr(lsum)} + tax {inr(taxes)} = total {inr(total or 0)}."))
    if qr_print:
        diffs = [f"{k}: QR {a} vs printed {b}" for k, a, b in qr_print if a and b and str(a) != str(b)]
        out.append(R("R19", 1, "E-invoice QR matches the printed invoice", "fail" if diffs else "pass", "security", "ap_manager",
                     "; ".join(diffs) + ". The PDF may have been edited." if diffs else "Invoice number, GSTINs and total in the signed QR match the print."))
    low = [(n, F[n]["confidence"]) for n in ("invoice_no", "total", "subtotal", "tax_igst", "tax_cgst", "tax_sgst", "supplier_gstin", "bank_account")
           if n in F and F[n]["confidence"] < SETTINGS["min_conf"]]
    low += [(f"line {i} quantity/amount", l["confidence"]) for i, l in enumerate(lines, 1) if l["confidence"] < SETTINGS["min_conf"]]
    out.append(R("R23", 4, "Money and ID fields read with high confidence", "warn" if low else "pass", "confirm", "ap",
                 "Confirm: " + ", ".join(f"{n} ({c:.2f})" for n, c in low) + "." if low else f"All key fields at or above {SETTINGS['min_conf']}."))
    return out


# ---------- stage: identify vendor ----------

def identify_vendor(F, doc):
    out, g = [], val(F, "supplier_gstin")
    vendor = db.one("SELECT * FROM vendors WHERE gstin=?", (g,)) if g else None
    if vendor:
        out.append(R("R05", 1, "Vendor is in the vendor master", "pass", "hold", "ap", f"GSTIN {g} matches {vendor['name']} exactly."))
    else:
        same_pan = db.one("SELECT * FROM vendors WHERE substr(gstin,3,10)=?", (pan_of(g),)) if g else None
        if same_pan:
            out.append(R("R05", 1, "Vendor is in the vendor master", "fail", "hold", "ap",
                         f"GSTIN {g} is new, but its PAN matches {same_pan['name']}: same company, registered in "
                         f"{STATES.get(state_of(g), 'another state')}. Add this registration to the vendor master; do not create a new vendor."))
        else:
            po = db.one("SELECT * FROM purchase_orders WHERE po_no=?", (val(F, "po_no"),)) if val(F, "po_no") else None
            out.append(R("R05", 1, "Vendor is in the vendor master", "fail", "hold", "procurement" if po else "ap",
                         f"No vendor with GSTIN {g or '(not found)'}. " + (f"The invoice quotes {po['po_no']}, so finish onboarding before it can be paid. Bank details will come from onboarding, never from this invoice."
                                                                         if po else "No PO quoted either. Find out who ordered this; if nobody claims it, reject it.")))
        return None, out
    out.append(R("R06", 1, "GSTIN is valid", "pass" if is_valid_gstin(g) else "fail", "hold", "vendor",
                 "Format and checksum valid." if is_valid_gstin(g) else f"{g} fails the GSTIN checksum."))
    if doc["channel"] == "email":
        domain = doc["sender"].split("@")[-1]
        allowed = [d.strip() for d in vendor["email_domains"].split(",")]
        if domain in allowed:
            out.append(R("R07", 1, "Sender domain is on file", "pass", "security", "ap_manager", f"{domain} is on file for {vendor['name']}."))
        else:
            near = max(allowed, key=lambda a: fuzz.ratio(a, domain))
            look = fuzz.ratio(near, domain) >= 80
            out.append(R("R07", 1, "Sender domain is on file", "fail", "security", "ap_manager",
                         f"Sent from {domain}, which is not on file ({', '.join(allowed)})." + (f" It looks like {near}: a lookalike domain." if look else "")))
    else:
        out.append(R("R07", 1, "Sender domain is on file", "info", "security", "ap_manager", "Uploaded by a user, so there is no sender to check."))
    acct = val(F, "bank_account")
    if acct and acct != vendor["bank_account"]:
        out.append(R("R08", 6, "Bank details match the vendor master", "fail", "security", "ap_manager",
                     f"Invoice asks for payment to account ending {acct[-4:]}; vendor master has {vendor['bank_account'][-4:]}."))
    else:
        out.append(R("R08", 6, "Bank details match the vendor master", "pass" if acct else "info", "security", "ap_manager",
                     f"Account ending {acct[-4:]} matches." if acct else "No bank details on the invoice; payment goes to the account on file."))
    return vendor, out


# ---------- stage: match PO and receipt ----------

def billed_before(po_no, line_no, exclude_invoice):
    r = db.one("""SELECT COALESCE(SUM(l.qty),0) q FROM invoice_lines l JOIN invoices i ON i.invoice_id=l.invoice_id
                  WHERE l.po_no=? AND l.po_line=? AND i.outcome IN ('approved','signoff') AND i.invoice_id<>?""", (po_no, line_no, exclude_invoice))
    return r["q"]


def received(po_no, line_no):
    return db.one("SELECT COALESCE(SUM(qty_received),0) q FROM receipts WHERE po_no=? AND line_no=?", (po_no, line_no))["q"]


def match_lines(lines, po_no):
    po_lines = db.q("SELECT * FROM po_lines WHERE po_no=?", (po_no,))
    matched = []
    for l in lines:
        best = max(po_lines, key=lambda p: fuzz.token_set_ratio(l["description"], p["description"]), default=None)
        score = fuzz.token_set_ratio(l["description"], best["description"]) if best else 0
        matched.append((l, best if score >= SETTINGS["line_match_min"] else None, round(score / 100, 2)))
    return matched


def find_po_candidates(vendor_id, lines, exclude_invoice):
    cands = []
    for po in db.q("SELECT * FROM purchase_orders WHERE vendor_id=? AND status='open'", (vendor_id,)):
        m = match_lines(lines, po["po_no"])
        if not m:
            continue
        parts = []
        for l, p, s in m:
            if not p:
                parts.append(0)
                continue
            price_ok = abs(l["unit_price"] - p["unit_price"]) <= max(p["unit_price"] * SETTINGS["price_tol_pct"] / 100, 0.01)
            fits = billed_before(po["po_no"], p["line_no"], exclude_invoice) + l["qty"] <= p["qty"]
            parts.append(s * (1 if price_ok else 0.7) * (1 if fits else 0.5))
        cands.append((po["po_no"], round(sum(parts) / len(parts), 2)))
    return sorted(cands, key=lambda c: -c[1])


def match_po(F, lines, vendor, invoice_id):
    out, po_no, suggested = [], val(F, "po_no"), None
    if po_no:
        po = db.one("SELECT * FROM purchase_orders WHERE po_no=?", (po_no,))
        if not po:
            out.append(R("R11", 2, "PO found", "fail", "hold", "procurement", f"The invoice quotes {po_no}, which does not exist."))
            return None, None, [], out
        out.append(R("R11", 2, "PO found", "pass", "hold", "procurement", f"{po_no} quoted on the invoice."))
    else:
        cands = find_po_candidates(vendor["vendor_id"], lines, invoice_id)
        listing = ", ".join(f"{p} ({s:.2f})" for p, s in cands) or "none"
        if cands and cands[0][1] >= 0.8 and (len(cands) == 1 or cands[0][1] - cands[1][1] >= 0.2):
            po_no = suggested = cands[0][0]
            out.append(R("R11", 2, "PO found", "warn", "confirm", "ap",
                         f"No PO quoted. Candidates by vendor, items and balance: {listing}. Suggested {po_no}; confirm it."))
        else:
            out.append(R("R11", 2, "PO found", "fail", "hold", "procurement", f"No PO quoted and no clear candidate ({listing})."))
            return None, None, [], out
        po = db.one("SELECT * FROM purchase_orders WHERE po_no=?", (po_no,))
    ok = po["vendor_id"] == vendor["vendor_id"] and po["status"] == "open"
    out.append(R("R12", 2, "PO is open and belongs to this vendor", "pass" if ok else "fail", "hold", "procurement",
                 f"{po_no} is open and raised on {vendor['name']}." if ok else f"{po_no} is {po['status']} or raised on another vendor."))
    matched = match_lines(lines, po_no)
    unmatched = [l for l, p, _ in matched if not p]
    out.append(R("R16", 2, "Every invoice line is on the PO", "fail" if unmatched else "pass", "hold", "procurement",
                 "Not on the PO: " + "; ".join(l["description"] for l in unmatched) + "." if unmatched else f"{len(matched)} of {len(matched)} lines matched to {po_no}."))
    price, recv, bal = [], [], []
    for l, p, s in matched:
        if not p:
            continue
        tol = min(p["unit_price"] * SETTINGS["price_tol_pct"] / 100, SETTINGS["price_tol_abs"])
        if abs(l["unit_price"] - p["unit_price"]) > tol:
            price.append(f"{p['description']}: billed {inr(l['unit_price'])}, PO {inr(p['unit_price'])} (tolerance {inr(tol)})")
        before, got = billed_before(po_no, p["line_no"], invoice_id), received(po_no, p["line_no"])
        if before + l["qty"] > got:
            recv.append(f"{p['description']}: billed {before:g} before + {l['qty']:g} now = {before + l['qty']:g}, received {got:g}")
        if before + l["qty"] > p["qty"]:
            bal.append(f"{p['description']}: {p['qty']:g} ordered, {before:g} billed before, this invoice {l['qty']:g}, "
                       f"so {before + l['qty'] - p['qty']:g} beyond the PO")
    out.append(R("R13", 4, "Unit prices within tolerance", "fail" if price else "pass", "hold", "procurement",
                 "; ".join(price) + "." if price else "All unit prices match the PO."))
    out.append(R("R14", 3, "Billed quantity has been received", "fail" if recv else "pass", "hold", "stores",
                 "; ".join(recv) + "." if recv else "Everything billed has been received (goods receipts)."))
    out.append(R("R15", 2, "Billed so far stays within the PO", "fail" if bal else "pass", "hold", "procurement",
                 "; ".join(bal) + "." if bal else "Within the remaining PO balance."))
    return po_no, suggested, matched, out


# ---------- stage: business rules ----------

def business_rules(F, lines, vendor, matched, doc, invoice_id, buyer):
    out, no_norm = [], db.norm_invoice_no(val(F, "invoice_no") or "")
    dup = db.one("""SELECT * FROM invoices WHERE vendor_id=? AND invoice_no_norm=? AND invoice_id<>? AND outcome<>'rejected'
                    ORDER BY invoice_id LIMIT 1""", (vendor["vendor_id"], no_norm, invoice_id)) if no_norm else None
    out.append(R("R09", 5, "Not already processed", "fail" if dup else "pass", "reject", "vendor",
                 f"Same as {dup['invoice_no']} ({inr(dup['total'])}), {dup['outcome']} on {str(dup['decided_at'])[:10]}: numbers match once "
                 f"separators and leading zeros are removed." if dup else "No earlier invoice with this number from this vendor."))
    inv_date, total = parse_date(val(F, "invoice_date")), val(F, "total")
    if not dup and inv_date and total:
        near = [r for r in db.q("SELECT * FROM invoices WHERE vendor_id=? AND invoice_id<>? AND outcome<>'rejected' AND abs(total-?)<=1",
                                (vendor["vendor_id"], invoice_id, total)) if parse_date(r["invoice_date"]) and abs((parse_date(r["invoice_date"]) - inv_date).days) <= 30]
        # Same amount alone is not suspicious if goods receipts cover both invoices (e.g. two equal deliveries).
        covered = bool(matched) and all(p and billed_before(p["po_no"], p["line_no"], invoice_id) + l["qty"] <= received(p["po_no"], p["line_no"])
                                        for l, p, _ in matched)
        if near and covered:
            out.append(R("R10", 5, "No near-duplicate", "pass", "hold", "ap",
                         f"Same total as {near[0]['invoice_no']} within 30 days, but goods receipts cover both, so this is a separate delivery."))
        else:
            out.append(R("R10", 5, "No near-duplicate", "fail" if near else "pass", "hold", "ap",
                         f"Same vendor and total as {near[0]['invoice_no']} within 30 days, different number, and receipts don't cover both. Check it is not a resend."
                         if near else "No invoice with the same total within 30 days."))
    sup_state, pos_state = state_of(vendor["gstin"]), state_of(buyer["gstin"])
    has_igst, has_split = "tax_igst" in F, "tax_cgst" in F or "tax_sgst" in F
    inter = sup_state != pos_state
    expected = "IGST" if inter else "CGST + SGST"
    charged = "IGST" if has_igst and not has_split else "CGST + SGST" if has_split and not has_igst else "unclear"
    ok = charged == expected
    sub = val(F, "subtotal") or 0
    out.append(R("R17", 7, "GST type fits the place of supply", "pass" if ok else "fail", "hold", "vendor",
                 f"Supplier in {STATES.get(sup_state, sup_state)} ({sup_state}), delivery to {STATES.get(pos_state, pos_state)} ({pos_state}): "
                 f"{'different' if inter else 'same'} state, so {expected} is due" + (f", and the invoice charges {charged}." if ok else
                 f". The invoice charges {charged}. We cannot claim the input tax credit until it is corrected.")))
    taxes = sum(F[k]["value"] for k in ("tax_igst", "tax_cgst", "tax_sgst") if k in F)
    rates = {p["gst_rate"] for _, p, _ in matched if p}
    eff = round(taxes / sub * 100, 1) if sub else None
    if rates and eff is not None:
        exp = max(rates)
        out.append(R("R18", 7, "GST rate matches the PO", "pass" if abs(eff - exp) <= 0.1 else "fail", "hold", "vendor",
                     f"Charged {eff:g}%, PO says {exp:g}%."))
    recv_date = parse_date(doc["received_at"][:10])
    if inv_date:
        bad = inv_date > recv_date or (recv_date - inv_date).days > SETTINGS["max_age_days"]
        out.append(R("R04", 4, "Invoice date is plausible", "fail" if bad else "pass", "hold", "ap",
                     f"Dated {inv_date:%d %b %Y}, received {recv_date:%d %b %Y}."))
    terms = int(vendor["payment_terms_days"])
    due = inv_date + timedelta(days=terms) if inv_date else None
    if vendor["msme"] in ("micro", "small") and inv_date:
        cap = inv_date + timedelta(days=SETTINGS["msme_max_days"])
        due = min(due, cap)
        out.append(R("R21", 8, "MSME payment limit respected", "info", "info", "ap",
                     f"{vendor['name']} is a {vendor['msme']} enterprise: must be paid by {cap:%d %b %Y} at the latest (45-day limit). "
                     f"Due {due:%d %b %Y} on {terms}-day terms; prioritised."))
    first = not db.one("SELECT 1 FROM invoices WHERE vendor_id=? AND outcome='approved' AND invoice_id<>?", (vendor["vendor_id"], invoice_id))
    big = (total or 0) > SETTINGS["auto_approve_cap"]
    reasons = ([f"{inr(total)} is above the {inr(SETTINGS['auto_approve_cap'])} automatic approval limit"] if big else []) + (["first invoice from this vendor"] if first else [])
    out.append(R("R22", 0, "Can be approved without sign-off", "warn" if reasons else "pass", "signoff", "ap_manager",
                 "Needs sign-off: " + " and ".join(reasons) + "." if reasons else f"{inr(total or 0)} is within the automatic approval limit."))
    return out, due


# ---------- decision ----------

def decide(results, due, vendor, total):
    fails = [r for r in results if r["outcome"] == "fail"]
    sec = [r for r in fails if r["severity"] == "security"]
    rej = [r for r in fails if r["severity"] == "reject"]
    holds = [r for r in fails if r["severity"] == "hold"] + [r for r in results if r["outcome"] == "warn" and r["severity"] == "confirm"]
    sign = [r for r in results if r["outcome"] == "warn" and r["severity"] == "signoff"]
    passed = sum(1 for r in results if r["outcome"] == "pass")
    if sec:
        phone = vendor["phone"] if vendor else "the number on file"
        return dict(outcome="security", title="On hold, security: payment blocked", reason=" ".join(r["detail"] for r in sec),
                    next=f"AP manager: call {vendor['name'] if vendor else 'the vendor'} on {phone} (number on file) to confirm. Do not reply to the email.")
    if rej:
        r = rej[0]
        return dict(outcome="rejected", title="Rejected: duplicate" if r["rule_id"] == "R09" else f"Rejected: {r['title'].lower()}",
                    reason=r["detail"], next="Linked to the original. Vendor told it is already being processed; nothing will be paid twice.")
    if holds:
        owners = list(dict.fromkeys(OWNERS[r["owner"]] for r in holds))
        names = list(dict.fromkeys(PROBLEM.get(r["rule_id"], r["title"].lower()) if not (r["rule_id"] == "R11" and r["outcome"] == "fail")
                                   else "no PO found" for r in holds))
        return dict(outcome="hold", title="On hold: " + ", ".join(names), reason=" ".join(r["detail"] for r in holds),
                    next="Waiting on: " + ", ".join(owners) + ".")
    if sign:
        return dict(outcome="signoff", title="Needs sign-off", reason=sign[0]["detail"], next="AP manager approves in one click.")
    return dict(outcome="approved", title="Approved", reason=f"All {passed} checks passed with evidence; {inr(total)} is within the automatic approval limit.",
                next=f"Added to the ERP export. Scheduled for payment on {due:%d %b %Y} (due date)." if due else "Added to the ERP export.")


# ---------- follow-up tasks and drafted messages (facts from rule results; wording from templates) ----------

def build_tasks(inv, results, decision, vendor, doc):
    ref = f"AP-{inv['invoice_id']:04d}"
    d = parse_date(inv["invoice_date"])
    inv = dict(inv, invoice_date=f"{d:%d %b %Y}" if d else "?")
    head = f"{inv['invoice_no'] or 'your invoice'} dated {inv['invoice_date']} for {inr(inv['total'] or 0)}"
    tasks = []
    if decision["outcome"] == "security":
        who = vendor["name"] if vendor else "The vendor"
        phone = vendor["phone"] if vendor else "the number on file"
        tasks.append(dict(owner_role="ap_manager", kind="call",
                          ask=f"Did {who} really change its bank account? Call {phone}, the number on file, to confirm. Do not reply to the email it came from."))
        return tasks
    if decision["outcome"] == "rejected" and vendor:
        body = (f"Hello {vendor['name']} team,\n\nWe received {head} again. It is the same invoice as one we have already processed, "
                f"so no action is needed and it will not be paid twice.\n\n{decision['reason']}\n\nPayment is scheduled as per the original invoice.\n\n"
                f"Thank you,\nAccounts Payable, Sharma Components Pvt Ltd")
        tasks.append(dict(owner_role="vendor", kind="message", ask="Tell the vendor this invoice is already being processed.",
                          draft_to=vendor["contact_email"], draft_subject=f"{inv['invoice_no']}: already received [{ref}]", draft_body=body))
        return tasks
    if decision["outcome"] == "signoff":
        tasks.append(dict(owner_role="ap_manager", kind="signoff", ask=decision["reason"]))
        return tasks
    by_owner = {}
    for r in results:
        if (r["outcome"] == "fail" and r["severity"] == "hold") or (r["outcome"] == "warn" and r["severity"] == "confirm"):
            by_owner.setdefault(r["owner"], []).append(r)
    for owner, rs in by_owner.items():
        issues = "\n".join(f"- {r['title']}: {r['detail']}" for r in rs)
        if owner == "vendor" and vendor:
            body = (f"Hello {vendor['name']} team,\n\nWe received {head}. We can't process it yet:\n\n{issues}\n\n"
                    f"What we need: a revised invoice that fixes the points above, quoting {inv['po_no'] or 'our PO number'}.\n\n"
                    f"Please reply to this email with the revised PDF and keep [{ref}] in the subject, so it reaches the right invoice.\n\n"
                    f"Thank you,\nAccounts Payable, Sharma Components Pvt Ltd")
            fixes = ", ".join(dict.fromkeys(PROBLEM.get(r["rule_id"], r["title"].lower()) for r in rs))
            tasks.append(dict(owner_role=owner, kind="message", ask=f"Can you send a revised invoice that fixes the {fixes}?", draft_to=vendor["contact_email"],
                              draft_subject=f"{inv['invoice_no']} dated {inv['invoice_date']}: revised invoice needed [{ref}]", draft_body=body))
        elif owner in INTERNAL_EMAIL:
            ask = {"procurement": "Amend the PO, or tell us to ask the vendor for a revised invoice.",
                   "stores": "Confirm what was received, or record the missing goods receipt."}[owner]
            body = (f"Hi,\n\n{vendor['name'] if vendor else 'A vendor'}'s invoice {head} is on hold:\n\n{issues}\n\n{ask}\n\nThanks,\nAP desk [{ref}]")
            tasks.append(dict(owner_role=owner, kind="message", ask=ask, draft_to=INTERNAL_EMAIL[owner],
                              draft_subject=f"Invoice {inv['invoice_no']} on hold: your input needed [{ref}]", draft_body=body))
        else:
            asks = []
            for r in rs:
                if r["rule_id"] == "R11" and inv.get("po_suggested"):
                    asks.append(f"Is {inv['po_suggested']} the right PO for this invoice? It is the only open PO from this vendor that matches the items, rates and remaining quantity.")
                elif r["rule_id"] == "R23":
                    asks.append("Check these values against the document and correct them if needed: " + r["detail"].replace("Confirm: ", ""))
                elif r["rule_id"] == "R10":
                    asks.append("Is this a new invoice or a resend of an earlier one? " + r["detail"])
                else:
                    asks.append(r["detail"])
            tasks.append(dict(owner_role=owner, kind="confirm", ask=" ".join(asks)))
    return tasks
