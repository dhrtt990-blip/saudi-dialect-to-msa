"""Regression guard for the approved local benchmark and its recorded provenance."""
from collections import Counter
from pathlib import Path
import hashlib
import json

from src.common import read_jsonl
from src.validate_golden import validate_rows

ROOT = Path(__file__).resolve().parents[1]

def test_golden_release_has_complete_and_distinct_roster():
    rows = read_jsonl(ROOT / "data/golden_test.jsonl")
    assert len(rows) == 100
    assert [x["id"] for x in rows] == [f"g{i:03d}" for i in range(1, 101)]
    assert sorted(Counter(x["confirmed_by"] for x in rows).values()) == [25, 25, 25, 25]
    assert sorted(Counter(x["reviewed_by"] for x in rows).values()) == [25, 25, 25, 25]
    for x in rows:
        assert x["reviewed_by"] != x["confirmed_by"]
        assert x["drafted_by"] == "ai_assistant"

def test_golden_sha256_and_validation():
    data = (ROOT / "data/golden_test.jsonl").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert (ROOT / "data/golden_test.sha256").read_text().split()[0] == digest
    report = json.loads((ROOT / "data/golden_test_review.json").read_text())
    assert report["golden_sha256"] == digest
    rows = read_jsonl(ROOT / "data/golden_test.jsonl")
    errors, warnings, _ = validate_rows(rows)
    assert not errors
    assert len(warnings) == 1

def test_g032_reference_follows_recorded_canonical_source():
    rows = read_jsonl(ROOT / "data/golden_test.jsonl")
    row = next(x for x in rows if x["id"] == "g032")
    assert "قلتم:" in row["reference"]
