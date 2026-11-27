# NLP Applications — Requirements and Evidence Matrix

This report separates available files from demonstrated model performance. The golden test was approved by the team according to its leader's 20 November 2026 attestation; named reviewer allocations are explained in `docs/GOLDEN_TEST_TEAM_APPROVAL.md`.

| Requirement | Evidence in this repository | Verified status |
|---|---|---|
| One narrow NLP task, model within 4B | Saudi dialect → MSA, Qwen3-1.7B | Task and model selected |
| LoRA/QLoRA fine-tuning | Colab notebook | Pipeline code prepared; actual fine-tuning has no results yet |
| Baseline/tuned/full comparative evaluation | `src/evaluate.py` | Evaluation logic implemented; real model outcomes are not measured |
| Verification-and-repair pipeline | `src/pipeline.py`, `src/facts.py` | Code present and mock scenarios tested |
| Local inference and RTL interface | Ollama setup, `app/streamlit_app.py` | Local trained-model demo has not been demonstrated |
| Approximately 100 reviewed golden examples | `data/golden_v3_r2.jsonl`, release record and leader attestation | 100/100 reported approved; strict format/fact checks passed for V3-R2 |
| Golden freeze before fine-tuning | Golden SHA-256 in team approval report | Local release prepared; GitHub commit needs to be made before training |
| Dataset origins, usage permissions, split | `docs/DATASET_CARD.md` | Known corpus license discrepancy documented; processed run statistics require execution |
| Golden / training split separation | Deduplication and overlap checks in `src/data_prep.py` | Controls coded; inspect actual training outputs after generating them |
| Ten adversarial safety cases | `data/safety_inputs.jsonl`, `src/safety_check.py` | Mock-only trial done; real-model execution and human judgments not measured |
| Model card / weights | `docs/MODEL_CARD.md` and training notebook | Model card includes setup and evaluation protocol; adapter not trained/published |
| Public GitHub and clean clone | Repository package, CI workflow | Upload and actual GitHub Actions execution need verification |
| Individual contribution evidence | Team review register, approval record | Team leader directly confirms 25 owner approvals and 25 reciprocal reviews per member, conducted in his presence |

**Required sequencing:** Upload and commit the approved Golden Test first. Verify the commit SHA and make sure training begins later. Then run corpus preparation and overlap checks, actual LoRA fine-tuning, real-model evaluation, local demonstration, and results publication.
