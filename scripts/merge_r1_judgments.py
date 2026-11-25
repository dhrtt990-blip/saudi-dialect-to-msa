"""Join independently completed rating sheets without inventing or reconciling judgments."""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluate import JUDGMENT_COLUMNS, load_judgments


def read_sheet(path: Path) -> dict[str, dict]:
    with path.open(encoding='utf-8-sig', newline='') as fh:
        header = fh.readline()
        fh.seek(0)
        rows = list(csv.DictReader(fh, delimiter=';' if header.count(';') > header.count(',') else ','))
    keys = [row.get('key', '').strip() for row in rows]
    if not all(keys) or len(keys) != len(set(keys)):
        raise ValueError(f'{path}: missing or duplicate judgment key')
    return dict(zip(keys, rows, strict=True))


def merge(template: Path, a_path: Path, b_path: Path, out: Path) -> None:
    truth, a, b = (read_sheet(p) for p in (template, a_path, b_path))
    if truth.keys() != a.keys() or truth.keys() != b.keys():
        raise ValueError('Rating keys do not match this run; historical or partial sheets cannot be silently imported')
    merged = []
    for key, original in truth.items():
        for rating in (a[key], b[key]):
            for field in ('source', 'reference', 'key_facts', 'output'):
                if rating.get(field) != original.get(field):
                    raise ValueError(f'{key}: {field} changed; use the original blind sheet')
        row = {column: original.get(column, '') for column in JUDGMENT_COLUMNS}
        for suffix, rating in (('a', a[key]), ('b', b[key])):
            row[f'rater_{suffix}'] = rating.get(f'rater_{suffix}', '')
            row[f'facts_lost_{suffix}'] = rating.get(f'facts_lost_{suffix}', '')
        row['final'] = ''
        row['facts_lost_final'] = ''
        row['auto_dialect_wrong'] = 'yes' if all(r.get('auto_dialect_wrong', '').strip().lower() in ('yes', 'y', '1', 'true') for r in (a[key], b[key])) else ''
        merged.append(row)
    if out.exists():
        raise FileExistsError(f'{out}: refusing to replace existing human work')
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='', dir=out.parent, delete=False) as fh:
            tmp = Path(fh.name)
            writer = csv.DictWriter(fh, fieldnames=JUDGMENT_COLUMNS)
            writer.writeheader()
            writer.writerows(merged)
        load_judgments(tmp, {k: len(r.get('key_facts', '').splitlines()) for k, r in truth.items()})
        os.link(tmp, out)  # Atomic create; never replace an existing human sheet.
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for field in ('template', 'a', 'b', 'out'):
        parser.add_argument(f'--{field}', type=Path, required=True)
    args = parser.parse_args()
    merge(args.template, args.a, args.b, args.out)
    print('Imported original independent judgments. No reconciliation or human verdict was invented.')
