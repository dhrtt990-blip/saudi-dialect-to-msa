# Golden Test — Validation Report (v2.2)

**Source:** `data/golden_test.jsonl`  
**Project validator:** `python -m src.validate_golden data/golden_test.jsonl`  
**Validation process exit code:** `0`  
**Release:** final, team-approved 100-message Golden Test

## Automated checks
- Rows: **100**; identifiers `g001` through `g100` are unique and ordered.
- Source texts: **100 unique**; source strings unchanged from the v2.0 file.
- Peer/owner pair: **100/100 complete and distinct**.
- Review allocation: **25 owner approvals and 25 peer reviews per member**.
- Facts, numbers, times and `must_keep`: **0 validator errors**.
- Lexicon coverage: **1 warning** for 37 messages not recognized by the short dialect-word list. This is a warning about the heuristic's limited coverage, not an assertion of 37 incorrect records.
- Prior-version comparison: **5 record changes only** (`g072`, `g085`, `g086`, `g088`, `g095`).
- Training/evaluation results are outside this dataset-validation report.

## Recorded validator output

```text
WARNING: 37 source(s) contain no word from the dialect list; check they are dialect: g005, g007, g008, g011, g013, g015, g020, g021, g023, g024, g027, g032, g033, g036, g038, g040, g048, g049, g052, g055, g058, g060, g065, g067, g069, g071, g076, g077, g079, g080, g082, g083, g089, g092, g095, g098, g099
100 rows, 92 with facts to keep (92%); first produced by: {'ai_assistant': 100}; 0 error(s), 1 warning(s)
```

## Integrity hash

`4b9d8425d8c26d54507475bb55f594d4670a78e72e7ad4e7a96a1e78d3971f19` — SHA-256 of `data/golden_test.jsonl`
