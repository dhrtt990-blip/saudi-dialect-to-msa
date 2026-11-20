# Saudi Dialect to Modern Standard Arabic (MSA) Rewriter

**KAUST Academy — NLP Applications (2026)**  
**Project:** Saudi Dialect to Modern Standard Arabic Rewriting with a Fact-Preservation Check

This project aims to rewrite short Saudi-dialect messages into formal Modern Standard Arabic while checking whether sensitive factual details (e.g. names, dates, times, numeric values, and Latin-script tokens) are preserved.

## Approach

- Planned backbone: **Qwen3-1.7B** with **LoRA** fine-tuning.
- Input: Saudi-dialect Arabic text.
- Output: an MSA rewrite plus deterministic checks of important facts.
- Safety workflow: validate the rewrite, attempt a bounded repair if applicable, and return the original if fact preservation cannot be verified by the implemented checks.

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

The project will compare an untuned model, a LoRA-adapted model, and the full checking pipeline. No real-model accuracy results should be inferred from mock runs or unit tests.

## Repository state

This initial GitHub release establishes traceability for the team-approved evaluation data **before real model training**. Additional implementation files, executable tests, the Overleaf proposal, and the formatted review workbook are maintained in the separate submission package and should be added without modifying the frozen Golden Test.

## Course submission

The team's deadline is **21 November 2026**. A public repository does not itself prove submission to Blackboard.
