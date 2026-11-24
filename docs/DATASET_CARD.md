# Dataset Card — Saudi Dialect to MSA Rewriter

## Scope and provenance

The project rewrites short Saudi-dialect messages into Modern Standard Arabic while preserving factual spans. Since 24 November 2026 the service is the booking-support desk of Darb Aljawza Travel, an invented travel agency (no real organisation's messages). Golden examples are kept out of the training split by `src/data_prep.py`, which fails if any overlap remains; no split has been built yet. The golden set of release v2.2 was **AI-drafted and team-reviewed**, not originally written by four people from scratch. The team leader attests that all 100 items were approved after four members performed 25 reciprocal peer reviews each. All four reciprocal pairings were confirmed directly by the team leader, who states the reviews and approvals occurred in his presence; see `docs/GOLDEN_TEST_TEAM_APPROVAL.md`.

## Training sources and licences

| Data | Scope | Use | Status |
|---|---|---|---|
| Khalid Almeman, multidialectal parallel Arabic corpus, [Zenodo 17776617](https://doi.org/10.5281/zenodo.17776617) | 50,010 short travel-related rows; use Saudi Dialect + Modern Standard Arabic columns | Candidate supervised training/validation | Source identified; final sampled subset and split counts must come from a real processing run |
| `src/data_prep.py` synthetic templates | 43 templates written as messages to a travel booking desk, filled with invented first names, amounts, dates, times, days, places and booking codes; five of them leave out a needed detail and the MSA side adds none | Candidate training/validation | Generator coded; actual build/report generated during preparation |
| `data/golden_test.jsonl` | 100 reviewed messages across nine service/administrative topic groups (release v2.2) | **Evaluation only** | Team approved per leader attestation; validator passed |
| `data/golden_v3_draft.jsonl` | 100 travel-desk messages `t001`–`t100` with `key_facts` and `missing` labels | **Draft of the next evaluation set** | Not reviewed; replaces v2.2 only after two members sign every row |

**Corpus licence discrepancy:** The Zenodo licence metadata and corresponding paper report CC BY 4.0, while a README inside the distribution states non-commercial reuse (CC BY-NC) and warns about upstream API terms. The project takes a cautious, non-commercial course-use approach and does not redistribute the raw corpus, processed derived lines, or adapter until the terms are clarified. The upstream source is acknowledged; this dataset card does not claim legal clearance to distribute derived weights.

## Golden Test v2.2 — team-approved release

- 100 unique `g001`–`g100` records; **92** include detectable fact spans according to the project's checker (93 since 24 November, when the checker began to read days, months and places); seven formal control messages were marked in the AI draft.
- Confirmed reciprocal pairings: Abdulrahman ↔ Yasser; Musaad ↔ Mohammed. Each member approved 25 items and peer-reviewed 25 items, in the team leader's presence.
- At `g032` the canonical wording remains the selected original review reference; the alternative wording is documented in `docs/INPUT_AUDIT_2026-11-20.md`.
- Comparisons to the original draft: 0 source edits; 4 MSA reference refinements (`g072`, `g086`, `g088`, `g095`); one `must_keep` refinement (`g085`); 95 complete rows unchanged. Mohammed and Musaad rechecked these five entries in the leader’s presence; see `docs/FIVE_CHANGE_AUDIT.md`.
- Strict structural and reference-fact check: **0 errors, 1 dialect-lexicon coverage warning** involving 37 sources.
- Golden SHA-256: `4b9d8425d8c26d54507475bb55f594d4670a78e72e7ad4e7a96a1e78d3971f19`.
- Additional evidence: `docs/GOLDEN_TEST_TEAM_APPROVAL.md` and `review/golden_review_approved.xlsx`.

**Repository freeze:** Release v2.2 was committed to GitHub on 20 November 2026 (commit `eb809ee`), before any training.

## Golden Test v3 — draft for the travel booking desk (not reviewed)

- 100 records `t001`–`t100` in seven groups: new booking 30, change 16, cancellation and refund 16, enquiry 14, complaint and follow-up 12, extras 6, already formal 6. The rows are in mixed order, so every 25 rows hold every group. Seven are travel messages of v2.2 kept word for word and five more are adapted from it.
- Not yet checked by a speaker of the dialect. It reads as one author's work: mostly general Najdi and urban Hijazi, short single sentences, tidy typing. It is a draft until two members have signed every row.
- `key_facts`: 335 labels, worded as in the reference (a date, a day, a place, a booking code, an amount, a count, a class); two messages have none. `missing`: 40 rows name the needed detail the message does not give (`date`, `destination`, `booking_reference`).
- Validator on the draft: 0 errors, 2 warnings (46 sources contain no word from the short dialect list; 2 rows have no key fact).
- No phone numbers, passport numbers or identity numbers; booking codes, amounts and the one e-mail address are invented.

## Separation and processing protocol

The processing code normalizes Arabic text and Arabic/Latin digits, removes repeated pairs and invalid facts, filters direct matches, substring matches, 5-gram near-duplicates and sensitive signature overlap with golden sources/references, then deterministically splits surviving examples into 90% training and 10% validation. Inspection of `data/processed/prep_report.json` after a real run is required to state the actual row counts or overlap outcomes. The model notebook begins with an illustrative 8,000-corpus / 2,000-template setting; these are **configuration values, not measured final dataset sizes**.

The external corpus is short tourism sentences, not messages to a booking desk, and it contains few numbers. The templates are the only training pairs from the service itself; this domain gap is a stated limit. Because the external travel corpus contains few numbers, synthetic fact-rich templates fill an important training coverage gap. The dataset's limited regional and domain diversity and shared AI-draft style are limitations to evaluate, not claims of already demonstrated robustness.

## Personal data

Use synthetic names, dates, amounts and example-domain addresses only. No real personal/customer records are needed. Review invented names for accidental matches with real individuals and avoid uploading customer messages to a public repository.
