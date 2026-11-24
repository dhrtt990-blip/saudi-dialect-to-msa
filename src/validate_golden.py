"""Check the golden test before it is committed and before anything is trained.

    python -m src.validate_golden data/golden_test.jsonl

One JSON object per line:

    {"id": "g001",
     "source": "<message in Saudi dialect>",
     "reference": "<the same message in formal MSA>",
     "must_keep": ["<proper name that must survive>", ...],        (optional)
     "key_facts": ["<a key fact, worded as in the reference>", ...],   (see docs/annotation_guidelines.md)
     "missing": ["date" | "destination" | "booking_reference", ...],   (needed details the message does not give)
     "drafted_by": "ai_assistant",                                 (optional: how the row was first produced)
     "reviewed_by": "<member who corrected the row>",
     "confirmed_by": "<another member who checked it again>"}

A row the team wrote from scratch uses "written_by" and "checked_by" instead of
the last two fields. Either way two different team members stand behind every
row, and the file says who.

"key_facts" and "missing" are labels. A file either carries them on every row
or on none: once one row is labelled, a row without them is an error. An empty
list is a label ("no key fact", "nothing missing").

Errors stop the run. Warnings are printed for a person to look at.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

from .common import normalize_for_dedup, read_jsonl
from .facts import compare_facts, contains_name, extract_facts, fact_present
from .lexicon import find_dialect_words
from .needs import DETAILS

REQUIRED = ("id", "source", "reference")
REVIEW_PAIRS = (("written_by", "checked_by"), ("reviewed_by", "confirmed_by"))
# What people leave in a cell instead of a name (in the normal form of `normalize_for_dedup`).
_NOT_A_NAME = {"no_reviewer", "no reviewer", "todo", "none", "na", "n a", "yes", "no", "ok", "done", "checked", "reviewed",
               "لا يوجد", "لايوجد", "لا احد", "غير محدد", "بدون", "نعم", "لا", "تم", "تمت", "تمت المراجعه"}
# Titles in front of a name are dropped, so that "د. سارة" and "سارة" are one person.
_TITLES = {"د", "دكتور", "الدكتور", "دكتوره", "الدكتوره", "م", "مهندس", "المهندس", "مهندسه", "المهندسه",
           "ا", "استاذ", "الاستاذ", "استاذه", "الاستاذه", "dr", "eng", "mr", "mrs", "ms", "prof"}


def _cell(value) -> str:
    """A sign-off cell as text. Anything that is not text counts as empty."""
    return value.strip() if isinstance(value, str) else ""


def name_key(value: str) -> str:
    """Normal form of a member's name, or "" when the cell holds no name.

    Two spellings of one name ("أحمد" and "احمد", an extra space, an invisible
    mark) give the same key, so one person cannot sign a row twice."""
    words = normalize_for_dedup(value).split()
    while len(words) > 1 and words[0] in _TITLES:
        words.pop(0)
    key = " ".join(words)
    if key in _NOT_A_NAME or sum(ch.isalpha() for ch in key) < 2:
        return ""
    return key


def review_pair(row: dict) -> tuple[str, str, tuple[str, str]] | None:
    """The two people who stand behind a row, with the field names used.

    A pair with both fields filled wins, so a stray single field of the other pair does not hide it."""
    partial = None
    for first_field, second_field in REVIEW_PAIRS:
        first, second = _cell(row.get(first_field)), _cell(row.get(second_field))
        if first and second:
            return first, second, (first_field, second_field)
        if (first or second) and partial is None:
            partial = (first, second, (first_field, second_field))
    return partial


def validate_rows(rows: list[dict], min_rows: int = 100, require_review: bool = True) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    seen_sources: dict[str, str] = {}
    with_facts = 0
    no_marker: list[str] = []
    drafted: Counter = Counter()
    labelled: list[str] = []        # rows that carry key_facts and missing
    unlabelled: list[str] = []
    no_key_fact: list[str] = []
    uncovered: list[str] = []       # a fact the checker reads is in the reference but not in key_facts
    n_key_facts = n_incomplete = 0

    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"line {n}: not a JSON object")
            continue
        rid = str(row.get("id", f"line {n}"))
        missing = [k for k in REQUIRED if not isinstance(row.get(k), str) or not row[k].strip()]
        if missing:
            errors.append(f"{rid}: missing or empty field(s): {', '.join(missing)}")
            continue
        if rid in seen_ids:
            errors.append(f"{rid}: duplicate id")
        seen_ids.add(rid)

        norm = normalize_for_dedup(row["source"])
        if norm in seen_sources:
            errors.append(f"{rid}: same source text as {seen_sources[norm]}")
        seen_sources[norm] = rid

        must_keep = row.get("must_keep", [])
        if not isinstance(must_keep, list) or any(not isinstance(t, str) or not t.strip() for t in must_keep):
            errors.append(f"{rid}: must_keep must be a list of non-empty strings")
            must_keep = []
        for term in must_keep:
            if not contains_name(row["source"], term):
                errors.append(f"{rid}: must_keep term '{term}' does not appear in the source")

        # The reference is the correct answer, so it has to pass the same fact
        # check the systems are held to.
        report = compare_facts(row["source"], row["reference"], must_keep)
        if not report.ok:
            parts = []
            if report.missing:
                parts.append("missing " + ", ".join(f["value"] for f in report.missing))
            if report.added:
                parts.append("added " + ", ".join(f["value"] for f in report.added))
            if report.must_keep_missing:
                parts.append("name lost " + ", ".join(report.must_keep_missing))
            errors.append(f"{rid}: reference does not keep the facts of the source ({'; '.join(parts)})")
        if extract_facts(row["source"]) or must_keep:
            with_facts += 1

        if "key_facts" in row and "missing" in row:
            labelled.append(rid)
        else:
            unlabelled.append(rid)
        key_facts = row.get("key_facts", [])
        if not isinstance(key_facts, list) or any(not isinstance(t, str) or not t.strip() for t in key_facts):
            errors.append(f"{rid}: key_facts must be a list of non-empty strings")
            key_facts = []
        for fact in key_facts:
            if not fact_present(row["reference"], fact):
                errors.append(f"{rid}: key fact '{fact}' is not found in the reference; word it as the reference does")
        details = row.get("missing", [])
        if not isinstance(details, list) or any(d not in DETAILS for d in details) or len(set(details)) != len(details):
            errors.append(f"{rid}: missing must be a list drawn from: {', '.join(DETAILS)}")
            details = []
        n_key_facts += len(key_facts)
        n_incomplete += bool(details)
        if "key_facts" in row:
            if not key_facts:
                no_key_fact.append(rid)
            in_labels = {f.key() for fact in key_facts for f in extract_facts(fact)}
            names_left = [name for name in must_keep if not any(contains_name(fact, name) or contains_name(name, fact) for fact in key_facts)]
            if names_left or any(f.key() not in in_labels for f in extract_facts(row["reference"])):
                uncovered.append(rid)

        pair = review_pair(row)
        drafted[str(row.get("drafted_by") or ("team" if pair and pair[2][0] == "written_by" else "not stated"))] += 1
        if require_review:
            first_key, second_key = (name_key(pair[0]), name_key(pair[1])) if pair else ("", "")
            if not first_key or not second_key:
                errors.append(f"{rid}: two team members must be named: reviewed_by + confirmed_by (or written_by + checked_by)")
            elif first_key == second_key:
                errors.append(f"{rid}: {pair[2][1]} must be a different member from {pair[2][0]}")

        left = find_dialect_words(row["reference"])["strong"]
        if left:
            warnings.append(f"{rid}: reference still contains dialect word(s): {', '.join(left)}")
        same = normalize_for_dedup(row["reference"]) == norm
        if same and find_dialect_words(row["source"])["strong"]:
            errors.append(f"{rid}: the reference is the same as a source that contains dialect words; write the MSA version")
        if not same and not find_dialect_words(row["source"])["strong"]:
            no_marker.append(rid)

    if no_marker:
        # Dialect shows in many ways the short word list does not cover, so this is a prompt to look, not a fault.
        warnings.append(f"{len(no_marker)} source(s) contain no word from the dialect list; check they are dialect: {', '.join(no_marker)}")
    if labelled and unlabelled:
        errors.append(f"{len(unlabelled)} row(s) carry no key_facts and missing labels although other rows do: {', '.join(unlabelled)}")
    if no_key_fact:
        warnings.append(f"{len(no_key_fact)} row(s) have no key fact labelled; check that nothing in them must survive: {', '.join(no_key_fact)}")
    if uncovered:
        warnings.append(f"{len(uncovered)} row(s) have a number, date, code, day, place or listed name in the reference that is not "
                        f"in key_facts; add it or confirm it is not a key fact: {', '.join(uncovered)}")
    if len(rows) < min_rows:
        errors.append(f"only {len(rows)} rows; at least {min_rows} are required")
    share = with_facts / len(rows) if rows else 0.0
    if rows and share < 0.6:
        warnings.append(f"only {share:.0%} of the rows contain a number, date, time, Latin word or listed name; "
                        "the fact checker is tested by the rest only as 'nothing to keep'")
    stats = {"rows": len(rows), "rows_with_facts": with_facts, "share_with_facts": round(share, 3), "drafted_by": dict(drafted)}
    if labelled:
        stats.update({"key_facts": n_key_facts, "rows_missing_a_detail": n_incomplete})
    return errors, warnings, stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate the golden test file.")
    p.add_argument("path")
    p.add_argument("--min-rows", type=int, default=100)
    p.add_argument("--allow-unreviewed", action="store_true", help="skip the two-member check (draft or template only)")
    args = p.parse_args(argv)

    try:
        rows = read_jsonl(args.path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    errors, warnings, stats = validate_rows(rows, args.min_rows, not args.allow_unreviewed)
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"{stats['rows']} rows, {stats['rows_with_facts']} with facts to keep ({stats['share_with_facts']:.0%}); "
          f"first produced by: {stats['drafted_by']}; {len(errors)} error(s), {len(warnings)} warning(s)")
    if "key_facts" in stats:
        print(f"{stats['key_facts']} key facts labelled; {stats['rows_missing_a_detail']} row(s) labelled as lacking a needed detail")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
