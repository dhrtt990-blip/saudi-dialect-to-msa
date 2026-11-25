# V3 pre-freeze technical review — warnings and outstanding evidence

Date: 25 November 2026. Review anchor: [d5bd182](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/commit/d5bd1822efbf38ba4fd1ed30bcf744d84f603c33). Dataset SHA-256: `09c1937ebac93056f1c33ef07037b157bc80e05361063474ef5e827dc73ccbbf`. This is a technical audit, not a new team approval. No dataset, checker, lexicon, historical results or sign-off was changed.

## Verified CI baseline
[Run 45682598512](https://github.com/dhrtt990-blip/saudi-dialect-to-msa/actions/runs/45682598512): 270 tests passed; V3 100 rows, 86 with machine-detectable facts, 322 key-fact entries, 40 missing-detail rows, zero errors, two warning groups. Passing structural checks does not prove semantic fidelity.

## Warning 1 — 46 sources without a strong dialect-lexicon match
The validator's short lexicon is a heuristic, not an exhaustive dialect classifier. The following source cues were manually inspected. Cues are illustrative of informal register, not a claim that each expression is uniquely Saudi. Retain the messages; do not insert artificial dialect markers or tune the evaluator on held-out benchmark rows to remove the warning. t042 and t086 have relatively mild dialect/register signals; natural mixed-register customer messages are acceptable, but do not call them strong dialect examples. Review disposition: retain as documented heuristic limitation; no blanket linguistic guarantee.

| ID | Source cue |
|---|---|
| t003 | ابي اعرف / من اي صالة تطلع / كم لازم اجي |
| t006 | ابي / جنب الشباك |
| t008 | ودي / سفرتي / عندي ظرف |
| t009 | ضيفوا لي / شنطة / كم سعرها |
| t011 | كنسلت / ما وصلني / انلغت ولا لا |
| t012 | ودي / المغرب (time usage) |
| t013 | نبي / 7 ليالي |
| t014 | اقدر / ابي / شهور |
| t015 | الشنطة / ما وصلت معي / لي يومين |
| t017 | لو سمحتوا / والصح |
| t018 | فلوسي / وانتو قلتوا |
| t019 | حنا / كبار |
| t021 | كم ياخذ / السواق |
| t022 | ابي / يضيق علي |
| t024 | ودي / الرجعة |
| t028 | ابي الغي / كم بيرجع لي |
| t029 | ابي كرسي متحرك |
| t033 | انتم قلتوا / كلموهم |
| t038 | فيه رحلة / المغرب |
| t040 | نبي فاتورة / وفيها |
| t041 | ابي / لين |
| t042 | احجزوا لي / 4 ايام (short mobile-message register) |
| t047 | نبي / لين / مع بعض |
| t050 | لو سمحتوا / كتبته غلط |
| t052 | الفطور داخل في السعر ولا لا / ما فهمتها |
| t054 | ابي احجز / لي ولزوجتي |
| t056 | الايميل / الواتس |
| t059 | ممكن تحجزون لي |
| t060 | انلغت / ابي فلوسي ترجع |
| t066 | فلوسي / لي اسبوعين انتظر |
| t071 | نبي / ل 5 اشخاص |
| t072 | الشنطة / معايا شنطتين / كل وحدة |
| t073 | محتاج احجز / الجاي / اهم شي |
| t076 | ابيها هادية / دور عالي |
| t077 | احد يرد علي / انلغى من نفسه |
| t081 | ابي استرد / حقت / الزايدة / ما اخذت |
| t082 | نبي / جنب بعض |
| t084 | عدلوا لي / يصير |
| t085 | ابي احجز / ومعنا رضيع |
| t086 | عندكم عروض / شهر 7 / ل 4 اشخاص |
| t088 | ابي سواق / حنا / شنط |
| t091 | كنسلوا / ما راح / فيه |
| t092 | احجزولي / تذكرتين |
| t093 | فيه / ولا لازم ترانزيت |
| t095 | ابي / بالليل |
| t096 | ولا يدخل بدونها / وكم مدة |

## Warning 2 — t003 and t004 have empty key_facts
The team-supplied source workbook notes explicitly state that t003 has no key fact and requires the booking reference; t004 has no key fact and the request itself is judged under meaning. Both have `missing: ["booking_reference"]`. Keep the intentional empty labels under this annotation scheme; the two human raters must check the full request, including question polarity, intent and constraints. Empty labels do not mean no meaning to preserve. For t003: departure terminal and how early to arrive. For t004: cancellation because of a circumstance, deduction and refund timing. Do not hallucinate booking references or operational answers. Review disposition: intentional annotation choice, retain warning transparently. If team elects to label intent-bearing spans as facts, use a new approved revision and re-run checks; do not silently change the current gold.

## Original 11 scrutiny cases — unresolved evidence dependency
The exact original list of 11 cases referred to in the team's handoff was not located in the accessible repository, original uploaded workbook (one review sheet), or available project records. Do not substitute 13 label differences, 15 workbook notes, or the 46/2 warnings for the original 11. The original list or its report is needed before these 11 can be independently closed.

## Separate finding: 13 changed label lists
The previous draft had 335 fact entries; the team-approved worksheet has 322. The following are **proposed additions or replacements for reviewer consideration only**, not approved edits and not the original 11. Exact reference spans improve coverage of actions, negation, exclusivity and source constraints. For t076, replace the positive-only label with the negated span, not both. For t008, t068, t081, t087 and t097 prefer the longer span in place of its corresponding shorter label; avoid redundant labels that double-weight one fact. Alternatives must be logically equivalent (not merely related). A string match remains insufficient to prove entailment.

| ID | Current labels (JSON) | Candidate reference spans (not applied) |
|---|---|---|
| t008 | ["أسبوع","H8W3KD","ظرف طارئ"] | تأجيل سفري أسبوعاً |
| t015 | ["K7M2QX","يومين"] | لم تصل حقيبتي؛ ألبس الملابس نفسها |
| t037 | ["K4T9WB","10 أيام","2350"] | ألغيت حجزي؛ لم يُرد إليّ شيء |
| t055 | ["التأشيرة لم تصدر \| لم تصدر التأشيرة","55273"] | لم أستطع السفر؛ استرداد المبلغ |
| t056 | ["booking@example.com","49026"] | بدلاً من الواتساب |
| t064 | ["المرشد","الغد"] | لا يتحدث العربية ولا الإنجليزية جيداً؛ نريد غيره |
| t068 | ["التذاكر الثلاث"] | استلمت التذاكر الثلاث؛ بريدي الإلكتروني |
| t076 | ["غرفة مفردة","المدينة","قريبة من المسجد النبوي \| بالقرب من المسجد النبوي","هادئة","طابق مرتفع \| دور عالٍ"] | ألّا تكون في طابق مرتفع |
| t080 | ["الأسبوع القادم"] | والدي متوعّك قليلاً |
| t081 | ["640","الحقيبة الإضافية"] | لم آخذ معي حقيبة |
| t083 | ["ساعة ونصفاً \| ساعة ونصف","180"] | لم يحضر السائق إلى المطار؛ أخذنا سيارة أجرة |
| t087 | ["تذكرة واحدة","M9D4XK"] | تذكرة واحدة فقط؛ الباقون فسيسافرون |
| t097 | ["412","مكيف","لا توجد غرف أخرى"] | مكيف الغرفة 412 معطل |

## Freeze disposition
Keep PR #3 open until the exact 11-case list is recovered or explicitly reconciled by the team. Obtain fresh sign-off for any changed content; regenerate workbook/CSV/JSONL/hash/manifest/tests together if a revised gold is accepted. Preserve V2.2, the current V3 approval evidence, and evaluator version. No V3 model run or human output adjudication is claimed.
