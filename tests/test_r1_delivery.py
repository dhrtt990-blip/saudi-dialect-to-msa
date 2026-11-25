"""Synthetic unit fixtures only; these are not project human ratings or model results."""
import csv

import pytest

from scripts.merge_r1_judgments import merge
from scripts.summarize_r1 import sign_test
from src.evaluate import JUDGMENT_COLUMNS, load_judgments


def sheet(path, **changes):
    row = dict.fromkeys(JUDGMENT_COLUMNS, '')
    row.update(key='unit_test_key', source='test source', reference='test reference',
               key_facts='1. test fact', output='test output')
    row.update(changes)
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=JUDGMENT_COLUMNS)
        writer.writeheader()
        writer.writerow(row)


def test_blank_sheets_do_not_become_human_judgments(tmp_path):
    paths = [tmp_path / n for n in ('template.csv', 'a.csv', 'b.csv')]
    for path in paths:
        sheet(path)
    out = tmp_path / 'joined.csv'
    merge(*paths, out)
    result = load_judgments(out)['unit_test_key']
    assert result['verdict'] is None and result['facts_a'] is None
    with pytest.raises(FileExistsError):
        merge(*paths, out)


@pytest.mark.parametrize('alteration', [{'output': 'other run'}, {'key': 'other_key'}, {'key_facts': '1. changed fact'}])
def test_changed_run_or_fact_labels_are_rejected(tmp_path, alteration):
    template, a, b, out = [tmp_path / n for n in ('template.csv', 'a.csv', 'b.csv', 'joined.csv')]
    sheet(template)
    sheet(a, **alteration)
    sheet(b)
    with pytest.raises(ValueError):
        merge(template, a, b, out)
    assert not out.exists()


def test_invalid_rating_does_not_create_a_deliverable(tmp_path):
    template, a, b, out = [tmp_path / n for n in ('template.csv', 'a.csv', 'b.csv', 'joined.csv')]
    sheet(template)
    sheet(a, rater_a='not_a_verdict')
    sheet(b)
    with pytest.raises(ValueError):
        merge(template, a, b, out)
    assert not out.exists()


def test_exact_two_sided_sign_test_known_probabilities():
    assert sign_test(0, 0) == 1
    assert sign_test(5, 5) == 1
    assert sign_test(10, 0) == 2 / 1024
    assert sign_test(0, 10) == 2 / 1024
