# Five-minute plan review — instructor's four questions

Revised 24 November 2026 after the instructor's feedback. No model has been trained or run; nothing below is a result.

## 1. What exactly does the model do, and why fine-tune?

**Task:** rewrite a customer's short Saudi-dialect message into formal MSA without changing its meaning or its facts, and without adding any. **Service:** the booking-support desk of Darb Aljawza Travel, an invented travel agency (no real organisation's messages). **User:** the staff member at the desk, who needs each chat message as a formal written request to file with the booking and send to the supplier. **Hypothesis:** a small prompted model may leave dialect in place and may drop, change or add details. Compare with a carefully prompted untuned model; do not assume gains.

## 2. What data is used, and what is held out?

**Training candidate:** Khalid Almeman's MSA/Saudi pairs from the 50,010-row multidialectal travel corpus, plus 43 template pairs written as messages to a booking desk. The corpus is tourism sentences, not booking requests; that gap is stated, not solved. Licensing conflict requires caution. **Evaluation:** a 100-message golden test for the travel desk. It is a draft today (`data/golden_v3_draft.jsonl`); the rows label their key facts, and 40 rows label the needed detail they lack. It replaces release v2.2 after two members have signed every row, and its commit comes before any training. **Separation:** exact, near-duplicate and distinctive-fact checks in `src/data_prep.py`, with an auditable processing report.

## 3. What is the workflow and failure behavior?

1. **Missing information.** A request to book without a date or a destination, or a request about a booking without its reference, is not rewritten. The app returns the question to ask the customer.
2. **Rewrite.** A LoRA-tuned Qwen3-1.7B rewrites locally.
3. **Check.** Deterministic checks compare numbers, dates, times, Latin tokens, days, months, listed places and listed names. A detail that is in the rewrite but not in the message counts as a difference, so a guessed date in digits, named day or listed city is caught; a period given in words ("الأسبوع القادم") is not.
4. **Repair or withhold.** On a difference the model gets one repair; if it still differs, the system withholds and returns the original.

The checker reads words, not meaning; numbers in words and places outside the list escape it. Right-to-left Streamlit UI for on-device presentation.

## 4. How will the team measure success?

Three systems on the **same frozen golden set**: untuned with a full prompt, LoRA alone, LoRA in the workflow. A rewrite is correct only if it passes the automatic fact check, leaves no listed dialect word, and two blind raters find the meaning kept and no labelled key fact lost or changed. Also reported: errors by type, wrong→right against right→wrong, what the checks missed, the checker as a classifier (the withheld rewrites are judged too), the missing-information check against the labels, and ten safety cases.

For T1, run the matched-prompt comparison with `--matched-prompt` in a separate output directory, using the same checkpoint family, quantization and decoding settings. Keep the few-shot baseline as the operational comparison. For T2–T3, report released and withheld counts out of all 100 rewrite attempts, plus problematic releases out of all releases. Report added, lost and changed information separately and keep the deployed clarification rate separate from rewrite withholding. Evaluate any rule changes informed by V3 on a separate, unseen set.

### Targets proposed to the team

The course asks for the targets to be fixed at the plan review. They are proposals until the team commits this file; after that they do not change.

| | Target | How it is read from the report |
|---|---|---|
| **T1** Fine-tuning helps | LoRA alone is correct on at least 10 more of the 100 messages than the untuned model (wrong→right minus right→wrong), and an exact two-sided sign test on the messages that changed gives p < 0.05 | "Examples that changed". With 0, 1, 2, 3, 4, 5, 6, 7, 8 messages getting worse, at least 10, 11, 12, 13, 14, 15, 17, 18, 20 must get better |
| **T2** The workflow protects the facts | At most 3 of the rewrites the full system releases have a problem in the raters' reading (meaning changed, content added, or a labelled key fact lost or changed) | "The fact checker as a classifier", cell "missed by the checks"; every case is listed in "What the checks missed" |
| **T3** The check costs little | The full system withholds at most 15 of the 100 rewrites, and at most 5 of the withheld ones are judged fine by the raters | "The fact checker as a classifier" |
| **T4** It asks instead of guessing | The check asks for exactly the labelled details on at least 80% of the messages that lack a needed detail, and asks needlessly on at most 10% of the complete ones | "Missing-information check" |
| **Gate** | The two raters agree on at least 80% of the verdicts before they reconcile; below that the guide is revised and the judging repeated | First lines of the report |

On the draft the missing-information check asks for exactly the labelled details on 32 of 40 messages (80%) and asks needlessly on 1 of 60. That is at the threshold of T4 and no more, and T4 was proposed after the draft had been scored (31 of 40 at the time; 32 after two words were added to the rules), so the draft is not evidence for it; the team may set another threshold before the plan review. The messages it misses are six complaints about a service in progress and one report of a wrong name on a ticket. The rules may be improved until the golden test is frozen, not after. The rules and the draft have the same author, so the number that counts is the one on the reviewed test.

### Planned evidence for the final presentation

- Golden freeze commit with date; reviewer assignments and reviews.
- Full provenance, licence verification, train/validation counts and overlap report.
- Model card, Hugging Face adapter, training configuration and logs.
- Identical-test baseline/tuned/full reports with counted errors and qualitative examples.
- Live local Ollama + Streamlit and adversarial safety report.
