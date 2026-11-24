# Saudi Dialect to Modern Standard Arabic (MSA) Rewriter

**KAUST Academy — NLP Applications (2026)**  
**Project:** Saudi Dialect to Modern Standard Arabic Rewriting with a Fact-Preservation Check

This project aims to rewrite short Saudi-dialect messages into formal Modern Standard Arabic while checking whether sensitive factual details (e.g. names, dates, times, numeric values, and Latin-script tokens) are preserved.

**Service (revised 24 November 2026):** the booking-support desk of Darb Aljawza Travel (وكالة درب الجوزاء للسفر), a travel agency invented for this project. Customers write to the desk in a chat, in Saudi dialect; the staff member needs each message as a formal written request in MSA, which is filed with the booking and sent on to the airline or the hotel. No real organisation's messages are used.

## Approach

- Planned backbone: **Qwen3-1.7B** with **LoRA** fine-tuning.
- Input: a customer's message to the booking desk, in Saudi dialect.
- Missing information: a request to book without a date or a destination, or a request about a booking without its reference, is not rewritten. The app returns the question to ask the customer.
- Output: an MSA rewrite plus deterministic checks of the facts the checker can read: numbers, dates, times, Latin-script tokens, days, months, listed places and listed names.
- Safety workflow: validate the rewrite, attempt a bounded repair if applicable, and return the original if fact preservation cannot be verified by the implemented checks.

## Instructor feedback of 24 November 2026

| Point | Answer in this repository |
|---|---|
| Tie it to a specific service | The booking desk of one invented travel agency: prompt, 43 training templates and a 100-message golden draft for that service |
| Handle missing information | `src/needs.py` and status `NEEDS_INFO`: the system asks for the date, the destination or the booking reference instead of guessing |
| Report what the checks miss | Key facts labelled on the golden messages; the report lists the labelled facts lost or changed in released rewrites and shows the checker as a classifier |

Details, limits and what has not been run: [`docs/INSTRUCTOR_FEEDBACK_RESPONSE.md`](docs/INSTRUCTOR_FEEDBACK_RESPONSE.md).

A rule-based checker **cannot guarantee full semantic or factual preservation**. The model fine-tuning and real-model evaluation are planned work, not completed experimental results.

## Golden Test — team-approved v2.2 (20 November 2026)

- 100 Saudi-dialect messages, each with an MSA reference and protected-fact fields.
- Each of four members approved 25 messages and reviewed 25 of another member's messages.
- Reciprocal pairs: Abdulrahman Alharthi ↔ Yasser Alhajlah; Musaad Alqahtani ↔ Mohammed Alrashdi.
- The team leader reports witnessing the reviews and approvals in person.
- Five approved refinements affect only `g072`, `g085`, `g086`, `g088`, and `g095`.
- The annotated set originated from AI-assisted drafts and was reviewed by the team; it should not be misrepresented as 100 independently human-authored source messages.

**Approved test:** [`data/golden_test.jsonl`](data/golden_test.jsonl).  
**Documented review:** [`review/review_evidence.csv`](review/review_evidence.csv) and [`review/approval_attestation.json`](review/approval_attestation.json).

**Expected SHA-256 for the approved JSONL:** `4b9d8425d8c26d54507475bb55f594d4670a78e72e7ad4e7a96a1e78d3971f19`.

### Golden Test v3 — draft, not reviewed

v2.2 covers general service topics. After the instructor's feedback the test moves to the travel booking desk. The draft is [`data/golden_v3_draft.jsonl`](data/golden_v3_draft.jsonl): 100 draft messages, each with its key facts and the needed detail it lacks, if any. It becomes the golden test only after two members have signed every row in [`review/golden_v3_review.xlsx`](review/golden_v3_review.xlsx). Until then `data/golden_test.jsonl` stays v2.2 and nothing is trained. Steps: [`docs/GOLDEN_V3_FREEZE_STEPS.md`](docs/GOLDEN_V3_FREEZE_STEPS.md).

The project will compare an untuned model, a LoRA-adapted model, and the full checking pipeline. No real-model accuracy results should be inferred from mock runs or unit tests.

## Repository state

The repository holds the frozen golden test v2.2 (commit `eb809ee`, 20 November 2026), the code, the tests, the training notebook and the documents. **No model has been trained or run yet.**

## Run from a clean clone

Python 3.11 or newer. No model and no GPU are needed for these steps; they use a rule-based stand-in and their numbers are not results.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt            # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest -q
.venv/bin/python -m src.validate_golden data/golden_test.jsonl
.venv/bin/python -m src.evaluate --client mock --golden data/golden_test.jsonl      # writes results/dryrun_mock/report.md
D2M_APP_ENGINE=mock .venv/bin/streamlit run app/streamlit_app.py                    # the app without a model
```

On Windows, `run_local.bat` creates the environment, runs the tests and the two dry runs (evaluation and safety check), checks Ollama, and writes `logs\local_run.txt`. With a real model the order is: freeze the golden test (`docs/GOLDEN_V3_FREEZE_STEPS.md`), train in Colab (`notebooks/train_qwen3_lora_colab.ipynb`), create the two Ollama models, then `python -m src.evaluate --golden data/golden_test.jsonl`.

## Course submission

The team's deadline is **21 November 2026**. A public repository does not itself prove submission to Blackboard.
