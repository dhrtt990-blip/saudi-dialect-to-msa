# Start here — travel agency V3-R1 only

**Current state:** Candidate, not active. Do not train or evaluate until the team resolves the original 11-case evidence dependency, records approval of the exact revised digest and freezes the candidate on main. The leader authorized the 11 technical corrections; that is not new peer or exact-hash instructor sign-off.

| File | Role |
|---|---|
| `data/golden_v3_r1_candidate.jsonl` | Current corrected candidate, only intended benchmark after formal activation |
| `data/golden_v3.jsonl` | Earlier team-approved V3 snapshot, preserve for audit |
| `data/golden_test.jsonl` | V2.2 historical benchmark, never use for new travel-desk training/evaluation |
| `data/golden_v3_draft.jsonl` | Draft, not an evaluation release |

[PR #3](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/pull/3) contains the work; main has not yet received it. SHA-256 of candidate: `e1dbff1b7a8045dc061a622b1233d2ccee8ef4b5901202a2f6391e9c906ef8e6`.

**After approval:** record freeze commit containing these bytes in `review/v3_r1_revision_manifest.json` and set status to `FROZEN_ACTIVE` in a reviewed follow-up commit on main; keep the candidate path fixed. Use `notebooks/train_qwen3_lora_colab.ipynb` at the resulting commit. Its preflight verifies the path, digest, exact IDs, clean committed files and freeze ancestry before allowing preparation/training. Do not locally bypass the preflight. The old notebook is archived for historical reproducibility only. Use separate `data/processed_v3_r1`, adapter and `results/v3_r1` paths. Record leakage checks, commit, hashes, model versions, human judgments and safety results. No license clearance is inferred; do not publish derived weights until cleared. Low-level CLI remains explicit for reproducibility; do not manually invoke it with V2.2 for this task.
