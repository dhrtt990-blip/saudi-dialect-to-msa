# Five-minute plan review — instructor's four questions

## 1. What exactly does the model do, and why fine-tune?

**Task:** rewrite short Saudi-dialect requests into formal MSA without changing meaning or factual details. **Audience:** customer-service and administrative staff. **Hypothesis:** a small prompted model may preserve formal tone less reliably and may introduce, drop, or rewrite details. Compare with a carefully prompted untuned model; do not assume gains.

## 2. What data is used, and what is held out?

**Training candidate:** Khalid Almeman's MSA/Saudi pairs from the 50,010-row multidialectal travel corpus, plus synthetic fact-bearing examples. Licensing conflict requires caution. **Evaluation:** 100 AI-assisted messages approved according to the team leader, with 25 peer reviews per member and reviewer-pair attribution fully documented in the approval report; the local Golden Test is prepared for its pre-training GitHub freeze commit. **Separation:** exact, near-duplicate and distinctive-fact checks in `src/data_prep.py`, with an auditable processing report. The AI draft is provenance only; `data/golden_test.jsonl` is the team-approved release. Publication of a freeze commit must be demonstrated before training.

## 3. What is the workflow and failure behavior?

A LoRA-tuned Qwen3-1.7B locally rewrites; deterministic checks compare supported number/date/time/Latin token patterns and listed names. On detected mismatch the model gets one repair; if still unresolved, the system withholds and returns the original. This checker cannot establish full semantic equivalence; name detection is limited and numbers expressed in words can escape it. Right-to-left Streamlit UI is planned for on-device presentation.

## 4. How will the team measure success?

Before (untuned with strong prompt), after (LoRA), and after-in-workflow (LoRA+checker+repair). On the **same frozen golden set**: human-assessed semantic correctness, MSA naturalness, fact preservation, dialect residuals, released-output factual error rate, withholding rate, failures, latency (if feasible), wrong→right vs right→wrong, and ten safety cases. Review judgments should be blind to the system. The team must set a numeric success threshold before experimentation. No real measured result exists yet.

### Planned evidence for the final presentation

- Golden freeze commit with date; reviewer assignments and reviews.
- Full provenance, licence verification, train/validation counts and overlap report.
- Model card, Hugging Face adapter, training configuration and logs.
- Identical-test baseline/tuned/full reports with counted errors and qualitative examples.
- Live local Ollama + Streamlit and adversarial safety report.
