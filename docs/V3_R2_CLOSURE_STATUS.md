# V3-R2 closure checklist — 28 November 2026

## Version and evidence

- Active dataset: `data/golden_v3_r2.jsonl`, 100 records, 335 labels, SHA-256 `415f40b7e754b006709d13c92a7f1b2eabbacdb03f7cf3e1dec3f40d12f26e76`.
- Data commit: `31b8de5d38e5c44bc7eb7fcc92ea0b59d06cae71`; activation: `bb4b3e358969bceae47fc6369d8a46c31115abaa`; cleanup: `07340b20f29f58470b6da49357c35317906b0e9a`.
- Historical evidence source: `16763e6ac46bdaf9ed67864c1df92f401bbcdd51`. Five aggregate JSON records are copied byte-for-byte. The historical execution narrative is preserved with a dated context note. The four team documents were updated for current status. No older benchmark or private weights are reintroduced.
- R1 training record: 8,613 train, 957 validation, 1,078 steps, two epochs; saved adapter digest `2ace6f366dfc35192385ade92d2548e57250ae6c419d07d4039e5257e49d5aa8`. This digest is for the recorded adapter artifact, not assumed to be the ZIP digest.
- Historical automatic passes: 82/100 baseline, 88/100 tuned, 89/100 full. Not human correctness or R2 results.

## Outstanding evidence and acceptance criteria

| Item | Status | Required evidence |
|---|---|---|
| V3-R2 data freeze | Complete | Recorded digest and commit |
| Historical aggregate evidence | Integrated | Exact source commit, preserved records |
| Human evaluation | Pending | Independently confirmed ratings on R2, final disputes, verified key mapping |
| T1–T3 | Pending | Original three system prediction files, verified SHA-256 values, keys and adjudicated judgments; apply recorded targets without changing them |
| T4 | Historical R1 met | Reconfirm unchanged missing-field rule on R2 |
| 12 safety cases | Definitions and historical totals documented | Original per-case inputs, outputs, decisions and reviewer notes |
| Adapter | Recorded, not independently verified | Private archive, archive checksum, extracted adapter checksum, configuration and reload evidence |
| Licence | Publication on hold | Resolve contradictory corpus licence statements and upstream terms before redistribution |

Do not copy suggested judgments into final human columns or claim independent agreement from the historical assisted set. Do not transfer predictions to R2 by changing the digest in their metadata; verify source/reference equivalence, original prediction checksums, output identity, evaluator version and the label-dependent keys. Keep raw outputs and weights private. Historical counts remain historical until a verified new evaluation is complete.
