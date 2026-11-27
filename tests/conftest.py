"""Make the repository root importable so tests can `import src...` from a clean clone."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Historical datasets are retrieved only into pytest temporary storage. They are
# never restored to the working data directory or used for new experiments.
import subprocess
import pytest

HISTORICAL_COMMIT = "bb4b3e358969bceae47fc6369d8a46c31115abaa"
HISTORICAL_FILES = [
    "data/golden_draft_ai.jsonl",
    "data/golden_test.jsonl",
    "data/golden_test.sha256",
    "data/golden_test_review.json",
    "data/golden_test_template.jsonl",
    "data/golden_v3.jsonl",
    "data/golden_v3.sha256",
    "data/golden_v3_draft.jsonl",
    "data/golden_v3_r1_candidate.jsonl",
    "data/golden_v3_r1_candidate.sha256",
    "review/golden_v3_review_approved.csv",
    "GOLDEN_V3_RELEASE_MANIFEST.json",
    "review/v3_review_evidence.csv",
    "review/v3_r1_revision_manifest.json",
    "review/v3_r1_technical_changes.csv"
]

@pytest.fixture(scope="session")
def historical_snapshot(tmp_path_factory):
    directory = tmp_path_factory.mktemp("historical_regression")
    for name in HISTORICAL_FILES:
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(subprocess.check_output(["git", "show", f"{HISTORICAL_COMMIT}:{name}"], cwd=ROOT))
    return directory
