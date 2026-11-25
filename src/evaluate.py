"""Score three systems on the golden test and write the comparison report.

    python -m src.evaluate --golden data/golden_test.jsonl --out results

  baseline  the untuned model with its own prompt and worked examples
  tuned     the fine-tuned model alone
  full      the fine-tuned model inside the pipeline (checker, repair, withhold)

A rewrite is CORRECT only if it passes three checks:
  1. facts      every number, date, time, Latin word and listed name is kept (automatic)
  2. dialect    no listed dialect word is left (automatic word list; a reviewer can overrule it)
  3. meaning    the meaning is kept and nothing is added (two team members, judging blind)

The first run writes `judgments_template.csv`. Two members fill it in without
knowing which system wrote which line. A second run with `--judgments` adds
check 3. Until then the report shows the automatic checks only and says so.

`--client mock` runs the same code with a rule-based stand-in and writes to
`<out>/dryrun_mock`. Those numbers are not results.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .common import normalize_for_dedup, read_jsonl, sha256_file, strip_marks, write_jsonl
from .facts import compare_facts
from .lexicon import find_dialect_words
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
HUMAN_ERRORS = ("meaning_changed", "content_added", "raters_disagree")
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
def judgment_key(example_id: str, output: str) -> str:
    """Same id and exactly the same text (up to spacing) give the same key, so
    identical outputs of two systems are judged once and the judge cannot tell
    the systems apart. Outputs that differ in any character get their own row."""
    return hashlib.sha1(f"{example_id}\x00{' '.join(output.split())}".encode("utf-8")).hexdigest()[:12]


# The automatic flags are left out on purpose: they would hint at the system and prime the verdict.
JUDGMENT_COLUMNS = ["key", "source", "reference", "output", "rater_a", "rater_b", "final", "auto_dialect_wrong"]


def write_judgment_template(path: Path, golden: list[dict], predictions: dict[str, dict[str, dict]], seed: int = 13) -> int:
    by_id = {g["id"]: g for g in golden}
    rows: dict[str, dict] = {}
    for preds in predictions.values():
        for pid, pred in preds.items():
            if not pred.get("released") or not pred.get("output"):
                continue
            key = judgment_key(pid, pred["output"])
            if key in rows:
                continue
            g = by_id[pid]
            rows[key] = {
                "key": key, "source": g["source"], "reference": g["reference"], "output": pred["output"],
                "rater_a": "", "rater_b": "", "final": "", "auto_dialect_wrong": "",
            }
    ordered = [rows[k] for k in sorted(rows)]
    random.Random(seed).shuffle(ordered)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=JUDGMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)
    return len(ordered)


def load_judgments(path: str | Path) -> dict[str, dict]:
    """Read the filled-in judgment sheet. Raises ValueError on an unknown verdict."""
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), 2):
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
            out[key] = {
                "verdict": verdict, "rater_a": a, "rater_b": b,
                "auto_dialect_wrong": (row.get("auto_dialect_wrong") or "").strip().lower() in ("yes", "y", "1", "true"),
            }
    return out


def rater_agreement(judgments: dict[str, dict]) -> dict:
    both = [j for j in judgments.values() if j["rater_a"] and j["rater_b"]]
    agree = sum(1 for j in both if j["rater_a"] == j["rater_b"])
    return {"judged_by_both": len(both), "agree": agree, "rate": agree / len(both) if both else None}


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
        return {**base, "released": False, "errors": [kind], "fact_error": False, "auto_pass": False,
                "judged": True, "correct": False, "chrf": None, "output": None, "detail": {}, "key": None, "list_vs_raters": False}

    report = compare_facts(example["source"], out, example.get("must_keep", ()))
    words = find_dialect_words(out)
    key = judgment_key(example["id"], out)
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
    return {
        **base, "released": True, "errors": errors, "fact_error": not report.ok, "auto_pass": auto_pass,
        "judged": verdict is not None, "correct": auto_pass and verdict == "ok", "chrf": round(chrf(out, example["reference"]), 4),
        "output": out,
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
    return {
        "n": n,
        "released": len(released),
        "withheld": errors.get("withheld", 0),
        "no_output": errors.get("no_output", 0),
        "repaired": sum(1 for e in per_example if e["repaired"]),
        "auto_pass": sum(1 for e in per_example if e["auto_pass"]),
        "fully_judged": fully_judged,
        "judged": sum(1 for e in released if e["judged"]),
        "correct": sum(1 for e in per_example if e["correct"]) if fully_judged else None,
        "released_with_fact_error": sum(1 for e in released if e["fact_error"]),
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


def render_markdown(meta: dict, scores: dict[str, dict], transitions: list[dict], golden: list[dict], max_examples: int = 3) -> str:
    by_id = {g["id"]: g for g in golden}
    present = [s for s in SYSTEMS if s in scores]
    judged = all(scores[s]["fully_judged"] for s in present)
    L: list[str] = []
    if meta.get("dry_run"):
        L += ["# DRY RUN with the mock client: these numbers are NOT results", "",
              "The mock client is a rule-based stand-in. This report only shows that the code runs end to end.", ""]
    else:
        L += ["# Evaluation on the golden test", ""]
    L += [f"- Golden test: `{meta['golden']}`, {meta['n']} examples, SHA-256 `{meta['golden_sha256'][:16]}…`",
          f"- Golden test commit: {meta.get('golden_commit') or 'not in a git repository yet'}",
          f"- Run: {meta['created_utc']}; models: " + ", ".join(f"{s} = `{meta['clients'].get(s, '?')}`" for s in present),
          f"- Meaning check: {'judged by two members' if judged else 'NOT complete. The comparison below uses the automatic checks only, so it is an upper bound on correctness.'}"]
    unresolved = max((scores[s]["error_counts"]["raters_disagree"] for s in present), default=0)
    if unresolved:
        L.append(f"- Up to {unresolved} rewrite(s) per system have a rater disagreement that is not reconciled in the `final` column. They are counted as not correct until it is.")
    if meta.get("agreement") and meta["agreement"]["judged_by_both"]:
        ag = meta["agreement"]
        L.append(f"- Rater agreement before reconciliation: {ag['agree']}/{ag['judged_by_both']} ({ag['rate']:.1%})")
    L += ["", "## Comparison", "",
          "| System | Released | Withheld | No output | Passed automatic checks | Correct (all three checks) | Released with a fact error | Repaired | chrF-style |",
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
    for err in ERROR_TYPES:
        cells = []
        for s in present:
            r = scores[s]
            if err not in HUMAN_ERRORS or r["fully_judged"] or not r["released"]:
                cells.append(str(r["error_counts"][err]))
            elif r["judged"]:
                cells.append(f"{r['error_counts'][err]} (partial: {r['judged']} of {r['released']} judged)")
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
        pipeline = RewritePipeline(client)
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
        try:
            judgments = load_judgments(args.judgments)
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
    }
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
