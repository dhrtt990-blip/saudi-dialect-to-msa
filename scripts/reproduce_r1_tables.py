"""Recompute R1 tables in a clean folder using only saved predictions and ratings."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reproduce(root: Path) -> dict:
    manifest = json.loads((root / 'release_manifest.json').read_text())
    results = root / 'results/v3_r1'
    original = json.loads((results / 'metrics.json').read_text())
    golden = root / 'data/golden_v3_r1_candidate.jsonl'
    assert digest(golden) == manifest['golden_sha256']
    assert original['meta']['n'] == 100 and not original['meta']['dry_run'] and not original['meta']['partial']
    for name, expected in manifest['prediction_sha256'].items():
        assert digest(results / f'predictions_{name}.jsonl') == expected
    with tempfile.TemporaryDirectory(prefix='r1-tables-') as temporary:
        out = Path(temporary)
        cmd = [sys.executable, '-m', 'src.evaluate', '--golden', str(golden),
               '--from-predictions', str(results), '--out', str(out)]
        if manifest.get('judgments_file'):
            cmd += ['--judgments', str(root / manifest['judgments_file'])]
        subprocess.run(cmd, cwd=root, check=True, capture_output=True, text=True)
        rebuilt = json.loads((out / 'metrics.json').read_text())
        for key in ('scores', 'transitions'):
            assert rebuilt[key] == original[key], f'{key} changed on reproduction'
        for key in ('needs', 'guessing', 'deployed', 'checker', 'agreement'):
            assert rebuilt['meta'].get(key) == original['meta'].get(key), f'{key} changed on reproduction'
    return {'reproduced': True, 'golden_sha256': manifest['golden_sha256'],
            'systems': {name: {'n': score['n'], 'released': score['released'],
                              'auto_pass': score['auto_pass'], 'withheld': score['withheld'], 'correct': score['correct']}
                        for name, score in original['scores'].items()},
            'model_calls': 0, 'new_human_judgments': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = reproduce(args.root.resolve())
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
