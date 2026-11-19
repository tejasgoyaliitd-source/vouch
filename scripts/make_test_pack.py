"""Build samples/test_pack: one clearly named file per test case, for evaluators to upload.

Files 01 to 05 are the exact invoice files attached to the five inbox emails, so uploading one after processing
the same email is caught as a duplicate (that is correct). Files 06 and 07 are new invoices the inbox never shows,
in a layout the samples do not use ("Invoice #", "Dated", "Amount payable"), to show the reader is not tuned to them.

Run from app/:  backend/.venv/Scripts/python scripts/make_test_pack.py
"""
import sys
from pathlib import Path

import pymupdf

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "backend"))
from ap.gst import make_gstin  # noqa: E402
from ap.intake import parse_eml  # noqa: E402

SAMPLES = APP / "samples"
OUT = SAMPLES / "test_pack"
BUYER = ("Sharma Components Pvt Ltd", "Plot 14, Okhla Phase II, New Delhi 110020", "07AAFCS5678K1ZQ")

FROM_INBOX = [  # (test pack name, inbox email or file)
    ("01_clean_einvoice.pdf", "happy_acme_einvoice.eml"),
    ("02_bank_details_changed.pdf", "e1_bank_change.eml"),
    ("03_billed_past_po.pdf", "e2_po_overbilled.eml"),
    ("04_paid_invoice_resent_as_scan.pdf", "e3_resent_scan.eml"),
    ("05_whatsapp_photo_no_po.jpg", "IMG_2041.jpg"),
]


def attachment(name):
    data = (SAMPLES / name).read_bytes()
    if not name.endswith(".eml"):
        return data
    return parse_eml(data)["attachments"][0][1]


def invoice_pdf(path, seller, meta, lines, tax_rate=18):
    """A plain one-page invoice in a layout the inbox samples do not use."""
    name, addr, gstin = seller
    doc = pymupdf.open()
    pg = doc.new_page(width=595, height=842)
    ink, grey = (0.09, 0.1, 0.12), (0.36, 0.38, 0.44)
    pg.insert_text((48, 70), name.upper(), fontsize=15, fontname="hebo", color=ink)
    pg.insert_text((48, 88), addr, fontsize=9.5, color=grey)
    pg.insert_text((48, 102), f"GST No. {gstin}", fontsize=9.5, color=grey)
    pg.insert_text((430, 70), "INVOICE", fontsize=15, fontname="hebo", color=ink)
    y = 92
    for label, value in meta:
        pg.insert_text((392, y), f"{label} {value}", fontsize=9.5, color=ink)
        y += 14
    pg.insert_text((48, 150), f"Buyer: {BUYER[0]}, New Delhi   GSTIN {BUYER[2]}", fontsize=9.5, color=ink)

    cols = [48, 300, 370, 410, 480]
    y = 190
    pg.draw_line((48, y - 13), (547, y - 13), color=grey, width=0.6)
    for x, t in zip(cols, ["Particulars", "HSN", "Qty", "Rate", "Amount"]):
        pg.insert_text((x, y), t, fontsize=9.5, fontname="hebo", color=ink)
    pg.draw_line((48, y + 6), (547, y + 6), color=grey, width=0.6)
    taxable = 0
    for desc, hsn, qty, rate in lines:
        y += 22
        amt = qty * rate
        taxable += amt
        for x, t in zip(cols, [desc, hsn, f"{qty:g}", f"{rate:,.2f}", f"{amt:,.2f}"]):
            pg.insert_text((x, y), t, fontsize=9.5, color=ink)
    tax = round(taxable * tax_rate / 100, 2)
    y += 34
    for label, value, bold in [("Taxable value", taxable, False), (f"IGST {tax_rate}%", tax, False), ("Amount payable", taxable + tax, True)]:
        pg.insert_text((370, y), f"{label}   {value:,.2f}", fontsize=10.5 if bold else 9.5, fontname="hebo" if bold else "helv", color=ink)
        y += 18
    pg.insert_text((48, 780), "Payment within 30 days of invoice date. This is a computer generated invoice.", fontsize=8.5, color=grey)
    doc.save(path)


def main():
    OUT.mkdir(exist_ok=True)
    for name, src in FROM_INBOX:
        (OUT / name).write_bytes(attachment(src))

    # 06: a vendor nobody onboarded (valid GSTIN, Maharashtra), no PO quoted
    invoice_pdf(OUT / "06_vendor_not_onboarded.pdf",
                ("Sunrise Office Mart", "Andheri East, Mumbai, Maharashtra 400069", make_gstin("27", "AAKCS4471M")),
                [("Bill No:", "SOM/2026/883"), ("Dated:", "17-11-2026")],
                [("Whiteboard markers (box of 10)", "9608", 20, 240), ("Desk organiser", "3926", 6, 650)])

    # 07: a known vendor, new invoice number, against an open PO with goods received
    invoice_pdf(OUT / "07_known_vendor_new_layout.pdf",
                ("Acme Supplies Pvt Ltd", "Sector 37, Gurugram, Haryana 122001", "06AABCA1234Q1ZQ"),
                [("Invoice #:", "ACM-5521"), ("Dated:", "17-11-2026"), ("Your order ref", "PO-4471")],
                [("Copier paper A4, 500 sheets (box)", "4802", 10, 900)])

    for p in sorted(OUT.iterdir()):
        print(f"{p.name:42s} {p.stat().st_size:>8,d} bytes")


if __name__ == "__main__":
    main()
