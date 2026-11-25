"""Score three systems on the golden test and write the comparison report.

    python -m src.evaluate --golden data/golden_v3_r1_candidate.jsonl --out results/v3_r1

  baseline  the untuned model with its own prompt and worked examples
  tuned     the fine-tuned model alone
  full      the fine-tuned model inside the pipeline (checker, repair, withhold)

All three rewrite every golden message, so the comparison is like for like: the
missing-information check is switched off for it and scored on its own.

A rewrite is CORRECT only if it passes four checks:
  1. facts      every number, date, time, Latin word, day, listed place and listed name is kept (automatic)
  2. dialect    no listed dialect word is left (automatic word list; a reviewer can overrule it)
  3. meaning    the meaning is kept and nothing is added (two team members, judging blind)
  4. key facts  no key fact labelled in the golden test is lost or changed (the same two members)

The report also says what the checks miss: the labelled key facts that are lost
or changed in rewrites the pipeline released, the rewrites it withheld although
nothing was wrong with them, and how the missing-information check did against
the labels of the golden test.

The first run writes `judgments_template.csv`. Two members fill it in without
knowing which system wrote which line. A second run with `--judgments` adds
checks 3 and 4. Until then the report shows the automatic checks only and says so.

`--client mock` runs the same code with a rule-based stand-in and writes to
`<out>/dryrun_mock`. Those numbers are not results.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .common import normalize_for_dedup, read_jsonl, sha256_file, strip_marks, write_jsonl
from .facts import checker_reads, compare_facts, fact_present
from .lexicon import find_dialect_words
from .needs import DETAILS, find_missing
from .pipeline import (
    DEFAULT_BASE_MODEL,
    DEFAULT_HOST,
    DEFAULT_TUNED_MODEL,
    LLMUnavailable,
    MockClient,
    OllamaClient,
    STATUS_MODEL_FAILURE,
    RewritePipeline,
    run_model,
)
from .prompts import build_messages
from .validate_golden import validate_rows

SYSTEMS = ("baseline", "tuned", "full")
SYSTEM_LABELS = {
    "baseline": "Untuned model + full prompt",
    "tuned": "Tuned model alone",
    "full": "Tuned model in the pipeline",
}
VERDICTS = ("ok", "meaning_changed", "content_added", "dialect_left")
AUTO_ERRORS = ("no_output", "withheld", "dropped_fact", "changed_fact", "added_fact", "name_lost", "dialect_left", "copied_input")
HUMAN_ERRORS = ("meaning_changed", "content_added", "key_fact_lost", "raters_disagree")
ERROR_TYPES = AUTO_ERRORS + HUMAN_ERRORS


# --------------------------------------------------------------------------- #
# Predictions
# --------------------------------------------------------------------------- #
def predict_model_only(client, example: dict) -> dict:
    """The model alone: whatever it answers is what the user would get."""
    r = run_model(client, build_messages(example["source"], few_shot=getattr(client, "few_shot", False)))
    if r.unavailable:
        raise LLMUnavailable(r.error or "model server unavailable")
    return {
        "id": example["id"],
        "output": r.output if r.ok else None,
        "released": r.ok,
        "status": "MODEL_ONLY" if r.ok else "NO_OUTPUT",
        "repaired": False,
    }


def predict_full(pipeline: RewritePipeline, example: dict) -> dict:
    res = pipeline.run(example["source"], example.get("must_keep", ()))
    if res.unavailable:
        raise LLMUnavailable(res.error or "model server unavailable")
    return {
        "id": example["id"],
        "output": res.text if res.released else None,
        "candidate": res.candidate,
        "released": res.released,
        "status": res.status,
        "repaired": res.repaired,
        "first_check_ok": res.first_check.get("ok") if res.first_check else None,
    }


# --------------------------------------------------------------------------- #
# chrF-style overlap with the reference (secondary, descriptive only)
# --------------------------------------------------------------------------- #
def chrf(hypothesis: str, reference: str, max_n: int = 6, beta: float = 2.0) -> float:
    """Character n-gram F-score (n = 1..6, beta = 2), own implementation.

    It follows the chrF idea but is not the sacreBLEU implementation, so do not
    compare it with published chrF numbers. There is one reference per message
    and many correct rewrites, so a low score does not mean a wrong rewrite."""
    hyp = "".join(strip_marks(hypothesis).split())
    ref = "".join(strip_marks(reference).split())
    if not hyp or not ref:
        return 0.0
    scores = []
    for n in range(1, max_n + 1):
        h = Counter(hyp[i:i + n] for i in range(len(hyp) - n + 1))
        r = Counter(ref[i:i + n] for i in range(len(ref) - n + 1))
        if not h or not r:
            continue
        overlap = sum((h & r).values())
        p, rec = overlap / sum(h.values()), overlap / sum(r.values())
        scores.append(0.0 if p + rec == 0 else (1 + beta**2) * p * rec / (beta**2 * p + rec))
    return sum(scores) / len(scores) if scores else 0.0


# --------------------------------------------------------------------------- #
# Blind judgments
# --------------------------------------------------------------------------- #
def judgment_key(example_id: str, output: str, key_facts: list[str] | tuple[str, ...] | None = None) -> str:
    """Same id and exactly the same text (up to spacing) give the same key, so
    identical outputs of two systems are judged once and the judge cannot tell
    the systems apart. Outputs that differ in any character get their own row.

    The labelled key facts are part of the key: the raters refer to them by number, so a sheet filled in
    for one list of facts must not be read against another. The key starts with a letter so that a
    spreadsheet never turns it into a number."""
    parts = [example_id, " ".join(output.split()), *(key_facts or ())]
    return "j" + hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:12]


# The automatic flags are left out on purpose: they would hint at the system and prime the verdict.
JUDGMENT_COLUMNS = ["key", "source", "reference", "key_facts", "output", "rater_a", "rater_b", "final",
                    "facts_lost_a", "facts_lost_b", "facts_lost_final", "auto_dialect_wrong"]
# What a rater writes in a facts_lost cell when no key fact is lost.
_NO_FACT_LOST = {"0", "none", "no", "-", "لا", "لا يوجد", "لايوجد", "صفر"}


def texts_to_judge(pred: dict) -> list[str]:
    """What the raters read for one prediction: the released rewrite, or the rewrite the pipeline
    withheld. The withheld ones are judged too, so the report can say how often withholding was needed."""
    if pred.get("released") and pred.get("output"):
        return [pred["output"]]
    if not pred.get("released") and pred.get("candidate"):
        return [pred["candidate"]]
    return []


def write_judgment_template(path: Path, golden: list[dict], predictions: dict[str, dict[str, dict]], seed: int = 13) -> int:
    by_id = {g["id"]: g for g in golden}
    rows: dict[str, dict] = {}
    for preds in predictions.values():
        for pid, pred in preds.items():
            if pid not in by_id:  # saved predictions can hold more rows than a run limited with --limit
                continue
            g = by_id[pid]
            for text in texts_to_judge(pred):
                key = judgment_key(pid, text, g.get("key_facts"))
                if key in rows:
                    continue
                rows[key] = {
                    "key": key, "source": g["source"], "reference": g["reference"],
                    "key_facts": "\n".join(f"{n}. {fact}" for n, fact in enumerate(g.get("key_facts") or [], 1)),
                    "output": text, "rater_a": "", "rater_b": "", "final": "",
                    "facts_lost_a": "", "facts_lost_b": "", "facts_lost_final": "", "auto_dialect_wrong": "",
                }
    ordered = [rows[k] for k in sorted(rows)]
    random.Random(seed).shuffle(ordered)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=JUDGMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)
    return len(ordered)


def _fact_numbers(cell: str | None, where: str, limit: int | None) -> frozenset[int] | None:
    """A facts_lost cell: None when empty (not judged), an empty set for "0" (nothing lost),
    else the numbers of the lost or changed facts ("2", "1,3")."""
    text = " ".join(strip_marks(cell or "").split()).lower()
    if not text:
        return None
    if text in _NO_FACT_LOST:
        return frozenset()
    parts = [part for part in re.split(r"[\s,،;؛]+", text) if part]
    if not all(part.isdigit() for part in parts) or any(int(part) < 1 or (limit is not None and int(part) > limit) for part in parts):
        allowed = f"1 to {limit}" if limit else "the numbers in the key_facts cell"
        raise ValueError(f"{where}='{cell}': write the numbers of the lost or changed key facts ({allowed}; for example 2 or 1,3), or 0 when none is lost")
    return frozenset(int(part) for part in parts)


def load_judgments(path: str | Path, fact_counts: dict[str, int] | None = None) -> dict[str, dict]:
    """Read the filled-in judgment sheet. Raises ValueError on an unknown verdict or fact number.

    `fact_counts` gives the number of labelled key facts per key, so a fact number that does not exist is refused."""
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = fh.readline()
        fh.seek(0)
        # Excel writes ";" between the cells where the comma is the decimal sign.
        reader = csv.DictReader(fh, delimiter=";" if header.count(";") > header.count(",") else ",")
        needed = [c for c in ("key", "rater_a", "rater_b") if c not in (reader.fieldnames or [])]
        if needed:
            raise ValueError(f"{path}: column(s) not found: {', '.join(needed)}. Keep the first row of the judgment sheet as it was written.")
        for n, row in enumerate(reader, 2):
            key = (row.get("key") or "").strip()
            if not key:
                continue
            a, b, final = ((row.get(c) or "").strip().lower() for c in ("rater_a", "rater_b", "final"))
            for name, value in (("rater_a", a), ("rater_b", b), ("final", final)):
                if value and value not in VERDICTS:
                    raise ValueError(f"{path}: line {n}: {name}='{value}' is not one of {', '.join(VERDICTS)}")
            if a and b:
                # `final` records what the two raters agreed after discussing a disagreement.
                verdict = final or (a if a == b else "raters_disagree")
            else:
                verdict = None  # not judged by two members yet, whatever `final` says
            limit = (fact_counts or {}).get(key)
            facts = {name: _fact_numbers(row.get(f"facts_lost_{name}"), f"{path}: line {n}: facts_lost_{name}", limit)
                     for name in ("a", "b", "final")}
            out[key] = {
                "verdict": verdict, "rater_a": a, "rater_b": b,
                "auto_dialect_wrong": (row.get("auto_dialect_wrong") or "").strip().lower() in ("yes", "y", "1", "true"),
                "facts_a": facts["a"], "facts_b": facts["b"], "facts_final": facts["final"],
            }
    return out


def rater_agreement(judgments: dict[str, dict]) -> dict:
    both = [j for j in judgments.values() if j["rater_a"] and j["rater_b"]]
    agree = sum(1 for j in both if j["rater_a"] == j["rater_b"])
    facts = [j for j in judgments.values() if j.get("facts_a") is not None and j.get("facts_b") is not None]
    return {"judged_by_both": len(both), "agree": agree, "rate": agree / len(both) if both else None,
            "facts_judged_by_both": len(facts), "facts_agree": sum(1 for j in facts if j["facts_a"] == j["facts_b"])}


def judge_facts(example: dict, text: str, judgment: dict | None) -> tuple[list[dict], bool]:
    """Every labelled key fact of `example` against one rewrite.

    `auto_found` is the automatic first look. `lost` is what the two raters say: True when both marked
    the fact (or `facts_lost_final` lists it), False when neither did, None while it is not judged.
    A fact only one rater marked is `disputed` until `facts_lost_final` settles it.
    The second value says whether the raters have judged the facts of this rewrite."""
    labels = example.get("key_facts") or []
    a = judgment.get("facts_a") if judgment else None
    b = judgment.get("facts_b") if judgment else None
    final = judgment.get("facts_final") if judgment else None
    judged = not labels or (a is not None and b is not None)  # `final` settles a disagreement; it does not replace the two raters
    facts = []
    for n, label in enumerate(labels, 1):
        if not judged:
            lost, disputed = None, False
        elif final is not None:
            lost, disputed = n in final, False
        else:
            lost, disputed = n in a and n in b, (n in a) != (n in b)
        facts.append({"n": n, "fact": label, "auto_found": fact_present(text, label),
                      "checker_reads": checker_reads(label, example.get("must_keep", ())), "lost": lost, "disputed": disputed})
    return facts, judged


PROBLEM_VERDICTS = ("meaning_changed", "content_added")


def detail_problem(verdict: str | None, facts: list[dict], facts_judged: bool) -> bool | None:
    """Whether the raters found the substance of a rewrite wrong: the meaning changed, content was added, or a
    key fact is lost or changed. None while they have not settled it. A leftover dialect word is not counted
    here: it says nothing about the facts."""
    if verdict in (None, "raters_disagree") or not facts_judged or any(f["disputed"] for f in facts):
        return None
    return verdict in PROBLEM_VERDICTS or any(f["lost"] for f in facts)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def assess(example: dict, pred: dict, judgments: dict[str, dict] | None = None) -> dict:
    """Apply the checks to one prediction."""
    out = pred.get("output")
    base = {"id": example["id"], "status": pred.get("status"), "repaired": bool(pred.get("repaired"))}
    if not pred.get("released") or not out:
        status = str(pred.get("status", ""))
        # A model that gave no usable answer is the same failure with or without the pipeline.
        kind = "withheld" if status.startswith(("WITHHELD", "BLOCKED")) and status != STATUS_MODEL_FAILURE else "no_output"
        # The rewrite the pipeline withheld is judged as well: was withholding needed?
        candidate = pred.get("candidate") if kind == "withheld" else None
        candidate_problem = None
        if candidate:
            held = (judgments or {}).get(judgment_key(example["id"], candidate, example.get("key_facts")))
            held_facts, held_judged = judge_facts(example, candidate, held)
            candidate_problem = detail_problem(held["verdict"] if held else None, held_facts, held_judged)
        return {**base, "released": False, "errors": [kind], "fact_error": False, "auto_pass": False,
                "judged": True, "verdict_judged": True, "facts_judged": True,
                "correct": False, "chrf": None, "output": None, "detail": {}, "key": None, "list_vs_raters": False,
                "facts": [], "detail_problem": None, "candidate": candidate, "candidate_problem": candidate_problem}

    report = compare_facts(example["source"], out, example.get("must_keep", ()))
    words = find_dialect_words(out)
    key = judgment_key(example["id"], out, example.get("key_facts"))
    judgment = (judgments or {}).get(key)
    errors: list[str] = []
    if not report.ok:
        errors.append(report.kind)
        if report.must_keep_missing and report.kind != "name_lost":
            errors.append("name_lost")
    # The word list can be overruled only where the two raters' verdict is `ok`: that is the conflict the column
    # exists to settle. One person cannot clear the flag alone, nor on a row the raters disagree about.
    overruled = bool(judgment and judgment["verdict"] == "ok" and judgment["auto_dialect_wrong"])
    dialect_left = bool(words["strong"]) and not overruled
    if dialect_left:
        errors.append("dialect_left")
    # The message came back unchanged although the reference shows it needed rewriting.
    src_norm = normalize_for_dedup(example["source"])
    if normalize_for_dedup(out) == src_norm and normalize_for_dedup(example["reference"]) != src_norm:
        errors.append("copied_input")
    auto_pass = not errors

    verdict = judgment["verdict"] if judgment else None
    if verdict and verdict != "ok" and verdict not in errors:
        errors.append(verdict)
    facts, facts_judged = judge_facts(example, out, judgment)
    if any(f["lost"] for f in facts):
        errors.append("key_fact_lost")
    if any(f["disputed"] for f in facts) and "raters_disagree" not in errors:
        errors.append("raters_disagree")
    facts_fine = facts_judged and not any(f["lost"] or f["disputed"] for f in facts)
    return {
        **base, "released": True, "errors": errors, "fact_error": not report.ok, "auto_pass": auto_pass,
        "judged": verdict is not None and facts_judged, "verdict_judged": verdict is not None, "facts_judged": facts_judged,
        "correct": auto_pass and verdict == "ok" and facts_fine,
        "chrf": round(chrf(out, example["reference"]), 4),
        "output": out, "facts": facts, "detail_problem": detail_problem(verdict, facts, facts_judged),
        "candidate": None, "candidate_problem": None,
        "detail": {"missing": report.missing, "added": report.added, "names_lost": report.must_keep_missing,
                   "dialect_words": words["strong"], "ambiguous_words": words["ambiguous"]},
        "key": key,
        # The word list found a dialect word, yet the raters' verdict on the whole rewrite is `ok`.
        # One of the two is wrong, and the team has to say which (see the report).
        "list_vs_raters": dialect_left and verdict == "ok",
    }


def score_system(golden: list[dict], predictions: dict[str, dict], judgments: dict[str, dict] | None = None) -> dict:
    per_example = []
    for g in golden:
        pred = predictions.get(g["id"]) or {"id": g["id"], "output": None, "released": False, "status": "MISSING_PREDICTION"}
        per_example.append(assess(g, pred, judgments))
    n = len(per_example)
    released = [e for e in per_example if e["released"]]
    fully_judged = bool(released) and all(e["judged"] for e in released)
    errors = Counter(err for e in per_example for err in e["errors"])
    chrfs = [e["chrf"] for e in released if e["chrf"] is not None]
    facts = [f for e in released for f in e["facts"]]
    lost = [f for f in facts if f["lost"]]
    key_facts = {
        "labelled": len(facts),
        "judged": sum(1 for f in facts if f["lost"] is not None),
        "lost": len(lost),
        "lost_checker_reads": sum(1 for f in lost if f["checker_reads"]),
        "lost_outside_checker": sum(1 for f in lost if not f["checker_reads"]),
        "lost_although_found_automatically": sum(1 for f in lost if f["auto_found"]),
        "disputed": sum(1 for f in facts if f["disputed"]),
        "not_found_automatically": sum(1 for f in facts if not f["auto_found"]),
    }
    return {
        "n": n,
        "released": len(released),
        "withheld": errors.get("withheld", 0),
        "no_output": errors.get("no_output", 0),
        "repaired": sum(1 for e in per_example if e["repaired"]),
        "auto_pass": sum(1 for e in per_example if e["auto_pass"]),
        "fully_judged": fully_judged,
        "judged": sum(1 for e in released if e["judged"]),
        "verdicts_judged": sum(1 for e in released if e["verdict_judged"]),
        "facts_judged": sum(1 for e in released if e["facts_judged"]),
        "correct": sum(1 for e in per_example if e["correct"]) if fully_judged else None,
        "released_with_fact_error": sum(1 for e in released if e["fact_error"]),
        "released_with_added_fact": sum(1 for e in released if e["detail"].get("added")),
        "key_facts": key_facts,
        "list_vs_raters": sum(1 for e in released if e["list_vs_raters"]),
        "error_counts": {k: errors.get(k, 0) for k in ERROR_TYPES},
        "chrf_mean": round(sum(chrfs) / len(chrfs), 4) if chrfs else None,
        "per_example": per_example,
    }


def count_transitions(before: dict, after: dict, key: str) -> dict:
    """Examples that changed between two systems on a boolean per-example key."""
    b = {e["id"]: bool(e[key]) for e in before["per_example"]}
    a = {e["id"]: bool(e[key]) for e in after["per_example"]}
    ids = [i for i in b if i in a]
    w2r = [i for i in ids if not b[i] and a[i]]
    r2w = [i for i in ids if b[i] and not a[i]]
    return {
        "key": key,
        "wrong_to_right": len(w2r), "right_to_wrong": len(r2w),
        "stayed_right": sum(1 for i in ids if b[i] and a[i]), "stayed_wrong": sum(1 for i in ids if not b[i] and not a[i]),
        "wrong_to_right_ids": w2r, "right_to_wrong_ids": r2w,
    }


# --------------------------------------------------------------------------- #
# What the checks miss
# --------------------------------------------------------------------------- #
def score_checker(full: dict) -> dict:
    """The fact checker as a classifier, on the full system.

    Its decision is release or withhold. The truth is the raters' reading of the same rewrite
    (`detail_problem`). `released_problem` is what the checker missed, and `withheld_fine` is
    what it withheld without need. A rewrite the raters have not settled is `not_judged`."""
    cells: Counter = Counter()
    for e in full["per_example"]:
        if e["released"]:
            problem, row = e["detail_problem"], "released"
        elif "withheld" in e["errors"]:
            problem, row = e["candidate_problem"], "withheld"
        else:
            cells["no_output"] += 1
            continue
        cells[f"{row}_{'not_judged' if problem is None else 'problem' if problem else 'fine'}"] += 1
    keys = ("released_fine", "released_problem", "released_not_judged", "withheld_fine", "withheld_problem", "withheld_not_judged", "no_output")
    return {key: cells.get(key, 0) for key in keys}


def score_needs(golden: list[dict]) -> dict | None:
    """The missing-information check against the `missing` labels of the golden test.

    The check reads the message only, so the result is the same whatever model is used.
    None when the golden test carries no such labels."""
    if not any("missing" in g for g in golden):
        return None
    rows = []
    for g in golden:
        labelled = [d for d in DETAILS if d in (g.get("missing") or [])]
        rows.append({"id": g["id"], "labelled": labelled, "asked": find_missing(g["source"])})
    incomplete = [r for r in rows if r["labelled"]]
    complete = [r for r in rows if not r["labelled"]]
    return {
        "incomplete": len(incomplete), "complete": len(complete),
        "asked_on_incomplete": sum(1 for r in incomplete if r["asked"]),
        "asked_exactly": sum(1 for r in incomplete if r["asked"] == r["labelled"]),
        "needless_asks": sum(1 for r in complete if r["asked"]),
        "missed_ids": [r["id"] for r in incomplete if not r["asked"]],
        "inexact_ids": [r["id"] for r in incomplete if r["asked"] and r["asked"] != r["labelled"]],
        "needless_ids": [r["id"] for r in complete if r["asked"]],
        "per_detail": {d: {"labelled": sum(1 for r in rows if d in r["labelled"]), "asked": sum(1 for r in rows if d in r["asked"]),
                           "both": sum(1 for r in rows if d in r["labelled"] and d in r["asked"])} for d in DETAILS},
        "rows": rows,
    }


def score_guessing(golden: list[dict], scores: dict[str, dict]) -> dict:
    """On the messages labelled as lacking a needed detail, with the check switched off: how often does a
    released rewrite carry a number, date, day, place or code that is not in the message?"""
    incomplete = {g["id"] for g in golden if g.get("missing")}
    out = {}
    for system, score in scores.items():
        rows = [e for e in score["per_example"] if e["id"] in incomplete]
        released = [e for e in rows if e["released"]]
        out[system] = {
            "incomplete": len(rows), "released": len(released),
            "added_fact": sum(1 for e in released if e["detail"].get("added")),
            "added_fact_ids": [e["id"] for e in released if e["detail"].get("added")],
            "content_added": sum(1 for e in released if "content_added" in e["errors"]) if score["fully_judged"] else None,
        }
    return out


def score_deployed(needs: dict, full: dict) -> dict:
    """The system as the app runs it: the missing-information check first, then the pipeline."""
    by_id = {e["id"]: e for e in full["per_example"]}
    judged = full["fully_judged"]
    out: Counter = Counter()
    for r in needs["rows"]:
        e = by_id.get(r["id"])
        if e is None:
            continue
        if r["asked"]:
            out["asked_needlessly" if not r["labelled"] else "asked_rightly" if r["asked"] == r["labelled"] else "asked_inexactly"] += 1
        elif r["labelled"]:
            out["not_asked_although_incomplete"] += 1
        elif not e["released"]:
            out["withheld_or_no_output"] += 1
        elif not judged:
            out["released_not_judged"] += 1
        else:
            out["released_correct" if e["correct"] else "released_not_correct"] += 1
    keys = ("asked_rightly", "asked_inexactly", "asked_needlessly", "not_asked_although_incomplete", "released_correct",
            "released_not_correct", "released_not_judged", "withheld_or_no_output")
    result = {key: out.get(key, 0) for key in keys}
    result["handled_as_intended"] = result["asked_rightly"] + result["released_correct"] if judged else None
    result["n"] = sum(out.values())
    return result


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _pct(part: int | None, whole: int) -> str:
    if part is None:
        return "not judged"
    return f"{part}/{whole} ({part / whole:.1%})" if whole else "0/0"


def _golden_commit(path: str) -> str | None:
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%H %cI", "--", path], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None


def _cell(text: str | None, limit: int = 140) -> str:
    t = " ".join((text or "-").split()).replace("|", "\\|")
    return t if len(t) <= limit else t[: limit - 1] + "…"


def _key_fact_sections(scores: dict[str, dict], present: list[str], by_id: dict[str, dict]) -> list[str]:
    """Labelled key facts in released rewrites, what the checks missed, and the checker as a classifier."""
    if not any(scores[s]["key_facts"]["labelled"] for s in present):
        return []
    L = ["", "## Key facts in released rewrites", "",
         ("Every golden message lists its key facts. For each rewrite a system released, the two raters mark the facts that are "
          "lost or changed. The automatic match is a first look only: it cannot tell a fact kept in other words from a lost one."), "",
         ("| System | Released rewrites | Labelled facts in them | Lost or changed (two raters) | of these, a kind the checker reads | "
          "of these, outside what the checker reads | Raters disagree | Not found by the automatic match |"),
         "|---|---|---|---|---|---|---|---|"]
    for s in present:
        r, k = scores[s], scores[s]["key_facts"]
        if k["labelled"] and k["judged"] == k["labelled"]:
            human = [str(k["lost"]), str(k["lost_checker_reads"]), str(k["lost_outside_checker"]), str(k["disputed"])]
        elif k["judged"]:
            human = [f"{k['lost']} (partial: {k['judged']} of {k['labelled']} judged)", str(k["lost_checker_reads"]), str(k["lost_outside_checker"]), str(k["disputed"])]
        else:
            human = ["not judged"] * 4
        L.append(f"| {SYSTEM_LABELS[s]} | {r['released']} | {k['labelled']} | " + " | ".join(human) + f" | {k['not_found_automatically']} |")
    if "full" not in present:
        return L
    full = scores["full"]
    k = full["key_facts"]
    L += ["", "### What the checks missed (full system)", ""]
    lost = [(e, f) for e in full["per_example"] if e["released"] for f in e["facts"] if f["lost"]]
    if not k["judged"]:
        L.append("Not judged yet. Until the two raters fill in the `facts_lost` columns this report cannot say what the checker let through.")
    elif lost:
        L += [f"{len(lost)} labelled key fact(s) are lost or changed in rewrites the pipeline released"
              + ("" if k["judged"] == k["labelled"] else f" (so far: {k['judged']} of {k['labelled']} facts judged)") + ".", "",
              "| id | Key fact | Checker reads this kind | Found by the automatic match | Released rewrite |", "|---|---|---|---|---|"]
        for e, f in lost:
            L.append(f"| {e['id']} | {_cell(f['fact'])} | {'yes' if f['checker_reads'] else 'no'} | {'yes' if f['auto_found'] else 'no'} | {_cell(e['output'])} |")
    else:
        L.append(f"None of the {k['judged']} judged key facts in released rewrites is marked lost or changed"
                 + ("." if k["judged"] == k["labelled"] else f" ({k['labelled'] - k['judged']} not judged yet)."))
    if k["disputed"]:
        L += ["", (f"{k['disputed']} more key fact(s) were marked by one rater only. They are neither lost nor kept until the two "
                   "raters settle them in `facts_lost_final`, and the rewrites they belong to are not counted as correct.")]
    added = [e for e in full["per_example"] if e["released"] and "content_added" in e["errors"]]
    if added:
        L += ["", f"The raters marked {len(added)} released rewrite(s) `content_added`: something is in the rewrite that the message does not say.", "",
              "| id | Source | Released rewrite |", "|---|---|---|"]
        L += [f"| {e['id']} | {_cell(by_id[e['id']]['source'])} | {_cell(e['output'])} |" for e in added]
    c = score_checker(full)
    L += ["", "### The fact checker as a classifier (full system)", "",
          ("The pipeline's decision against the raters' reading of the same rewrite. A rewrite has a problem when the raters "
           "marked it `meaning_changed` or `content_added`, or marked a key fact as lost or changed. The rewrites the pipeline "
           "withheld are judged too."), "",
          "| Pipeline decision | Meaning and key facts kept | Meaning changed, content added or a key fact lost | Not settled (not judged, or the raters disagree) |",
          "|---|---|---|---|",
          f"| Released | {c['released_fine']} | {c['released_problem']} (missed by the checks) | {c['released_not_judged']} |",
          f"| Withheld | {c['withheld_fine']} (withheld without need) | {c['withheld_problem']} (rightly withheld) | {c['withheld_not_judged']} |", "",
          f"No output from the model: {c['no_output']}. A leftover dialect word is not counted in this table; it has its own row among the error types."]
    return L


def _needs_sections(meta: dict) -> list[str]:
    """The missing-information check against the golden labels, guessing with the check off, and the system as deployed."""
    needs = meta.get("needs")
    if not needs:
        return []
    L = ["", "## Missing-information check", "",
         "The check runs before the model and reads the message only, so these numbers do not depend on the model.", "",
         f"- Messages labelled as lacking a needed detail: {needs['incomplete']} of {needs['incomplete'] + needs['complete']}",
         (f"- The check asked on {_pct(needs['asked_on_incomplete'], needs['incomplete'])} of them, "
          f"and for exactly the labelled details on {_pct(needs['asked_exactly'], needs['incomplete'])}"),
         f"- Needless asks on complete messages: {_pct(needs['needless_asks'], needs['complete'])}", "",
         "| Detail | Labelled as missing | Asked for | Both |", "|---|---|---|---|"]
    L += [f"| {d} | {v['labelled']} | {v['asked']} | {v['both']} |" for d, v in needs["per_detail"].items()]
    for title, key in (("Not asked although a detail is missing", "missed_ids"), ("Asked, but not for the labelled details", "inexact_ids"),
                       ("Asked needlessly", "needless_ids")):
        if needs[key]:
            L += ["", f"{title}: " + ", ".join(needs[key])]
    guessing = meta.get("guessing")
    if guessing:
        L += ["", "### Guessing when the check is switched off", "",
              ("The same incomplete messages, rewritten without asking. A rewrite that adds a number, a date in digits, a named "
               "day or month, a listed place or a code the message does not have is counted automatically as a guess. A period "
               "given in words (\"الأسبوع القادم\") or a place outside the list is not; the raters' `content_added` covers those."), "",
              "| System | Incomplete messages | Released | Released with an added detail (automatic) | Marked `content_added` by the raters |", "|---|---|---|---|---|"]
        for s in SYSTEMS:
            if s in guessing:
                g = guessing[s]
                human = "not judged" if g["content_added"] is None else str(g["content_added"])
                L.append(f"| {SYSTEM_LABELS[s]} | {g['incomplete']} | {g['released']} | {g['added_fact']} | {human} |")
    deployed = meta.get("deployed")
    if deployed:
        d = deployed
        L += ["", "### As deployed: the check first, then the pipeline", "",
              "| Outcome | Messages |", "|---|---|",
              f"| Asked for exactly the missing details | {d['asked_rightly']} |",
              f"| Asked, but not for exactly the missing details | {d['asked_inexactly']} |",
              f"| Asked needlessly | {d['asked_needlessly']} |",
              f"| Not asked although a detail is missing | {d['not_asked_although_incomplete']} |",
              f"| Rewritten and correct | {d['released_correct'] if d['handled_as_intended'] is not None else 'not judged'} |",
              f"| Rewritten and not correct | {d['released_not_correct'] if d['handled_as_intended'] is not None else 'not judged'} |",
              f"| Withheld or no output | {d['withheld_or_no_output']} |", "",
              "Handled as intended (asked for exactly the missing details, or rewritten correctly): "
              + ("not judged" if d["handled_as_intended"] is None else _pct(d["handled_as_intended"], d["n"]))]
    return L


def render_markdown(meta: dict, scores: dict[str, dict], transitions: list[dict], golden: list[dict], max_examples: int = 3) -> str:
    by_id = {g["id"]: g for g in golden}
    present = [s for s in SYSTEMS if s in scores]
    judged = all(scores[s]["fully_judged"] for s in present)
    verdicts_done = all(scores[s]["released"] and scores[s]["verdicts_judged"] == scores[s]["released"] for s in present)
    facts_done = all(scores[s]["released"] and scores[s]["facts_judged"] == scores[s]["released"] for s in present)
    has_key_facts = any(scores[s]["key_facts"]["labelled"] for s in present)
    L: list[str] = []
    if meta.get("dry_run"):
        L += ["# DRY RUN with the mock client: these numbers are NOT results", "",
              "The mock client is a rule-based stand-in. This report only shows that the code runs end to end.", ""]
    else:
        L += ["# Evaluation on the golden test", ""]
    L += [f"- Golden test: `{meta['golden']}`, {meta['n']} examples, SHA-256 `{meta['golden_sha256'][:16]}…`",
          f"- Golden test commit: {meta.get('golden_commit') or 'not in a git repository yet'}",
          f"- Run: {meta['created_utc']}; models: " + ", ".join(f"{s} = `{meta['clients'].get(s, '?')}`" for s in present),
          "- Meaning check: " + ("judged by two members" if verdicts_done else "NOT complete.")]
    if has_key_facts:
        L.append("- Key facts: " + ("marked by two members" if facts_done else
                                    "NOT complete. Some rewrites still lack `facts_lost_a` or `facts_lost_b` (write 0 when no fact is lost)."))
    if not judged:
        L.append("- No rewrite is counted as correct until every rewrite is judged. The comparison below uses the automatic checks only, "
                 "so it is an upper bound on correctness.")
    unresolved = max((scores[s]["error_counts"]["raters_disagree"] for s in present), default=0)
    if unresolved:
        L.append(f"- Up to {unresolved} rewrite(s) per system have a rater disagreement that is not reconciled yet (`final` for the verdict, "
                 "`facts_lost_final` for the key facts). They are counted as not correct until it is.")
    if meta.get("agreement") and meta["agreement"]["judged_by_both"]:
        ag = meta["agreement"]
        L.append(f"- Rater agreement before reconciliation: {ag['agree']}/{ag['judged_by_both']} ({ag['rate']:.1%})")
        if ag.get("facts_judged_by_both"):
            L.append(f"- Rewrites where both raters marked the same key facts as lost: {ag['facts_agree']}/{ag['facts_judged_by_both']}")
    L += ["", "## Comparison", "",
          ("All systems rewrite every message here, including the messages on which the app would first ask for a missing "
           "detail. The missing-information check is scored further down, and \"As deployed\" shows what the app does."
           if meta.get("needs") else
           "All systems rewrite every message here; the app would first ask about a message that lacks a needed detail. "
           "This golden test does not label missing details, so the missing-information check is not scored."), "",
          "| System | Released | Withheld | No output | Passed automatic checks | Correct (all checks) | Released with a fact error | Repaired | chrF-style |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in present:
        r = scores[s]
        L.append(f"| {SYSTEM_LABELS[s]} | {r['released']}/{r['n']} | {r['withheld']} | {r['no_output']} | {_pct(r['auto_pass'], r['n'])} | "
                 f"{_pct(r['correct'], r['n'])} | {_pct(r['released_with_fact_error'], r['released']) if r['released'] else '0/0'} | "
                 f"{r['repaired']} | {r['chrf_mean'] if r['chrf_mean'] is not None else '-'} |")
    L += ["", "Percentages of *passed* and *correct* are over all golden examples, so a withheld message counts as not correct. "
              "*Released with a fact error* is over released messages only.", "",
          "## Error types (count of examples; one example can have several)", "",
          "| Error type | " + " | ".join(SYSTEM_LABELS[s] for s in present) + " |", "|---|" + "---|" * len(present)]
    labelled = any("key_facts" in g for g in golden)
    for err in ERROR_TYPES:
        cells = []
        for s in present:
            r = scores[s]
            done = {"meaning_changed": r["verdicts_judged"], "content_added": r["verdicts_judged"],
                    "key_fact_lost": r["facts_judged"]}.get(err, r["judged"])   # rewrites judged for this kind of error
            if err == "key_fact_lost" and not labelled:
                cells.append("not labelled")   # a golden test without key facts: 0 would read as "checked, none lost"
            elif err not in HUMAN_ERRORS or done == r["released"]:
                cells.append(str(r["error_counts"][err]))
            elif done:
                cells.append(f"{r['error_counts'][err]} (partial: {done} of {r['released']} judged)")
            else:
                cells.append("not judged")
        L.append(f"| {err} | " + " | ".join(cells) + " |")

    conflicts: dict[str, dict] = {}
    for s in present:
        for e in scores[s]["per_example"]:
            if e["list_vs_raters"]:
                conflicts.setdefault(e["key"], e)
    if conflicts:
        L += ["", "## Word list against the raters", "",
              f"In {len(conflicts)} rewrite(s) the word list found a dialect word although the raters' verdict on the rewrite is `ok`. "
              "Each one counts as `dialect_left` until the team settles it: find the row by its key in the judgment sheet, then write "
              "`yes` in `auto_dialect_wrong` if the word is fine in that sentence, or `dialect_left` in `final` if the raters missed it, "
              "and score again.", "",
              "| Key | id | Word(s) | Output |", "|---|---|---|---|"]
        for key in sorted(conflicts):
            e = conflicts[key]
            L.append(f"| `{key}` | {e['id']} | {_cell(', '.join(e['detail']['dialect_words']))} | {_cell(e['output'])} |")

    L += _key_fact_sections(scores, present, by_id)
    L += _needs_sections(meta)

    L += ["", "## Examples that changed", "",
          "With about 100 examples a small gain can be chance, so the changes are counted in both directions.", "",
          "| From → to | Measured on | Wrong → right | Right → wrong | Stayed right | Stayed wrong |", "|---|---|---|---|---|---|"]
    for t in transitions:
        L.append(f"| {SYSTEM_LABELS[t['before']]} → {SYSTEM_LABELS[t['after']]} | {t['key']} | {t['wrong_to_right']} | {t['right_to_wrong']} | {t['stayed_right']} | {t['stayed_wrong']} |")
    for t in transitions:
        for direction in ("wrong_to_right_ids", "right_to_wrong_ids"):
            if t[direction]:
                L += ["", f"{t['before']} → {t['after']}, {direction.replace('_ids', '').replace('_', ' ')}: " + ", ".join(t[direction])]

    L += ["", "## Real examples per error type", "",
          f"The first {max_examples} examples of each type in golden-test order, not picked by hand."]
    for s in present:
        L += ["", f"### {SYSTEM_LABELS[s]}"]
        any_error = False
        for err in ERROR_TYPES:
            hits = [e for e in scores[s]["per_example"] if err in e["errors"]][:max_examples]
            if not hits:
                continue
            any_error = True
            L += ["", f"**{err}**", "", "| id | Source | Output | Detail |", "|---|---|---|---|"]
            for e in hits:
                d = e["detail"]
                detail = "; ".join(filter(None, [
                    "missing " + ", ".join(f["value"] for f in d["missing"]) if d.get("missing") else "",
                    "added " + ", ".join(f["value"] for f in d["added"]) if d.get("added") else "",
                    "names lost " + ", ".join(d["names_lost"]) if d.get("names_lost") else "",
                    "dialect " + ", ".join(d["dialect_words"]) if d.get("dialect_words") else "",
                    e.get("status") or "" if not e["released"] else "",
                ]))
                L.append(f"| {e['id']} | {_cell(by_id[e['id']]['source'])} | {_cell(e['output'])} | {_cell(detail)} |")
        if not any_error:
            L += ["", "No errors of any type."]
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run_predictions(system: str, golden: list[dict], args: argparse.Namespace) -> tuple[list[dict], str]:
    if args.client == "mock":
        client = MockClient("weak" if system == "baseline" else "medium")
    elif system == "baseline":
        client = OllamaClient(args.base_model, args.host, few_shot=True)
    else:
        client = OllamaClient(args.tuned_model, args.host, few_shot=False)
    if isinstance(client, OllamaClient):
        ok, why = client.is_available()
        if not ok:
            raise LLMUnavailable(why)
    if system == "full":
        # The three systems are compared on rewriting every message, so the missing-information check is off here.
        # It is scored on its own against the golden labels (`score_needs`, `score_deployed`).
        pipeline = RewritePipeline(client, ask=False)
        return [predict_full(pipeline, g) for g in golden], client.name + "+pipeline"
    return [predict_model_only(client, g) for g in golden], client.name


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate baseline, tuned and full system on the golden test.")
    p.add_argument("--golden", required=True)
    p.add_argument("--out", default="results")
    p.add_argument("--client", choices=["ollama", "mock"], default="ollama")
    p.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    p.add_argument("--tuned-model", default=DEFAULT_TUNED_MODEL)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--systems", nargs="+", choices=SYSTEMS, default=list(SYSTEMS))
    p.add_argument("--from-predictions", help="directory with predictions_<system>.jsonl from an earlier run; no model is called")
    p.add_argument("--judgments", help="filled-in judgments CSV (two raters)")
    p.add_argument("--min-rows", type=int, default=100)
    p.add_argument("--allow-unreviewed", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="smoke test on the first N examples; the report is marked partial")
    args = p.parse_args(argv)

    golden = read_jsonl(args.golden)
    errors, _, _ = validate_rows(golden, args.min_rows, not args.allow_unreviewed)
    if errors:
        print("ERROR: the golden test does not validate. Run `python -m src.validate_golden` first.")
        for e in errors[:10]:
            print("  " + e)
        return 1
    if args.limit:
        golden = golden[: args.limit]

    out_dir = Path(args.out) / ("dryrun_mock" if args.client == "mock" and not args.from_predictions else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    golden_sha = sha256_file(args.golden)
    predictions: dict[str, dict[str, dict]] = {}
    clients: dict[str, str] = {}
    dry_run = args.client == "mock"
    if args.from_predictions:
        meta_path = Path(args.from_predictions) / "run_meta.json"
        if not meta_path.is_file():
            print(f"ERROR: {meta_path} not found; it is written next to the predictions by the run that made them")
            return 1
        saved = json.loads(meta_path.read_text(encoding="utf-8"))
        if saved.get("golden_sha256") != golden_sha:
            print("ERROR: the saved predictions were made with a different golden test file. Run the systems again.")
            return 1
        dry_run = bool(saved.get("dry_run"))
    for system in args.systems:
        if args.from_predictions:
            path = Path(args.from_predictions) / f"predictions_{system}.jsonl"
            if not path.is_file():
                print(f"ERROR: {path} not found")
                return 1
            rows = read_jsonl(path)
            clients[system] = saved.get("clients", {}).get(system, "unknown") + " (saved predictions)"
            have, want = {r.get("id") for r in rows}, {g["id"] for g in golden}
            if want - have or (have - want and not args.limit):
                print(f"ERROR: {path} does not match the golden test: {len(want - have)} id(s) missing, {len(have - want)} unknown")
                return 1
        else:
            try:
                rows, clients[system] = run_predictions(system, golden, args)
            except LLMUnavailable as exc:
                # A server problem is not a model error; stop instead of scoring it as one.
                print(f"ERROR: {system}: {exc}. Nothing was scored.")
                return 2
            write_jsonl(out_dir / f"predictions_{system}.jsonl", rows)
        predictions[system] = {r["id"]: r for r in rows}

    judgments = None
    if args.judgments:
        by_id = {g["id"]: g for g in golden}
        fact_counts = {judgment_key(pid, text, by_id[pid].get("key_facts")): len(by_id[pid].get("key_facts") or [])
                       for preds in predictions.values() for pid, pred in preds.items() if pid in by_id for text in texts_to_judge(pred)}
        try:
            judgments = load_judgments(args.judgments, fact_counts)
            if fact_counts and not set(judgments) & set(fact_counts):
                raise ValueError(f"{args.judgments}: no row matches a rewrite of this run. Is it the sheet written by the run that made "
                                 "these predictions, and for this golden test?")
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 1
    scores = {s: score_system(golden, predictions[s], judgments) for s in args.systems}
    judged = all(scores[s]["fully_judged"] for s in args.systems)
    key = "correct" if judged else "auto_pass"
    order = [s for s in SYSTEMS if s in scores]
    transitions = [{"before": a, "after": b, **count_transitions(scores[a], scores[b], key)} for a, b in zip(order, order[1:], strict=False)]

    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not args.from_predictions:
        (out_dir / "run_meta.json").write_text(json.dumps(
            {"clients": clients, "dry_run": dry_run, "golden_sha256": golden_sha, "created_utc": created}, ensure_ascii=False, indent=2), encoding="utf-8")
    template_note = "no new judgment sheet (one was given)"
    if not args.judgments:
        # Never write over a sheet that may already hold the raters' work.
        template = out_dir / "judgments_template.csv"
        if template.exists():
            template = out_dir / f"judgments_template_{created.replace(':', '').replace('+0000', 'Z')}.csv"
        n_rows = write_judgment_template(template, golden, predictions)
        template_note = f"{template.name} ({n_rows} rewrites to judge)"
    meta = {
        "golden": args.golden, "n": len(golden), "golden_sha256": golden_sha, "golden_commit": _golden_commit(args.golden),
        "created_utc": created, "clients": clients, "dry_run": dry_run, "partial": bool(args.limit),
        "agreement": rater_agreement(judgments) if judgments else None,
        "needs": score_needs(golden),
    }
    if meta["needs"]:
        meta["guessing"] = score_guessing(golden, scores)
        if "full" in scores:
            meta["deployed"] = score_deployed(meta["needs"], scores["full"])
    if "full" in scores:
        meta["checker"] = score_checker(scores["full"])
    (out_dir / "metrics.json").write_text(json.dumps({"meta": meta, "scores": scores, "transitions": transitions}, ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_markdown(meta, scores, transitions, golden)
    if args.limit:
        report = f"> PARTIAL RUN on the first {args.limit} examples. Not a result.\n\n" + report
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"wrote {out_dir / 'report.md'}, metrics.json; judgment sheet: {template_note}")
    for s in order:
        r = scores[s]
        print(f"  {s:8s} released {r['released']}/{r['n']}  auto-pass {r['auto_pass']}  correct {r['correct'] if r['correct'] is not None else 'not judged'}  "
              f"released-with-fact-error {r['released_with_fact_error']}")
    if meta["needs"]:
        needs = meta["needs"]
        print(f"  missing-information check: asked on {needs['asked_on_incomplete']}/{needs['incomplete']} incomplete messages, "
              f"needless asks {needs['needless_asks']}/{needs['complete']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
