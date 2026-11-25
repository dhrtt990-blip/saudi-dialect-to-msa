"""Independent V3 release guard; historical V2.2 remains unchanged."""
import csv
import hashlib
import json
from pathlib import Path
from collections import Counter
from src.validate_golden import validate_rows

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["Abdulrahman Mastour Alharthi","Yasser Mansour Alhajlah","Mohammed Adeeb Alrashdi","Musaad Obaied Saad Alqahtani"]
PAIRS = [1, 0, 3, 2]

def test_v3_release_integrity_and_review():
    path = ROOT / "data/golden_v3.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    m = json.loads((ROOT / "GOLDEN_V3_RELEASE_MANIFEST.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == m["sha256"]
    assert [r["id"] for r in rows] == [f"t{i:03d}" for i in range(1, 101)]
    assert len({r["source"] for r in rows}) == 100
    assert sum(len(r["key_facts"]) for r in rows) == 322
    assert sum(bool(r["missing"]) for r in rows) == 40
    canonical = [[r["id"],r["source"],r["reference"],r["key_facts"],r["missing"],r["must_keep"],r["topic"],r.get("notes","")] for r in rows]
    assert hashlib.sha256(json.dumps(canonical,ensure_ascii=False,separators=(",",":")).encode()).hexdigest() == m["canonical_review_content_sha256"]
    with (ROOT / "review/v3_review_evidence.csv").open(encoding="utf-8", newline="") as f:
        evidence = list(csv.DictReader(f))
    with (ROOT / "review/golden_v3_review_approved.csv").open(encoding="utf-8", newline="") as f:
        full = list(csv.DictReader(f))
    assert len(evidence) == len(full) == 100
    for i,(r,e,c) in enumerate(zip(rows,evidence,full)):
        owner,peer=NAMES[i//25],NAMES[PAIRS[i//25]]
        assert r["reviewed_by"] == owner != peer == r["confirmed_by"]
        assert (e["id"],e["owner_primary_approver"],e["peer_reviewer"],e["owner_approval"],e["peer_review"]) == (r["id"],owner,peer,"APPROVED","COMPLETED")
        assert (c["id"],c["source"],c["reference"],c["key_facts"],c["missing"],c["must_keep"],c["reviewed_by"],c["confirmed_by"],c["topic"],c["notes"]) == (r["id"],r["source"],r["reference"],"\n".join(r["key_facts"]),", ".join(r["missing"]),"، ".join(r["must_keep"]),owner,peer,r["topic"],r.get("notes",""))
    assert Counter(r["reviewed_by"] for r in rows) == Counter({n:25 for n in NAMES})
    assert Counter(r["confirmed_by"] for r in rows) == Counter({n:25 for n in NAMES})
    errors,warnings,stats=validate_rows(rows)
    assert not errors, errors
    assert stats["key_facts"] == 322
    assert stats["rows_missing_a_detail"] == 40
