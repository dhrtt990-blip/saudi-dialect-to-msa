# Human evaluation — V3-R1 outputs (26 November 2026)

**Benchmark note (27 November 2026):** the active frozen benchmark is now **V3-R2** (`data/golden_v3_r2.jsonl`, SHA-256 `415f40b7e754b006709d13c92a7f1b2eabbacdb03f7cf3e1dec3f40d12f26e76`, 100 records, 335 labelled key facts). The ratings below cover **V3-R1 outputs** against the historical V3-R1 benchmark. They must not be transferred to V3-R2 without verification; re-mapping and review of the ratings against V3-R2 is pending.

## What was rated

206 distinct actual rewrites (including withheld candidates) from the V3-R1 evaluation, rated in two label sets. Rating categories: `ok` (acceptable), `meaning_changed`, `dialect_left`.

## Label-set provenance

- **Set A** labels were assigned directly by team members: Mohammed Al-Rashidi (108 of the 206 items) and Musaed Al-Qahtani (98).
- **Set B** labels began from AI-suggested labels that team members then reviewed and edited: Yasser Al-Hajlah (116 items) and Abdulrahman Al-Harthi (90). Set B is therefore **not an independent human rater**.

The figures below describe agreement between the two recorded label sets, not agreement between two fully independent human raters.

## Agreement between the two label sets

- Direct agreement: **78.6%** (162 of 206).
- Cohen's kappa: **0.659**.
- Agreement on identifying missing facts: **82.0%**.
- The recorded agreement gate is 0.80 (`review/v3_r1_targets.json`); observed direct agreement is 0.786.

## Disagreements

44 cases disagree on the overall verdict:

| Set A | Set B | Count |
|---|---|---|
| meaning_changed | ok | 22 |
| dialect_left | ok | 17 |
| between the two error categories | | 5 |

67 distinct cases disagree on the overall verdict, on missing-fact identification, or both (no case counted twice):

| Disagreement type | Count |
|---|---|
| Overall verdict only | 30 |
| Missing-fact identification only | 23 |
| Both | 14 |

The 44 verdict disagreements equal 30 + 14. Most verdict disagreement sits on the accept/reject boundary, not on the error type: set A was the stricter set overall.

## Status against targets

The disagreements await team adjudication before per-system human correctness (T1–T3) can be reported. Until adjudication, T1–T3 remain unreported rather than failed. T4 was met in the V3-R1 phase; final evaluation on the active V3-R2 benchmark is pending.

## V3-R2 review follow-up

The recorded V3-R1 label sets remain historical. Local technical review packages have been prepared, but their suggestions are not final human judgments and are not uploaded with the public aggregate records. Re-check affected labels, collect independent human decisions, resolve disputes, verify the three saved prediction digests and system-to-output key mapping, then compute T1–T3. The original 0.80 agreement gate was not met by the recorded verdict agreement. Do not claim a passed independent-rater gate based on these two label sets.
