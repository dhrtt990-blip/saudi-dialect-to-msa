# Dataset Card — Saudi Dialect to MSA Rewriter

## Scope and provenance

The project rewrites short Saudi-dialect messages into Modern Standard Arabic while preserving factual spans. All golden examples are separate from the training split. The final golden set was **AI-drafted and team-reviewed**, not originally written by four people from scratch. The team leader attests that all 100 items were approved after four members performed 25 reciprocal peer reviews each. All four reciprocal pairings were confirmed directly by the team leader, who states the reviews and approvals occurred in his presence; see `docs/GOLDEN_TEST_TEAM_APPROVAL.md`.

## Training sources and licences

| Data | Scope | Use | Status |
|---|---|---|---|
| Khalid Almeman, multidialectal parallel Arabic corpus, [Zenodo 17776617](https://doi.org/10.5281/zenodo.17776617) | 50,010 short travel-related rows; use Saudi Dialect + Modern Standard Arabic columns | Candidate supervised training/validation | Source identified; final sampled subset and split counts must come from a real processing run |
| `src/data_prep.py` synthetic templates | 31 templates filled with invented names, amounts, dates, times, numbers, identifiers | Candidate training/validation | Generator coded; actual build/report generated during preparation |
| `data/golden_test.jsonl` | 100 reviewed messages across nine service/administrative topic groups | **Evaluation only** | Team approved per leader attestation; validator passed |

**Corpus licence discrepancy:** The Zenodo licence metadata and corresponding paper report CC BY 4.0, while a README inside the distribution states non-commercial reuse (CC BY-NC) and warns about upstream API terms. The project takes a cautious, non-commercial course-use approach and does not redistribute the raw corpus, processed derived lines, or adapter until the terms are clarified. The upstream source is acknowledged; this dataset card does not claim legal clearance to distribute derived weights.

## Golden Test v2.2 — team-approved release

- 100 unique `g001`–`g100` records; **92** include detectable fact spans according to the project's checker; seven formal control messages were marked in the AI draft.
- Confirmed reciprocal pairings: Abdulrahman ↔ Yasser; Musaad ↔ Mohammed. Each member approved 25 items and peer-reviewed 25 items, in the team leader's presence.
- At `g032` the canonical wording remains the selected original review reference; the alternative wording is documented in `docs/INPUT_AUDIT_2026-11-20.md`.
- Comparisons to the original draft: 0 source edits; 4 MSA reference refinements (`g072`, `g086`, `g088`, `g095`); one `must_keep` refinement (`g085`); 95 complete rows unchanged. Mohammed and Musaad rechecked these five entries in the leader’s presence; see `docs/FIVE_CHANGE_AUDIT.md`.
- Strict structural and reference-fact check: **0 errors, 1 dialect-lexicon coverage warning** involving 37 sources.
- Golden SHA-256: `4b9d8425d8c26d54507475bb55f594d4670a78e72e7ad4e7a96a1e78d3971f19`.
- Additional evidence: `docs/GOLDEN_TEST_TEAM_APPROVAL.md` and `review/golden_review_approved.xlsx`.

**Repository freeze:** A local release and SHA-256 are ready. Record the first GitHub commit SHA/date only after actual push, before training begins. A local file hash is not a Git commit or proof that the freeze already occurred.

## Separation and processing protocol

The processing code normalizes Arabic text and Arabic/Latin digits, removes repeated pairs and invalid facts, filters direct matches, substring matches, 5-gram near-duplicates and sensitive signature overlap with golden sources/references, then deterministically splits surviving examples into 90% training and 10% validation. Inspection of `data/processed/prep_report.json` after a real run is required to state the actual row counts or overlap outcomes. The model notebook begins with an illustrative 8,000-corpus / 2,000-template setting; these are **configuration values, not measured final dataset sizes**.

Because the external travel corpus contains few numbers, synthetic fact-rich templates fill an important training coverage gap. The dataset's limited regional and domain diversity and shared AI-draft style are limitations to evaluate, not claims of already demonstrated robustness.

## Personal data

Use synthetic names, dates, amounts and example-domain addresses only. No real personal/customer records are needed. Review invented names for accidental matches with real individuals and avoid uploading customer messages to a public repository.

## Travel-agency V3 — 25 November 2026 update

A separate, AI-assisted, team-reviewed travel benchmark contains 100 messages, 322 labelled fact entries and 40 messages with missing details. Review evidence is in [V3 team approval](GOLDEN_V3_TEAM_APPROVAL.md) and [manifest](../GOLDEN_V3_RELEASE_MANIFEST.json). V2.2 was frozen in commit eb809eef46f2c9849f305478d7cd7e1c0846e91c and remains unchanged. V3 must be isolated from training/validation and checked for leakage before new experiments. Historical V2.2 results do not establish performance on V3. On 25 November 2026, the team leader reported that the supervising instructor had reviewed the complete presented results and approved the project. This is a leader-reported approval, not a directly supplied instructor record. It does not establish approval of a specific V3 file hash or results of experiments not yet performed. Licensing remains unresolved.
