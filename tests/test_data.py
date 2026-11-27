"""Golden-test validation and training-data preparation."""
import csv
import json

import pytest

from src import data_prep
from src.common import read_jsonl, write_jsonl
from src.data_prep import (
    CorpusFormatError, GoldenIndex, clean_pairs, detect_columns, generate_synthetic, load_corpus_csv, load_team_jsonl,
    remove_golden_overlap,
)
from src.facts import compare_facts
from src.prompts import SYSTEM_PROMPT
from src.validate_golden import main as validate_main
from src.validate_golden import validate_rows


def row(i, source="ابغى موعد يوم 3/5", reference="أريد موعداً في يوم 3/5.", **kw):
    base = {"id": f"g{i:03d}", "source": source, "reference": reference, "written_by": "Sara", "checked_by": "Noura"}
    base.update(kw)
    return base


def golden(n=3):
    return [row(i, f"ابغى الطلب رقم {1000 + i} يوصل بسرعة", f"أريد أن يصل الطلب رقم {1000 + i} بسرعة.") for i in range(n)]


# ------------------------------- validation -------------------------------- #
def test_valid_rows_pass():
    errors, warnings, stats = validate_rows(golden(3), min_rows=3)
    assert errors == [] and stats == {"rows": 3, "rows_with_facts": 3, "share_with_facts": 1.0, "drafted_by": {"team": 3}}


def test_too_few_rows():
    errors, _, _ = validate_rows(golden(3), min_rows=100)
    assert any("at least 100" in e for e in errors)


def test_reference_must_keep_the_facts():
    errors, _, _ = validate_rows([row(1, reference="أريد موعداً في يوم 4/5.")], min_rows=1)
    assert any("does not keep the facts" in e and "3/5" in e for e in errors)


def test_duplicate_id_and_source():
    rows = [row(1), row(1, source="ابغى موعد ثاني"), row(2)]
    errors, _, _ = validate_rows(rows, min_rows=1)
    assert any("duplicate id" in e for e in errors) and any("same source text" in e for e in errors)


def test_missing_field():
    errors, _, _ = validate_rows([{"id": "x", "source": "نص"}], min_rows=1)
    assert any("reference" in e for e in errors)


@pytest.mark.parametrize("writer,checker", [
    ("NO_REVIEWER", "Noura"), ("Sara", ""), ("Sara", "sara"),
    # one person under two spellings, and cells that hold no name
    ("أحمد", "احمد"), ("أسامة", "أسامه"), ("Sara Ali", "Sara  Ali"), ("سارة", "ســارة"), ("سارة", "سارة\u200f"),
    ("سارة", "-"), ("سارة", "n/a"), ("سارة", "؟"), ("سارة", "لا يوجد"), ("سارة", ["منيرة"]),
    # a title does not make a second person, and a word that is not a name does not sign
    ("د. سارة", "سارة"), ("Dr. Sara Ali", "sara ali"), ("أ. أحمد", "م. احمد"), ("سارة", "yes"), ("سارة", "تم"), ("سارة", "لا أحد"),
])
def test_review_is_required(writer, checker):
    errors, _, _ = validate_rows([row(1, written_by=writer, checked_by=checker)], min_rows=1)
    assert errors
    assert validate_rows([row(1, written_by=writer, checked_by=checker)], min_rows=1, require_review=False)[0] == []


def test_ai_drafted_rows_need_a_reviewer_and_a_confirmer():
    base = {"id": "g1", "source": "ابغى موعد يوم 3/5", "reference": "أريد موعداً في يوم 3/5.", "drafted_by": "ai_assistant"}
    assert validate_rows([base], min_rows=1)[0]                                                    # nobody named
    assert validate_rows([{**base, "reviewed_by": "Sara"}], min_rows=1)[0]                              # no confirmer
    assert validate_rows([{**base, "reviewed_by": "Sara", "confirmed_by": "sara "}], min_rows=1)[0]     # the same person twice
    errors, _, stats = validate_rows([{**base, "reviewed_by": "Sara", "confirmed_by": "Noura"}], min_rows=1)
    assert errors == [] and stats["drafted_by"] == {"ai_assistant": 1}
    # a complete pair is accepted even if a field of the other pair was left in the row
    assert validate_rows([{**base, "written_by": "Sara", "reviewed_by": "Sara", "confirmed_by": "Noura"}], min_rows=1)[0] == []


def test_rows_without_a_listed_dialect_word_give_one_warning():
    rows = [row(i, f"طلبي رقم {i} ما وصل", f"طلبي رقم {i} لم يصل.") for i in range(1, 4)]
    errors, warnings, _ = validate_rows(rows, min_rows=1)
    assert errors == [] and len(warnings) == 1 and warnings[0].startswith("3 source(s)") and "g001, g002, g003" in warnings[0]


def test_non_object_rows_and_copied_dialect_references_are_errors():
    errors, _, _ = validate_rows([["x"], row(2, "ابغى موعد", "ابغى موعد")], min_rows=1)
    assert any("not a JSON object" in e for e in errors) and any("write the MSA version" in e for e in errors)


def test_must_keep_must_be_in_source_and_reference():
    errors, _, _ = validate_rows([row(1, must_keep=["فهد"])], min_rows=1)
    assert any("does not appear in the source" in e for e in errors)
    ok = row(2, "اللي كلمني فهد", "الذي حدثني فهد", must_keep=["فهد"])
    assert validate_rows([ok], min_rows=1)[0] == []
    lost = row(3, "اللي كلمني فهد", "الذي حدثني موظف", must_keep=["فهد"])
    assert any("name lost" in e for e in validate_rows([lost], min_rows=1)[0])


def test_warnings_for_dialect_in_reference_and_low_fact_share():
    rows = [row(1, "ابغى موعد", "ابغى موعداً"), row(2, "وش الاخبار", "ما الأخبار")]
    errors, warnings, _ = validate_rows(rows, min_rows=1)
    assert errors == []
    assert any("still contains dialect" in w for w in warnings) and any("only 0%" in w for w in warnings)


def test_shipped_template_validates_as_a_template(capsys, historical_snapshot):
    template = str(historical_snapshot / "data/golden_test_template.jsonl")
    assert validate_main([template, "--min-rows", "10", "--allow-unreviewed"]) == 0
    assert validate_main([template]) == 1  # 10 rows, reviewers NO_REVIEWER: not a real golden test
    assert "ERROR" in capsys.readouterr().out


# --------------------------------- loading --------------------------------- #
def write_csv(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)


def test_detect_columns():
    assert detect_columns(["id", "MSA", "Saudi", "Egyptian"]) == ("Saudi", "MSA")
    assert detect_columns(["الفصحى", "السعودية"]) == ("السعودية", "الفصحى")
    with pytest.raises(CorpusFormatError, match="Columns found"):
        detect_columns(["a", "b"])
    with pytest.raises(CorpusFormatError):
        detect_columns(["MSA", "Saudi_Najdi", "Saudi_Hijazi"])


def test_load_corpus_csv(tmp_path):
    path = tmp_path / "c.csv"
    write_csv(path, ["MSA", "Saudi", "Egyptian"], [["أريد غرفة", "ابغى غرفة", "عايز اوضة"]])
    assert load_corpus_csv(str(path)) == [{"dialect": "ابغى غرفة", "msa": "أريد غرفة", "source": "corpus", "label_stripped": False}]
    assert load_corpus_csv(str(path), dialect_col="Egyptian")[0]["dialect"] == "عايز اوضة"
    with pytest.raises(CorpusFormatError, match="not found"):
        load_corpus_csv(str(path), dialect_col="Nope", msa_col="MSA")


PUBLISHED_HEADER = ["Modern Standard Arabic", "Saudi Dialect", "Egyptian Dialect", "Iraqi Dialect", "Levantine Dialect", "Moroccan Dialect"]


def test_published_corpus_format(tmp_path):
    # The layout of the Zenodo file: six columns, a "- Saudi: " label in every dialect cell, stray double spaces.
    # The sentences here are written for the test; they are not rows of the corpus.
    path = tmp_path / "c.csv"
    write_csv(path, PUBLISHED_HEADER, [
        ["أريد  غرفة  هادئة.", "- Saudi: ابغى غرفة هادية.", "- Egyptian: عايز اوضة هادية.", "", "", ""],
        ["أين المحطة؟", "- saudi : وين المحطة؟", "", "", "", ""],
        ["السفر جميل.", "السفر جميل.", "", "", "", ""],
    ])
    assert detect_columns(PUBLISHED_HEADER) == ("Saudi Dialect", "Modern Standard Arabic")
    pairs = load_corpus_csv(str(path))
    assert [(p["dialect"], p["msa"], p["label_stripped"]) for p in pairs] == [
        ("ابغى غرفة هادية.", "أريد غرفة هادئة.", True), ("وين المحطة؟", "أين المحطة؟", True), ("السفر جميل.", "السفر جميل.", False)]
    kept, dropped = clean_pairs(pairs)
    assert len(kept) == 2 and dropped["identical_over_cap"] == 1   # the label does not count as a Latin word


def test_load_team_jsonl(tmp_path):
    path = tmp_path / "t.jsonl"
    write_jsonl(path, [{"dialect": " ابغى ", "msa": "أريد"}])
    assert load_team_jsonl([str(path)]) == [{"dialect": "ابغى", "msa": "أريد", "source": "team"}]
    write_jsonl(path, [{"dialect": "ابغى"}])
    with pytest.raises(ValueError):
        load_team_jsonl([str(path)])


# -------------------------------- synthetic -------------------------------- #
def test_synthetic_is_reproducible_and_keeps_facts():
    a, b = generate_synthetic(150, seed=7), generate_synthetic(150, seed=7)
    assert a == b and a != generate_synthetic(150, seed=8)
    assert all(compare_facts(p["dialect"], p["msa"]).ok for p in a)
    assert all(p["source"] == "synthetic" for p in a)


def test_synthetic_covers_the_fact_formats():
    import re
    pairs = generate_synthetic(1500, seed=13)
    text = "\n".join(p["dialect"] for p in pairs)
    for pattern in (r"[٠-٩]", r"\d,\d{3}", r"\d\.\d", r"\d%", r"\d{4}-\d\d-\d\d", r"@example\.", r"[A-Z]{2,3}-?\d{4,6}", r"\d{1,2}:\d\d"):
        assert re.search(pattern, text), pattern
    # Counted nouns are plural in the templates, which is right only for 3 to 10.
    assert all(3 <= int(n) <= 10 for n in re.findall(r"(\d+) (?:ايام|ساعات|شهور|اصناف)", text))
    assert len({p["dialect"] for p in pairs}) > 1000


def test_synthetic_pairs_read_as_sound_arabic():
    import re
    ascii_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫٪", "0123456789,.%")
    pairs = generate_synthetic(6000, seed=13)
    msa = "\n".join(p["msa"] for p in pairs).translate(ascii_digits)
    dialect = "\n".join(p["dialect"] for p in pairs).translate(ascii_digits)

    def riyal(amount):
        if "." in amount:
            return "ريال"
        last_two = int(amount.replace(",", "")) % 100
        return "ريالات" if 3 <= last_two <= 10 else "ريالاً" if 11 <= last_two <= 99 else "ريال"

    counted = re.findall(r"([\d,]+(?:\.\d+)?) (ريالات|ريالاً|ريال)", msa)
    assert len(counted) > 500 and {noun for _, noun in counted} == {"ريالاً", "ريال"}   # no amount in the list ends in 3 to 10
    assert all(noun == riyal(amount) for amount, noun in counted)
    assert data_prep._riyal("7") == "ريالات" and data_prep._riyal("710") == "ريالات" and data_prep._riyal("710.75") == "ريال"
    # Two amounts set against each other are different amounts ("2500" and "2,500" are one amount).
    both = re.findall(r"السعر في العرض ([\d,.]+) وفي الفاتورة ([\d,.]+)،", dialect)
    assert len(both) > 50 and all(float(a.replace(",", "")) < float(b.replace(",", "")) for a, b in both)
    # A time window reads in order on a 12-hour dial: the second time is one to four hours after the first ("11:10", then "1:40").
    windows = re.findall(r"قالوا بين (\d+):\d+ و (\d+):\d+", dialect)
    assert len(windows) > 50 and all(1 <= (int(h2) - int(h1)) % 12 <= 4 for h1, h2 in windows)
    assert {(int(h1), int(h2)) for h1, h2 in windows} & {(11, 1), (12, 2), (10, 12)}   # windows across noon occur and are in order
    # The name templates are written in the masculine, so only men's names fill them.
    assert not re.search("ريما|غادة|لجين|دانة|شهد|وعد الجهني|جود الشمري", dialect)
    # A payment goes through a way to pay, not through a government service.
    assert not re.search(r"دفعت [\d,.]+ ريال من (?:Absher|Tawakkalna|Nafath|Qiwa)", dialect)
    # The year-first date is kept for messages that are already formal; nobody types it in a chat.
    iso = [p for p in pairs if re.search(r"\d{4}-\d{2}-\d{2}", p["dialect"].translate(ascii_digits))]
    assert iso and all(p["dialect"] == p["msa"] for p in iso)
    # Arabic-Indic digits come with the Arabic thousands separator and percent sign, on both sides alike.
    arabic = [p for p in pairs if re.search("[٠-٩]", p["dialect"])]
    assert arabic and not any(re.search(r"[٠-٩][,%]|[,%][٠-٩]", p["dialect"] + p["msa"]) for p in arabic)
    # A package costs thousands, and the dearer price is the one the customer complains about.
    packages = re.findall(r"الباقة حقت \S+ بـ ([\d,]+) ريال وانا شفتها في موقعكم بـ ([\d,]+)", dialect)
    assert len(packages) > 50 and all(2000 < int(low.replace(",", "")) < int(high.replace(",", "")) for high, low in packages)


def test_prepare_refuses_negative_limits(tmp_path):
    gpath = tmp_path / "golden.jsonl"
    write_jsonl(gpath, golden(3))
    for bad in ({"corpus_limit": -30, "synthetic_n": 50}, {"synthetic_n": -1}):
        with pytest.raises(SystemExit, match="cannot be negative"):
            data_prep.prepare(args_for(tmp_path, gpath, **bad))


# --------------------------------- cleaning -------------------------------- #
def test_clean_pairs_reasons():
    pairs = [
        {"dialect": "ابغى موعد يوم 3/5", "msa": "أريد موعداً يوم 3/5", "source": "x"},
        {"dialect": "ابغى موعد يوم 3/5", "msa": "أريد موعداً يوم 3/5", "source": "x"},      # duplicate
        {"dialect": "ابغى موعد يوم 4/5", "msa": "أريد موعداً يوم 9/5", "source": "x"},      # fact mismatch
        {"dialect": "", "msa": "أريد", "source": "x"},                                       # empty
        {"dialect": "قصير", "msa": "قصير", "source": "x"},                                   # too short
        {"dialect": "نأمل تحديث البيانات", "msa": "نأمل تحديث البيانات", "source": "x"},     # identical, over cap
    ]
    kept, dropped = clean_pairs(pairs)
    assert [p["dialect"] for p in kept] == ["ابغى موعد يوم 3/5"]
    assert dict(dropped) == {"duplicate": 1, "fact_mismatch": 1, "empty": 1, "length": 1, "identical_over_cap": 1}


def test_identical_pairs_are_capped_not_removed():
    pairs = [{"dialect": f"ابغى الطلب رقم {i}", "msa": f"أريد الطلب رقم {i}", "source": "x"} for i in range(95)]
    pairs += [{"dialect": f"نأمل تحديث الطلب {i}", "msa": f"نأمل تحديث الطلب {i}", "source": "x"} for i in range(50)]
    kept, dropped = clean_pairs(pairs, max_identical_frac=0.05)
    assert len(kept) == 100 and dropped["identical_over_cap"] == 45


# ----------------------------- golden separation --------------------------- #
G = [{"id": "g1", "source": "ابغى اغير موعدي من يوم 12/4 لين يوم 19/4 الساعة 10:30",
      "reference": "أريد تغيير موعدي من يوم 12/4 إلى يوم 19/4 الساعة 10:30."}]


@pytest.mark.parametrize("text,kind", [
    ("ابغى اغير موعدي من يوم 12/4 لين يوم 19/4 الساعة 10:30", "exact"),
    ("أبغى أغيّر موعدي من يوم ١٢/٤ لين يوم ١٩/٤ الساعة ١٠:٣٠!", "exact"),
    ("السلام عليكم ابغى اغير موعدي من يوم 12/4 لين يوم 19/4 الساعة 10:30 وشكرا", "contained"),
    ("ابغى اغير موعدي من يوم 12/4 لين يوم 19/4 الساعة 11:30", "near_duplicate"),
    ("أريد تغيير موعدي من يوم 12/4 إلى يوم 19/4 الساعة 10:30.", "exact"),
])
def test_golden_index_catches(text, kind):
    assert GoldenIndex(G).match(text)["kind"] == kind


def test_golden_index_lets_unrelated_text_pass():
    assert GoldenIndex(G).match("وين اقدر استلم الشحنة رقم 5521 في جدة؟") is None


def test_pair_removed_when_either_side_collides():
    pairs = [
        {"dialect": "شي ثاني تماما عن الفاتورة", "msa": G[0]["reference"], "source": "x"},
        {"dialect": G[0]["source"], "msa": "صياغة اخرى مختلفة", "source": "x"},
        {"dialect": "وين المكتب الرئيسي؟", "msa": "أين المكتب الرئيسي؟", "source": "x"},
    ]
    kept, removed = remove_golden_overlap(pairs, GoldenIndex(G))
    assert len(kept) == 1 and len(removed) == 2 and removed[0]["golden"] == "g1:reference"


# --------------------------------- end to end ------------------------------ #
def args_for(tmp_path, golden_path, **kw):
    ns = data_prep.build_parser().parse_args(["--golden", str(golden_path), "--out", str(tmp_path / "out"), "--min-golden-rows", "3"])
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_prepare_end_to_end(tmp_path):
    gpath = tmp_path / "golden.jsonl"
    gold = golden(3)
    write_jsonl(gpath, gold)
    cpath = tmp_path / "corpus.csv"
    rows = [[f"أريد حجز غرفة رقم {i} في الفندق", f"ابغى احجز غرفة رقم {i} في الفندق"] for i in range(40)]
    rows.append([gold[0]["reference"], gold[0]["source"]])  # a golden pair hidden in the corpus
    write_csv(cpath, ["MSA", "Saudi"], rows)
    report = data_prep.prepare(args_for(tmp_path, gpath, corpus_csv=str(cpath), synthetic_n=60))

    assert report["removed_for_golden_overlap"] == 1 and report["overlap_remaining_after_filter"] == 0
    assert report["loaded"] == {"corpus_rows_in_file": 41, "corpus": 41, "synthetic": 60}
    assert len(report["closest_kept_pairs"]) == 5 and all(c["shared_content"] < 0.6 for c in report["closest_kept_pairs"])
    assert report["train_sha256"] and report["corpus_file_sha256"] and report["removed_for_shared_fact"] == 0
    train, val = read_jsonl(tmp_path / "out" / "train.jsonl"), read_jsonl(tmp_path / "out" / "val.jsonl")
    assert len(train) == report["train"] and len(val) == report["val"] and len(val) >= 1
    assert train[0]["messages"][0]["content"] == SYSTEM_PROMPT and train[0]["meta"]["source"] in ("corpus", "synthetic")
    texts = {m["content"] for r in train + val for m in r["messages"][1:]}
    assert gold[0]["source"] not in texts and gold[0]["reference"] not in texts
    saved = json.loads((tmp_path / "out" / "prep_report.json").read_text(encoding="utf-8"))
    assert saved["golden_sha256"] == report["golden_sha256"] and saved["pairs_with_facts"] > 0


def test_corpus_limit_counts_cleaned_pairs(tmp_path):
    gpath = tmp_path / "golden.jsonl"
    write_jsonl(gpath, golden(3))
    cpath = tmp_path / "corpus.csv"
    rows = [[f"أريد حجز الغرفة {i} في الفندق", f"- Saudi: ابغى احجز الغرفة {i} في الفندق"] for i in range(30)] * 2   # every row twice
    write_csv(cpath, ["Modern Standard Arabic", "Saudi Dialect"], rows)
    report = data_prep.prepare(args_for(tmp_path, gpath, corpus_csv=str(cpath), corpus_limit=20))
    assert report["loaded"] == {"corpus_rows_in_file": 60, "corpus": 20} and report["corpus_labels_stripped"] == 60
    assert report["dropped_from_corpus"] == {"duplicate": 30} and report["train"] + report["val"] == 20


def test_pairs_sharing_a_distinctive_fact_with_the_golden_test_are_removed(tmp_path):
    from src.data_prep import distinctive_facts, remove_shared_facts
    gold = [{"id": "g1", "source": "ارسلوها على help@example.org ورقم الطلب TRK90417 والمبلغ 250", "reference": "x"}]
    assert distinctive_facts(gold[0]["source"]) == {("email", "help@example.org"), ("code", "TRK90417"), ("number", "90417")}
    pairs = [{"dialect": "ارسلوا العقد على help@example.org", "msa": "", "source": "s"},
             {"dialect": "الرقم TRK90417 ما يشتغل", "msa": "", "source": "s"},
             {"dialect": "دفعت 250 ريال من Mada", "msa": "", "source": "s"},          # a short number and a plain word are not distinctive
             {"dialect": "الطلب 5083317 متأخر", "msa": "", "source": "s"}]
    kept, removed = remove_shared_facts(pairs, gold)
    assert [p["dialect"] for p in kept] == ["دفعت 250 ريال من Mada", "الطلب 5083317 متأخر"] and len(removed) == 2


def test_a_golden_fact_in_another_dress_is_still_found():
    from src.data_prep import remove_shared_facts
    gold = [{"id": "g1", "source": "الرابط www.example.com/track والطلب J-20481 ورقمي 0551234567", "reference": "المرجع TRK90417 والكوبون SAVE20"}]
    same_fact = ["افتح https://www.example.com/track", "الطلب J 20481 تأخر", "الطلب j20481 تأخر", "اتصلوا على +966551234567",
                 "اتصلوا على 055 123 4567", "الرمز trk90417 ما يشتغل", "جربت الكوبون SAVE 20", "الكوبون save-20 منتهي"]
    other = ["افتح www.example.com/help", "الطلب J-20482 تأخر", "اتصلوا على 0551234568", "الموعد 2026-11-30 الساعة 10",
             "المبلغ 12,000 والباقي 250", "من 9:00 الى 11:30 يوم 20/12", "الكوبون SAVE 30"]
    kept, removed = remove_shared_facts([{"dialect": text, "msa": "", "source": "s"} for text in same_fact + other], gold)
    assert [p["dialect"] for p in kept] == other and len(removed) == len(same_fact)
    # the MSA side of a pair is read as well
    assert remove_shared_facts([{"dialect": "وين الطلب؟", "msa": "أين الطلب J-20481؟", "source": "s"}], gold)[0] == []


def test_prepare_is_reproducible(tmp_path):
    gpath = tmp_path / "golden.jsonl"
    write_jsonl(gpath, golden(3))
    data_prep.prepare(args_for(tmp_path, gpath, synthetic_n=80, out=str(tmp_path / "a")))
    data_prep.prepare(args_for(tmp_path, gpath, synthetic_n=80, out=str(tmp_path / "b")))
    assert (tmp_path / "a" / "train.jsonl").read_text(encoding="utf-8") == (tmp_path / "b" / "train.jsonl").read_text(encoding="utf-8")


def test_prepare_refuses_an_invalid_golden_test(tmp_path):
    gpath = tmp_path / "golden.jsonl"
    write_jsonl(gpath, [row(1, written_by="NO_REVIEWER")] * 1)
    with pytest.raises(SystemExit, match="does not validate"):
        data_prep.prepare(args_for(tmp_path, gpath, synthetic_n=10))


def test_prepare_needs_a_source(tmp_path):
    gpath = tmp_path / "golden.jsonl"
    write_jsonl(gpath, golden(3))
    with pytest.raises(SystemExit, match="no training source"):
        data_prep.prepare(args_for(tmp_path, gpath))


def test_few_shot_example_in_golden_is_refused(tmp_path):
    from src.prompts import FEW_SHOT_EXAMPLES
    gpath = tmp_path / "golden.jsonl"
    src, ref = FEW_SHOT_EXAMPLES[0]
    write_jsonl(gpath, golden(3) + [row(9, src, ref)])
    with pytest.raises(SystemExit, match="few-shot example"):
        data_prep.prepare(args_for(tmp_path, gpath, synthetic_n=10))


def test_cli_reports_bad_csv(tmp_path, capsys):
    gpath = tmp_path / "golden.jsonl"
    write_jsonl(gpath, golden(3))
    cpath = tmp_path / "c.csv"
    write_csv(cpath, ["a", "b"], [["x", "y"]])
    code = data_prep.main(["--golden", str(gpath), "--min-golden-rows", "3", "--corpus-csv", str(cpath), "--out", str(tmp_path / "o")])
    assert code == 1 and "Columns found" in capsys.readouterr().out


# ------------------------- key-fact and missing labels ---------------------- #
def labelled(i, **kw):
    base = row(i, "ابغى احجز تذكرتين لجدة يوم الخميس", "أريد حجز تذكرتين إلى جدة يوم الخميس.", key_facts=["تذكرتين", "جدة", "الخميس"], missing=[])
    base.update(kw)
    return base


def test_labelled_rows_pass_and_are_counted():
    rows = [labelled(1), labelled(2, source="ابغى احجز 3 تذاكر", reference="أريد حجز 3 تذاكر.", key_facts=["3 تذاكر"], missing=["date", "destination"])]
    errors, warnings, stats = validate_rows(rows, min_rows=2)
    assert errors == [] and warnings == [] and stats["key_facts"] == 4 and stats["rows_missing_a_detail"] == 1


def test_key_fact_must_be_worded_as_in_the_reference():
    errors, _, _ = validate_rows([labelled(1, key_facts=["تذكرتين", "الجمعة"])], min_rows=1)
    assert any("key fact 'الجمعة' is not found in the reference" in e for e in errors)
    errors, _, _ = validate_rows([labelled(1, key_facts=["تذكرتان | تذكرتين", "جدة", "الخميس"])], min_rows=1)
    assert errors == []                                          # either wording of an alternative may be the one in the reference


@pytest.mark.parametrize("bad", [{"missing": ["recipient"]}, {"missing": ["date", "date"]}, {"missing": "date"}, {"key_facts": "جدة"}, {"key_facts": ["جدة", ""]}])
def test_label_fields_are_checked(bad):
    errors, _, _ = validate_rows([labelled(1, **bad)], min_rows=1)
    assert any("missing must be a list" in e or "key_facts must be a list" in e for e in errors)


def test_a_file_is_labelled_on_every_row_or_on_none():
    errors, _, _ = validate_rows([labelled(1), row(2, "ابغى موعد يوم 4/5", "أريد موعداً في يوم 4/5.")], min_rows=2)
    assert any("carry no key_facts and missing labels although other rows do: g002" in e for e in errors)
    errors, _, stats = validate_rows(golden(3), min_rows=3)
    assert errors == [] and "key_facts" not in stats             # a file without labels is validated as before


def test_unlabelled_facts_and_empty_labels_are_pointed_out():
    rows = [labelled(1, key_facts=["تذكرتين"]),
            labelled(2, source="ابغى احجز 3 تذاكر لدبي بكره", reference="أريد حجز 3 تذاكر إلى دبي غداً.", key_facts=[])]
    errors, warnings, _ = validate_rows(rows, min_rows=2)
    assert errors == []
    assert any("1 row(s) have no key fact labelled" in w and "g002" in w for w in warnings)
    assert any("2 row(s) have a number, date, code, day, place or listed name in the reference that is not in key_facts" in w for w in warnings)
