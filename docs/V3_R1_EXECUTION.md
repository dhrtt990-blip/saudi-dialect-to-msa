# Historical execution record — V3-R1

This is the historical execution narrative from the team's [source commit](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/blob/16763e6ac46bdaf9ed67864c1df92f401bbcdd51/docs/V3_R1_EXECUTION.md). References to active R1 and blank rating sheets describe that execution date, not current status. V3-R2 is now active, and the later label-set status is documented in [HUMAN_EVAL_V3_R1.md](HUMAN_EVAL_V3_R1.md). No private artifacts were inspected during this integration.

# Travel desk V3 R1 execution

The active benchmark is frozen at `51127bdfb65a19adb763501d139515dd4479ff27`, activated at `1fe1f8a0e10813cb421608831938221135cba735`. This execution starts from `66d26070ba6b98ca3356e39914282bfc72326c76`. Its CI run [45688309066](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/actions/runs/45688309066) completed successfully. No historical V2.2 model result is a V3-R1 result.

## Data preparation

The notebook release preflight passed locally and in a Google Colab Tesla T4 runtime. Golden SHA-256 is `e1dbff1b7a8045dc061a622b1233d2ccee8ef4b5901202a2f6391e9c906ef8e6`: 100 messages, 335 labelled key facts, 40 incomplete requests. No frozen labels or rules were changed.

The original Zenodo CSV downloaded successfully: 18,375,663 bytes, MD5 `67eea3fcb2c7671963afff33787f8dd8`, SHA-256 `ceab0017eb85bdf4b7435ed59cdce5f2718a41e59d675f32ca4338e12e6aacc8`. Python on the Mac initially rejected its TLS certificate chain; curl downloaded it with certificate verification enabled. Colab downloaded it through the existing script successfully.

With seed 13, 8,000 cleaned corpus examples and 2,000 synthetic examples were assembled. Cleaning removed 323 examples; Golden overlap filtering removed 107 more, leaving 9,570 pairs: 8,613 training and 957 validation. Of these, 7,876 are corpus pairs and 1,694 synthetic pairs. The written train/validation files match between Mac and Colab byte for byte. See `review/v3_r1_preparation_summary.json` for counts and checksums.

`scripts/audit_r1.py` separately rechecks every written source and target against the Golden exact/containment/near-duplicate index and its distinctive facts. Both splits have zero remaining matches under the configured thresholds (near duplicate 0.8; shared content 0.6). This is a bounded string-based leakage audit, not proof of semantic independence. Full examples and training files stay in the private team bundle pending licence clarification.

## Missing information

The unchanged rule checker asks on 33/40 incomplete messages, asks for exactly the labelled details on 32/40, and asks needlessly on 1/60 complete messages. It misses 7/40 incomplete messages and asks an extra detail on one. These are automatic rule results, independent of model training. T4 meets its historical thresholds of at least 80% exact requests and at most 10% needless requests. The targets were recovered unchanged from the historical team package and are recorded in `review/v3_r1_targets.json`; this recovery is not a new preregistration.

## Tests and runtime

281 tests passed locally after adding delivery and human-rating guards; final edits require the final test run. An initial sandboxed run could not bind the local HTTP test server; rerunning with local server access passed all tests. The Mac is an Apple M5 with 16 GB unified memory and approximately 690 GiB free disk space, with no CUDA. Colab supplied a Tesla T4, Python 3 GPU backend, approximately 12.7 GB RAM and 112.6 GB disk. Weights for Qwen3-1.7B downloaded and loaded successfully.

Training initialization found optional `torchao 0.10.0` incompatible with PEFT's minimum 0.16.0. The failed attempt is retained in its own output directory; no optimizer step was claimed for it. Execution records must establish a positive step count, a saved adapter, final metrics and successful reload before marking training complete.

Detailed model predictions, blind rating sheets and error examples stay in the private team bundle. Public publication covers code and aggregate results only. No new weights are published while corpus licensing remains unresolved.

## Completed R1 training and export

Run `travel-v3-r1-20261125T195842Z` completed 1,078 steps and two epochs on the Tesla T4. Trainer runtime was 7,042.7243 seconds; the final adapter was saved after 7,044.2135 seconds. Validation loss was 0.0969375 after epoch one and 0.0879845 after epoch two. These losses do not establish Golden quality. Both epoch checkpoints and the final adapter are saved locally. The complete downloaded training ZIP passed SHA-256 and ZIP CRC checks.

The final adapter digest is `2ace6f366dfc35192385ade92d2548e57250ae6c419d07d4039e5257e49d5aa8`. It was reloaded from disk, generated five nonempty validation rewrites, and merged only after the unadapted base was exported. Both models were converted to Q8_0 with llama.cpp `bb692efaa43809dd8584fefddda42a54a9a50846`. Sizes and digests appear in the model card and private conversion manifest.

Compatibility repairs are recorded, not hidden: unused torchao was removed; pyarrow 26.0.1 remained loaded after 23.0.1 was installed; Transformers 5 lacks the former config `_commit_hash` attribute, so the actual base revision was resolved from the sole local Hugging Face snapshot. Standard venv failed in Colab; virtualenv created the separate converter environment. Transformers 4.57.6 could not read the tokenizer format written by 5.23.0; conversion succeeded with 5.23.0. No failed attempt contributes a released model artifact.

The public training aggregate is `review/v3_r1_training_summary.json`. The maintained primary notebook preserves the preflight and incorporates observed repairs; the exact historical executed cell source, differing runtime overlays and checksums are retained separately. A public notebook edit does not retrospectively change the recorded training source commit.

## Actual R1 comparison and local demonstration

The models were imported locally from the verified matched GGUF files and passed all four exact prompt-template checks each. Evaluation executed from clean commit `229141e9d4fd7bbcca9fdaa369adeea067535e45` with temperature 0, inference seed 0, 512 maximum new tokens and thinking off. All three prediction files contain the same 100 frozen IDs. The saved prediction digests and a separate execution receipt bind the outputs to this source and the actual Ollama model digests.

| System | Released | Automatic passes | Repairs attempted | Released after repair | Withheld |
|---|---|---|---|---|---|
| Fixed prompted baseline | 100/100 | 82/100 | 0 | 0 | 0/100 |
| LoRA alone | 100/100 | 88/100 | 0 | 0 | 0/100 |
| Full pipeline | 90/100 | 89/100 | 11 | 1 | 10/100 |

Baseline-to-tuned automatic transitions: 11 failures became passes and five passes became failures. Tuned-to-full: one failure became a pass and no pass became a failure. These are not human semantic-correctness transitions. The full system has zero automatically detected fact errors among 90 released messages, but actual released outputs can change intent; the private analysis documents examples. The zero is not a human false-release count.

The 12-case travel safety run produced 10 RELEASED_CHECKED, one ASKED and one BLOCKED. Released checks do not establish semantic safety. Two separate blind sheets contain 206 distinct actual rewrites, including withheld candidates. All human rating fields remain blank; there is no invented agreement or human T1–T3 result. T4 is met, and T3's numeric withholding limit alone is met.

The actual Chrome/Streamlit demonstration used the R1 tuned model on a MacBook Pro Apple M5, 16 GB, macOS 27.2.1 build 26B131, Ollama 0.40.18. The complete request preserved Jeddah, 19/4 and 10:30; the incomplete request produced date and destination questions without a rewrite. Windows was not tested. Detailed inputs and outputs remain in the private team bundle.
