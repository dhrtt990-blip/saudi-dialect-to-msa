"""Recheck the frozen release and written splits without fitting or changing data."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common import read_jsonl, sha256_file
from src.data_prep import GoldenIndex, distinctive_facts
from src.evaluate import score_needs


def audit(root: Path = ROOT) -> dict:
    manifest = json.loads((root / 'review/v3_r1_revision_manifest.json').read_text())
    assert manifest['status'] == 'FROZEN_ACTIVE'
    golden_path = root / manifest['candidate']
    assert sha256_file(golden_path) == manifest['sha256']
    golden = read_jsonl(golden_path)
    assert [r['id'] for r in golden] == [f't{i:03}' for i in range(1, 101)]
    prep = json.loads((root / 'data/processed_v3_r1/prep_report.json').read_text())
    assert prep['golden_sha256'] == manifest['sha256']
    index = GoldenIndex(golden, prep['thresholds']['near_duplicate'], prep['thresholds']['shared_content'])
    golden_facts = set().union(*(distinctive_facts(r[k]) for r in golden for k in ('source', 'reference')))
    splits = {}
    for name in ('train', 'val'):
        path = root / f'data/processed_v3_r1/{name}.jsonl'
        assert sha256_file(path) == prep[f'{name}_sha256']
        rows = read_jsonl(path)
        texts = [m['content'] for r in rows for m in r['messages'][1:]]
        overlaps = [i for i, t in enumerate(texts) if index.match(t)]
        shared = [i for i, t in enumerate(texts) if distinctive_facts(t) & golden_facts]
        assert not overlaps and not shared, f'{name}: residual golden overlap'
        splits[name] = {'rows': len(rows), 'sha256': sha256_file(path),
                        'golden_text_overlap': len(overlaps), 'golden_distinctive_fact_overlap': len(shared)}
    return {'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'golden_sha256': manifest['sha256'], 'freeze_commit': manifest['freeze_commit'],
            'splits': splits, 'needs': score_needs(golden)}


if __name__ == '__main__':
    out = ROOT / 'evidence/v3_r1'
    out.mkdir(parents=True, exist_ok=True)
    result = audit()
    (out / 'independent_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'needs'}, indent=2))
