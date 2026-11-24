# Model Card — Planned Qwen3-1.7B LoRA Saudi Dialect → MSA Rewriter

## Model objective

Rewriting short Saudi-dialect messages into formal Modern Standard Arabic while retaining intent and facts (numbers, dates, times, Latin-script content and explicitly listed names). The service is the booking-support desk of a travel agency: customers' messages about bookings, changes, cancellations, refunds, enquiries and complaints.

- **Base model:** `Qwen/Qwen3-1.7B`, within the course's 4B parameter limit.
- **Adaptation:** supervised LoRA; QLoRA fallback described in `notebooks/train_qwen3_lora_colab.ipynb`.
- **Deployment plan:** local Ollama inference and right-to-left Streamlit interface.
- **Pipeline:** missing-information check (ask for the date, destination or booking reference instead of rewriting) → rewrite → deterministic fact comparison (now including days, months and listed places) → one repair attempt → release/withhold; semantic equivalence is not guaranteed by rules.
- **Repository:** `dhrtt990-blip/saudi-dialect-to-msa` on GitHub (public).

## Training provenance

Training notebook, dependency files and data preparation code are present. At this release checkpoint **no real training log, LoRA adapter checkpoint, measured training duration or published adapter is provided**. Values are supplied from a reproducible run, not filled with estimates. Source corpus usage requires licence clarification as detailed in `docs/DATASET_CARD.md`.

## Golden reference benchmark

The 100-example benchmark in `data/golden_test.jsonl` is approved according to the team leader's attestation, with 25 reciprocal peer reviews per team member. All four reciprocal pairings were confirmed directly by the leader, who witnessed the team review and approval; the register is `review/golden_review_approved.xlsx`. Strict validator output: 0 errors, 1 dialect lexicon coverage warning. Golden Test v2.2 has 100/100 owner approvals and peer reviews, with five refinements rechecked by Mohammed and Musaad in the team leader’s presence. Commit the benchmark **before** real training.

## Evaluation design (future real measurements)

| System | Release rate | Meaning/quality judgements | Preserved factual spans | False releases / withheld |
|---|---|---|---|---|
| Untuned Qwen3-1.7B with full baseline prompt | Measure on real model | Two blinded human raters | Calculate using golden set | Report experimentally |
| LoRA-tuned model alone | Measure on real model | Two blinded human raters | Calculate using golden set | Report experimentally |
| Tuned model + verification pipeline | Measure on real model | Two blinded human raters | Calculate using golden set | Report experimentally |

Also report wrong→right versus right→wrong examples, error categories, ten adversarial inputs, and local inference timing if measured. Mock-only evaluations are diagnostics, not model accuracy results.

## Limitations and responsible use

- Pattern checks cannot fully understand meaning or preserve every implicit fact.
- The candidate corpus is short, often machine-generated and travel-focused; generalization to other dialect regions and domains is uncertain.
- Some synthetic training templates and golden examples share an AI drafting process, so data leakage and style shortcuts require careful checks.
- Proper-name matching only covers names explicitly supplied as `must_keep`.
- Days, months and places are found by short word lists. A place outside the list is not checked, and a listed word is read as a day or a place whatever it means in the sentence.
- The missing-information check is a short set of rules on words. It misses requests worded in ways the rules do not cover and sometimes asks needlessly; both are counted on the golden test.
- Final adapter sharing and licence will be chosen after confirming upstream rights.
