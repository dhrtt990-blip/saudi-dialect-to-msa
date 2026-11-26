import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_travel_notebook_requires_active_release_and_uses_only_v3_r2():
    nb = json.loads((ROOT / "notebooks/train_qwen3_lora_colab.ipynb").read_text(encoding="utf-8"))
    source = ["".join(c.get("source", [])) for c in nb["cells"]]
    assert "data/golden_test.jsonl" not in "\n".join(source)
    assert 'GOLDEN_PATH = "data/golden_v3_r2.jsonl"' in source[2]
    assert 'm.get("status") == "FROZEN_ACTIVE"' in source[7]
    assert "hashlib.sha256" in source[7]
    assert "freeze_commit" in source[7]
    assert "V3_PREP_OK" in source[10] and "V3_PREP_OK" in source[15]
    record = json.loads((ROOT / "review/v3_r2_release.json").read_text(encoding="utf-8"))
    prior = json.loads((ROOT / "review/v3_r1_revision_manifest.json").read_text(encoding="utf-8"))
    assert record["status"] == "FROZEN_ACTIVE"
    assert prior["status"] == "FROZEN_SUPERSEDED"
    assert record["freeze_commit"] == "31b8de5d38e5c44bc7eb7fcc92ea0b59d06cae71"
    assert record["sha256"] in source[7]
    assert "data/golden_v3_r1_candidate.jsonl" not in "\n".join(source)
    assert "V3_PREFLIGHT_OK" in source[10] and "V3_PREFLIGHT_OK" in source[15]
    assert '"--golden", GOLDEN_PATH' in source[10]
    assert "results/v3_r2" in source[29]
