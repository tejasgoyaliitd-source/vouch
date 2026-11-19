# Vouch: invoice to decision

Zamp AI Solutions Associate case, PS-1. A vendor invoice arrives by email or upload (digital PDF, scan, phone photo, Word, `.eml`). Vouch reads it, checks it against the vendor master, purchase orders and goods receipts, and decides: approved, needs sign-off, on hold (with an owner and a drafted message), security hold, or rejected. Every step streams live and is written to a hash-chained audit log.

**Live app: https://vouch-4scy.vercel.app** (first load can take about 7 seconds while the server wakes up)

## Try it in two minutes

1. Open the live app and sign in as **Ananya Rao** (demo data, no password).
2. In **Inbox**, click **Process all**. Each row fills in a 12-step map as it runs; open any row with **View steps** to see every check and the evidence behind it.
3. Click **Test files** to download the files below, then upload them (or drag them onto the inbox) and compare each result with the expected one. The pipeline never reads file names; rename them if you like.
4. Upload an invoice of your own.

Other people: **Neha Kapoor** (AP manager) releases security holds and can restore the starting data. **Vikram Shah** (internal audit) can see everything and change nothing.

## Test files (`samples/test_pack/`)

| File | What it tests | Expected |
|---|---|---|
| `01_clean_einvoice.pdf` | Signed e-invoice that matches the PO, goods receipts and price | Approved, scheduled for payment |
| `02_bank_details_changed.pdf` | Same vendor and amount, but a bank account the vendor master does not have | Security hold, payment blocked |
| `03_billed_past_po.pdf` | Second invoice on one PO that bills 10 units more than were ordered | On hold, procurement decides |
| `04_paid_invoice_resent_as_scan.pdf` | An invoice already paid, sent again as a scan with the number written differently | Rejected as a duplicate |
| `05_whatsapp_photo_no_po.jpg` | Tilted phone photo, no PO number, wrong type of GST | On hold: vendor fixes GST, AP confirms the suggested PO |
| `06_vendor_not_onboarded.pdf` | A supplier nobody has onboarded, no PO quoted | On hold: find out who ordered it |
| `07_known_vendor_new_layout.pdf` | A known vendor in a layout the samples do not use | Approved |

Files 01 to 05 are the attachments of the five inbox emails, so uploading one you already processed from the inbox comes back as a duplicate. That is the correct result.

## How it decides

- **Reading.** Signed e-invoice QR first, then the PDF text layer, then local OCR (Tesseract) for scans and photos, which are straightened and cleaned first. A label-based parser and a language model (Gemini) read the same page. Model values must appear on the page; where the two readers disagree, a person confirms.
- **Privacy.** Bank details, IFSC, PAN, phone numbers and emails are swapped for placeholders before any text reaches the model.
- **Deciding.** 22 deterministic rules, grouped into the eight questions AP answers before paying. The model never decides. A wrong hold costs a day; a wrong payment can cost lakhs, so anything uncertain stops and goes to a named person with a drafted message.
- **Order.** Invoices run one at a time in the order they arrived, so two bills against the same PO are checked in sequence.

## Code map

- `backend/ap/extract.py`: routing (QR, text layer, OCR), reading and the merge of the two readers
- `backend/ap/privacy.py`: reversible masking before any model call
- `backend/ap/rules.py`: the 22 checks, the decision, and follow-up tasks with drafted messages
- `backend/ap/pipeline.py`: the 12 steps; each writes one audit event
- `frontend/src/runner.jsx`: the inbox queue (one at a time, process on arrival) and the step map
- `scripts/make_samples.py`, `scripts/make_test_pack.py`: rebuild the demo data and test files

## Run it locally

Backend (Python 3.12+, [Tesseract](https://github.com/tesseract-ocr/tesseract) installed):

```
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # optional: add a GEMINI_API_KEY; without one, the local parser reads alone
python -m uvicorn main:app --port 8000
```

Frontend (Node 20+):

```
cd frontend
npm install
npm run dev    # http://localhost:5173, forwards /api to port 8000
```

Tests: `cd backend && MODEL_PROVIDER=off python -m pytest -q tests`

## Not built

- A live mailbox connection (emails arrive as `.eml` files) and an ERP connection (approved bills go to a CSV export).
- A server-side queue: the batch runs from the open browser tab, so closing the tab stops invoices that have not started yet. Anything already started finishes.
