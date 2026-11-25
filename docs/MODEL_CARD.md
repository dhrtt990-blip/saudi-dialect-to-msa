# Model card — Travel desk V3-R1 Qwen3-1.7B LoRA

## Purpose and workflow

Rewrite fictional Darb Aljawza Travel customer messages from Saudi dialect into formal Modern Standard Arabic while preserving intent and booking facts. The system presents missing-detail questions for staff, rewrites, checks supported facts, attempts one repair and withholds a rewrite when the difference persists. A rule pass does not establish semantic equivalence.

## Model and training

- Base: `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, within the 4B course limit.
- Actual training source: `66d26070ba6b98ca3356e39914282bfc72326c76`; exact executed cell SHA-256 `127be1fcbdd6a0cc9ee3eb0b6984b3a6b094fd44c28f185277aa47f8c0a9e4ac`.
- Run: `travel-v3-r1-20261125T195842Z`, Tesla T4, float16 LoRA, seed 13, 2 epochs, 1,078 optimizer steps.
- Rank 16, alpha 32, dropout 0.05, all linear layers; 17,432,576 trainable parameters of 1,738,007,552 total.
- Assistant-only loss, maximum 768 tokens, batch 4 × accumulation 4, learning rate 0.0001, cosine schedule.
- 8,613 training pairs and 957 validation pairs; the written files matched between Mac and Colab. Golden R1 remained evaluation-only and was used only to exclude overlap during preparation.
- Trainer runtime: 7,042.7243 seconds. Runtime through final adapter saving: 7,044.2135 seconds. Epoch validation losses: 0.0969375 and 0.0879845. These are training-source losses, not Golden accuracy.
- Saved adapter SHA-256: `2ace6f366dfc35192385ade92d2548e57250ae6c419d07d4039e5257e49d5aa8`. The adapter was reloaded from disk and generated nonempty rewrites for five validation examples.

The public aggregate record is [review/v3_r1_training_summary.json](../review/v3_r1_training_summary.json). Detailed logs, checkpoints, source, package freeze and reload outputs remain in the private team bundle. Loaded and installed modules are recorded separately: pyarrow 26.0.1 remained loaded after pip installed 23.0.1. This execution is not described as a clean restart with 23.0.1.

## Frozen benchmark and evaluation

The active benchmark is `data/golden_v3_r1_candidate.jsonl`: 100 messages, 335 labelled key facts, 40 incomplete requests, SHA-256 `e1dbff1b7a8045dc061a622b1233d2ccee8ef4b5901202a2f6391e9c906ef8e6`. Freeze and approval evidence remain unchanged. Historical V2.2 outputs are separate and are not new R1 results.

Compare a fixed prompted baseline, LoRA alone and the full pipeline on all 100 messages, with missing-detail checks disabled for that three-system comparison and scored separately. Report automatic passes, releases, repairs and withholding with denominators. Human meaning, added content, labelled-fact losses and unnecessary withholding require genuine blind judgments. Unjudged human outcomes remain pending, not zero. Actual automatic pass counts are 82/100 for the baseline, 88/100 for LoRA alone and 89/100 for the full pipeline. The full pipeline releases 90/100 and withholds 10/100; it attempts 11 repairs, releases one repaired output and withholds ten. Two-rater correctness is unjudged. Baseline-to-tuned automatic transitions are 11 failures to passes and 5 passes to failures, a net gain of 6. These are automatic outcomes, not semantic gains. See [public R1 aggregates](../results/public_v3_r1_summary.json).

The unchanged missing-detail rules ask on 33/40 incomplete messages, ask for exactly the labelled fields on 32/40, and ask needlessly on 1/60 complete messages. This meets historical T4 at its lower exact-request threshold. Fixed T1–T4 are in [review/v3_r1_targets.json](../review/v3_r1_targets.json), with the timing of their historical recovery disclosed.

## Matched deployment artifacts

Both HF exports were converted using llama.cpp `bb692efaa43809dd8584fefddda42a54a9a50846`, Q8_0, and the same saved tokenizer. Each GGUF is 1,834,426,208 bytes.

| Artifact | SHA-256 |
|---|---|
| Untuned base Q8_0 | `3ac117c8d53c7ed174523db645fcaa76cae9cf6661438332f693c8c7f450a56e` |
| Merged LoRA Q8_0 | `93118a663a1b600fa1373b0a13d0fd14dae936c4a2d29e8bfa63c2ebc27341a8` |

The conversion runtime uses Transformers 5.23.0 to read its own saved tokenizer format. The attempted 4.57.6 conversion failed and contributes no model artifact. The preserved conversion manifest records all source-file digests. Both models passed the four-case exact prompt-template and repeat-penalty checks in Ollama 0.40.18 on an Apple M5 Mac. An actual Chrome/Streamlit demonstration released a complete booking request with its city, date and time, and asked for date and destination on an incomplete request. macOS 27.2.1 was tested; Windows was not.

## Limits and licensing

The checker reads bounded patterns, words and supplied names; it misses some semantic changes, number words and relationships between preserved facts. The corpus is short and AI-generated; the small benchmark originated from AI-assisted drafts and team review. Neither establishes generalization to real customers or other domains. Two human raters must review the actual R1 output sheets; no AI analysis is counted as their agreement.

Base model licence: Apache 2.0. Corpus licence statements conflict between Zenodo metadata and its attached README, with upstream terms unresolved; see [dataset card](DATASET_CARD.md) and [licence audit](../review/v3_r1_licence_check.json). New weights and detailed derived texts remain private. Historical V2.2 weights and evidence are preserved.

## Safety and human review status

All 12 travel safety cases ran: 10 RELEASED_CHECKED, one ASKED and one BLOCKED. RELEASED_CHECKED is not semantic safety; actual released outputs include changes to a complaint and to a question. Assistant error analysis is separate from human ratings. Separate A/B blind sheets contain 206 distinct rewrites and withheld candidates. No genuine R1 ratings were supplied, so agreement and T1–T3 remain pending. T4 meets its fixed thresholds; the withholding part of T3 alone is within its limit.
