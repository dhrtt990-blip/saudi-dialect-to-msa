# NLP Applications requirements and evidence

The active task is booking-support rewriting for the fictional Darb Aljawza Travel agency. New execution uses Golden V3-R1 only. Historical V2.2 results do not satisfy an R1 performance requirement.

| Requirement group | Evidence | Verified state |
|---|---|---|
| Tests and CI | Local test logs in the private bundle; [CI on 229141e](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/actions/runs/45713438398) | 281 local tests passed; that exact CI run succeeded. Recheck after final edits. |
| Freeze before training | `review/v3_r1_revision_manifest.json`, commit `51127bdfb65a19adb763501d139515dd4479ff27`, activation `1fe1f8a0e10813cb421608831938221135cba735` | FROZEN_ACTIVE; 100 messages, 335 labelled key facts, 40 incomplete requests. Notebook preflight passed on Mac and Colab. |
| Leakage prevention | `review/v3_r1_preparation_summary.json`, `scripts/audit_r1.py`, full private processing report | 8,613 training and 957 validation rows, matching across Mac and Colab. No residual Golden text or distinctive-fact matches under documented thresholds. |
| Training and three-system comparison | Instrumented notebook, distinct timestamped R1 run directory; `scripts/export_r1.py`, `src/evaluate.py` | 1,078 steps and two epochs completed on Tesla T4. Final adapter saved, downloaded and reloaded; five validation outputs and matched Q8_0 exports verified. Actual same-100 comparison: baseline 82/100, tuned 88/100, full 89/100 automatic passes. Full releases 90/100, attempts 11 repairs, releases one repaired output and withholds ten. See results/public_v3_r1_summary.json. |
| Human review and safety | `scripts/summarize_r1.py`, `scripts/merge_r1_judgments.py`, `docs/BLIND_RATING_GUIDE_V3_R1.md`, travel safety fixtures | All 12 actual safety cases ran: 10 released after bounded checks, one asked and one blocked. Semantic failures remain. Separate blind A/B sheets contain 206 distinct outputs; genuine ratings, agreement and human T1–T3 remain pending. |
| Report and presentation | `scripts/build_r1_report.py`, `scripts/reproduce_r1_tables.py`, execution documentation and private bundle | The final private report/deck are generated from the actual saved evidence. The bundle includes a release manifest and clean-folder table-reproduction receipt; those receipts must be checked before marking delivery complete. |

## Scope and safeguards

- One narrow task, one selected base model: Qwen3-1.7B, within the 4B limit.
- The workflow checks missing details, rewrites, compares supported facts, attempts one repair, then releases or withholds.
- The missing-information rule checker was measured separately on frozen R1: asked on 33/40 incomplete messages, exactly labelled details on 32/40, and needless questions on 1/60 complete messages. This meets historical T4 at its lower exact-request threshold. The unchanged targets are in `review/v3_r1_targets.json`.
- Actual Ollama and Chrome/Streamlit demonstration passed complete and missing-detail requests on Apple M5, 16 GB, macOS 27.2.1. Both models passed exact prompt-template checks. No Windows demonstration is claimed.
- Team approval and the distinction between the original 11 checker disagreements and the 11 fact-label edits remain as recorded in the existing release evidence. This execution does not request or invent new signatures.
- Corpus licensing is unresolved. Public publication is limited to cleaned code and aggregate evidence; detailed predictions, rating sheets and new derived weights stay private.
