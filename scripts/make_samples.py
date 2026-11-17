"""Create synthetic master data and the five demo inputs (happy path + E1..E4).

Run from app/:  backend/.venv/Scripts/python scripts/make_samples.py
Writes data/*.csv, data/history.json and samples/*.
"""
import base64
import csv
import io
import json
import random
import sys
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pymupdf
import qrcode
from PIL import Image, ImageFilter, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from ap.gst import make_gstin  # noqa: E402

DATA, SAMPLES = ROOT / "data", ROOT / "samples"
DATA.mkdir(exist_ok=True)
SAMPLES.mkdir(exist_ok=True)
IST = timezone(timedelta(hours=5, minutes=30))
random.seed(7)
np.random.seed(7)

BUYER = {"name": "Sharma Components Pvt Ltd", "addr": "Plot 14, Okhla Phase II, New Delhi 110020",
         "gstin": make_gstin("07", "AAFCS5678K"), "email": "ap@sharmacomponents.in"}

VENDORS = [
    dict(vendor_id="V001", name="Acme Supplies Pvt Ltd", gstin=make_gstin("06", "AABCA1234Q"), state="06", msme="",
         bank_account="50200011342210", ifsc="HDFC0001234", email_domains="acmesupplies.com",
         contact_email="accounts@acmesupplies.com", phone="+91 98110 44410", payment_terms_days=30,
         addr="Sector 37, Gurugram, Haryana 122001"),
    dict(vendor_id="V002", name="Bharat Steel Traders", gstin=make_gstin("07", "AAACB4321M"), state="07", msme="small",
         bank_account="00881234568834", ifsc="SBIN0000881", email_domains="bharatsteel.co.in",
         contact_email="accounts@bharatsteel.co.in", phone="+91 98101 22871", payment_terms_days=21,
         addr="Naraina Industrial Area, New Delhi 110028"),
    dict(vendor_id="V003", name="Northwind IT Services Pvt Ltd", gstin=make_gstin("29", "AAGCN7788P"), state="29", msme="",
         bank_account="912010000450457", ifsc="UTIB0000123", email_domains="northwindit.in",
         contact_email="accounts@northwindit.in", phone="+91 80 4110 2290", payment_terms_days=30,
         addr="Koramangala, Bengaluru, Karnataka 560034"),
    dict(vendor_id="V004", name="Kumar Packaging", gstin=make_gstin("06", "BQZPK2266H"), state="06", msme="micro",
         bank_account="3812005129", ifsc="PUNB0123400", email_domains="kumarpackaging.in",
         contact_email="accounts@kumarpackaging.in", phone="+91 99100 31187", payment_terms_days=15,
         addr="Sector 6, Faridabad, Haryana 121006"),
]
V = {v["vendor_id"]: v for v in VENDORS}

POS = [("PO-4471", "V001", "2026-10-20"), ("PO-4502", "V002", "2026-10-15"), ("PO-4390", "V003", "2026-10-01"),
       ("PO-4519", "V004", "2026-10-30"), ("PO-4388", "V004", "2026-09-10")]
PO_LINES = [
    ("PO-4471", 1, "PAPA4", "Copier paper A4, 500 sheets (box)", "4802", 80, 900, 18),
    ("PO-4471", 2, "TN2400", "Toner cartridge TN-2400", "8443", 24, 2500, 18),
    ("PO-4471", 3, "DLV", "Delivery charges", "9965", 2, 6000, 18),
    ("PO-4502", 1, "SB40", "Steel bracket SB-40", "7326", 100, 450, 18),
    ("PO-4390", 1, "SUP40", "Annual support, 40 laptops", "9987", 1, 200000, 18),
    ("PO-4519", 1, "CTN5", "Corrugated carton 5-ply", "4819", 300, 30, 18),
    ("PO-4519", 2, "CTN3S", "Carton 3-ply small", "4819", 120, 50, 18),
    ("PO-4388", 1, "TAPE48", "BOPP tape roll 48mm", "3919", 500, 22, 18),
]
RECEIPTS = [
    ("GRN-8812", "PO-4471", 1, 40, "2026-11-05"), ("GRN-8812", "PO-4471", 2, 12, "2026-11-05"), ("GRN-8812", "PO-4471", 3, 1, "2026-11-05"),
    ("GRN-8813", "PO-4471", 1, 40, "2026-11-12"), ("GRN-8813", "PO-4471", 2, 12, "2026-11-12"), ("GRN-8813", "PO-4471", 3, 1, "2026-11-12"),
    ("GRN-8839", "PO-4502", 1, 60, "2026-10-28"), ("GRN-8840", "PO-4502", 1, 50, "2026-11-11"),
    ("GRN-8790", "PO-4390", 1, 1, "2026-11-01"),
    ("GRN-8850", "PO-4519", 1, 300, "2026-11-08"), ("GRN-8850", "PO-4519", 2, 120, "2026-11-08"),
    ("GRN-8701", "PO-4388", 1, 500, "2026-09-20"),
]
HISTORY = [
    dict(vendor_id="V001", invoice_no="INV/2026/088", invoice_date="2026-10-08", po_no="PO-4410", subtotal=50000, tax=9000,
         total=59000, decided_at="2026-10-10T12:00:00+05:30", lines=[dict(po_line=1, qty=50, unit_price=1000, amount=50000)]),
    dict(vendor_id="V004", invoice_no="KP/1102", invoice_date="2026-09-22", po_no="PO-4388", subtotal=11000, tax=1980,
         total=12980, decided_at="2026-09-24T10:30:00+05:30", lines=[dict(po_line=1, qty=500, unit_price=22, amount=11000)]),
    dict(vendor_id="V002", invoice_no="INV/BS/0318", invoice_date="2026-10-30", po_no="PO-4502", subtotal=27000, tax=4860,
         total=31860, decided_at="2026-11-01T11:05:00+05:30", lines=[dict(po_line=1, qty=60, unit_price=450, amount=27000)]),
    dict(vendor_id="V003", invoice_no="INV/2026/042", invoice_date="2026-11-05", po_no="PO-4390", subtotal=200000, tax=36000,
         total=236000, decided_at="2026-11-07T15:40:00+05:30", lines=[dict(po_line=1, qty=1, unit_price=200000, amount=200000)]),
]


def write_csv(name, header, rows):
    with open(DATA / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def money(x):
    s = f"{x:.2f}"
    whole, dec = s.split(".")
    if len(whole) > 3:  # Indian grouping: 12,34,567.00
        head, tail = whole[:-3], whole[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        whole = f"{head},{tail}"
    return f"{whole}.{dec}"


def irp_qr_payload(v, inv):
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
    data = {"SellerGstin": v["gstin"], "BuyerGstin": BUYER["gstin"], "DocNo": inv["no"], "DocTyp": "INV",
            "DocDt": inv["date_dmy"], "TotInvVal": inv["total"], "ItemCnt": len(inv["lines"]),
            "MainHsnCode": inv["lines"][0][2], "Irn": inv["irn"], "IrnDt": inv["date_iso"] + " 10:12:00"}
    head = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"data": json.dumps(data), "iss": "NIC"}).encode())
    return f"{head}.{body}.{b64(b'demo-signature-not-verified')}"


def draw_invoice(path, v, inv, style="A"):
    c = canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    y = H - 50
    c.setFont("Helvetica-Bold", 15)
    c.drawString(40, y, v["name"].upper())
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 14, v["addr"])
    c.drawString(40, y - 26, f"GSTIN: {v['gstin']}   Phone: {v['phone']}   Email: {v['contact_email']}")
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(W - 40, y, "TAX INVOICE")
    c.setFont("Helvetica", 10)
    label_no = {"A": "Invoice No.", "B": "Invoice #", "C": "Bill No"}[style]
    c.drawRightString(W - 40, y - 18, f"{label_no}: {inv['no']}")
    c.drawRightString(W - 40, y - 31, f"Date: {inv['date_dmy']}")
    if inv.get("po"):
        c.drawRightString(W - 40, y - 44, f"PO No: {inv['po']}")
    y -= 75
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Bill to")
    c.setFont("Helvetica", 9.5)
    c.drawString(40, y - 13, BUYER["name"])
    c.drawString(40, y - 25, BUYER["addr"])
    c.drawString(40, y - 37, f"GSTIN: {BUYER['gstin']}")
    c.drawString(40, y - 49, "Place of supply: Delhi (07)")
    if inv.get("irn"):
        img = qrcode.make(irp_qr_payload(v, inv), box_size=3, border=2)
        c.drawImage(ImageReader(img.get_image()), W - 150, y - 70, 105, 105)
        c.setFont("Helvetica", 6.5)
        c.drawRightString(W - 40, y - 80, f"IRN: {inv['irn'][:32]}")
        c.drawRightString(W - 40, y - 88, inv["irn"][32:])
    y -= 110
    cols = [40, 65, 300, 360, 420, 480]
    c.setFont("Helvetica-Bold", 9.5)
    for x, t in zip(cols, ["#", "Description", "HSN", "Qty", "Rate", "Amount"]):
        c.drawString(x, y, t)
    c.line(40, y - 5, W - 40, y - 5)
    c.setFont("Helvetica", 9.5)
    for i, (desc, qty, hsn, rate) in enumerate(inv["lines"], 1):
        y -= 18
        for x, t in zip(cols, [str(i), desc, hsn, str(qty), money(rate), money(qty * rate)]):
            c.drawString(x, y, t)
    c.line(40, y - 8, W - 40, y - 8)
    y -= 26
    c.drawRightString(W - 120, y, "Subtotal")
    c.drawRightString(W - 40, y, money(inv["subtotal"]))
    for label, amt in inv["taxes"]:
        y -= 15
        c.drawRightString(W - 120, y, label)
        c.drawRightString(W - 40, y, money(amt))
    y -= 18
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W - 120, y, "Total (INR)")
    c.drawRightString(W - 40, y, money(inv["total"]))
    y -= 45
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(40, y, "Bank details")
    c.setFont("Helvetica", 9.5)
    if inv.get("bank_note"):
        y -= 13
        c.drawString(40, y, inv["bank_note"])
    c.drawString(40, y - 13, f"A/c No: {inv['bank'][0]}   IFSC: {inv['bank'][1]}")
    c.drawString(40, y - 40, f"Payment terms: {v['payment_terms_days']} days from invoice date")
    c.drawString(40, 60, "This is a computer generated invoice.")
    c.save()


def make_inv(v, no, date_iso, po, lines, intra, bank=None, bank_note=None, irn=False):
    sub = sum(q * r for _, q, _, r in lines)
    taxes = [("CGST 9%", sub * 0.09), ("SGST 9%", sub * 0.09)] if intra else [("IGST 18%", sub * 0.18)]
    d = datetime.fromisoformat(date_iso)
    return dict(no=no, date_iso=date_iso, date_dmy=d.strftime("%d/%m/%Y"), po=po, subtotal=sub, taxes=taxes,
                total=round(sub + sum(t for _, t in taxes), 2), bank=bank or (v["bank_account"], v["ifsc"]),
                bank_note=bank_note, irn=("%064x" % random.getrandbits(256)) if irn else None,
                lines=[(desc, q, hsn, r) for desc, q, hsn, r in lines])


def render(pdf_path, dpi):
    doc = pymupdf.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def as_scan(pdf_in, pdf_out):
    img = render(pdf_in, 150).convert("L").rotate(0.7, expand=True, fillcolor=255)
    arr = np.asarray(img).astype(np.int16) + np.random.normal(0, 14, (img.height, img.width)).astype(np.int16)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.4))
    img.save(pdf_out, "PDF", resolution=150)


def as_photo(pdf_in, jpg_out):
    img = render(pdf_in, 170).rotate(-1.6, expand=True, fillcolor=(214, 205, 186))
    img = ImageOps.colorize(ImageOps.grayscale(img), black=(40, 34, 28), white=(236, 228, 210))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    img.save(jpg_out, "JPEG", quality=72)


def eml(path, sender, subject, body, attach_path, when):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, BUYER["email"], subject
    m["Date"], m["Message-ID"] = format_datetime(when), make_msgid(domain=sender.split("@")[1])
    m.set_content(body)
    m.add_attachment(Path(attach_path).read_bytes(), maintype="application", subtype="pdf", filename=Path(attach_path).name)
    Path(path).write_bytes(bytes(m))


if __name__ == "__main__":
    write_csv("vendors.csv", list(VENDORS[0].keys()), [list(v.values()) for v in VENDORS])
    write_csv("purchase_orders.csv", ["po_no", "vendor_id", "po_date"], POS)
    write_csv("po_lines.csv", ["po_no", "line_no", "item_code", "description", "hsn", "qty", "unit_price", "gst_rate"], PO_LINES)
    write_csv("receipts.csv", ["grn_no", "po_no", "line_no", "qty_received", "received_date"], RECEIPTS)
    (DATA / "history.json").write_text(json.dumps(HISTORY, indent=1))
    (DATA / "buyer.json").write_text(json.dumps(BUYER, indent=1))

    acme, bharat, north, kumar = V["V001"], V["V002"], V["V003"], V["V004"]
    acme_lines = [("Copier paper A4, 500 sheets (box)", 40, "4802", 900), ("Toner cartridge TN-2400", 12, "8443", 2500),
                  ("Delivery charges", 1, "9965", 6000)]
    tmp = SAMPLES / "_src"
    tmp.mkdir(exist_ok=True)

    happy = make_inv(acme, "INV/2026/117", "2026-11-12", "PO-4471", acme_lines, intra=False, irn=True)
    draw_invoice(SAMPLES / "INV-2026-117.pdf", acme, happy, "A")
    eml(SAMPLES / "happy_acme_einvoice.eml", "billing@acmesupplies.com", "Invoice INV/2026/117",
        "Dear team,\nPlease find attached our invoice INV/2026/117 against PO-4471.\nRegards,\nAcme Supplies",
        SAMPLES / "INV-2026-117.pdf", datetime(2026, 11, 14, 10, 42, tzinfo=IST))

    e1 = make_inv(acme, "INV/2026/121", "2026-11-13", "PO-4471", acme_lines, intra=False, irn=True,
                  bank=("39100077317731", "ICIC0004321"), bank_note="Please note our NEW bank account below.")
    draw_invoice(SAMPLES / "INV-2026-121.pdf", acme, e1, "A")
    eml(SAMPLES / "e1_bank_change.eml", "billing@acme-supp1ies.com", "Updated bank details - INV/2026/121",
        "Dear team,\nOur bank account has changed. Kindly pay INV/2026/121 to the new account on the invoice.\nRegards,\nAcme Supplies",
        SAMPLES / "INV-2026-121.pdf", datetime(2026, 11, 14, 10, 47, tzinfo=IST))

    e2 = make_inv(bharat, "INV/BS/0331", "2026-11-13", "PO-4502", [("Steel bracket SB-40", 50, "7326", 450)], intra=True)
    draw_invoice(SAMPLES / "INV-BS-0331.pdf", bharat, e2, "B")
    eml(SAMPLES / "e2_po_overbilled.eml", "billing@bharatsteel.co.in", "INV/BS/0331",
        "Hello,\nInvoice INV/BS/0331 for the second delivery of SB-40 brackets is attached.\nBharat Steel Traders",
        SAMPLES / "INV-BS-0331.pdf", datetime(2026, 11, 14, 10, 51, tzinfo=IST))

    e3 = make_inv(north, "INV-2026-42", "2026-11-05", "PO-4390", [("Annual support, 40 laptops", 1, "9987", 200000)], intra=False)
    draw_invoice(tmp / "e3_digital.pdf", north, e3, "A")
    as_scan(tmp / "e3_digital.pdf", SAMPLES / "Scan_20261114_1102.pdf")
    eml(SAMPLES / "e3_resent_scan.eml", "accounts@northwindit.in", "Reminder: payment due",
        "Hi,\nGentle reminder that the attached invoice is due. Please arrange payment.\nNorthwind IT Services",
        SAMPLES / "Scan_20261114_1102.pdf", datetime(2026, 11, 14, 11, 20, tzinfo=IST))

    e4 = make_inv(kumar, "KP/1187", "2026-11-10", None,
                  [("Corrugated carton 5-ply", 300, "4819", 30), ("Carton 3-ply small", 120, "4819", 50)], intra=True)
    draw_invoice(tmp / "e4_digital.pdf", kumar, e4, "C")
    as_photo(tmp / "e4_digital.pdf", SAMPLES / "IMG_2041.jpg")
    print("written:", sorted(p.name for p in SAMPLES.iterdir() if p.is_file()))
