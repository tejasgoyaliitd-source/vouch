"""The second reader must never add a value that is not on the page, and must flag disagreements."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ap.extract import merge_model  # noqa: E402

PAGE = "TAX INVOICE Invoice No.: INV/2026/117 Date: 12/11/2026 PO No: PO-4471 Subtotal 72,000.00 IGST 18% 12,960.00 Total (INR) 84,960.00"


def local():
    f = lambda v, c=0.99: dict(value=v, confidence=c, source="text layer", bbox=None)
    return {"invoice_no": f("INV/2026/117"), "total": f(84960.0), "subtotal": f(72000.0)}, []


def test_agreement_raises_confidence():
    F, _, rep = merge_model(*local(), {"invoice_no": "INV/2026/117", "total": 84960, "subtotal": 72000, "line_items": []}, PAGE)
    assert set(rep["agree"]) == {"invoice_no", "total", "subtotal"} and F["total"]["source"] == "Model + parser"


def test_value_not_on_page_is_dropped():
    F, _, rep = merge_model(*local(), {"po_no": "PO-9999", "line_items": []}, PAGE)
    assert "po_no" not in F and rep["not_on_page"]


def test_model_fills_a_gap_only_with_page_values():
    F, _, rep = merge_model(*local(), {"po_no": "PO-4471", "igst": 12960, "line_items": []}, PAGE)
    assert F["po_no"]["value"] == "PO-4471" and F["tax_igst"]["value"] == 12960 and F["tax_igst"]["rate"] == 18


def test_checksum_valid_gstin_beats_a_copied_ocr_misread():
    page = PAGE + " GSTIN: O6BQZPK2266H1ZC"
    F = {"supplier_gstin": dict(value="06BQZPK2266H1ZC", confidence=0.85, source="OCR", bbox=None)}
    F, _, rep = merge_model(F, [], {"supplier_gstin": "O6BQZPK2266H1ZC", "line_items": []}, page)
    assert F["supplier_gstin"]["confidence"] == 0.85 and not rep["disagree"] and rep["checksum_kept"] == ["supplier_gstin"]


def test_disagreement_keeps_parser_and_flags():
    F, _, rep = merge_model(*local(), {"total": 72000, "line_items": []}, PAGE)  # on the page, but not the total
    assert F["total"]["value"] == 84960.0 and F["total"]["confidence"] <= 0.6 and rep["disagree"][0]["field"] == "total"
