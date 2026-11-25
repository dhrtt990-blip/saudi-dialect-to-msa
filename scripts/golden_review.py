"""Review sheet for the golden test.

The 100 messages in data/golden_draft_ai.jsonl were drafted with an AI assistant.
They become the golden test only after one team member has corrected every row
and a second member has checked every row again. The file records both names.

    # 1. make the sheet (skip this if the team already has it)
    python scripts/golden_review.py export data/golden_draft_ai.jsonl golden_review.csv

    # 2. first member: correct `source` and `reference` where needed, then write your name in `reviewed_by`
    #    second member: read every row again, fix what is left, then write your name in `confirmed_by`

    # 3. turn the reviewed sheet (.xlsx or .csv) into the golden test and validate it
    python scripts/golden_review.py import golden_review.xlsx

Step 3 writes data/golden_test.jsonl and data/golden_test_review.json (who
reviewed, and how many rows differ from the draft). Nothing is written if the
sheet does not validate. Only the Python standard library is needed.

A sheet may carry two label columns, `key_facts` (one fact per line, worded as
in the reference) and `missing` (date, destination, booking_reference). They are
read when the sheet has them; a sheet without them imports as before. For the
travel-desk draft pass `--draft data/golden_v3_draft.jsonl`.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common import normalize_for_dedup, read_jsonl, sha256_file, write_jsonl  # noqa: E402
from src.validate_golden import validate_rows  # noqa: E402

# key, header shown in the sheet
COLUMNS = [
    ("id", "id"),
    ("topic", "topic — الموضوع"),
    ("source", "source — الرسالة باللهجة"),
    ("reference", "reference — الصياغة الفصحى"),
    ("must_keep", "must_keep — أسماء يجب أن تبقى (بينها فاصلة)"),
    ("key_facts", "key_facts — الحقائق الأساسية (كل حقيقة في سطر، كما في الفصحى)"),
    ("missing", "missing — تفصيل لازم غير موجود (date / destination / booking_reference)"),
    ("reviewed_by", "reviewed_by — المراجع"),
    ("confirmed_by", "confirmed_by — المتأكد"),
    ("notes", "notes — ملاحظات"),
]
NEEDED = ("id", "source", "reference", "must_keep", "reviewed_by", "confirmed_by")
KNOWN = tuple(key for key, _ in COLUMNS)
_NAME_SEPARATORS = re.compile(r"[،,;؛|\n\r]+")
# A key fact may hold a number with a comma ("1,500") or alternatives ("تذكرتان | تذكرتين"). A line break, a semicolon,
# an Arabic comma, or a comma followed by a space ends one.
_FACT_SEPARATORS = re.compile(r"[;؛،\n\r]+|,\s+")
_DETAIL_SEPARATORS = re.compile(r"[\s،,;؛|/]+")
_MULTILINE = ("must_keep", "key_facts", "missing")
# Invisible direction marks that a phone or a spreadsheet can leave in a cell (LRM, RLM, ALM, embeddings, isolates, BOM).
_BIDI_MARKS = re.compile("[" + "".join(chr(c) for c in (0x200E, 0x200F, 0x061C, 0xFEFF, *range(0x202A, 0x202F), *range(0x2066, 0x206A))) + "]")
# Excel writes a control character inside a cell as _xHHHH_; a line break typed in a cell is _x000D_ plus a newline.
_OOXML_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")


class SheetError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_csv(rows: list[dict], path: str | Path) -> None:
    """Write the review sheet. UTF-8 with a byte-order mark, so Excel shows Arabic correctly."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([header for _, header in COLUMNS])
        for row in rows:
            cells = dict(row, must_keep="، ".join(row.get("must_keep", [])), key_facts="\n".join(row.get("key_facts", [])),
                         missing=", ".join(row.get("missing", [])))
            writer.writerow([cells.get(key, "") for key, _ in COLUMNS])


# --------------------------------------------------------------------------- #
# Reading a sheet
# --------------------------------------------------------------------------- #
_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_P = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _column_index(ref: str) -> int:
    """Zero-based column of a cell reference: A1 -> 0, AB7 -> 27."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _string_item(node: ET.Element) -> str:
    """Text of a shared or inline string: a plain <t>, or rich-text runs. Phonetic runs are left out."""
    parts = [t.text or "" for t in node.findall(f"{_M}t")]
    for run in node.findall(f"{_M}r"):
        parts += [t.text or "" for t in run.findall(f"{_M}t")]
    return _OOXML_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), "".join(parts))


def _first_sheet(archive: zipfile.ZipFile) -> tuple[str, list[str]]:
    """Path of the first worksheet, and the names of all worksheets when the workbook lists them."""
    names = set(archive.namelist())
    titles: list[str] = []
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        listed = workbook.findall(f"{_M}sheets/{_M}sheet")
        titles = [sheet.get("name") or "" for sheet in listed]
        targets = {rel.get("Id"): rel.get("Target") for rel in rels.findall(f"{_P}Relationship")}
        target = targets[listed[0].get(f"{_R}id")]
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if path in names:
            return path, titles
    except (KeyError, IndexError, AttributeError, ET.ParseError):
        pass
    sheets = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
    if not sheets:
        raise SheetError("no worksheet found in the .xlsx file")
    return sheets[0], titles


def read_xlsx(path: str | Path, notes: list[str] | None = None) -> list[list[str]]:
    """Cell texts of the first worksheet, row by row.

    A workbook with several worksheets is read all the same; what was left unread is added to `notes`."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise SheetError(f"{path} is not an .xlsx file") from None
    with archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [_string_item(si) for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(f"{_M}si")]
        sheet_path, titles = _first_sheet(archive)
        if notes is not None and len(titles) > 1:
            notes.append(f"the workbook has {len(titles)} sheets; only the first one, '{titles[0]}', was read "
                         f"(not read: {', '.join(repr(t) for t in titles[1:])}). Check that it is the reviewed one.")
        root = ET.fromstring(archive.read(sheet_path))
        table = []
        for row in root.iter(f"{_M}row"):
            cells: dict[int, str] = {}
            for position, cell in enumerate(row.findall(f"{_M}c")):
                index = _column_index(cell.get("r")) if cell.get("r") else position
                value = cell.find(f"{_M}v")
                if cell.get("t") == "s" and value is not None and value.text is not None:
                    text = shared[int(value.text)]
                elif cell.get("t") == "inlineStr":
                    inline = cell.find(f"{_M}is")
                    text = _string_item(inline) if inline is not None else ""
                else:
                    text = value.text if value is not None and value.text is not None else ""
                cells[index] = text
            table.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        return table


def read_csv(path: str | Path) -> list[list[str]]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            return [row for row in csv.reader(fh, delimiter=delimiter)]
    except UnicodeDecodeError:
        raise SheetError(f"{path} is not saved as UTF-8. In Excel choose 'CSV UTF-8', or pass the .xlsx file instead.") from None


def read_table(path: str | Path, notes: list[str] | None = None) -> list[list[str]]:
    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx(path, notes)
    if suffix == ".csv":
        return read_csv(path)
    raise SheetError(f"{path}: expected an .xlsx or .csv file")


def _header_key(cell: str) -> str:
    """'source — الرسالة باللهجة' -> 'source'."""
    return re.split(r"[\s—–\-(:]", cell.strip(), maxsplit=1)[0].lower()


def rows_from_table(table: list[list[str]]) -> list[dict]:
    """Rows of the sheet as dictionaries keyed by the English column key."""
    numbered = [(n, row) for n, row in enumerate(table, 1) if any((cell or "").strip() for cell in row)]
    if not numbered:
        raise SheetError("the sheet is empty")
    filled = [row for _, row in numbered]
    keys = [_header_key(_BIDI_MARKS.sub("", cell or "")) for cell in filled[0]]
    absent = [k for k in NEEDED if k not in keys]
    if absent:
        raise SheetError(f"the first row must hold the column names; not found: {', '.join(absent)}. Do not rename or delete the header cells.")
    # A renamed or extra column would otherwise be dropped, or would replace the real one, without a word.
    unknown = sorted({k for k in keys if k and k not in KNOWN})
    if unknown:
        raise SheetError(f"column(s) not known: {', '.join(unknown)}. Only these are read: {', '.join(KNOWN)}. "
                         "Delete the extra column, or move its text into notes.")
    if ("key_facts" in keys) != ("missing" in keys):
        raise SheetError("the sheet has only one of the two label columns key_facts and missing. Keep both (an empty cell "
                         "means \"none\"), or delete both.")
    repeated = sorted(k for k, count in Counter(k for k in keys if k).items() if count > 1)
    if repeated:
        raise SheetError(f"column name(s) used more than once: {', '.join(repeated)}. Keep one column for each name.")
    rows = []
    for number, cells in numbered[1:]:
        for i, cell in enumerate(cells):
            if (i >= len(keys) or not keys[i]) and (cell or "").strip():
                raise SheetError(f"row {number}: a column without a name holds text ('{cell.strip()[:30]}'). "
                                 "Give the column one of the known names, or delete it.")
        row = {}
        for i, key in enumerate(keys):
            if not key:
                continue
            text = _BIDI_MARKS.sub("", cells[i] if i < len(cells) else "")
            # Line breaks separate the entries of the list columns, so they are kept there until the entries are split.
            row[key] = text.strip() if key in _MULTILINE else " ".join(text.split())
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def build_golden(sheet_rows: list[dict], draft_by_id: dict[str, dict]) -> list[dict]:
    golden = []
    for row in sheet_rows:
        rid = row.get("id", "")
        draft = draft_by_id.get(rid, {})
        item = {
            "id": rid,
            "topic": row.get("topic") or draft.get("topic", ""),
            "source": row.get("source", ""),
            "reference": row.get("reference", ""),
            "must_keep": [" ".join(name.split()) for name in _NAME_SEPARATORS.split(row.get("must_keep", "")) if name.strip()],
            "drafted_by": draft.get("drafted_by", "ai_assistant") if draft else "team",
            "reviewed_by": row.get("reviewed_by", ""),
            "confirmed_by": row.get("confirmed_by", ""),
        }
        if "key_facts" in row or "missing" in row:  # the sheet has the label columns: an empty cell is a label too
            item["key_facts"] = [" ".join(fact.split()) for fact in _FACT_SEPARATORS.split(row.get("key_facts", "")) if fact.strip()]
            item["missing"] = [detail.lower() for detail in _DETAIL_SEPARATORS.split(row.get("missing", "")) if detail]
        if item["source"] and normalize_for_dedup(item["source"]) == normalize_for_dedup(item["reference"]):
            item["control"] = True  # already formal: the right answer is the message itself
        # A hint that the draft carries for the reviewers is not the team's note: a note is kept only if the team wrote or changed it.
        note = row.get("notes", "")
        if note and " ".join(note.split()) != " ".join(str(draft.get("notes", "")).split()):
            item["notes"] = note
        golden.append(item)
    return golden


def change_summary(golden: list[dict], draft_by_id: dict[str, dict]) -> dict:
    """How the reviewed rows differ from the draft (exact text, spacing aside)."""
    def same(a: str, b: str) -> bool:
        return " ".join(a.split()) == " ".join(b.split())

    from_draft = [g for g in golden if g["id"] in draft_by_id]
    source_changed = [g["id"] for g in from_draft if not same(g["source"], draft_by_id[g["id"]]["source"])]
    reference_changed = [g["id"] for g in from_draft if not same(g["reference"], draft_by_id[g["id"]]["reference"])]
    names_changed = [g["id"] for g in from_draft if g["must_keep"] != draft_by_id[g["id"]].get("must_keep", [])]
    labels_changed = [g["id"] for g in from_draft if "key_facts" in g and (
        g["key_facts"] != draft_by_id[g["id"]].get("key_facts", []) or sorted(g["missing"]) != sorted(draft_by_id[g["id"]].get("missing", [])))]
    touched = set(source_changed) | set(reference_changed) | set(names_changed) | set(labels_changed)
    return {
        "rows": len(golden),
        "rows_from_draft": len(from_draft),
        "rows_added_by_team": len(golden) - len(from_draft),
        "draft_rows_removed": len(set(draft_by_id) - {g["id"] for g in golden}),
        "sources_changed": len(source_changed),
        "references_changed": len(reference_changed),
        "must_keep_changed": len(names_changed),
        "labels_changed": len(labels_changed),
        "rows_unchanged_from_draft": len(from_draft) - len(touched),
        "reviewed_by": dict(Counter(g["reviewed_by"] for g in golden)),
        "confirmed_by": dict(Counter(g["confirmed_by"] for g in golden)),
        "changed_ids": sorted(touched),
    }


def cmd_export(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.draft)
    export_csv(rows, args.sheet)
    print(f"wrote {args.sheet} with {len(rows)} rows. Open it in Excel or Google Sheets; keep the first row as it is.")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    notes: list[str] = []
    try:
        sheet_rows = rows_from_table(read_table(args.sheet, notes))
    except (SheetError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for note in notes:
        print(f"WARNING: {note}")
    draft_by_id = {r["id"]: r for r in read_jsonl(args.draft)} if Path(args.draft).is_file() else {}
    golden = build_golden(sheet_rows, draft_by_id)
    errors, warnings, stats = validate_rows(golden, args.min_rows, require_review=True)
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"{len(errors)} error(s). Nothing was written. Fix the sheet and run the import again.")
        return 1

    summary = change_summary(golden, draft_by_id)
    write_jsonl(args.out, golden)
    summary.update({
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sheet": Path(args.sheet).name,
        "draft_file": "data/golden_draft_ai.jsonl" if draft_by_id and Path(args.draft).resolve() == (ROOT / "data/golden_draft_ai.jsonl").resolve() else (str(args.draft) if draft_by_id else None),
        "draft_sha256": sha256_file(args.draft) if draft_by_id else None,
        "golden_file": "data/golden_test.jsonl" if Path(args.out).resolve() == (ROOT / "data/golden_test.jsonl").resolve() else str(args.out),
        "golden_sha256": sha256_file(args.out),
        "rows_with_facts": stats["rows_with_facts"],
    })
    review_path = Path(args.out).with_name(Path(args.out).stem + "_review.json")
    review_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({summary['rows']} rows) and {review_path}")
    print(f"compared with the draft: {summary['sources_changed']} source(s) and {summary['references_changed']} reference(s) changed, "
          f"{summary['rows_unchanged_from_draft']} row(s) unchanged, {summary['rows_added_by_team']} added, {summary['draft_rows_removed']} removed")
    if draft_by_id and not summary["changed_ids"] and not summary["rows_added_by_team"]:
        print("NOTE: no row differs from the AI draft. If the reviewers found nothing to correct, say so in the dataset card; "
              "otherwise check that this is the reviewed sheet.")
    print("next: git add data/golden_test.jsonl data/golden_test_review.json && git commit, before any training run")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the golden draft for review, or import the reviewed sheet.")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="draft JSONL -> review sheet (CSV)")
    exp.add_argument("draft")
    exp.add_argument("sheet")
    exp.set_defaults(run=cmd_export)
    imp = sub.add_parser("import", help="reviewed sheet (.xlsx or .csv) -> golden test JSONL")
    imp.add_argument("sheet")
    imp.add_argument("--draft", default=str(ROOT / "data" / "golden_draft_ai.jsonl"))
    imp.add_argument("--out", default=str(ROOT / "data" / "golden_test.jsonl"))
    imp.add_argument("--min-rows", type=int, default=100)
    imp.set_defaults(run=cmd_import)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
