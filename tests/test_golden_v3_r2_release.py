import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_r2_context_revision():
    old = (ROOT / "data/golden_v3_r1_candidate.jsonl").read_bytes()
    new = (ROOT / "data/golden_v3_r2.jsonl").read_bytes()
    record = json.loads((ROOT / "review/v3_r2_release.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(old).hexdigest() == "e1dbff1b7a8045dc061a622b1233d2ccee8ef4b5901202a2f6391e9c906ef8e6"
    assert hashlib.sha256(new).hexdigest() == record["sha256"] == "5b6de8add8fbd466316fa9dfc230d96af1b48d4d4278f8b5a16ccdbd71712275"
    a, b = ([json.loads(line) for line in data.splitlines()] for data in (old, new))
    assert [r["id"] for r in b] == [f"t{i:03d}" for i in range(1, 101)]
    assert len(a) == len(b) == 100
    assert all({k:v for k,v in x.items() if k != "key_facts"} == {k:v for k,v in y.items() if k != "key_facts"} for x,y in zip(a,b))
    assert all(len(x["key_facts"]) == len(y["key_facts"]) for x,y in zip(a,b))
    assert sum(x["key_facts"] != y["key_facts"] for x,y in zip(a,b)) == 96
    assert sum(v != w for x,y in zip(a,b) for v,w in zip(x["key_facts"],y["key_facts"])) == 274
    assert sum(len(y["key_facts"]) for y in b) == 335
    assert not any(re.fullmatch(r"[\d.,:/]+", v.strip()) for y in b for v in y["key_facts"])
    assert b[8]["key_facts"] == ["حقيبة وزنها 23 كيلوغراماً", "حجزي رقم 35178"]
