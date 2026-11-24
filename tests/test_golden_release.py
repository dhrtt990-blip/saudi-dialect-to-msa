"""Regression guard for the approved local benchmark and its recorded provenance.

The release is recognised by its ids: `g001`... is release v2.2 (general service topics), `t001`... is
release v3 (travel booking desk, with key facts and missing details labelled). The same file therefore
holds before and after the v3 freeze (docs/GOLDEN_V3_FREEZE_STEPS.md)."""
from collections import Counter
from pathlib import Path
import hashlib
import json

from src.common import read_jsonl
from src.validate_golden import validate_rows

ROOT = Path(__file__).resolve().parents[1]


def release(rows):
    prefix = rows[0]["id"][0]
    assert prefix in ("g", "t")
    return "v2.2" if prefix == "g" else "v3"


def test_golden_release_has_complete_and_distinct_roster():
    rows = read_jsonl(ROOT / "data/golden_test.jsonl")
    assert len(rows) == 100
    prefix = "g" if release(rows) == "v2.2" else "t"
    assert [x["id"] for x in rows] == [f"{prefix}{i:03d}" for i in range(1, 101)]
    assert sorted(Counter(x["confirmed_by"] for x in rows).values()) == [25, 25, 25, 25]
    assert sorted(Counter(x["reviewed_by"] for x in rows).values()) == [25, 25, 25, 25]
    for x in rows:
        assert x["reviewed_by"] != x["confirmed_by"]
        assert x["drafted_by"] == "ai_assistant"

def test_golden_sha256_and_validation():
    data = (ROOT / "data/golden_test.jsonl").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert (ROOT / "data/golden_test.sha256").read_text(encoding="utf-8").split()[0] == digest
    report = json.loads((ROOT / "data/golden_test_review.json").read_text(encoding="utf-8"))
    assert report["golden_sha256"] == digest
    rows = read_jsonl(ROOT / "data/golden_test.jsonl")
    # The release records name the same file: a new golden test is not frozen until they are updated with it.
    manifest = json.loads((ROOT / "GOLDEN_RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["sha256"] == digest and manifest["release"] == release(rows)
    assert f"{digest}  data/golden_test.jsonl" in (ROOT / "RELEASE_CHECKSUMS_SHA256.txt").read_text(encoding="utf-8")
    errors, warnings, stats = validate_rows(rows)
    assert not errors
    if release(rows) == "v2.2":
        assert len(warnings) == 1
    else:
        # Every message carries both labels (an empty list says "none"), nearly all have a key fact, and enough
        # messages lack a needed detail for the measurement to mean something.
        assert all(isinstance(x.get("key_facts"), list) and isinstance(x.get("missing"), list) for x in rows)
        assert sum(1 for x in rows if x["key_facts"]) >= 95 and stats["rows_missing_a_detail"] >= 25

def test_g032_reference_follows_recorded_canonical_source():
    rows = read_jsonl(ROOT / "data/golden_test.jsonl")
    if release(rows) != "v2.2":
        return
    row = next(x for x in rows if x["id"] == "g032")
    assert "قلتم:" in row["reference"]
