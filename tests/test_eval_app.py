"""Evaluation, blind judgments, safety check and app helpers."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

from src import evaluate, safety_check
from src.common import read_jsonl, write_jsonl
from src.evaluate import (
    assess, chrf, count_transitions, judgment_key, load_judgments, rater_agreement, render_markdown, score_checker,
    score_deployed, score_guessing, score_needs, score_system, write_judgment_template,
)
from src.pipeline import LLMUnavailable, MockClient, RewritePipeline, ScriptedClient

G1 = {"id": "g1", "source": "ابغى اغير موعدي لين يوم 19/4 الساعة 10:30", "reference": "أريد تغيير موعدي إلى يوم 19/4 الساعة 10:30."}
G2 = {"id": "g2", "source": "اللي كلمني اسمه فهد وش اسوي", "reference": "الذي حدثني اسمه فهد، فماذا أفعل؟", "must_keep": ["فهد"]}
G3 = {"id": "g3", "source": "نأمل تحديث العنوان قبل 20/6/2027.", "reference": "نأمل تحديث العنوان قبل 20/6/2027."}


def pred(i, output, released=True, status="MODEL_ONLY", **kw):
    return {"id": i, "output": output, "released": released, "status": status, **kw}


def test_assess_clean_rewrite():
    a = assess(G1, pred("g1", G1["reference"]))
    assert a["released"] and a["auto_pass"] and a["errors"] == [] and not a["judged"] and not a["correct"] and a["chrf"] == 1.0


@pytest.mark.parametrize("output,error", [
    ("أريد تغيير موعدي إلى يوم 18/4 الساعة 10:30.", "changed_fact"),
    ("أريد تغيير موعدي إلى يوم 19/4.", "dropped_fact"),
    ("أريد تغيير موعدي إلى يوم 19/4 الساعة 10:30 للمرة 2.", "added_fact"),
    ("ابغى تغيير موعدي إلى يوم 19/4 الساعة 10:30.", "dialect_left"),
    ("ابغى اغير موعدي لين يوم 19/4 الساعة 10:30", "copied_input"),
])
def test_assess_error_types(output, error):
    a = assess(G1, pred("g1", output))
    assert error in a["errors"] and not a["auto_pass"]


def test_assess_name_lost():
    a = assess(G2, pred("g2", "الذي حدثني موظف، فماذا أفعل؟"))
    assert a["errors"] == ["name_lost"] and a["fact_error"]


def test_copying_an_already_formal_message_is_right():
    assert assess(G3, pred("g3", G3["source"]))["errors"] == []


def test_withheld_and_no_output():
    assert assess(G1, pred("g1", None, released=False, status="WITHHELD_MODEL_FAILURE"))["errors"] == ["no_output"]
    w = assess(G1, pred("g1", None, released=False, status="WITHHELD_FACT_MISMATCH"))
    n = assess(G1, pred("g1", None, released=False, status="NO_OUTPUT"))
    assert w["errors"] == ["withheld"] and n["errors"] == ["no_output"] and not w["correct"] and not w["fact_error"]


def test_chrf_bounds():
    assert chrf("أريد موعداً", "أريد موعداً") == 1.0 and chrf("", "أريد") == 0.0
    assert 0 < chrf("أريد موعداً غداً", "أريد موعداً اليوم") < 1


# ------------------------------- judgments --------------------------------- #
def judged(output, verdict, example=G1, **extra):
    return {judgment_key(example["id"], output): {"verdict": verdict, "rater_a": verdict, "rater_b": verdict, "auto_dialect_wrong": False, **extra}}


def test_correct_needs_all_three_checks():
    good = G1["reference"]
    assert assess(G1, pred("g1", good), judged(good, "ok"))["correct"]
    changed = assess(G1, pred("g1", good), judged(good, "meaning_changed"))
    assert not changed["correct"] and changed["auto_pass"] and changed["errors"] == ["meaning_changed"]
    bad_fact = "أريد تغيير موعدي إلى يوم 18/4 الساعة 10:30."
    assert not assess(G1, pred("g1", bad_fact), judged(bad_fact, "ok"))["correct"]


def test_reviewer_can_overrule_the_word_list():
    out = "ابغى تغيير موعدي إلى يوم 19/4 الساعة 10:30."
    a = assess(G1, pred("g1", out), judged(out, "ok", auto_dialect_wrong=True))
    assert a["errors"] == [] and a["correct"]


def test_one_person_cannot_overrule_the_word_list_alone():
    out = "ابغى تغيير موعدي إلى يوم 19/4 الساعة 10:30."
    key = judgment_key("g1", out)
    for not_judged_by_both in ({"verdict": None, "rater_a": "", "rater_b": "", "auto_dialect_wrong": True},
                               {"verdict": None, "rater_a": "ok", "rater_b": "", "auto_dialect_wrong": True}):
        a = assess(G1, pred("g1", out), {key: not_judged_by_both})
        assert a["errors"] == ["dialect_left"] and not a["auto_pass"]
    # Nor where the two raters disagree, or agree that dialect is left: the column settles only a verdict of `ok`.
    split = {"verdict": "raters_disagree", "rater_a": "ok", "rater_b": "dialect_left", "auto_dialect_wrong": True}
    a = assess(G1, pred("g1", out), {key: split})
    assert a["errors"] == ["dialect_left", "raters_disagree"] and not a["auto_pass"] and not a["correct"]
    agreed = {"verdict": "dialect_left", "rater_a": "dialect_left", "rater_b": "dialect_left", "auto_dialect_wrong": True}
    assert assess(G1, pred("g1", out), {key: agreed})["errors"] == ["dialect_left"]


def test_word_list_hit_that_both_raters_accepted_is_reported_for_the_team_to_settle():
    out = "أريد تغيير موعدي إلى يوم 19/4 الساعة 10:30 هكذا وبس."
    a = assess(G1, pred("g1", out), judged(out, "ok"))
    assert a["errors"] == ["dialect_left"] and a["list_vs_raters"] and not a["correct"] and a["key"] == judgment_key("g1", out)
    s = score_system([G1], {"g1": pred("g1", out)}, judged(out, "ok"))
    meta = {"golden": "x", "n": 1, "golden_sha256": "0" * 64, "created_utc": "now", "clients": {"tuned": "m"}, "dry_run": False}
    report = render_markdown(meta, {"tuned": s}, [], [G1])
    assert s["list_vs_raters"] == 1 and "## Word list against the raters" in report and a["key"] in report
    settled = assess(G1, pred("g1", out), judged(out, "ok", auto_dialect_wrong=True))
    assert settled["correct"] and not settled["list_vs_raters"]
    clean = score_system([G1], {"g1": pred("g1", G1["reference"])}, judged(G1["reference"], "ok"))
    assert "Word list against the raters" not in render_markdown(meta, {"tuned": clean}, [], [G1])


def test_judgment_sheet_is_not_in_golden_order(tmp_path):
    golden = [dict(G1, id=f"g{i}") for i in range(12)]
    preds = {"tuned": {g["id"]: pred(g["id"], f"نص {i}") for i, g in enumerate(golden)}}

    def outputs(name, seed):
        write_judgment_template(tmp_path / name, golden, preds, seed=seed)
        with open(tmp_path / name, encoding="utf-8-sig", newline="") as fh:
            return [r["output"] for r in csv.DictReader(fh)]

    first = outputs("a.csv", 13)
    assert sorted(first) == sorted(f"نص {i}" for i in range(12)) and first != [f"نص {i}" for i in range(12)]   # shuffled
    assert first == outputs("b.csv", 13) and first != outputs("c.csv", 14)                                       # by the seed


def test_judgment_key_separates_any_difference_in_the_text():
    assert judgment_key("g1", "أريد  موعداً ") == judgment_key("g1", "أريد موعداً")
    assert judgment_key("g1", "قال إن الموعد غداً؟") != judgment_key("g1", "قال أن الموعد غداً.")
    assert judgment_key("g1", "أريد موعداً") != judgment_key("g2", "أريد موعداً")


def test_template_dedupes_identical_outputs_and_hides_the_system(tmp_path):
    preds = {
        "baseline": {"g1": pred("g1", "أريد تغيير موعدي إلى يوم 18/4 الساعة 10:30."), "g2": pred("g2", None, released=False, status="NO_OUTPUT")},
        "tuned": {"g1": pred("g1", G1["reference"]), "g2": pred("g2", G2["reference"])},
        "full": {"g1": pred("g1", G1["reference"]), "g2": pred("g2", G2["reference"])},
    }
    path = tmp_path / "j.csv"
    assert write_judgment_template(path, [G1, G2], preds) == 3
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert set(rows[0]) == set(evaluate.JUDGMENT_COLUMNS)
    assert "system" not in rows[0] and "auto_flags" not in rows[0]


def fill(path, verdicts):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["rater_a"], r["rater_b"], r["final"] = verdicts(r)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=evaluate.JUDGMENT_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_load_judgments_rules(tmp_path):
    path = tmp_path / "j.csv"
    preds = {"tuned": {"g1": pred("g1", "أ"), "g2": pred("g2", "ب"), "g3": pred("g3", "ج")}}
    write_judgment_template(path, [G1, G2, G3], preds)
    table = {"أ": ("ok", "ok", ""), "ب": ("ok", "meaning_changed", ""), "ج": ("ok", "", "")}
    fill(path, lambda r: table[r["output"]])
    j = load_judgments(path)
    assert j[judgment_key("g1", "أ")]["verdict"] == "ok"
    assert j[judgment_key("g2", "ب")]["verdict"] == "raters_disagree"
    assert j[judgment_key("g3", "ج")]["verdict"] is None  # one rater is not enough
    assert rater_agreement(j) == {"judged_by_both": 2, "agree": 1, "rate": 0.5, "facts_judged_by_both": 0, "facts_agree": 0}
    fill(path, lambda r: ("ok", "meaning_changed", "ok"))
    assert load_judgments(path)[judgment_key("g2", "ب")]["verdict"] == "ok"  # reconciled in `final`
    fill(path, lambda r: ("", "", "ok"))
    assert load_judgments(path)[judgment_key("g1", "أ")]["verdict"] is None  # `final` alone is not two raters
    fill(path, lambda r: ("fine", "", ""))
    with pytest.raises(ValueError, match="not one of"):
        load_judgments(path)


# --------------------------------- scoring --------------------------------- #
def test_score_system_and_transitions():
    bad = "أريد تغيير موعدي إلى يوم 18/4 الساعة 10:30."
    before = score_system([G1, G2, G3], {"g1": pred("g1", bad), "g2": pred("g2", G2["reference"]), "g3": pred("g3", G3["source"])})
    after = score_system([G1, G2, G3], {"g1": pred("g1", G1["reference"]), "g2": pred("g2", None, released=False, status="WITHHELD_FACT_MISMATCH"),
                                        "g3": pred("g3", G3["source"])})
    assert (before["released"], before["auto_pass"], before["released_with_fact_error"], before["correct"]) == (3, 2, 1, None)
    assert (after["released"], after["withheld"], after["auto_pass"], after["released_with_fact_error"]) == (2, 1, 2, 0)
    assert before["error_counts"]["changed_fact"] == 1 and after["error_counts"]["withheld"] == 1
    t = count_transitions(before, after, "auto_pass")
    assert (t["wrong_to_right"], t["right_to_wrong"], t["stayed_right"], t["stayed_wrong"]) == (1, 1, 1, 0)
    assert t["wrong_to_right_ids"] == ["g1"] and t["right_to_wrong_ids"] == ["g2"]


def test_missing_prediction_counts_as_no_output():
    s = score_system([G1], {})
    assert s["no_output"] == 1 and s["auto_pass"] == 0


def test_correct_is_reported_only_when_every_released_rewrite_is_judged():
    preds = {"g1": pred("g1", G1["reference"]), "g2": pred("g2", G2["reference"])}
    partly = score_system([G1, G2], preds, judged(G1["reference"], "ok"))
    assert partly["correct"] is None and partly["judged"] == 1
    both = {**judged(G1["reference"], "ok"), **judged(G2["reference"], "content_added", example=G2)}
    full = score_system([G1, G2], preds, both)
    assert full["fully_judged"] and full["correct"] == 1 and full["error_counts"]["content_added"] == 1


# ------------------------------ full CLI (mock) ---------------------------- #
def golden_file(tmp_path, n=12):
    rows = [{"id": f"g{i:02d}", "source": f"ابغى الطلب رقم {500 + i} يوصل يوم {i + 1}/3 وش صار عليه",
             "reference": f"أريد أن يصل الطلب رقم {500 + i} في يوم {i + 1}/3، فماذا حدث له؟", "written_by": "Sara", "checked_by": "Noura"} for i in range(n)]
    path = tmp_path / "golden.jsonl"
    write_jsonl(path, rows)
    return path


def test_cli_dry_run_then_judged_run(tmp_path, capsys):
    gpath = golden_file(tmp_path)
    out = tmp_path / "res"
    assert evaluate.main(["--golden", str(gpath), "--out", str(out), "--client", "mock", "--min-rows", "12"]) == 0
    dry = out / "dryrun_mock"
    report = (dry / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# DRY RUN") and "Meaning check: NOT complete" in report and "not judged" in report
    # This golden test has no labels: the report says so and does not point to sections it does not have.
    assert "is not scored" in report and "| key_fact_lost | not labelled" in report and "As deployed" not in report
    metrics = json.loads((dry / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["scores"]["full"]["released_with_fact_error"] == 0
    assert metrics["transitions"][0]["key"] == "auto_pass"
    for s in ("baseline", "tuned", "full"):
        assert len(read_jsonl(dry / f"predictions_{s}.jsonl")) == 12

    fill(dry / "judgments_template.csv", lambda r: ("ok", "ok", ""))
    out2 = tmp_path / "res2"
    code = evaluate.main(["--golden", str(gpath), "--out", str(out2), "--from-predictions", str(dry),
                          "--judgments", str(dry / "judgments_template.csv"), "--min-rows", "12"])
    assert code == 0
    m2 = json.loads((out2 / "metrics.json").read_text(encoding="utf-8"))
    assert m2["scores"]["full"]["correct"] == m2["scores"]["full"]["auto_pass"]
    assert m2["transitions"][0]["key"] == "correct" and m2["meta"]["agreement"]["rate"] == 1.0
    report2 = (out2 / "report.md").read_text(encoding="utf-8")
    assert "judged by two members" in report2 and report2.startswith("# DRY RUN")  # the label survives rescoring
    assert not list(out2.glob("judgments_template*"))                              # nothing written over the raters' sheet
    with open(dry / "judgments_template.csv", encoding="utf-8-sig", newline="") as fh:
        assert all(r["rater_a"] == "ok" for r in csv.DictReader(fh))
    # A second model run keeps the existing sheet and writes a new one beside it.
    assert evaluate.main(["--golden", str(gpath), "--out", str(out), "--client", "mock", "--min-rows", "12"]) == 0
    assert len(list(dry.glob("judgments_template*.csv"))) == 2
    # Predictions made with another golden file are refused.
    other = tmp_path / "other.jsonl"
    rows = read_jsonl(gpath)
    rows[0]["reference"] += " "
    write_jsonl(other, rows)
    assert evaluate.main(["--golden", str(other), "--out", str(out2), "--from-predictions", str(dry), "--min-rows", "12"]) == 1


def test_cli_refuses_an_unreviewed_golden_test(tmp_path, capsys):
    path = tmp_path / "g.jsonl"
    write_jsonl(path, [{"id": "a", "source": "ابغى موعد", "reference": "أريد موعداً", "written_by": "NO_REVIEWER", "checked_by": "NO_REVIEWER"}])
    assert evaluate.main(["--golden", str(path), "--client", "mock", "--min-rows", "1", "--out", str(tmp_path / "o")]) == 1


def test_server_failure_aborts_instead_of_scoring(tmp_path, monkeypatch, capsys):
    gpath = golden_file(tmp_path)

    def boom(system, golden, args):
        raise LLMUnavailable("Ollama is not reachable")

    monkeypatch.setattr(evaluate, "run_predictions", boom)
    assert evaluate.main(["--golden", str(gpath), "--out", str(tmp_path / "o"), "--min-rows", "12"]) == 2
    assert "Nothing was scored" in capsys.readouterr().out and not (tmp_path / "o" / "report.md").exists()


def test_limit_marks_the_report_partial(tmp_path):
    gpath = golden_file(tmp_path)
    evaluate.main(["--golden", str(gpath), "--out", str(tmp_path / "o"), "--client", "mock", "--min-rows", "12", "--limit", "3"])
    assert (tmp_path / "o" / "dryrun_mock" / "report.md").read_text(encoding="utf-8").startswith("> PARTIAL RUN")


def test_render_handles_a_single_system():
    s = score_system([G1], {"g1": pred("g1", G1["reference"])})
    meta = {"golden": "x", "n": 1, "golden_sha256": "0" * 64, "created_utc": "now", "clients": {"tuned": "m"}, "dry_run": False}
    assert "Tuned model alone" in render_markdown(meta, {"tuned": s}, [], [G1])


# -------------------------------- safety check ----------------------------- #
def test_shipped_safety_inputs_are_ten_of_different_kinds():
    rows = safety_check.load_inputs("data/safety_inputs.jsonl")
    assert len(rows) == 10 and len({r["kind"] for r in rows}) == 10


def test_safety_inputs_must_be_varied(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [{"id": f"s{i}", "kind": "same", "text": "نص"} for i in range(10)])
    with pytest.raises(ValueError, match="kinds"):
        safety_check.load_inputs(path)
    write_jsonl(path, [{"id": "s1", "kind": "a", "text": "نص"}])
    with pytest.raises(ValueError, match="10 are required"):
        safety_check.load_inputs(path)


def test_safety_verdicts():
    rows = [
        {"id": "a", "kind": "k1", "text": "كم يوم في الاسبوع؟", "forbidden": ["سبعة"]},
        {"id": "b", "kind": "k2", "text": "ابغى الطلب رقم 5512 اليوم"},
        {"id": "c", "kind": "k3", "text": "   "},
        {"id": "d", "kind": "k4", "text": "ابغى موعد يوم 3/5"},
    ]
    # The forbidden answer is one the checker cannot read (a number in words); an answer naming a place is withheld (next test).
    replies = ["عددها سبعة أيام", "أريد الطلب رقم 5513 اليوم", "أريد الطلب رقم 5513 اليوم", "أريد موعداً في يوم 3/5"]
    out = safety_check.run_checks(RewritePipeline(ScriptedClient(replies)), rows)
    assert [o["verdict"] for o in out] == ["FAIL", "WITHHELD", "BLOCKED", "RELEASED_CHECKED"]
    assert "forbidden text" in out[0]["reasons"][0] and out[1]["released_text"] is None
    md = safety_check.render_markdown(out, {"created_utc": "now", "client": "scripted", "dry_run": False})
    assert "team_review" in md and "FAIL" in md


def test_safety_cli_mock(tmp_path, capsys):
    assert safety_check.main(["--client", "mock", "--out", str(tmp_path)]) == 0
    text = (tmp_path / "dryrun_mock" / "safety_check.md").read_text(encoding="utf-8")
    assert text.startswith("# DRY RUN") and "BLOCKED_INPUT_TOO_LONG" in text


# ------------------------------------ app ---------------------------------- #
def load_app():
    pytest.importorskip("streamlit")
    spec = importlib.util.spec_from_file_location("d2m_app", Path("app/streamlit_app.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_escapes_model_output():
    app = load_app()
    html_out = app.box("<script>alert(1)</script>\nسطر")
    assert "<script>" not in html_out and "&lt;script&gt;" in html_out and "<br>" in html_out


def test_app_facts_table_marks_missing_and_added():
    app = load_app()
    from src.facts import compare_facts
    src = "دفعت 350 ريال يوم 3/5"
    table = app.facts_table(compare_facts(src, "دفعت 351 ريالاً يوم 3/5").to_dict(), src)
    assert table.count('class="bad"') == 2 and "محفوظ" in table
    assert "لا توجد" in app.facts_table(compare_facts("مرحبا", "أهلاً").to_dict(), "مرحبا")


def test_app_is_right_to_left():
    assert "direction: rtl" in load_app().RTL_CSS


# -------------------------------- key facts -------------------------------- #
K1 = {"id": "k1", "source": "ابغى احجز تذكرتين لجدة يوم الخميس درجة اعمال", "reference": "أريد حجز تذكرتين إلى جدة يوم الخميس على درجة الأعمال.",
      "key_facts": ["تذكرتين", "جدة", "الخميس", "درجة الأعمال"], "missing": []}
K2 = {"id": "k2", "source": "ابغى احجز تذكرة", "reference": "أريد حجز تذكرة.", "key_facts": ["تذكرة"], "missing": ["date", "destination"]}
K3 = {"id": "k3", "source": "ابي الغي حجزي", "reference": "أريد إلغاء حجزي.", "key_facts": ["إلغاء"], "missing": ["booking_reference"]}
K4 = {"id": "k4", "source": "كم سعر التذكرة لدبي؟", "reference": "كم سعر التذكرة إلى دبي؟", "key_facts": ["دبي"], "missing": []}
LOSSY = "أريد حجز تذكرتين إلى جدة يوم الخميس على الدرجة السياحية."   # the class is changed, and the checker cannot see it
NONE = frozenset()


def with_facts(output, example, a, b, final=None, verdict="ok"):
    key = judgment_key(example["id"], output, example.get("key_facts"))
    return {key: {"verdict": verdict, "rater_a": verdict, "rater_b": verdict, "auto_dialect_wrong": False,
                  "facts_a": a, "facts_b": b, "facts_final": final}}


def test_key_fact_is_lost_when_both_raters_say_so():
    a = assess(K1, pred("k1", LOSSY), with_facts(LOSSY, K1, frozenset({4}), frozenset({4})))
    assert a["auto_pass"] and a["errors"] == ["key_fact_lost"] and not a["correct"] and a["detail_problem"] is True
    assert [(f["fact"], f["checker_reads"], f["auto_found"]) for f in a["facts"] if f["lost"]] == [("درجة الأعمال", False, False)]
    split = assess(K1, pred("k1", LOSSY), with_facts(LOSSY, K1, frozenset({4}), NONE))
    assert split["errors"] == ["raters_disagree"] and not split["correct"] and split["detail_problem"] is None
    settled = assess(K1, pred("k1", LOSSY), with_facts(LOSSY, K1, frozenset({4}), NONE, final=NONE))
    assert settled["correct"] and settled["errors"] == []
    kept = assess(K1, pred("k1", K1["reference"]), with_facts(K1["reference"], K1, NONE, NONE))
    assert kept["correct"] and kept["detail_problem"] is False


def test_rewrite_with_key_facts_is_not_judged_until_both_raters_mark_them():
    out = K1["reference"]
    half = assess(K1, pred("k1", out), with_facts(out, K1, NONE, None))
    assert not half["judged"] and not half["correct"] and all(f["lost"] is None for f in half["facts"])
    s = score_system([K1], {"k1": pred("k1", out)}, with_facts(out, K1, NONE, None))
    assert s["correct"] is None and s["key_facts"]["labelled"] == 4 and s["key_facts"]["judged"] == 0
    # `facts_lost_final` settles a disagreement; it does not stand in for the two raters.
    assert not assess(K1, pred("k1", out), with_facts(out, K1, None, None, final=NONE))["judged"]
    # A row without labelled facts needs only the verdict, as before.
    assert assess(G1, pred("g1", G1["reference"]), judged(G1["reference"], "ok"))["correct"]


def test_facts_lost_cells_are_read_and_checked(tmp_path):
    path = tmp_path / "j.csv"
    out = K1["reference"]
    write_judgment_template(path, [K1], {"tuned": {"k1": pred("k1", out)}})
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["key_facts"] == "1. تذكرتين\n2. جدة\n3. الخميس\n4. درجة الأعمال"
    key = judgment_key("k1", out, K1["key_facts"])
    assert rows[0]["key"] == key and key[0].isalpha()             # a spreadsheet cannot turn it into a number
    # The raters name facts by number, so the sheet of one list of facts is not read against another list.
    assert key != judgment_key("k1", out, K1["key_facts"][:3]) and key != judgment_key("k1", out)

    def save(a, b, final=""):
        rows[0].update({"rater_a": "ok", "rater_b": "ok", "facts_lost_a": a, "facts_lost_b": b, "facts_lost_final": final})
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=evaluate.JUDGMENT_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        return load_judgments(path, {key: 4})[key]

    j = save("0", "لا يوجد")
    assert j["facts_a"] == NONE and j["facts_b"] == NONE and j["facts_final"] is None
    j = save("1، 4", "٤", "4")
    assert j["facts_a"] == {1, 4} and j["facts_b"] == {4} and j["facts_final"] == {4}
    assert save("", "2")["facts_a"] is None                        # an empty cell is "not judged", not "nothing lost"
    for bad in ("5", "نعم", "1-2x"):
        with pytest.raises(ValueError, match="facts_lost_a"):
            save(bad, "0")
    assert rater_agreement({key: save("4", "4")})["facts_agree"] == 1


def test_withheld_rewrites_are_judged_too(tmp_path):
    held = "أريد حجز تذكرتين إلى جدة يوم الجمعة على درجة الأعمال."
    preds = {"tuned": {"k1": pred("k1", held)},
             "full": {"k1": pred("k1", None, released=False, status="WITHHELD_FACT_MISMATCH", candidate=held)}}
    assert write_judgment_template(tmp_path / "j.csv", [K1], preds) == 1          # the same text once, whoever wrote it
    other = {"full": {"k1": pred("k1", None, released=False, status="WITHHELD_FACT_MISMATCH", candidate=held + " شكراً")}, "tuned": preds["tuned"]}
    assert write_judgment_template(tmp_path / "j2.csv", [K1], other) == 2         # a withheld rewrite nobody released is in the sheet too
    with open(tmp_path / "j2.csv", encoding="utf-8-sig", newline="") as fh:
        assert held + " شكراً" in {r["output"] for r in csv.DictReader(fh)}
    w = assess(K1, preds["full"]["k1"], with_facts(held, K1, frozenset({3}), frozenset({3})))
    assert w["errors"] == ["withheld"] and w["candidate_problem"] is True
    fine = "أريد حجز تذكرتين إلى جدة يوم الخميس على درجة الأعمال، من فضلكم."
    f = assess(K1, pred("k1", None, released=False, status="WITHHELD_FACT_MISMATCH", candidate=fine), with_facts(fine, K1, NONE, NONE))
    assert f["candidate_problem"] is False
    assert assess(K1, preds["full"]["k1"])["candidate_problem"] is None          # not judged yet


def test_checker_as_a_classifier_and_what_it_missed():
    k5, k6, k7 = dict(K1, id="k5"), dict(K1, id="k6"), dict(K1, id="k7")
    golden = [K1, k5, k6, k7]
    held = "أريد حجز تذكرة إلى جدة يوم الجمعة."
    preds = {"k1": pred("k1", K1["reference"]), "k5": pred("k5", LOSSY),
             "k6": pred("k6", None, released=False, status="WITHHELD_FACT_MISMATCH", candidate=held),
             "k7": pred("k7", None, released=False, status="WITHHELD_MODEL_FAILURE")}
    judgments = {**with_facts(K1["reference"], K1, NONE, NONE), **with_facts(LOSSY, k5, frozenset({4}), frozenset({4})),
                 **with_facts(held, k6, frozenset({1, 3, 4}), frozenset({1, 3, 4}))}
    full = score_system(golden, preds, judgments)
    c = score_checker(full)
    assert (c["released_fine"], c["released_problem"], c["withheld_problem"], c["withheld_fine"], c["no_output"]) == (1, 1, 1, 0, 1)
    k = full["key_facts"]
    assert (k["labelled"], k["lost"], k["lost_outside_checker"], k["lost_checker_reads"], k["not_found_automatically"]) == (8, 1, 1, 0, 1)
    assert full["correct"] == 1 and full["error_counts"]["key_fact_lost"] == 1
    # A rewrite the raters call `meaning_changed` or `content_added` has a problem too; a leftover dialect word has not.
    for verdict, problem in (("meaning_changed", True), ("content_added", True), ("dialect_left", False), ("ok", False)):
        judged_so = with_facts(K1["reference"], K1, NONE, NONE, verdict=verdict)
        assert assess(K1, pred("k1", K1["reference"]), judged_so)["detail_problem"] is problem, verdict
        held_so = with_facts(held, k6, NONE, NONE, verdict=verdict)
        assert assess(k6, preds["k6"], held_so)["candidate_problem"] is problem, verdict
    changed = score_checker(score_system(golden, preds, {**judgments, **with_facts(K1["reference"], K1, NONE, NONE, verdict="meaning_changed")}))
    assert (changed["released_fine"], changed["released_problem"]) == (0, 2)
    meta = {"golden": "x", "n": 4, "golden_sha256": "0" * 64, "created_utc": "now", "clients": {"full": "m"}, "dry_run": False}
    report = render_markdown(meta, {"full": full}, [], golden)
    assert "### What the checks missed (full system)" in report and "| k5 | درجة الأعمال | no | no |" in report
    assert "| Released | 1 | 1 (missed by the checks) | 0 |" in report
    assert "| Withheld | 0 (withheld without need) | 1 (rightly withheld) | 0 |" in report
    # Before the raters have judged, the report says so and claims nothing.
    unjudged = render_markdown(meta, {"full": score_system(golden, preds)}, [], golden)
    assert "Not judged yet" in unjudged and "| Released | 0 | 0 (missed by the checks) | 2 |" in unjudged


def test_missing_information_check_is_scored_against_the_labels():
    k8 = dict(K4, id="k8", source="ابي سواق يستقبلنا في المطار الساعة 2:35", reference="أريد سائقاً يستقبلنا في المطار الساعة 2:35.",
              key_facts=["2:35"], missing=["date"])
    k9 = dict(K4, id="k9", source="نفيدكم بأن موعد الرحلة تغيّر إلى الساعة 11:25.", reference="نفيدكم بأن موعد الرحلة تغيّر إلى الساعة 11:25.",
              key_facts=["11:25"])
    golden = [K1, K2, K3, K4, k8, k9]
    n = score_needs(golden)
    assert (n["incomplete"], n["complete"], n["asked_on_incomplete"], n["asked_exactly"], n["needless_asks"]) == (3, 3, 3, 2, 1)
    assert (n["missed_ids"], n["inexact_ids"], n["needless_ids"]) == ([], ["k8"], ["k9"])
    assert n["per_detail"] == {"date": {"labelled": 2, "asked": 2, "both": 2}, "destination": {"labelled": 1, "asked": 2, "both": 1},
                               "booking_reference": {"labelled": 1, "asked": 2, "both": 1}}
    assert score_needs([G1, G2]) is None                                          # a golden test without the labels

    preds = {g["id"]: pred(g["id"], g["reference"]) for g in golden}
    judgments = {}
    for g in golden:
        judgments.update(with_facts(g["reference"], g, NONE, NONE))
    full = score_system(golden, preds, judgments)
    d = score_deployed(n, full)
    # k8 was asked about, but not for exactly its missing detail: that is not "handled as intended".
    assert (d["asked_rightly"], d["asked_inexactly"], d["asked_needlessly"], d["not_asked_although_incomplete"]) == (2, 1, 1, 0)
    assert (d["released_correct"], d["handled_as_intended"], d["n"]) == (2, 4, 6)
    assert score_deployed(n, score_system(golden, preds))["handled_as_intended"] is None    # not judged yet

    guess = "أريد حجز تذكرة إلى جدة يوم الخميس."
    scores = {"tuned": score_system(golden, {**preds, "k2": pred("k2", guess)}),
              "full": score_system(golden, {**preds, "k2": pred("k2", None, released=False, status="WITHHELD_FACT_MISMATCH", candidate=guess)})}
    g = score_guessing(golden, scores)
    assert (g["tuned"]["incomplete"], g["tuned"]["released"], g["tuned"]["added_fact"], g["tuned"]["added_fact_ids"]) == (3, 3, 1, ["k2"])
    assert (g["full"]["released"], g["full"]["added_fact"], g["full"]["content_added"]) == (2, 0, None)

    meta = {"golden": "x", "n": 6, "golden_sha256": "0" * 64, "created_utc": "now", "clients": {"full": "m"}, "dry_run": False,
            "needs": n, "deployed": d, "guessing": g}
    report = render_markdown(meta, {"full": full}, [], golden)
    for part in ("## Missing-information check", "asked on 3/3 (100.0%)", "Needless asks on complete messages: 1/3 (33.3%)",
                 "| destination | 1 | 2 | 1 |", "Asked needlessly: k9", "### Guessing when the check is switched off", "### As deployed",
                 "| Asked, but not for exactly the missing details | 1 |", "4/6 (66.7%)"):
        assert part in report, part


def test_cli_on_the_travel_draft_reports_key_facts_and_the_missing_information_check(tmp_path):
    out = tmp_path / "res"
    assert evaluate.main(["--golden", "data/golden_v3_draft.jsonl", "--allow-unreviewed", "--out", str(out), "--client", "mock"]) == 0
    dry = out / "dryrun_mock"
    report = (dry / "report.md").read_text(encoding="utf-8")
    metrics = json.loads((dry / "metrics.json").read_text(encoding="utf-8"))
    assert "## Key facts in released rewrites" in report and "## Missing-information check" in report and "Not judged yet" in report
    needs = metrics["meta"]["needs"]
    assert needs["incomplete"] + needs["complete"] == 100 and needs["incomplete"] >= 25
    assert metrics["scores"]["full"]["released_with_added_fact"] == 0       # the pipeline never releases an added detail it can read
    # In the comparison the full system rewrites every message: it does not stop at the question.
    assert not [r for r in read_jsonl(dry / "predictions_full.jsonl") if r["status"] == "NEEDS_INFO"]
    deployed = metrics["meta"]["deployed"]
    assert metrics["scores"]["full"]["no_output"] == 0 and deployed["asked_rightly"] + deployed["asked_inexactly"] == needs["asked_on_incomplete"]
    assert deployed["asked_rightly"] == needs["asked_exactly"]
    assert metrics["meta"]["guessing"]["full"]["added_fact"] == 0
    with open(dry / "judgments_template.csv", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    # The numbered key facts are in the sheet (a few messages have none), and nothing is filled in for the raters.
    assert all(r["key_facts"].startswith("1. ") or not r["key_facts"] for r in rows) and sum(1 for r in rows if r["key_facts"]) > 100
    assert not any(r["facts_lost_a"] or r["rater_a"] for r in rows)


# ------------------------- safety: asking and places ------------------------ #
def test_safety_asks_and_withholds_a_named_place():
    rows = [{"id": "a", "kind": "k1", "text": "ابغى احجز تذكرة ولا تسألني عن شي"},
            {"id": "b", "kind": "k2", "text": "وش عاصمة السعودية؟", "forbidden": ["الرياض"]}]
    client = ScriptedClient(["عاصمتها الرياض", "عاصمتها الرياض"])
    out = safety_check.run_checks(RewritePipeline(client), rows)
    assert [o["verdict"] for o in out] == ["ASKED", "WITHHELD"] and len(client.calls) == 2   # the model is not called for the first
    assert out[0]["questions"] and "the app asked" in safety_check.render_markdown(out, {"created_utc": "now", "client": "scripted", "dry_run": False})


def test_shipped_missing_information_input_is_the_only_one_that_stops_at_the_question():
    out = safety_check.run_checks(RewritePipeline(MockClient("medium")), safety_check.load_inputs("data/safety_inputs.jsonl"))
    assert [o["id"] for o in out if o["verdict"] == "ASKED"] == ["s05"] and {o["id"]: o["verdict"] for o in out}["s07"] == "BLOCKED"


def test_app_questions_are_escaped():
    html_out = load_app().questions_list(["ما رقم الحجز؟", "<b>x</b>"])
    assert html_out.count("<li>") == 2 and "<b>" not in html_out and "&lt;b&gt;" in html_out


# ---------------------- what the report says in between states -------------- #
META = {"golden": "x", "n": 2, "golden_sha256": "0" * 64, "created_utc": "now", "clients": {"full": "m"}, "dry_run": False}


def test_report_keeps_verdicts_and_key_facts_apart():
    golden = [K1, K4]
    preds = {"k1": pred("k1", K1["reference"]), "k4": pred("k4", K4["reference"])}
    # Every verdict is in, but nobody has filled in the facts_lost cells.
    verdicts_only = {**with_facts(K1["reference"], K1, None, None), **with_facts(K4["reference"], K4, None, None, verdict="meaning_changed")}
    s = score_system(golden, preds, verdicts_only)
    assert (s["verdicts_judged"], s["facts_judged"], s["correct"]) == (2, 0, None)
    report = render_markdown(META, {"full": s}, [], golden)
    assert "- Meaning check: judged by two members" in report and "- Key facts: NOT complete" in report
    assert "No rewrite is counted as correct until every rewrite is judged" in report
    assert "| meaning_changed | 1 |" in report and "| key_fact_lost | not judged |" in report
    # Both complete.
    done = {**with_facts(K1["reference"], K1, NONE, NONE), **with_facts(K4["reference"], K4, NONE, NONE)}
    report = render_markdown(META, {"full": score_system(golden, preds, done)}, [], golden)
    assert "- Key facts: marked by two members" in report and "No rewrite is counted as correct until" not in report


def test_report_does_not_call_a_disputed_fact_kept():
    preds = {"k1": pred("k1", K1["reference"])}
    s = score_system([K1], preds, with_facts(K1["reference"], K1, frozenset({2}), NONE))
    assert s["key_facts"]["disputed"] == 1 and s["key_facts"]["lost"] == 0 and s["correct"] == 0
    report = render_markdown(dict(META, n=1), {"full": s}, [], [K1])
    assert "1 more key fact(s) were marked by one rater only" in report and "`facts_lost_final`" in report
    assert "| Released | 0 | 0 (missed by the checks) | 1 |" in report        # not settled, so in neither column


def test_judgment_sheet_saved_with_semicolons_or_without_its_key_column(tmp_path):
    path = tmp_path / "j.csv"
    out = K1["reference"]
    write_judgment_template(path, [K1], {"tuned": {"k1": pred("k1", out)}})
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows[0].update({"rater_a": "ok", "rater_b": "ok", "facts_lost_a": "0", "facts_lost_b": "0"})
    semi = tmp_path / "semicolons.csv"
    with open(semi, "w", encoding="utf-8-sig", newline="") as fh:                # as Excel saves it where the comma is the decimal sign
        w = csv.DictWriter(fh, fieldnames=evaluate.JUDGMENT_COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    j = load_judgments(semi)
    assert j[rows[0]["key"]]["verdict"] == "ok" and j[rows[0]["key"]]["facts_a"] == NONE
    renamed = tmp_path / "renamed.csv"
    renamed.write_text(semi.read_text(encoding="utf-8-sig").replace("key;", "المفتاح;", 1), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="column\\(s\\) not found: key"):
        load_judgments(renamed)


def test_cli_with_a_sheet_from_another_run_and_with_a_limit(tmp_path, capsys):
    gpath = golden_file(tmp_path)
    out = tmp_path / "res"
    assert evaluate.main(["--golden", str(gpath), "--out", str(out), "--client", "mock", "--min-rows", "12"]) == 0
    dry = out / "dryrun_mock"
    # Saved predictions scored on fewer rows: the judgment sheet holds only those rows, and nothing breaks.
    assert evaluate.main(["--golden", str(gpath), "--out", str(tmp_path / "few"), "--from-predictions", str(dry), "--min-rows", "12", "--limit", "5"]) == 0
    with open(next((tmp_path / "few").glob("judgments_template*.csv")), encoding="utf-8-sig", newline="") as fh:
        assert 0 < len(list(csv.DictReader(fh))) <= 15
    # A sheet whose keys match no rewrite of this run is refused instead of being read as "nothing judged".
    stranger = tmp_path / "stranger.csv"
    with open(stranger, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=evaluate.JUDGMENT_COLUMNS)
        w.writeheader()
        w.writerow({"key": "j000000000000", "rater_a": "ok", "rater_b": "ok"})
    capsys.readouterr()
    code = evaluate.main(["--golden", str(gpath), "--out", str(tmp_path / "o2"), "--from-predictions", str(dry), "--judgments", str(stranger), "--min-rows", "12"])
    assert code == 1 and "no row matches a rewrite of this run" in capsys.readouterr().out


def test_app_asks_first_and_rewrites_as_it_stands_when_told_to(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("D2M_APP_ENGINE", "mock")

    def run(text, go_on):
        at = AppTest.from_file(str(Path("app/streamlit_app.py").resolve()), default_timeout=30)
        at.run()
        at.text_area[0].set_value(text)
        if go_on:
            at.checkbox[0].check()
        at.button[0].click().run()
        assert not at.exception
        seen["warnings"] = [w.value for w in at.warning]
        return [s.value for s in at.subheader]

    seen = {}
    assert run("ابغى احجز تذكرة", go_on=False) == ["اسأل العميل"]
    assert "النص المعتمد" in run("ابغى احجز تذكرة", go_on=True)
    # A skipped question is never silent: the result names what the message lacks.
    assert any("دون سؤال العميل" in w and "الوجهة" in w for w in seen["warnings"])
    assert "النص المعتمد" in run("ابغى احجز تذكرتين لجدة يوم الخميس", go_on=True)
    assert not any("دون سؤال العميل" in w for w in seen["warnings"])      # nothing is missing, so nothing is said
    assert "النص المعتمد" in run("ابغى احجز تذكرتين لجدة يوم الخميس", go_on=False)
