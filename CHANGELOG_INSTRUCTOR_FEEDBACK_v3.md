# Changes after the instructor's feedback — 24 November 2026

Reason: the instructor's three points of 24 November 2026 (tie the project to a specific service; ask for missing information instead of guessing; label key facts and report what the checks miss). The full answer is in `docs/INSTRUCTOR_FEEDBACK_RESPONSE.md`.

No model was trained or run for these changes. The golden test in `data/golden_test.jsonl` is still v2.2 and its bytes are unchanged.

## New files

| File | What it is |
|---|---|
| `src/gazetteer.py` | Word lists: 12 days, 22 months, 95 places |
| `src/needs.py` | The missing-information check |
| `data/golden_v3_draft.jsonl` | Draft of 100 travel-desk messages with `key_facts` and `missing`; not reviewed by the team yet |
| `review/golden_v3_review.xlsx` | The review sheet for the draft; sign-off columns empty |
| `docs/INSTRUCTOR_FEEDBACK_RESPONSE.md`, `docs/GOLDEN_V3_FREEZE_STEPS.md` | The answer to the feedback, and the steps to review and freeze v3 |

## Changed files

| File | Change |
|---|---|
| `src/facts.py` | The checker also reads days, months and listed places (compared by presence). New: `fact_present`, `checker_reads` |
| `src/common.py` | JSONL files are written as bytes, so they are the same on Windows and Linux. The SHA-256 recorded for the golden test is taken from the file the import writes; with a text-mode file it would differ on Windows from the file Git stores |
| `src/pipeline.py` | Status `NEEDS_INFO`; `RewritePipeline(..., ask=True)` and `run(..., ask=...)`. The message for a released rewrite now says what was compared and that nothing else was |
| `src/evaluate.py` | Key facts judged by the two raters (columns `facts_lost_a`, `facts_lost_b`, `facts_lost_final`); error type `key_fact_lost`; withheld rewrites are judged; report sections on key facts, what the checks missed, the checker as a classifier, the missing-information check. Judgment keys start with a letter and depend on the key facts. A judgment sheet saved with semicolons is read; a sheet without its `key` column, or one that matches no rewrite of the run, is refused |
| `src/validate_golden.py`, `scripts/golden_review.py` | Label fields `key_facts` and `missing`; two more columns in the review sheet, kept together or not at all |
| `src/prompts.py`, `src/data_prep.py` | Prompt, worked examples and 43 templates for the travel desk; names are first names only; year-first dates only in formal messages |
| `src/safety_check.py`, `data/safety_inputs.jsonl` | Verdict `ASKED`; inputs moved to the travel desk; `s05` is now a request that lacks its date and destination (the already-formal case it replaces is covered by the six formal messages of the golden draft) |
| `app/streamlit_app.py` | Shows the questions to ask; a box to rewrite the message as it stands, and then a note that names what the message lacks |
| `notebooks/train_qwen3_lora_colab.ipynb` | The golden-test cell also stops while the file is still release v2.2 |
| `tests/test_golden_release.py` | Recognises the release by its ids, so it holds for v2.2 now and for v3 after the freeze; compares the golden file with the release manifest and the checksum list |
| `.github/workflows/ci.yml` | The JSONL syntax step also reads the v3 draft |
| Documents | `README.md` (service, feedback table, run from a clean clone), `ابدأ_هنا.md`, `docs/PROPOSAL.md`, `docs/PLAN_REVIEW_PREP.md` (targets T1 to T4), `docs/DATASET_CARD.md`, `docs/MODEL_CARD.md`, `docs/MODEL_RISKS_AND_LIMITATIONS.md`, `docs/COURSE_REQUIREMENTS_MATRIX.md`, `docs/annotation_guidelines.md` (sections 8 and 9) |

## Existing tests that had to change, and why

| Test | Change | Why |
|---|---|---|
| `tests/test_core.py` (`SRC`, `GOOD`, `BAD`) | The sample message now names its booking number | Without it the request is incomplete and the pipeline asks instead of rewriting |
| `tests/test_eval_app.py::test_load_judgments_rules` | Two more keys in the agreement record | Agreement on key facts is reported too |
| `tests/test_eval_app.py::test_safety_verdicts` | The forbidden answer is a number in words | An answer that names a city is now withheld by the checker; a new test covers that |
| `tests/test_scripts.py::test_export_has_the_review_columns` | Two more columns | `key_facts` and `missing` |
| `tests/test_data.py::test_synthetic_pairs_read_as_sound_arabic` | Two patterns follow the new template wording, and the digit map reads the Arabic separators | The templates were rewritten |
| `tests/test_golden_release.py` | See above | It must hold before and after the v3 freeze |

Tests: 187 before, 291 after.

## Numbers that moved

- `python -m src.validate_golden data/golden_test.jsonl` now prints 93 rows with facts (92 before), because days and places count as facts. Errors and warnings are unchanged: 0 and 1.
- Error types in the report: 12 (11 before; `key_fact_lost` is new).

## Corrections before delivery

No team member has reviewed these changes yet; that review is the team's. Corrections made before delivery: the classifier table now counts `meaning_changed` as a problem; a request to book that also asks about cancelling is no longer asked for a booking number; an amount, a phone number, an e-mail address or a flight number that another word introduces is no longer taken for a booking reference; 7 `missing` labels were corrected (complaints about a service in progress need the booking reference), which lowered the measured rate of the check on the draft from 32 of 33 to 32 of 40. "فندق" and "تأمين", both named in the guide's list of things to book, were then added to the rules: the check now asks on 33 of the 40, and for exactly the labelled details on 32; three formal messages written by the agency were replaced with formal messages written by a customer.

Also corrected: a request to book that also cancels a booking the customer calls his own is asked for that booking's number; when the staff member rewrites without asking, the app names what the message lacks and says exactly what the checker refuses; the direction of travel or of a change is part of the key facts in eight rows; the report no longer points to sections it does not have when the golden test carries no labels.

Left open, and stated in `docs/MODEL_RISKS_AND_LIMITATIONS.md`: a number that directly follows the word for the booking is taken as its reference even when it is an amount; the checker does not read a period given in words ("الأسبوع القادم"). Also left open: with every verdict filled in but some `facts_lost` cells empty, the "Guessing" and "As deployed" tables show "not judged" for more than is strictly unjudged. The last corrections were checked by the tests and by a rehearsal of the freeze steps.
