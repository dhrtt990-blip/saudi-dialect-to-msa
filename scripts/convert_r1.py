"""Convert the matched, verified HF exports with one pinned llama.cpp checkout.

Run with the converter's separate Python environment, after export_r1.py succeeds.
This script neither installs dependencies nor publishes files.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common import sha256_file

CONVERTER_COMMIT = 'bb692efaa43809dd8584fefddda42a54a9a50846'


def convert(run_dir: Path, export_dir: Path, converter: Path, output: Path) -> dict:
    manifest = json.loads((run_dir / 'export_manifest.json').read_text())
    assert manifest['successful_reload'] and manifest['smoke_count'] == 5
    assert sha256_file(run_dir / 'final_adapter/adapter_model.safetensors') == manifest['adapter_sha256']
    actual = subprocess.check_output(['git', '-C', str(converter), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == CONVERTER_COMMIT, f'Wrong converter checkout: {actual}'
    assert not subprocess.check_output(['git', '-C', str(converter), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    output.mkdir(parents=True, exist_ok=True)
    result = {'created_utc': datetime.now(timezone.utc).isoformat(), 'converter_commit': actual,
              'converter_script_sha256': sha256_file(converter / 'convert_hf_to_gguf.py'),
              'adapter_sha256': manifest['adapter_sha256'], 'base_revision': manifest['base_revision'],
              'golden_sha256': manifest['golden_sha256'], 'outtype': 'q8_0', 'files': {}}
    for kind, name in [('base', 'travel-v3-r1-qwen3-base-q8_0.gguf'),
                       ('merged', 'travel-v3-r1-qwen3-1.7b-q8_0.gguf')]:
        source = (export_dir / kind).resolve()
        assert source == Path(manifest[f'{kind}_dir']).resolve()
        target = output / name
        assert not target.exists(), f'Refusing to overwrite {target}'
        cmd = [sys.executable, str(converter / 'convert_hf_to_gguf.py'), str(source),
               '--outfile', str(target.resolve()), '--outtype', 'q8_0', '--use-temp-file']
        with (output / f'conversion_{kind}.log').open('w') as log:
            subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
        with target.open('rb') as fh:
            assert fh.read(4) == b'GGUF'
        assert target.stat().st_size > 1_000_000_000
        result['files'][kind] = {'name': name, 'bytes': target.stat().st_size,
                                 'sha256': sha256_file(target), 'command': cmd,
                                 'source_sha256': {p.name: sha256_file(p) for p in sorted(source.iterdir()) if p.is_file()}}
    (output / 'conversion_manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--export-dir', type=Path, required=True)
    parser.add_argument('--converter', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(convert(args.run_dir, args.export_dir, args.converter, args.out), indent=2))
