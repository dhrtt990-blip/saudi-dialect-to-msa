"""Evaluation, blind judgments, safety check and app helpers."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

from src import evaluate, safety_check
from src.common import read_jsonl, write_jsonl
from src.evaluate import (
    assess, chrf, count_transitions, judgment_key, load_judgments, rater_agreement, render_markdown, score_system,
    write_judgment_template,
)
from src.pipeline import LLMUnavailable, RewritePipeline, ScriptedClient

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
