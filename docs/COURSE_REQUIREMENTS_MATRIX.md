# NLP Applications requirements and evidence

The active task is booking-support rewriting for the fictional Darb Aljawza Travel agency. New execution uses Golden V3-R1 only. Historical V2.2 results do not satisfy an R1 performance requirement.

| Requirement group | Evidence | Verified state |
|---|---|---|
| Tests and CI | Local test logs in the private bundle; [CI on d5afaca](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/actions/runs/45703816364) | 281 local tests passed; that exact CI run succeeded. Recheck after final edits. |
| Freeze before training | `review/v3_r1_revision_manifest.json`, commit `51127bdfb65a19adb763501d139515dd4479ff27`, activation `1fe1f8a0e10813cb421608831938221135cba735` | FROZEN_ACTIVE; 100 messages, 335 labelled key facts, 40 incomplete requests. Notebook preflight passed on Mac and Colab. |
| Leakage prevention | `review/v3_r1_preparation_summary.json`, `scripts/audit_r1.py`, full private processing report | 8,613 training and 957 validation rows, matching across Mac and Colab. No residual Golden text or distinctive-fact matches under documented thresholds. |
| Training and three-system comparison | Instrumented notebook, distinct timestamped R1 run directory; `scripts/export_r1.py`, `src/evaluate.py` | 1,078 steps and two epochs completed on Tesla T4. Final adapter saved, downloaded and reloaded; five validation outputs and matched Q8_0 exports verified. The actual R1 comparison is pending local model import and evaluation. |
| Human review and safety | `scripts/summarize_r1.py`, `scripts/merge_r1_judgments.py`, `docs/BLIND_RATING_GUIDE_V3_R1.md`, travel safety fixtures | Tools and 12 travel safety inputs prepared. Actual R1 safety outputs and two independent human judgments are not yet established. |
| Report and presentation | `scripts/build_r1_report.py`, `scripts/reproduce_r1_tables.py`, execution documentation and private bundle | Report and deck are in preparation. Final numeric tables must be rebuilt from actual saved predictions in a clean extraction. |

## Scope and safeguards

- One narrow task, one selected base model: Qwen3-1.7B, within the 4B limit.
- The workflow checks missing details, rewrites, compares supported facts, attempts one repair, then releases or withholds.
- The missing-information rule checker was measured separately on frozen R1: asked on 33/40 incomplete messages, exactly labelled details on 32/40, and needless questions on 1/60 complete messages. This meets historical T4 at its lower exact-request threshold. The unchanged targets are in `review/v3_r1_targets.json`.
- The new model's local Ollama and Streamlit demonstration is pending. The available local device is an Apple M5 Mac with 16 GB memory; no Windows demonstration is claimed.
- Team approval and the distinction between the original 11 checker disagreements and the 11 fact-label edits remain as recorded in the existing release evidence. This execution does not request or invent new signatures.
- Corpus licensing is unresolved. Public publication is limited to cleaned code and aggregate evidence; detailed predictions, rating sheets and new derived weights stay private.
