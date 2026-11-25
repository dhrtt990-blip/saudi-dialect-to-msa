import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_travel_notebook_requires_active_release_and_uses_only_v3_r1():
    nb = json.loads((ROOT / "notebooks/train_qwen3_lora_colab.ipynb").read_text(encoding="utf-8"))
    source = ["".join(c.get("source", [])) for c in nb["cells"]]
    assert "data/golden_test.jsonl" not in "\n".join(source)
    assert 'GOLDEN_PATH = "data/golden_v3_r1_candidate.jsonl"' in source[2]
    assert 'm.get("status") == "FROZEN_ACTIVE"' in source[7]
    assert "hashlib.sha256" in source[7]
    assert "freeze_commit" in source[7]
    assert "V3_PREFLIGHT_OK" in source[10] and "V3_PREFLIGHT_OK" in source[15]
    assert '"--golden", GOLDEN_PATH' in source[10]
    assert "results/v3_r1" in source[29]
