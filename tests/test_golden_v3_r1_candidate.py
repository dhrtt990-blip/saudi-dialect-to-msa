"""Regression guard for the separately leader-authorized V3-R1 candidate."""
import hashlib
import json
import csv
from pathlib import Path
from src.validate_golden import validate_rows

ROOT = Path(__file__).resolve().parents[1]

def test_v3_r1_exact_delta_and_integrity(historical_snapshot):
    ROOT = historical_snapshot
    old_path = ROOT / "data/golden_v3.jsonl"
    new_path = ROOT / "data/golden_v3_r1_candidate.jsonl"
    m = json.loads((ROOT / "review/v3_r1_revision_manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == m["source_sha256"]
    assert hashlib.sha256(new_path.read_bytes()).hexdigest() == m["sha256"]
    old = [json.loads(x) for x in old_path.read_text(encoding="utf-8").splitlines()]
    new = [json.loads(x) for x in new_path.read_text(encoding="utf-8").splitlines()]
    assert len(old) == len(new) == 100
    with (ROOT / "review/v3_r1_technical_changes.csv").open(encoding="utf-8", newline="") as f:
        log = {r["id"]: r for r in csv.DictReader(f)}
    expected = set(["t008","t015","t037","t055","t056","t064","t076","t081","t083","t087","t097"])
    assert set(log) == expected
    changed = set()
    for a, b in zip(old, new):
        assert a["id"] == b["id"]
        assert {k:v for k,v in a.items() if k != "key_facts"} == {k:v for k,v in b.items() if k != "key_facts"}
        if a["key_facts"] != b["key_facts"]:
            changed.add(a["id"])
            assert a["key_facts"] == json.loads(log[a["id"]]["before"])
            assert b["key_facts"] == json.loads(log[a["id"]]["after"])
    assert changed == expected
    assert sum(len(r["key_facts"]) for r in new) == 335
    assert sum(bool(r["missing"]) for r in new) == 40
    assert "ألّا تكون في طابق مرتفع" in next(r for r in new if r["id"] == "t076")["key_facts"]
    assert "تذكرة واحدة فقط" in next(r for r in new if r["id"] == "t087")["key_facts"]
    errors, warnings, stats = validate_rows(new)
    assert not errors, errors
    assert stats["key_facts"] == 335
    assert stats["rows_missing_a_detail"] == 40
