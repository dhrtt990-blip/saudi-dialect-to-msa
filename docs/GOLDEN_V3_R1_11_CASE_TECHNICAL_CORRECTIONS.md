# V3-R1 — 11 prioritized technical corrections before freeze

**25 November 2026.** The team leader explicitly authorized technical correction of 11 cases. The original handoff's 11-case list could not be recovered; the 11 below are independently selected from the concrete defects observed in the current team-approved workbook. They are not represented as the original list. The source benchmark remains byte-identical; this candidate changes only the `key_facts` field on exactly 11 records. Sources, references, missing-information labels, original owner/peer metadata and V2.2 are unchanged. The recorded owner/peer names refer to the earlier review, not new signatures on this revision.

| ID | Before | After | Rationale |
|---|---|---|---|
| t008 | ["أسبوع","H8W3KD","ظرف طارئ"] | ["تأجيل سفري أسبوعاً","H8W3KD","ظرف طارئ"] | Preserve direction of the date change (postpone, not advance) together with its duration. |
| t015 | ["K7M2QX","يومين"] | ["لم تصل حقيبتي","K7M2QX","يومين","ألبس الملابس نفسها"] | Preserve the missing-baggage complaint and continuing hardship, not merely the incident identifier and duration. |
| t037 | ["K4T9WB","10 أيام","2350"] | ["ألغيت حجزي","K4T9WB","10 أيام","لم يُرد إليّ شيء","2350"] | Preserve cancellation and non-receipt of the refund. |
| t055 | ["التأشيرة لم تصدر \| لم تصدر التأشيرة","55273"] | ["لم أستطع السفر","التأشيرة لم تصدر \| لم تصدر التأشيرة","استرداد المبلغ","55273"] | Preserve inability to travel, its cause and the refund request. |
| t056 | ["booking@example.com","49026"] | ["أرسلوا إليّ التذاكر","booking@example.com","بدلاً من الواتساب","49026"] | Preserve the requested document and channel replacement, not just the email address. |
| t064 | ["المرشد","الغد"] | ["المرشد الذي معنا في الجولة","لا يتحدث العربية ولا الإنجليزية جيداً","نريد غيره","الغد"] | Preserve negative language-proficiency complaint and replacement request. |
| t076 | ["غرفة مفردة","المدينة","قريبة من المسجد النبوي \| بالقرب من المسجد النبوي","هادئة","طابق مرتفع \| دور عالٍ"] | ["غرفة مفردة","المدينة","قريبة من المسجد النبوي \| بالقرب من المسجد النبوي","هادئة","ألّا تكون في طابق مرتفع"] | Replace the positive-only high-floor span with the actual negated constraint; a high-floor request is the opposite meaning. |
| t081 | ["640","الحقيبة الإضافية"] | ["640","الحقيبة الإضافية","لم آخذ معي حقيبة"] | Preserve the reason for refund: the customer did not take a bag. |
| t083 | ["ساعة ونصفاً \| ساعة ونصف","180"] | ["لم يحضر السائق إلى المطار","ساعة ونصفاً \| ساعة ونصف","أخذنا سيارة أجرة","180"] | Preserve driver no-show and substitute taxi, as well as the wait and cost. |
| t087 | ["تذكرة واحدة","M9D4XK"] | ["تذكرة واحدة فقط","M9D4XK","الباقون فسيسافرون"] | Preserve exclusive partial refund and the remaining travelers' unchanged plans. |
| t097 | ["412","مكيف","لا توجد غرف أخرى"] | ["مكيف الغرفة 412 معطل","لا توجد غرف أخرى"] | Link the malfunction to the room and its air conditioner; avoid double-counting the room number as a separate label. Human review must verify the malfunction, not just the room number. |

Before: 322 fact-label entries; candidate: 335. Both have 100 rows and 40 rows with missing-detail labels. Labels are reference anchors, not a proof of entailment. In particular `fact_present` checks machine-readable atoms where available and may miss changed relations/negation; independent human raters must assess the entire meaning. No tuning of the checker or lexicon to the benchmark was performed. The two warning groups remain documented in the [pre-freeze audit](GOLDEN_V3_PREFREEZE_WARNING_AUDIT_2026-11-25.md).

Two other observed scope issues (t068, receipt/email and t080, father's illness) are not part of this 11-row patch and remain unchanged, with semantic assessment required. The original 11-case report is still needed for an exact reconciliation. This technical candidate is not a retroactively team-signed gold, a frozen active benchmark or evidence of V3 model performance.

- Candidate: [JSONL](../data/golden_v3_r1_candidate.jsonl), SHA-256 `e1dbff1b7a8045dc061a622b1233d2ccee8ef4b5901202a2f6391e9c906ef8e6`.
- [Change log CSV](../review/v3_r1_technical_changes.csv), [manifest](../review/v3_r1_revision_manifest.json).
- Validate with `python -m src.validate_golden data/golden_v3_r1_candidate.jsonl` and `python -m pytest -q tests/test_golden_v3_r1_candidate.py`.
- Before activation: reconcile original 11 cases, record explicit approval of the exact candidate and freeze commit, confirm split isolation, then run new evaluation. Never reuse V2.2 scores as V3 scores.
