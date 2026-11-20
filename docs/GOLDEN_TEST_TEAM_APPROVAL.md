# Golden Test v2.2 — Approved team review and GitHub freeze

**Project:** Saudi Dialect to Modern Standard Arabic Rewriter with a Fact-Preservation Check  
**Review documented:** 20 November 2026  
**Approval basis:** Direct report by team leader Abdulrahman Mastour Alharthi, who witnessed all members' approvals and reciprocal peer reviews in person.

## Review matrix

| Owner / approver | Owned messages | Peer reviewer of their messages | Reviews performed by owner |
|---|---:|---|---:|
| Abdulrahman Mastour Alharthi | 25 | Yasser Mansour Alhajlah | 25 |
| Yasser Mansour Alhajlah | 25 | Abdulrahman Mastour Alharthi | 25 |
| Mohammed Adeeb Alrashdi | 25 | Musaad Obaied Saad Alqahtani | 25 |
| Musaad Obaied Saad Alqahtani | 25 | Mohammed Adeeb Alrashdi | 25 |

Every one of the 100 messages has an individual approval and a peer review. Row-level evidence: [review_evidence.csv](../review/review_evidence.csv).

## Five reapproved refinements

The team additionally reviewed these five refinements: `g072`, `g085`, `g086`, `g088`, and `g095`. Mohammed Adeeb Alrashdi and Musaad Obaied Saad Alqahtani checked and approved the refinements under the leader's supervision. Four MSA references were improved (`g072`, `g086`, `g088`, `g095`); the `must_keep` list was updated for `g085`. All 100 Saudi-dialect source strings remained unchanged.

## Version provenance

- Approved dataset: [data/golden_test.jsonl](../data/golden_test.jsonl).
- Original dataset initially generated with AI assistance, then reviewed by the team. The record documents review, not independent human authorship of every example.
- Dataset contains exactly **100 unique message IDs**.
- Golden Test **SHA-256:** `4b9d8425d8c26d54507475bb55f594d4670a78e72e7ad4e7a96a1e78d3971f19`.
- **Independent GitHub freeze commit:** [eb809eef46f2c9849f305478d7cd7e1c0846e91c](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/commit/eb809eef46f2c9849f305478d7cd7e1c0846e91c).

The documented approvals are based on the leader's account and row-level review register, not independently collected electronic signatures.

**Test-data isolation:** training inputs must be checked against these records before training. No actual LoRA fine-tuning or model-based test-set evaluation is claimed here.
