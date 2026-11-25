"""Reload a saved R1 adapter, run validation smoke checks, and save matched HF exports.

Run after releasing the training model from GPU memory. This does not publish
weights or evaluate Golden R1. Convert both exports with the same pinned converter.
"""
from __future__ import annotations

import argparse
import gc
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.common import read_jsonl, sha256_file
from src.facts import compare_facts
from src.pipeline import clean_output


def export(run_dir: Path, export_dir: Path) -> dict:
    import torch
    from peft import PeftConfig, PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    provenance = json.loads((run_dir / 'provenance.json').read_text())
    manifest = json.loads((ROOT / 'review/v3_r1_revision_manifest.json').read_text())
    assert provenance['status'] == 'training_saved' and provenance['global_step'] > 0
    assert provenance['golden_sha256'] == manifest['sha256']
    assert sha256_file(ROOT / manifest['candidate']) == manifest['sha256']
    adapter = run_dir / 'final_adapter'
    adapter_weights = adapter / 'adapter_model.safetensors'
    config = PeftConfig.from_pretrained(str(adapter))
    assert config.r == 16 and config.lora_alpha == 32
    base_id = config.base_model_name_or_path
    assert base_id == 'Qwen/Qwen3-1.7B'
    revision = provenance.get('base_model_revision')
    assert revision, 'Record trainer.model.config._commit_hash before releasing the training model'
    export_dir.mkdir(parents=True, exist_ok=False)
    base_dir, merged_dir = export_dir / 'base', export_dir / 'merged'
    tok = AutoTokenizer.from_pretrained(str(adapter))
    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    dtype = torch.float16 if device.startswith('cuda') else torch.float32
    base = AutoModelForCausalLM.from_pretrained(base_id, revision=revision, dtype=dtype, device_map=device)
    base_revision = getattr(base.config, '_commit_hash', None)
    assert base_revision == revision
    # Save the unadapted weights before PeftModel mutates this model.
    base.save_pretrained(base_dir, max_shard_size='2GB')
    tok.save_pretrained(base_dir)
    restored = PeftModel.from_pretrained(base, str(adapter))
    restored.eval()
    validation_path = ROOT / 'data/processed_v3_r1/val.jsonl'
    assert sha256_file(validation_path) == provenance['prep_report']['val_sha256']
    rows = read_jsonl(validation_path)[:5]
    smoke = []
    for row in rows:
        messages = row['messages']
        prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = tok(prompt, return_tensors='pt').to(restored.device)
        with torch.inference_mode():
            tokens = restored.generate(**inputs, max_new_tokens=256, do_sample=False)
        text = clean_output(tok.decode(tokens[0, inputs['input_ids'].shape[1]:], skip_special_tokens=True))
        assert text, 'Restored adapter returned no text'
        check = compare_facts(messages[1]['content'], text)
        smoke.append({'source': messages[1]['content'], 'reference': messages[-1]['content'],
                      'output': text, 'automatic_fact_check_ok': check.ok})
    (run_dir / 'reload_smoke.json').write_text(json.dumps(smoke, ensure_ascii=False, indent=2))
    merged = restored.merge_and_unload(safe_merge=True)
    merged.save_pretrained(merged_dir, max_shard_size='2GB')
    tok.save_pretrained(merged_dir)
    result = {'saved_utc': datetime.now(timezone.utc).isoformat(), 'base_model': base_id,
              'base_revision': base_revision, 'adapter_sha256': sha256_file(adapter_weights),
              'adapter_config_sha256': sha256_file(adapter / 'adapter_config.json'),
              'base_dir': str(base_dir), 'merged_dir': str(merged_dir), 'smoke_count': len(smoke),
              'successful_reload': True, 'device': device, 'dtype': str(dtype), 'platform': platform.platform(),
              'golden_sha256': manifest['sha256'], 'training_code_commit': provenance['code_commit']}
    (run_dir / 'export_manifest.json').write_text(json.dumps(result, indent=2))
    del merged, restored, base
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--export-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.run_dir, args.export_dir), indent=2))
