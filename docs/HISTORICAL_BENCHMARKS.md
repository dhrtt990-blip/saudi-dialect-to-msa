# Historical benchmark archive

Only `data/golden_v3_r2.jsonl` and its checksum are current. Older test sets, draft files, duplicate review workbooks and the old notebook were removed from the current branch at the team leader's request; no history was rewritten.

All original bytes, initial-draft provenance, review evidence and historical results remain recoverable from [the pre-cleanup commit](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/tree/bb4b3e358969bceae47fc6369d8a46c31115abaa). Historical manifest paths refer to that snapshot, not the current working tree. Regression tests retrieve historical inputs into temporary storage only; use a full Git clone for these tests. The original V3-R2 freeze commit and digest remain unchanged.

Removed paths:
- `data/golden_draft_ai.jsonl`
- `data/golden_test.jsonl`
- `data/golden_test.sha256`
- `data/golden_test_review.json`
- `data/golden_test_template.jsonl`
- `data/golden_v3.jsonl`
- `data/golden_v3.sha256`
- `data/golden_v3_draft.jsonl`
- `data/golden_v3_r1_candidate.jsonl`
- `data/golden_v3_r1_candidate.sha256`
- `review/golden_review_approved.xlsx`
- `review/golden_v3_review_approved.csv`
- `notebooks/archive/train_qwen3_lora_colab_v2_2_historical.ipynb`
