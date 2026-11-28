# Saudi Dialect to Modern Standard Arabic (MSA) Rewriter

## CURRENT TEAM WORK — Travel agency V3-R2 (FROZEN_ACTIVE)

**Use only the frozen V3-R2 benchmark for new evaluation.** [Start here](docs/START_TRAVEL_V3_R2.md) and [current notebook](notebooks/train_qwen3_lora_colab.ipynb). [Active dataset](data/golden_v3_r2.jsonl), SHA-256 `415f40b7e754b006709d13c92a7f1b2eabbacdb03f7cf3e1dec3f40d12f26e76`, freeze commit `31b8de5d38e5c44bc7eb7fcc92ea0b59d06cae71`. Team approval and final leader authorization are recorded. Earlier datasets and results are historical; old benchmark files are removed from the current branch and retained in the [immutable historical snapshot](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/tree/bb4b3e358969bceae47fc6369d8a46c31115abaa). Do not transfer scores or judgments without verification. Run the preflight and verify data isolation before any training or final evaluation.

**KAUST Academy — NLP Applications (2026)**  
**Project:** Saudi Dialect to Modern Standard Arabic Rewriting with a Fact-Preservation Check

This project aims to rewrite short Saudi-dialect messages into formal Modern Standard Arabic while checking whether sensitive factual details (e.g. names, dates, times, numeric values, and Latin-script tokens) are preserved.

## Approach

- Backbone used in the historical V3-R1 run: **Qwen3-1.7B** with **LoRA** fine-tuning.
- Input: Saudi-dialect Arabic text.
- Output: an MSA rewrite plus deterministic checks of important facts.
- Safety workflow: validate the rewrite, attempt a bounded repair if applicable, and return the original if fact preservation cannot be verified by the implemented checks.

A rule-based checker **cannot guarantee full semantic or factual preservation**. V3-R1 training and the three-system automatic comparison are documented in the historical execution record. Final V3-R2 evaluation and human correctness are pending.

## Historical Golden Test — team-approved v2.2 (20 November 2026)

- 100 Saudi-dialect messages, each with an MSA reference and protected-fact fields.
- Each of four members approved 25 messages and reviewed 25 of another member's messages.
- Reciprocal pairs: Abdulrahman Alharthi ↔ Yasser Alhajlah; Musaad Alqahtani ↔ Mohammed Alrashdi.
- The team leader reports witnessing the reviews and approvals in person.
- Five approved refinements affect only `g072`, `g085`, `g086`, `g088`, and `g095`.
- The annotated set originated from AI-assisted drafts and was reviewed by the team; it should not be misrepresented as 100 independently human-authored source messages.

**Historical V2.2 test (not for current work):** [frozen snapshot](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/blob/bb4b3e358969bceae47fc6369d8a46c31115abaa/data/golden_test.jsonl).  
**Documented review:** [`review/review_evidence.csv`](review/review_evidence.csv) and [`review/approval_attestation.json`](review/approval_attestation.json).

**Expected SHA-256 for the approved JSONL:** `4b9d8425d8c26d54507475bb55f594d4670a78e72e7ad4e7a96a1e78d3971f19`.

The historical V3-R1 comparison used a fixed prompted baseline, a LoRA-adapted model, and the full checking pipeline. No real-model accuracy results should be inferred from mock runs or unit tests.

## Repository state

The current working dataset is frozen V3-R2. Historical execution records from the team's branch are retained separately as [V3-R1 evidence](docs/V3_R1_EXECUTION.md), including [training](review/v3_r1_training_summary.json), [preparation](review/v3_r1_preparation_summary.json) and [automatic results](results/public_v3_r1_summary.json). Raw predictions, adapter archive and per-case safety outputs are not included; they must be verified privately.

## Team roles and contributions

Recorded contributions; entries marked "to confirm" still need the team's confirmation before submission.

- **Abdulrahman Al-Harthi (project leader)** — human output ratings, sheet B (90 of the 206 items); historical V2.2 Golden Test: 25 approvals and 25 peer reviews (reciprocal pair with Yasser Al-Hajlah). Remaining responsibilities to confirm.
- **Yasser Al-Hajlah** — human output ratings, sheet B (116 of the 206 items); historical V2.2 Golden Test: 25 approvals and 25 peer reviews (reciprocal pair with Abdulrahman Al-Harthi). Remaining responsibilities to confirm.
- **Musaed Al-Qahtani** — human output ratings, sheet A (98 of the 206 items); historical V2.2 Golden Test: 25 approvals and 25 peer reviews (reciprocal pair with Mohammed Al-Rashidi). Remaining responsibilities to confirm.
- **Mohammed Al-Rashidi** — V3-R1 training execution and evaluation run (Colab, Tesla T4; PR #5); human output ratings, sheet A (108 of the 206 items); historical V2.2 Golden Test: 25 approvals and 25 peer reviews (reciprocal pair with Musaed Al-Qahtani). Remaining responsibilities to confirm.

Proposal and report authorship, presentation preparation, and remaining code contributions are to confirm.

## Human evaluation status (27 November 2026)

The 206 distinct V3-R1 rewrites were rated in two label sets. Set A labels were assigned directly by the team members listed above. Set B labels began from AI-suggested labels that team members then reviewed and edited; set B is therefore not an independent human rater, and the figures below describe agreement between the two recorded label sets.

- Direct agreement between the two sets: **78.6%** (162 of 206); Cohen's kappa **0.659**; agreement on identifying missing facts **82.0%**. Details: [docs/HUMAN_EVAL_V3_R1.md](docs/HUMAN_EVAL_V3_R1.md).
- 67 distinct cases differ on the overall verdict, on missing-fact identification, or both: 30 verdict-only, 23 missing-fact-only, 14 both (the 44 verdict disagreements are 30 + 14).
- These ratings cover **V3-R1 outputs** against the historical V3-R1 benchmark. The active benchmark is V3-R2; scores and judgments must not be transferred without verification. Adjudication of the disagreements, per-system human correctness, and the final V3-R2 evaluation are pending.

## Course submission

The team's deadline is **21 November 2026**. A public repository does not itself prove submission to Blackboard.

## Historical status — 25 November 2026

The historical V2.2 evaluation has recorded automatic pass counts (71 baseline, 85 tuned, 85 full pipeline out of 100) in [results/public_summary.json](results/public_summary.json). These are not human semantic accuracy. The travel-agency V3 benchmark was separately team-reviewed on 25 November; see [V3 approval](docs/GOLDEN_V3_TEAM_APPROVAL.md) and [manifest](GOLDEN_V3_RELEASE_MANIFEST.json). V2.2 remains frozen and is not replaced. This paragraph is a historical status snapshot; later V3-R1 execution and rating records are documented above. Licensing and final V3-R2 assessment remain pending. On 25 November 2026, the team leader reported that the supervising instructor had reviewed the complete presented results and approved the project. This is a leader-reported approval, not a directly supplied instructor record. It does not establish approval of a specific V3 file hash or results of experiments not yet performed. Earlier text in this README describing planned work reflects the pre-training snapshot.

## Current closure status — 28 November 2026

See [closure checklist](docs/V3_R2_CLOSURE_STATUS.md). Use the frozen dataset commit `31b8de5d38e5c44bc7eb7fcc92ea0b59d06cae71`, activation commit `bb4b3e358969bceae47fc6369d8a46c31115abaa` and cleanup commit `07340b20f29f58470b6da49357c35317906b0e9a` for exact version references.
