# Start here — travel agency V3-R2

**FROZEN_ACTIVE — 27 November 2026.** The team approved contextual corrections and the team leader authorized final freeze. The verified dataset is recorded in commit `31b8de5d38e5c44bc7eb7fcc92ea0b59d06cae71`; activation is recorded in `bb4b3e358969bceae47fc6369d8a46c31115abaa`. Use the frozen V3-R2 evaluation benchmark only; older versions are historical and are no longer present in the working data directory. They are recoverable only from [the preserved Git snapshot](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/tree/bb4b3e358969bceae47fc6369d8a46c31115abaa). Do not restore or use them for new experiments.

- Benchmark: `data/golden_v3_r2.jsonl`.
- Freeze commit: `31b8de5d38e5c44bc7eb7fcc92ea0b59d06cae71`.
- SHA-256: `415f40b7e754b006709d13c92a7f1b2eabbacdb03f7cf3e1dec3f40d12f26e76`.
- 100 messages, 335 labels, 274 improved labels across 96 rows, zero bare numeric labels, 40 missing-detail rows.
- [Data checks](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/actions/runs/45911404302): 273 tests passed; zero validation errors, two previously documented warning groups.

## Next steps
1. Use [the current notebook](../notebooks/train_qwen3_lora_colab.ipynb) on main. Run the preflight and verify the actual code commit and frozen digest.
2. Use the benchmark only for exclusion checks and evaluation, never as training or validation examples. If training is already complete, verify the original preparation report and the model's lineage against the unchanged source/reference texts and run a fresh overlap check before reporting V3-R2 results. Do not retrain solely because annotation wording changed unless the isolation or experiment protocol requires it.
3. New preparation outputs go to `data/processed_v3_r2`. New evaluations go to `results/v3_r2`. Record actual model versions, code and data hashes.
4. Existing reviewer judgments depend on label wording. Re-link only after verifying the identical output and label mapping; re-check affected judgments and resolve the 67 disputed outputs. Do not claim completed human evaluation or transfer old scores automatically. Recorded set B was suggestion-assisted and subsequently reviewed; independent confirmation is required. The 11 missing-information checker disagreements remain a separate evaluation issue.
5. Keep derived weights and data local until licence clearance. The two warning groups are documented; automated matching is not semantic accuracy. Team approval is leader-attested; no new individual signatures or exact-digest supervisor approval are asserted.

Historical training and aggregate evidence: [execution record](V3_R1_EXECUTION.md). See [closure status](V3_R2_CLOSURE_STATUS.md) before reporting final metrics.
