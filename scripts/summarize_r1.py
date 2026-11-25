"""Rebuild a public aggregate and separate blank rater sheets from actual R1 predictions."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common import sha256_file
from src.evaluate import HUMAN_ERRORS, SYSTEMS


def sign_test(better: int, worse: int) -> float:
    n = better + worse
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(better, worse) + 1)) / 2**n) if n else 1.0


def public_score(score: dict) -> dict:
    result = {k: score[k] for k in (
        'n', 'released', 'withheld', 'no_output', 'repaired', 'auto_pass', 'correct',
        'fully_judged', 'judged', 'released_with_fact_error', 'released_with_added_fact',
        'key_facts', 'error_counts', 'chrf_mean')}
    result['key_facts'] = dict(result['key_facts'])
    result['error_counts'] = dict(result['error_counts'])
    facts = result['key_facts']
    if not facts['judged']:
        for key in ('lost', 'lost_checker_reads', 'lost_outside_checker', 'lost_although_found_automatically', 'disputed'):
            facts[key] = None
    if not score['verdicts_judged']:
        for key in HUMAN_ERRORS:
            result['error_counts'][key] = None
    result['human_judgment_status'] = 'complete' if score['fully_judged'] else 'partial' if score['verdicts_judged'] or facts['judged'] else 'pending'
    return result


def summarize(directory: Path) -> dict:
    metrics = json.loads((directory / 'metrics.json').read_text())
    manifest = json.loads((ROOT / 'review/v3_r1_revision_manifest.json').read_text())
    meta, scores = metrics['meta'], metrics['scores']
    assert meta['golden_sha256'] == manifest['sha256']
    assert meta['n'] == 100 and not meta['dry_run'] and not meta['partial']
    prediction_hashes = {}
    systems = {}
    for name in SYSTEMS:
        score = scores[name]
        assert score['n'] == 100
        assert {r['id'] for r in score['per_example']} == {f't{i:03}' for i in range(1, 101)}
        prediction_hashes[name] = sha256_file(directory / f'predictions_{name}.jsonl')
        systems[name] = public_score(score)
    needs = meta['needs']
    exact = needs['asked_exactly'] / needs['incomplete']
    needless = needs['needless_asks'] / needs['complete']
    full = scores['full']
    targets = {
        'T1': {'status': 'pending_human_judgments'},
        'T2': {'status': 'pending_human_judgments'},
        'T3': {'withheld': full['withheld'], 'denominator': 100,
               'withholding_limit_met': full['withheld'] <= 15,
               'status': 'not_met' if full['withheld'] > 15 else 'pending_human_judgments'},
        'T4': {'exact_requests': needs['asked_exactly'], 'incomplete': needs['incomplete'],
               'needless_requests': needs['needless_asks'], 'complete': needs['complete'],
               'status': 'met' if exact >= .8 and needless <= .1 else 'not_met'},
    }
    if all(scores[n]['fully_judged'] for n in SYSTEMS):
        transition = next(t for t in metrics['transitions'] if t['before'] == 'baseline' and t['after'] == 'tuned')
        assert transition['key'] == 'correct'
        better, worse = transition['wrong_to_right'], transition['right_to_wrong']
        p_value = sign_test(better, worse)
        targets['T1'] = {'net_gain': better - worse, 'wrong_to_right': better, 'right_to_wrong': worse,
                         'two_sided_sign_test_p': p_value, 'status': 'met' if better - worse >= 10 and p_value < .05 else 'not_met'}
        checker = meta['checker']
        if not checker['released_not_judged']:
            targets['T2'] = {'released_problems': checker['released_problem'],
                             'released': full['released'], 'status': 'met' if checker['released_problem'] <= 3 else 'not_met'}
        if not checker['withheld_not_judged']:
            targets['T3'].update(incorrect_withholds=checker['withheld_fine'],
                                  status='met' if full['withheld'] <= 15 and checker['withheld_fine'] <= 5 else 'not_met')
    return {'release': 'Golden V3-R1', 'golden_sha256': manifest['sha256'],
            'clients': meta['clients'], 'prediction_sha256': prediction_hashes,
            'systems': systems, 'targets': targets, 'agreement': meta.get('agreement'),
            'transitions': [{k: v for k, v in t.items() if not k.endswith('_ids')} for t in metrics['transitions']],
            'needs': {k: v for k, v in needs.items() if k not in ('rows', 'missed_ids', 'inexact_ids', 'needless_ids')},
            'interpretation': 'Automatic passes do not establish semantic correctness. Unjudged human outcomes are null or pending, never zero.'}


def prepare_sheets(directory: Path) -> None:
    template = directory / 'judgments_template.csv'
    if not template.exists():
        return
    with template.open(encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    for rater in ('a', 'b'):
        out = directory / f'blind_rater_{rater.upper()}.csv'
        if out.exists():
            continue
        columns = ['key', 'source', 'reference', 'key_facts', 'output', f'rater_{rater}', f'facts_lost_{rater}', 'auto_dialect_wrong']
        with out.open('w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=ROOT / 'results/v3_r1')
    args = parser.parse_args()
    result = summarize(args.results)
    (args.results / 'aggregate_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    prepare_sheets(args.results)
    print(json.dumps(result['targets'], indent=2))
