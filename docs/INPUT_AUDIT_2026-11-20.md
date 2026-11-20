# Source and Golden Test audit — 20 November 2026

The project was prepared from `dialect2msa.zip` and two separately submitted 100-message Excel workbooks. Their `reviewed_by` / `confirmed_by` cells were originally blank; the **completed owner approvals and reciprocal peer reviews were subsequently confirmed by the team leader** for all four members, including their pairings and in-person witness. The completed register is `review/golden_review_approved.xlsx`.

## Source consistency

The two Excel sources use the same 100 unique IDs; only the MSA reference wording at `g032` differs. The canonical approved dataset retains the wording from `golden_review.xlsx` and `data/golden_draft_ai.jsonl`:

> متى يُودَع المبلغ المسترجع؟ قلتم: من 7 إلى 14 يوم عمل، وهذا هو اليوم 20.

The alternate submitted workbook wording was:

> متى يُودَع المبلغ المسترجع؟ ذكرتم من 7 إلى 14 يوم عمل، وهذا هو اليوم 20.

No source or reference text was modified by this metadata and register update. The team's reported approval is documented under `docs/GOLDEN_TEST_TEAM_APPROVAL.md`.

## Reproducible record

- Approved Golden Test: `data/golden_test.jsonl` (100 records).
- Per-message owner/reviewer: `review/golden_review_approved.xlsx` and `review/review_evidence.csv`.
- Direct leader attestation: `review/approval_attestation.json`.
- SHA-256: `data/golden_test.sha256`.
- Structural/fact validator: 0 errors; one small-dialect-lexicon coverage warning.
- Freeze procedure: `docs/GITHUB_PUBLISH_GUIDE.md`; a GitHub commit is recorded only after publication.

The preceding PII project and its separate Golden Test have not been incorporated into this dataset.

## Team-approved refinements (v2.2)

The team then reviewed and approved five changes to the canonical set (`g072`, `g085`, `g086`, `g088`, `g095`), completed in person by Mohammed and Musaad according to the team leader. The original text of every message remains unchanged. See `docs/FIVE_CHANGE_AUDIT.md` and `review/golden_review_approved.xlsx` for the current final release.
