from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_only_current_benchmark_files_are_in_data():
    assert sorted(p.name for p in (ROOT / "data").glob("golden*")) == ["golden_v3_r2.jsonl", "golden_v3_r2.sha256"]
