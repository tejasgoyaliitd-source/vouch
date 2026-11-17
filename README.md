# Vouch: invoice to decision

Zamp ASA case study, PS-1. A vendor invoice comes in by email or upload (PDF, scan, phone photo, Word, `.eml`). The process reads it, checks it against the vendor master, purchase orders and goods receipts, and decides: approved, needs sign-off, on hold (with an owner and a drafted message), security hold, or rejected. Every stage is streamed live and written to a hash-chained audit log.

## Run it

Backend (Python 3.12+, Tesseract OCR installed):

```
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn main:app --port 8000
```

Frontend (Node 20+):

```
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

Regenerate demo data and inputs: `backend/.venv/Scripts/python scripts/make_samples.py`
Check the five scenarios: `cd backend && .venv/Scripts/python -m pytest -q tests`

## Demo inputs (samples/)

| Input | What it tests | Expected |
|---|---|---|
| `happy_acme_einvoice.eml` | e-invoice with signed QR, by email | Approved, exported for the ERP |
| `e1_bank_change.eml` | perfect PO match, new bank account, lookalike sender domain | Security hold, payment blocked, call the number on file |
| `e2_po_overbilled.eml` | second invoice takes billing past the PO (stores accepted 10 extra) | On hold, procurement decides |
| `e3_resent_scan.eml` | same invoice resent as a scan, number reformatted | Rejected as duplicate |
| `IMG_2041.jpg` | phone photo, no PO quoted, CGST + SGST on an inter-state supply | On hold: vendor fixes GST type, AP confirms suggested PO |

## How it is built

- `backend/ap/extract.py`: routing (QR, text layer, OCR) and reading. Tesseract runs locally; photos are straightened and cleaned first. OCR misreads in GSTINs are repaired by position and kept only if the checksum validates.
- `backend/ap/privacy.py`: bank, IFSC, PAN, phone and email are swapped for placeholders before any model call.
- `backend/ap/rules.py`: 22 deterministic checks mapped to the eight questions AP answers before paying, the decision, and the follow-up tasks with drafted messages.
- `backend/ap/pipeline.py`: the 12 stages; each writes one event.
- `frontend/`: React + Tailwind. Run view, work queue, invoice page, dashboard, inbox, records, audit.

## Not built yet

- Model extractor: `extract.model_extract` returns nothing until a provider key is set, so fields come from the label-based local parser.
- Live mailbox polling (emails arrive as `.eml` for now).
- Deployment.
