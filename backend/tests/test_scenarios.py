"""Success criteria for the slice: each demo input must produce the decision the design says it should.
Runs the real pipeline (real OCR, real QR decoding) on a fresh database, in demo order.
Run: .venv/Scripts/python -m pytest -q tests   (or: python tests/test_scenarios.py)"""
import os
import sys
from pathlib import Path

os.environ["AP_DB"] = str(Path(__file__).parent / "test.db")
os.environ["STAGE_DELAY"] = "0"
os.environ["MODEL_PROVIDER"] = "off"  # the rules are tested without network calls; test_merge covers the second reader
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ap import db, pipeline  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

EXPECTED = [  # file, outcome, rules that must fail, rules that must warn
    ("happy_acme_einvoice.eml", "approved", set(), set()),
    ("e1_bank_change.eml", "security", {"R07", "R08"}, set()),
    ("e2_po_overbilled.eml", "hold", {"R15"}, set()),
    ("e3_resent_scan.eml", "rejected", {"R09"}, set()),
    ("IMG_2041.jpg", "hold", {"R17"}, {"R11"}),
]


def run_all():
    db.reset()
    out = []
    for name, *_ in EXPECTED:
        run_id = pipeline.run_sync((SAMPLES / name).read_bytes(), name, "upload" if not name.endswith(".eml") else None)
        inv = db.one("SELECT i.* FROM invoices i JOIN runs r ON r.invoice_id=i.invoice_id WHERE r.run_id=?", (run_id,))
        res = db.q("SELECT rule_id, outcome FROM rule_results WHERE invoice_id=?", (inv["invoice_id"],))
        out.append((inv, {r["rule_id"] for r in res if r["outcome"] == "fail"}, {r["rule_id"] for r in res if r["outcome"] == "warn"}))
    return out


def test_scenarios():
    results = run_all()
    for (name, outcome, must_fail, must_warn), (inv, failed, warned) in zip(EXPECTED, results):
        assert inv["outcome"] == outcome, f"{name}: expected {outcome}, got {inv['outcome']} ({inv['outcome_title']})"
        assert must_fail <= failed, f"{name}: expected failures {must_fail}, got {failed}"
        assert must_warn <= warned, f"{name}: expected warnings {must_warn}, got {warned}"
    assert db.verify_chain(), "audit event chain broken"


if __name__ == "__main__":
    for (name, *_), (inv, failed, warned) in zip(EXPECTED, run_all()):
        print(f"{name:28s} -> {inv['outcome']:9s} | {inv['outcome_title']} | failed {sorted(failed)} warned {sorted(warned)}")
    print("audit chain intact:", db.verify_chain())
