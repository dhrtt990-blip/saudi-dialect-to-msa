# NLP Applications — Requirements and Evidence Matrix

This report separates available files from demonstrated model performance. The golden test was approved by the team according to its leader's 20 November 2026 attestation; named reviewer allocations are explained in `docs/GOLDEN_TEST_TEAM_APPROVAL.md`.

| Requirement | Evidence in this repository | Verified status |
|---|---|---|
| One narrow NLP task, model within 4B | Saudi dialect → MSA for the booking desk of a travel agency, Qwen3-1.7B | Task, service and model selected |
| Instructor feedback 1: a specific service | `src/prompts.py`, 43 templates in `src/data_prep.py`, `data/golden_v3_draft.jsonl` | Code and draft present; the draft is not reviewed |
| Instructor feedback 2: ask for missing information | `src/needs.py`, status `NEEDS_INFO` in `src/pipeline.py`, the app | Coded and unit-tested; scored against golden labels only on the draft |
| Instructor feedback 3: report what the checks miss | `key_facts` labels, `facts_lost` columns and report sections in `src/evaluate.py` | Coded and unit-tested; no real-model output has been judged |
| LoRA/QLoRA fine-tuning | Colab notebook | Pipeline code prepared; actual fine-tuning has no results yet |
| Baseline/tuned/full comparative evaluation | `src/evaluate.py` | Evaluation logic implemented; real model outcomes are not measured |
| Verification-and-repair pipeline | `src/pipeline.py`, `src/facts.py` | Code present and mock scenarios tested |
| Local inference and RTL interface | Ollama setup, `app/streamlit_app.py` | Local trained-model demo has not been demonstrated |
| Approximately 100 reviewed golden examples | `data/golden_test.jsonl`, review workbook and leader attestation | 100/100 reported approved; strict format/fact checks passed. This is release v2.2 (general topics); the travel-desk release v3 is a draft awaiting review (`docs/GOLDEN_V3_FREEZE_STEPS.md`) |
| Golden freeze before fine-tuning | Golden SHA-256 in team approval report; commit `eb809ee` of 20 November 2026 | Release v2.2 is committed and no model has been trained. The travel-desk release v3 must be committed before training |
| Dataset origins, usage permissions, split | `docs/DATASET_CARD.md` | Known corpus license discrepancy documented; processed run statistics require execution |
| Golden / training split separation | Deduplication and overlap checks in `src/data_prep.py` | Controls coded; inspect actual training outputs after generating them |
| Ten adversarial safety cases | `data/safety_inputs.jsonl`, `src/safety_check.py` | Mock-only trial done; real-model execution and human judgments not measured |
| Model card / weights | `docs/MODEL_CARD.md` and training notebook | Model card includes setup and evaluation protocol; adapter not trained/published |
| Public GitHub and clean clone | Repository package, CI workflow | Upload and actual GitHub Actions execution need verification |
| Individual contribution evidence | Team review register, approval record | Team leader directly confirms 25 owner approvals and 25 reciprocal reviews per member, conducted in his presence |

**Required sequencing:** Review and freeze Golden Test v3 first (`docs/GOLDEN_V3_FREEZE_STEPS.md`), verify its commit SHA, and make sure training begins later. Then run corpus preparation and overlap checks, actual LoRA fine-tuning, real-model evaluation, local demonstration, and results publication.
