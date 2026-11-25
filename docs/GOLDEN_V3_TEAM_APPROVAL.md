# Golden Test V3 — travel-agency team approval

**Review date:** 25 November 2026. **Status:** team approved by leader attestation; instructor decision and V3 model evaluation are separate and not established.

The leader, Abdulrahman Mastour Alharthi, confirms that every team member personally approved their assigned messages and reviewed the reciprocal partner's messages in person, under his direct supervision. The uploaded workbook's sign-off columns were blank; reviewer names were transcribed administratively from the leader's confirmed assignment. No digital signatures or independent eyewitness evidence are claimed. This is review of benchmark inputs/references/labels, not human judgments of model outputs.

| IDs | Owner approval | Peer review | Count |
|---|---|---|---:|
| t001–t025 | Abdulrahman Mastour Alharthi | Yasser Mansour Alhajlah | 25 |
| t026–t050 | Yasser Mansour Alhajlah | Abdulrahman Mastour Alharthi | 25 |
| t051–t075 | Mohammed Adeeb Alrashdi | Musaad Obaied Saad Alqahtani | 25 |
| t076–t100 | Musaad Obaied Saad Alqahtani | Mohammed Adeeb Alrashdi | 25 |

100/100 owner approvals and 100/100 reciprocal reviews. 100 unique sources and IDs, 322 key-fact entries (each line is one label, including alternatives), 40 messages with missing-detail labels. The workbook has the same sources and references as the earlier draft; 13 records have revised key-fact lists: t008, t015, t037, t055, t056, t064, t068, t076, t080, t081, t083, t087, t097. These exact reviewed lists are preserved. Some labels are shorter than draft labels (e.g. t076 negation, t087 exclusivity, t064 language complaint); human semantic review remains necessary and these are limitations, not a claim of exhaustive fact coverage. The original draft is AI-assisted, not independently human-authored. The `control` metadata from the draft is retained where present; it was not an editable workbook column.

## Evidence and integrity
- [Approved JSONL](../data/golden_v3.jsonl), SHA-256 `09c1937ebac93056f1c33ef07037b157bc80e05361063474ef5e827dc73ccbbf`.
- [Full review CSV](../review/golden_v3_review_approved.csv), [row-level evidence](../review/v3_review_evidence.csv), [attestation](../review/v3_approval_attestation.json), [manifest](../GOLDEN_V3_RELEASE_MANIFEST.json).
- Source workbook SHA-256: `ce9b192385e871ca360359e62058c335c87270763785dda467d5cce4cc4b53f4`; canonical content comparison SHA-256: `38b6e7c95ff3c5f629d65190531239a1aee0655aaf7f53607ec74628d58ca662` (ordered rows of [id,source,reference,key_facts,missing,must_keep,topic,notes], compact UTF-8 JSON). An approved XLSX was prepared for the leader; the full review CSV is the repository representation.
- Original draft provenance: [travel branch commit](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/commit/245342a47e34ae1b2734efccef61e17542f19c39).

## Experiment boundary
V2.2 is unchanged; historical 71/85/85 automatic results apply only to V2.2. Do not reuse them as V3 results. The benchmark has been reviewed after those experiments; V3 is not an untouched test of decisions made using V2.2. Before any new V3 training/evaluation, record the commit and digest, confirm instructor scope, run overlap checks on training and validation, and document new runs, human judgments and safety review. Do not claim that the 25 November approval predates prior training. Run `python -m src.validate_golden data/golden_v3.jsonl` and the release regression test.
