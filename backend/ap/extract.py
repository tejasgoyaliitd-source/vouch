"""Reading documents. Routing is code; reading text is PyMuPDF (text layer) or Tesseract (scans, photos);
e-invoice QR codes are decoded with OpenCV. Field parsing here is a label-based baseline that works on
text from any route; a model extractor can replace it (see model_extract) without changing anything else."""
import base64
import io
import json
import os
import re
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytesseract
from PIL import Image, ImageOps

from .gst import GSTIN_RE, is_valid_gstin, repair_gstin

_TESS = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if Path(_TESS).exists():
    pytesseract.pytesseract.tesseract_cmd = _TESS

NUM = r"\d{1,3}(?:,\d{2,3})*(?:\.\d{2})|\d+\.\d{2}"


# ---------- page images ----------

def pdf_page_image(path, dpi=200) -> Image.Image:
    pix = pymupdf.open(path)[0].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def deskew(gray: Image.Image) -> tuple[Image.Image, float]:
    """Find the small rotation that makes text rows sharpest (projection profile), then undo it."""
    small = gray.copy()
    small.thumbnail((900, 900))
    arr = np.asarray(small) < 140
    best, best_angle = -1.0, 0.0
    for angle in np.arange(-4, 4.01, 0.2):
        rot = np.asarray(Image.fromarray(arr.astype(np.uint8) * 255).rotate(angle, fillcolor=0)) > 0
        score = float(np.var(rot.sum(axis=1)))
        if score > best:
            best, best_angle = score, float(angle)
    return gray.rotate(best_angle, expand=True, fillcolor=255), round(best_angle, 1)


def clean_for_ocr(img: Image.Image) -> tuple[Image.Image, list[str]]:
    steps = []
    gray = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    steps.append("grayscale + contrast")
    gray, angle = deskew(gray)
    if abs(angle) >= 0.2:
        steps.append(f"straightened by {abs(angle)} degrees")
    if gray.width < 2000:
        f = 2200 / gray.width
        gray = gray.resize((int(gray.width * f), int(gray.height * f)), Image.LANCZOS)
        steps.append("upscaled for OCR")
    return gray, steps


# ---------- words -> rows (same code path for text layer and OCR) ----------

def rows_from_words(words, width, height):
    """words: list of (x0, y0, x1, y1, text, conf). Returns rows with text, bbox (normalised) and confidence."""
    words = [w for w in words if w[4].strip()]
    if not words:
        return []
    hs = sorted(w[3] - w[1] for w in words)
    tol = max(hs[len(hs) // 2] * 0.55, 2)
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows, cur, cy = [], [], None
    for w in words:
        c = (w[1] + w[3]) / 2
        if cy is None or abs(c - cy) <= tol:
            cur.append(w)
            cy = c if cy is None else (cy * (len(cur) - 1) + c) / len(cur)
        else:
            rows.append(cur)
            cur, cy = [w], c
    rows.append(cur)
    out = []
    for r in rows:
        r.sort(key=lambda w: w[0])
        out.append(dict(text=" ".join(w[4] for w in r), words=[dict(t=w[4], b=[w[0] / width, w[1] / height, w[2] / width, w[3] / height], c=w[5]) for w in r],
                        conf=round(sum(w[5] for w in r) / len(r), 2)))
    return out


def text_layer_rows(path):
    page = pymupdf.open(path)[0]
    words = [(w[0], w[1], w[2], w[3], w[4], 0.99) for w in page.get_text("words")]
    return rows_from_words(words, page.rect.width, page.rect.height), len(page.get_text().strip())


def ocr_rows(gray: Image.Image):
    d = pytesseract.image_to_data(gray, config="--oem 1 --psm 11", output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(d["text"]):
        conf = float(d["conf"][i])
        if t.strip() and conf >= 0:
            words.append((d["left"][i], d["top"][i], d["left"][i] + d["width"][i], d["top"][i] + d["height"][i], t, round(conf / 100, 2)))
    return rows_from_words(words, gray.width, gray.height)


def docx_rows(path):
    import docx
    doc = docx.Document(path)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for t in doc.tables:
        for row in t.rows:
            lines.append(" ".join(c.text.strip() for c in row.cells))
    return [dict(text=l, words=[], conf=0.99) for l in lines]


# ---------- e-invoice QR ----------

def read_einvoice_qr(img: Image.Image):
    """Dense signed QR codes (~550 chars) need both detectors and enough resolution."""
    data = ""
    for scale in (1.0, 1.5):
        im = img if scale == 1.0 else img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        arr = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)
        for det in (cv2.QRCodeDetectorAruco(), cv2.QRCodeDetector()):
            try:
                data = det.detectAndDecode(arr)[0]
            except cv2.error:
                data = ""
            if data:
                break
        if data:
            break
    if not data or data.count(".") != 2:
        return None
    try:
        body = data.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        inner = json.loads(payload["data"]) if isinstance(payload.get("data"), str) else payload.get("data")
        return inner if inner and "SellerGstin" in inner else None
    except Exception:
        return None


# ---------- routing ----------

def route_and_read(path: str, kind: str) -> dict:
    """Decide how to read the document, read it, and report why."""
    if kind == "pdf":
        rows, chars = text_layer_rows(path)
        alnum_words = sum(1 for r in rows for w in r["words"] if re.search(r"[A-Za-z]{3,}", w["t"]))
        page_img = pdf_page_image(path, 200)
        qr = read_einvoice_qr(page_img)
        if chars >= 50 and alnum_words >= 15:
            reason = f"Text layer found ({chars:,} characters)"
            reason += " and a signed e-invoice QR code. Route: QR for header fields, text for lines." if qr else ". Route: text layer."
            return dict(route="einvoice" if qr else "text", reason=reason, rows=rows, qr=qr, preview=page_img, steps=[])
        gray, steps = clean_for_ocr(page_img)
        why = "Page 1 has no usable text layer" if chars < 50 else "Text layer looks like gibberish"
        return dict(route="scan", reason=f"{why} ({chars} characters), so it is a scan. Route: clean up, then OCR (Tesseract, local).",
                    rows=ocr_rows(gray), qr=qr, preview=gray, steps=steps)
    if kind in ("jpg", "png"):
        img = Image.open(path).convert("RGB")
        gray, steps = clean_for_ocr(img)
        return dict(route="photo", reason="Image file, so treat it as a photo. Route: " + ", ".join(steps) + ", then OCR (Tesseract, local).",
                    rows=ocr_rows(gray), qr=read_einvoice_qr(img), preview=gray, steps=steps)
    if kind == "docx":
        return dict(route="docx", reason="Word file. Route: read paragraphs and tables directly.", rows=docx_rows(path), qr=None, preview=None, steps=[])
    return dict(route="unsupported", reason=f"Unsupported file type ({kind}).", rows=[], qr=None, preview=None, steps=[])


# ---------- field parsing (baseline, label based) ----------

def _num(s):
    return float(s.replace(",", "")) if s else None


def _find(rows, pattern, group=1, flags=re.I):
    for r in rows:
        m = re.search(pattern, r["text"], flags)
        if m:
            return m.group(group), r
    return None, None


def _bbox(row, value):
    if not row or not row["words"]:
        return None
    v = re.sub(r"\s", "", str(value)).lower()
    hits = [w for w in row["words"] if len(re.sub(r"\W", "", w["t"])) >= 2 and re.sub(r"\s", "", w["t"]).lower().strip(":") in v]
    hits = hits or row["words"]
    return [min(w["b"][0] for w in hits), min(w["b"][1] for w in hits), max(w["b"][2] for w in hits), max(w["b"][3] for w in hits)]


def _conf(row, value):
    if not row:
        return 0.0
    v = re.sub(r"\s", "", str(value)).lower()
    hits = [w["c"] for w in row["words"] if re.sub(r"\s", "", w["t"]).lower().strip(":") in v and len(w["t"]) >= 2]
    return round(min(hits) if hits else row["conf"], 2)


def parse_fields(rows, buyer_gstin, source):
    """Returns (fields, lines). Each field: value, confidence, source, bbox."""
    F = {}

    def put(name, value, row, conf=None):
        if value is not None and value != "":
            F[name] = dict(value=value, confidence=conf if conf is not None else _conf(row, value), source=source, bbox=_bbox(row, value))

    gstins, seen = [], set()
    for r in rows:  # strict matches first, then OCR repairs after a GSTIN label (accepted only if the checksum holds)
        for g in GSTIN_RE.findall(r["text"]):
            gstins.append((g, r, None))
            seen.add(g)
        for tok in re.findall(r"GSTIN\s*[:.]?\s*([0-9A-Za-z]{15})", r["text"], re.I):
            fixed = repair_gstin(tok)
            if fixed and fixed not in seen and fixed != tok:
                gstins.append((fixed, r, 0.85))
                seen.add(fixed)
    for g, r, conf in gstins:
        name = "buyer_gstin" if g == buyer_gstin else "supplier_gstin"
        if name not in F:
            put(name, g, r, conf)
            if conf:
                F[name]["note"] = "OCR misread corrected by position; checksum verified"
    v, r = _find(rows, r"(?:invoice\s*(?:no\.?|#|number)|bill\s*no\.?)\s*[:.]?\s*([A-Z0-9][A-Z0-9/\-]{2,})")
    put("invoice_no", v, r)
    v, r = _find(rows, r"\bdate\s*[:.]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})")
    put("invoice_date", v, r)
    v, r = _find(rows, r"\b(PO-\d{3,6})\b", flags=0)
    put("po_no", v, r)
    v, r = _find(rows, rf"sub\s*total\s*[:]?\s*({NUM})")
    put("subtotal", _num(v) if v else None, r, _conf(r, v) if v else None)
    v, r = _find(rows, rf"(?<!sub)(?<!sub )total\s*(?:\(inr\))?\s*[:]?\s*(?:rs\.?|inr|₹)?\s*({NUM})")
    put("total", _num(v) if v else None, r, _conf(r, v) if v else None)
    for r in rows:
        for m in re.finditer(rf"\b([CSI]GST)\s*@?\s*(\d+(?:\.\d+)?)\s*%\s*({NUM})", r["text"], re.I):
            put(f"tax_{m.group(1).lower()}", _num(m.group(3)), r, _conf(r, m.group(3)))
            F[f"tax_{m.group(1).lower()}"]["rate"] = float(m.group(2))
    v, r = _find(rows, r"a/?c\.?\s*(?:no\.?)?\s*[:.]?\s*(\d{9,18})")
    put("bank_account", v, r)
    v, r = _find(rows, r"\b([A-Z]{4}0[A-Z0-9]{6})\b", flags=0)
    put("ifsc", v, r)

    lines = []
    line_re = re.compile(rf"^(?:(\d{{1,3}})\s+)?(.*?[A-Za-z].*?)\s+(\d{{4,8}})\s+(\d+(?:\.\d+)?)\s+({NUM})\s+({NUM})$")
    for r in rows:
        m = line_re.match(r["text"].strip())
        if not m:
            continue
        qty, rate, amt = float(m.group(4)), _num(m.group(5)), _num(m.group(6))
        consistent = abs(qty * rate - amt) <= 1
        lines.append(dict(description=m.group(2).strip(), hsn=m.group(3), qty=qty, unit_price=rate, amount=amt,
                          confidence=round(min(_conf(r, m.group(4)), _conf(r, m.group(6))) * (1 if consistent else 0.6), 2),
                          bbox=_bbox(r, m.group(0)), consistent=consistent))
    return F, lines


def qr_fields(qr: dict) -> dict:
    from datetime import datetime
    out = {}
    m = {"SellerGstin": "supplier_gstin", "BuyerGstin": "buyer_gstin", "DocNo": "invoice_no", "DocDt": "invoice_date", "TotInvVal": "total", "Irn": "irn"}
    for k, name in m.items():
        if k in qr:
            out[name] = dict(value=qr[k], confidence=1.0, source="e-invoice QR", bbox=None)
    return out


# ---------- second reader: merge the model's reading with the local parser ----------

MODEL_TO_LOCAL = {"cgst": "tax_cgst", "sgst": "tax_sgst", "igst": "tax_igst"}
NUMERIC_FIELDS = {"subtotal", "total", "tax_cgst", "tax_sgst", "tax_igst"}


def _numbers(text):
    return [float(t.replace(",", "")) for t in re.findall(r"\d[\d,]*(?:\.\d+)?", text) if t.replace(",", "").replace(".", "", 1).isdigit()]


def _norm(s):
    return re.sub(r"\s+", "", str(s)).upper()


def merge_model(F, lines, data, page_text):
    """Every model value must be found on the page. Agreement with the parser raises confidence;
    disagreement keeps the parser's value and lowers confidence so a person confirms it."""
    nums, page = _numbers(page_text), _norm(page_text)
    found = lambda name, v: any(abs(v - x) <= 0.5 for x in nums) if name in NUMERIC_FIELDS else _norm(v) in page
    same = lambda name, a, b: abs(float(a) - float(b)) <= 0.5 if name in NUMERIC_FIELDS else _norm(a) == _norm(b)
    report = dict(agree=[], model_only=[], disagree=[], not_on_page=[])
    for key, v in data.items():
        if key == "line_items" or v in (None, ""):
            continue
        name = MODEL_TO_LOCAL.get(key, key)
        if name in NUMERIC_FIELDS:
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
        if not found(name, v):
            report["not_on_page"].append(f"{name} = {v}")
            if name in F:
                F[name]["confidence"] = min(F[name]["confidence"], 0.7)
            continue
        if name in F:
            if same(name, F[name]["value"], v):
                F[name].update(confidence=max(F[name]["confidence"], 0.97), source="Model + parser")
                report["agree"].append(name)
            elif name.endswith("gstin") and is_valid_gstin(F[name]["value"]) and not is_valid_gstin(_norm(v)):
                F[name]["source"] = "Parser, checksum verified"  # a deterministic check beats both readers
                report.setdefault("checksum_kept", []).append(name)
            else:
                F[name].update(confidence=min(F[name]["confidence"], 0.6), source="Parser; model differs")
                report["disagree"].append(dict(field=name, parser=F[name]["value"], model=v))
        else:
            F[name] = dict(value=v, confidence=0.9, source="Model", bbox=None)
            report["model_only"].append(name)
        if name in ("tax_cgst", "tax_sgst", "tax_igst") and F[name].get("rate") is None and F.get("subtotal"):
            F[name]["rate"] = round(F[name]["value"] / float(F["subtotal"]["value"]) * 100, 2)
    m_lines = []
    for l in data.get("line_items") or []:
        try:
            q, p, a = float(l["qty"]), float(l["unit_price"]), float(l["amount"])
        except (TypeError, ValueError, KeyError):
            continue
        m_lines.append(dict(description=str(l.get("description", "")).strip(), hsn=str(l.get("hsn") or ""), qty=q, unit_price=p, amount=a,
                            confidence=0.9, bbox=None, consistent=abs(q * p - a) <= 1))
    if m_lines and (not lines or not all(l["consistent"] for l in lines)):
        report["lines"] = f"used the model's {len(m_lines)} line items (parser found {len(lines)})"
        lines = m_lines
    elif m_lines:
        ok = len(m_lines) == len(lines) and all(abs(a["amount"] - b["amount"]) <= 1 and abs(a["qty"] - b["qty"]) < 0.01 for a, b in zip(lines, m_lines))
        for l in lines:
            l["confidence"] = max(l["confidence"], 0.97) if ok else min(l["confidence"], 0.6)
        report["lines"] = f"{len(lines)} line item{'' if len(lines) == 1 else 's'}, both readers agree" if ok else "line items differ between readers"
    return F, lines, report
