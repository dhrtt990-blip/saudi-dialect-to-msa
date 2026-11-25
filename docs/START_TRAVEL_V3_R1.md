# Start here — travel agency V3-R1 only

**ACTIVE / FROZEN — 25 November 2026.** PR #4 was merged into main; the team leader has explicitly authorized final freeze and the next training phase. The data is evaluation-only. Training may start only after the preflight and actual data-preparation overlap checks succeed.

| File | Role |
|---|---|
| `data/golden_v3_r1_candidate.jsonl` | **Active frozen V3-R1 benchmark** (filename retained to preserve references and freeze history) |
| `data/golden_v3.jsonl` | Earlier V3 approval snapshot, audit only |
| `data/golden_test.jsonl` | Historical V2.2, not for new travel training/evaluation |
| `data/golden_v3_draft.jsonl` | Draft, not an evaluation release |

- Frozen data commit: `51127bdfb65a19adb763501d139515dd4479ff27`.
- Activation commit: `1fe1f8a0e10813cb421608831938221135cba735` ([PR #4](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/pull/4)).
- SHA-256: `e1dbff1b7a8045dc061a622b1233d2ccee8ef4b5901202a2f6391e9c906ef8e6`.
- 100 messages, 335 key-fact labels, 40 missing-detail rows; 272 tests passed, zero validation errors, two documented warning groups in [activation CI](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/actions/runs/45687663037).

## Execution and reproduction
The R1 run `travel-v3-r1-20261125T195842Z` completed 1,078 steps and a saved-adapter reload. See [execution evidence](V3_R1_EXECUTION.md), [training summary](../review/v3_r1_training_summary.json) and [model card](MODEL_CARD.md). Check these artifacts before starting another training run.

For a new independent training run:

1. Open [the current training notebook](../notebooks/train_qwen3_lora_colab.ipynb) on main in Colab using a fresh clone. Record the actual checkout SHA. Use T4 GPU and run in order.
2. Run the preflight; it checks the active manifest, exact SHA-256, IDs, clean files and ancestry of the freeze commit. Do not bypass it.
3. Run data preparation with the frozen benchmark only as an exclusion/filter input, not as training or validation samples. Inspect `data/processed_v3_r1/prep_report.json`: require matching golden SHA-256 and zero remaining overlap. Do not train if the report fails. Save the report and actual split counts.
4. Train a distinct V3-R1 adapter and evaluate baseline, tuned and full pipeline into `results/v3_r1` only. Do not reuse V2.2 predictions or weights as the new tuned result. Record code/weight versions and actual results.
5. Evaluate missing-information disagreements, human judgments, safety and error analysis. The recovered original 11 checker disagreements and 11 technical annotation edits are different sets; see [reconciliation](V3_R1_RECONCILIATION.txt). Do not claim all checker errors were fixed. Two validator warning groups remain documented in the audit.
6. Licence clearance is unresolved; keep weights and derived data local until cleared. The leader approval is not new peer signatures or exact-hash instructor approval. R1 training, saved-adapter reload and the actual automatic comparison are verified: 82/88/89 passes out of 100. See [public aggregates](../results/public_v3_r1_summary.json). Independent human correctness remains pending.
