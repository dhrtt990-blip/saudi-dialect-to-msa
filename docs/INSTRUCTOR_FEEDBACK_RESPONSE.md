# Response to the instructor's feedback of 24 November 2026

**Status.** The code and its tests are in this repository. No model has been trained or run, and the travel-desk golden test is a draft that the team has not reviewed yet. Nothing on this page is a result.

## The service

The booking-support desk of **Darb Aljawza Travel (وكالة درب الجوزاء للسفر)**, a travel agency invented for this project. No real organisation's messages are used.

- Customers write to the desk in a chat, in Saudi dialect.
- The staff member needs each message as a formal written request in MSA: it is filed with the booking and sent on to the supplier (the airline, the hotel, the transport company). A chat message in dialect cannot be forwarded as it is. Producing that request is the one job of the system.
- Six kinds of message: new booking, change, cancellation and refund, enquiry, complaint and follow-up, extras (baggage, seats, insurance, invoices). The golden draft also holds six messages that a customer wrote formally, as controls.

We chose a travel agency because the open training corpus is travel and tourism text.

## The three points and what changed

| Instructor's point | What changed | Where | How it is measured |
|---|---|---|---|
| **Tie it to a specific service** | One service, described above. The prompt, the training templates and the golden draft are all written for it. | `docs/PROPOSAL.md`, `src/prompts.py`, the 43 templates in `src/data_prep.py`, `data/golden_v3_draft.jsonl` | The golden test and the template pairs all come from this one service |
| **Handle missing information** | A check runs before the model. A request to book that gives no date or no destination, or a request about an existing booking that gives no booking reference, is not rewritten: the app shows the question to put to the customer. The staff member may still choose to rewrite the message as it stands; the app then names the details that are missing, and the fact checker refuses a number, a date in digits, a named day or month, a listed place or a code that the message does not contain. It does not see a period given in words ("الأسبوع القادم") or a place outside its list. | `src/needs.py`, status `NEEDS_INFO` in `src/pipeline.py`, `app/streamlit_app.py` | 40 of the 100 draft messages are labelled with the detail they lack. The report counts: asked for exactly the missing details, asked for other details, not asked, asked needlessly, and how often each system adds a detail when the check is switched off |
| **Report what the checks miss** | The draft lists 335 key facts; two messages have no labelled facts. For every rewrite, two raters mark the key facts that are lost or changed. The report lists each lost fact in a rewrite the pipeline released, says whether the checker reads that kind of fact, and shows the checker as a classifier: released and fine, released with a problem (missed), withheld rightly, withheld without need. The rewrites the pipeline withheld are judged too. | `src/evaluate.py`, `src/facts.py`, `src/validate_golden.py`, `scripts/golden_review.py`, `docs/annotation_guidelines.md` | Report sections "Key facts in released rewrites", "What the checks missed" and "The fact checker as a classifier" |

## The recipient, and which details the system asks for

The instructor's example of a missing detail was the recipient. Here the recipient of the formal request is the supplier.

- For an **existing booking**, the booking reference is what identifies the supplier. "The air conditioner in room 412 is broken" cannot be passed to a hotel until the desk knows which booking it is. So the booking reference is the detail the system asks for.
- For a **new booking**, the desk chooses the supplier itself, so nothing about the recipient can be missing from the customer's message. What can be missing is when and where to.

| Kind of request | Needed details |
|---|---|
| A request to book (a flight, a room, a package, a car, a tour) | the date and the destination |
| A request to act on a booking the customer already has, a problem with a booked service, or a question about his own booking | the booking reference |
| A general question (prices, baggage rules, visas) | none |

The check covers these three details only. It does not ask for the departure city, the number of travellers or their names; the desk collects those on its booking form. That is a limit of this version.

## What the fact checker reads now

Before: numbers, dates, times, e-mail addresses, links, words in Latin letters, and names the user lists.
Added: weekdays and relative days ("بكره" and "غداً" are the same day), months by name, and 95 listed places (`src/gazetteer.py`).

It still does not read: numbers written in words ("تذكرتين"), a travel class ("درجة الأعمال"), a place that is not in the list, and anything that depends on meaning (which price belongs to which package). These are the facts the key-fact labels and the two raters cover, and the report splits every lost fact into "a kind the checker reads" and "outside what the checker reads". Only labelled facts can be reported as missed, so the report is as complete as the labels are.

## What the missing-information check does on the draft

It asks on 33 of the 40 messages labelled as lacking a detail, for exactly the labelled details on 32, and asks needlessly on 1 of the 60 complete messages (t042, a cruise from Jeddah: the rules ask for a destination, and the guide counts the cruise itself as the destination).

The 7 it does not ask about are six complaints or follow-ups about a service in progress (a broken air conditioner, a driver who did not come, a lost bag, a visa not received) and one report of a wrong name on a ticket. None of them uses a word the rules look for. This is the main thing this check misses today.

It can also ask without need: a general question that uses the noun of an act ("هل فيه استرجاع؟") is asked for a booking reference. The draft has no general question of this kind, so the 1 of 60 does not measure it.

A bare number directly followed by a supported currency word is treated as an amount. A bare number without a currency marker can still be ambiguous.

The draft and its initial rules have the same author, so these numbers are not an independent measurement. The independent part is the team's review, in which members rewrite messages in their own words; a further set written by members who have not read `src/needs.py` would be a cleaner test.

## Limits we state

1. **The training corpus is not booking requests.** The open corpus (Almeman 2025) is short travel and tourism sentences. The 43 template pairs are the only training pairs written as messages to a booking desk. This gap is real and the evaluation will show its cost.
2. **The draft reads as one author's work.** It is mostly general Najdi and urban Hijazi, in short single sentences, typed more tidily than customers type. The reviewers are asked to rewrite messages in their own dialect.
3. **The word lists are short.** A place that is not listed is not read, so its loss is not caught and the check may ask for a destination the message does give.
4. **A listed word is read whatever it means.** "الاثنين" (both of them) is read as Monday and "الخبر" (the news) as the city, so a correct rewrite that words it differently is withheld or repaired. The classifier table counts these.
5. **The checker reads words, not meaning.** A rewrite can keep every fact and still say something else. The raters' verdict covers that.

## The golden test: from v2.2 to v3

`data/golden_test.jsonl` is still release v2.2 (general service topics), frozen in commit `eb809ee` on 20 November 2026. It stays in place until the team has reviewed the travel-desk draft.

- The draft is `data/golden_v3_draft.jsonl`: 100 messages `t001` to `t100`. Seven of them are travel messages of v2.2 kept word for word, and five more are adapted from it.
- Each row carries `key_facts` and `missing`. The review workbook is `review/golden_v3_review.xlsx`; its sign-off columns are empty.
- The rule of the course is that the golden test is fixed before training. No model has been trained or run, so replacing the test now keeps that rule. v2.2 will be kept under a git tag and in `data/archive/` (steps 1 and 3 of `docs/GOLDEN_V3_FREEZE_STEPS.md`).
- Each member signs the rows he reviewed, in the sheet itself, and the import records how many rows differ from the draft.

## Targets proposed to the team

They are in `docs/PLAN_REVIEW_PREP.md` (T1 to T4). The team fixes them by committing that file before the plan review and before any model is run.

## Not done and not checked

- No fine-tuning, no Ollama run, no evaluation on a real model, no error analysis.
- No rewrite of a real model has been judged, so there is no list of missed facts yet. The labels and the report code are in place; the first list comes with the evaluation.
- The Colab notebook has not been run. The corpus download and the data preparation on the full corpus have not been run from this repository; with the checker now reading days and places, the number of corpus pairs dropped for a fact mismatch is unknown (on a sample of 45 real corpus rows it drops 4, the same 4 as before the change).
- The travel-desk draft has not been read by a native speaker of the dialect.
