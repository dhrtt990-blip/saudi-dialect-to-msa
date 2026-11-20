"""The golden draft that ships with the repository, the review sheet and the corpus download."""
import csv
import functools
import hashlib
import html
import http.client
import http.server
import importlib.util
import json
import threading
import zipfile
from pathlib import Path

import pytest

from src.common import read_jsonl
from src.data_prep import GoldenIndex, generate_synthetic, remove_golden_overlap, remove_shared_facts
from src.prompts import FEW_SHOT_EXAMPLES
from src.validate_golden import validate_rows

DRAFT = "data/golden_draft_ai.jsonl"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


review = load_script("golden_review")
corpus = load_script("download_corpus")


# ------------------------------ the shipped draft --------------------------- #
def test_draft_is_complete_and_passes_every_automatic_check():
    rows = read_jsonl(DRAFT)
    assert [r["id"] for r in rows] == [f"g{i:03d}" for i in range(1, 101)]
    errors, warnings, stats = validate_rows(rows, min_rows=100, require_review=False)
    assert errors == []
    assert not [w for w in warnings if "reference still contains dialect" in w]
    assert stats["share_with_facts"] >= 0.7 and stats["drafted_by"] == {"ai_assistant": 100}
    assert 5 <= sum(1 for r in rows if r.get("control")) <= 10


def test_draft_is_not_a_golden_test_until_two_members_have_signed_every_row():
    rows = read_jsonl(DRAFT)
    assert not any(k in r for r in rows for k in ("reviewed_by", "confirmed_by", "written_by", "checked_by"))
    errors, _, _ = validate_rows(rows, min_rows=100)
    assert len([e for e in errors if "two team members must be named" in e]) == 100


def test_draft_is_apart_from_the_prompt_examples_and_the_template_pairs():
    rows = read_jsonl(DRAFT)
    index = GoldenIndex(rows)
    for source, target in FEW_SHOT_EXAMPLES:
        assert index.match(source) is None and index.match(target) is None
    pairs = generate_synthetic(2000, seed=13)
    kept, removed = remove_shared_facts(pairs, rows)
    kept, collided = remove_golden_overlap(kept, index)
    assert len(collided) + len(removed) < 0.01 * len(pairs)


# -------------------------------- review sheet ------------------------------ #
def column(i):
    name, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        name = chr(65 + r) + name
    return name


def write_xlsx(path, table, inline=False):
    """A minimal workbook, written by hand so the test needs no spreadsheet library."""
    main = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    strings, sheet_rows = [], []
    for r, row in enumerate(table, 1):
        cells = []
        for c, value in enumerate(row):
            if value == "":
                continue  # an empty cell is simply absent, as in real files
            ref, text = f"{column(c)}{r}", html.escape(value, quote=False)
            if inline:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
            else:
                if value not in strings:
                    strings.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>')
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {main} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                                      '<sheets><sheet name="review" sheetId="1" r:id="rId7"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {main}><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
        if not inline:
            rich = [f"<si><r><t>{html.escape(s[:2], quote=False)}</t></r><r><t>{html.escape(s[2:], quote=False)}</t></r><rPh><t>x</t></rPh></si>" if i == 1
                    else f"<si><t>{html.escape(s, quote=False)}</t></si>" for i, s in enumerate(strings)]
            z.writestr("xl/sharedStrings.xml", f"<sst {main}>{''.join(rich)}</sst>")


def reviewed_table(tmp_path, edit=None, reviewer="نورة", confirmer="سعد"):
    """The exported sheet as the team would return it: both names filled in, optionally with an edit."""
    sheet = tmp_path / "sheet.csv"
    review.export_csv(read_jsonl(DRAFT), sheet)
    with open(sheet, encoding="utf-8-sig", newline="") as fh:
        table = list(csv.reader(fh))
    keys = [review._header_key(c) for c in table[0]]
    for row in table[1:]:
        row[keys.index("reviewed_by")], row[keys.index("confirmed_by")] = reviewer, confirmer
    if edit:
        edit(table, keys)
    return table, keys


def write_table_csv(path, table):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(table)


def run_import(tmp_path, sheet):
    out = tmp_path / "golden_test.jsonl"
    code = review.main(["import", str(sheet), "--draft", DRAFT, "--out", str(out)])
    return code, out


def test_export_has_the_review_columns(tmp_path):
    table, keys = reviewed_table(tmp_path, reviewer="", confirmer="")
    assert keys == ["id", "topic", "source", "reference", "must_keep", "reviewed_by", "confirmed_by", "notes"]
    assert len(table) == 101 and table[21][keys.index("must_keep")] == "النرجس، الياسمين"


def test_reviewed_sheet_becomes_the_golden_test(tmp_path, capsys):
    def edit(table, keys):
        table[1][keys.index("source")] = "موعدي يوم الاحد 22/11 الساعة 9:15 ما يناسبني ابد، يمدي تخلونه العصر؟"
        table[3][keys.index("notes")] = "تمت المراجعة"
        table[4][keys.index("notes")] += " راجعتها مع زميل من جدة."      # text added after the draft's own hint is the team's note

    table, _ = reviewed_table(tmp_path, edit)
    sheet = tmp_path / "reviewed.csv"
    write_table_csv(sheet, table)
    code, out = run_import(tmp_path, sheet)
    assert code == 0
    rows = read_jsonl(out)
    assert len(rows) == 100 and validate_rows(rows)[0] == []
    assert rows[0]["reviewed_by"] == "نورة" and rows[0]["confirmed_by"] == "سعد" and rows[0]["drafted_by"] == "ai_assistant"
    assert rows[20]["must_keep"] == ["النرجس", "الياسمين"] and rows[9].get("control") is True and rows[2]["notes"] == "تمت المراجعة"
    # The draft's hints to the reviewers stay in the sheet; only the team's own notes reach the golden test.
    assert sum(1 for r in read_jsonl(DRAFT) if "notes" in r) == 20 and [r["id"] for r in rows if "notes" in r] == ["g003", "g004"]
    assert rows[3]["notes"].startswith("ملاحظة المسودة") and rows[3]["notes"].endswith("راجعتها مع زميل من جدة.")
    summary = json.loads((tmp_path / "golden_test_review.json").read_text(encoding="utf-8"))
    assert summary["sources_changed"] == 1 and summary["references_changed"] == 0 and summary["rows_unchanged_from_draft"] == 99
    assert summary["changed_ids"] == ["g001"] and summary["reviewed_by"] == {"نورة": 100} and summary["golden_sha256"]


def test_unchanged_sheet_is_accepted_but_called_out(tmp_path, capsys):
    table, _ = reviewed_table(tmp_path)
    sheet = tmp_path / "reviewed.csv"
    write_table_csv(sheet, table)
    assert run_import(tmp_path, sheet)[0] == 0
    assert "no row differs from the AI draft" in capsys.readouterr().out


@pytest.mark.parametrize("reviewer,confirmer", [("نورة", ""), ("", "سعد"), ("نورة", "نورة")])
def test_sheet_without_two_different_names_writes_nothing(tmp_path, capsys, reviewer, confirmer):
    table, _ = reviewed_table(tmp_path, reviewer=reviewer, confirmer=confirmer)
    sheet = tmp_path / "reviewed.csv"
    write_table_csv(sheet, table)
    code, out = run_import(tmp_path, sheet)
    assert code == 1 and not out.exists() and "Nothing was written" in capsys.readouterr().out


def test_a_broken_fact_in_the_reviewed_sheet_is_refused(tmp_path, capsys):
    def edit(table, keys):
        table[1][keys.index("reference")] = table[1][keys.index("reference")].replace("9:15", "9:45")

    table, _ = reviewed_table(tmp_path, edit)
    sheet = tmp_path / "reviewed.csv"
    write_table_csv(sheet, table)
    code, out = run_import(tmp_path, sheet)
    assert code == 1 and not out.exists() and "g001: reference does not keep the facts" in capsys.readouterr().out


@pytest.mark.parametrize("inline", [False, True])
def test_xlsx_sheet_is_read_like_the_csv(tmp_path, inline):
    table, _ = reviewed_table(tmp_path)
    sheet = tmp_path / "reviewed.xlsx"
    write_xlsx(sheet, table, inline=inline)
    read = review.read_xlsx(sheet)
    assert read[0] == table[0] and read[1][:4] == table[1][:4]   # the header includes a rich-text cell with a phonetic run
    code, out = run_import(tmp_path, sheet)
    assert code == 0 and [r["source"] for r in read_jsonl(out)] == [r["source"] for r in read_jsonl(DRAFT)]


def test_rows_added_by_the_team_and_semicolon_csv(tmp_path):
    def edit(table, keys):
        extra = [""] * len(keys)
        for key, value in (("id", "g101"), ("source", "وين وصل طلبي 7741؟"), ("reference", "أين وصل طلبي 7741؟"),
                           ("must_keep", ""), ("reviewed_by", "نورة"), ("confirmed_by", "سعد")):
            extra[keys.index(key)] = value
        table.append(extra)
        table.append([""] * len(keys))  # a blank line at the end is ignored

    table, _ = reviewed_table(tmp_path, edit)
    sheet = tmp_path / "reviewed.csv"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter=";").writerows(table)
    code, out = run_import(tmp_path, sheet)
    rows = read_jsonl(out)
    assert code == 0 and len(rows) == 101 and rows[-1]["drafted_by"] == "team"
    assert json.loads((tmp_path / "golden_test_review.json").read_text(encoding="utf-8"))["rows_added_by_team"] == 1


def test_sheet_problems_are_explained(tmp_path, capsys):
    table, keys = reviewed_table(tmp_path)
    bad_header = tmp_path / "renamed.csv"
    write_table_csv(bad_header, [["رقم"] + table[0][1:]] + table[1:])
    assert review.main(["import", str(bad_header), "--draft", DRAFT, "--out", str(tmp_path / "o.jsonl")]) == 1
    assert "not found: id" in capsys.readouterr().out
    not_utf8 = tmp_path / "ansi.csv"
    not_utf8.write_bytes("id,source\ng001,موعد\n".encode("cp1256"))
    assert review.main(["import", str(not_utf8), "--out", str(tmp_path / "o.jsonl")]) == 1
    assert "CSV UTF-8" in capsys.readouterr().out
    assert review.main(["import", str(tmp_path / "x.ods"), "--out", str(tmp_path / "o.jsonl")]) == 1
    not_zip = tmp_path / "fake.xlsx"
    not_zip.write_text("hello", encoding="utf-8")
    assert review.main(["import", str(not_zip), "--out", str(tmp_path / "o.jsonl")]) == 1


def test_changed_header_cells_are_refused(tmp_path, capsys):
    table, keys = reviewed_table(tmp_path)
    cases = {
        # a renamed column used to lose every listed name without a word
        "renamed": (["must keep — أسماء" if key == "must_keep" else cell for cell, key in zip(table[0], keys, strict=True)], "not found: must_keep"),
        "extra": (table[0] + ["comments"], "not known: comments"),
        # a second column with a known name used to replace the real one
        "twice": (table[0] + ["reference (old draft)"], "more than once: reference"),
    }
    # a column with no name at all used to be dropped with whatever was typed in it
    nameless = tmp_path / "nameless.csv"
    write_table_csv(nameless, [table[0] + [""]] + [table[1] + ["تعليق مهم"]] + table[2:])
    code, out = run_import(tmp_path, nameless)
    assert code == 1 and not out.exists() and "row 2: a column without a name holds text" in capsys.readouterr().out
    for name, (header, message) in cases.items():
        sheet = tmp_path / f"{name}.csv"
        write_table_csv(sheet, [header] + [row + [""] * (len(header) - len(row)) for row in table[1:]])
        code, out = run_import(tmp_path, sheet)
        assert code == 1 and not out.exists() and message in capsys.readouterr().out, name


def test_cells_are_cleaned_before_they_are_used(tmp_path):
    def edit(table, keys):
        table[5][keys.index("id")] = "g005" + chr(0x200F)                              # an invisible direction mark typed into the id
        table[21][keys.index("must_keep")] = "النرجس_x000D_\nالياسمين"                 # one name per line, as Excel stores a line break
        table[1][keys.index("notes")] = chr(0x202B) + "تمت المراجعة" + chr(0x202C)

    table, _ = reviewed_table(tmp_path, edit)
    sheet = tmp_path / "reviewed.xlsx"
    write_xlsx(sheet, table)
    code, out = run_import(tmp_path, sheet)
    rows = read_jsonl(out)
    assert code == 0 and rows[4]["id"] == "g005" and rows[4]["drafted_by"] == "ai_assistant"
    assert rows[20]["must_keep"] == ["النرجس", "الياسمين"] and rows[0]["notes"] == "تمت المراجعة"
    summary = json.loads((tmp_path / "golden_test_review.json").read_text(encoding="utf-8"))
    assert summary["rows_added_by_team"] == 0 and summary["draft_rows_removed"] == 0 and summary["must_keep_changed"] == 0


def test_a_second_worksheet_is_reported(tmp_path, capsys):
    table, _ = reviewed_table(tmp_path)
    one, two = tmp_path / "one.xlsx", tmp_path / "two.xlsx"
    write_xlsx(one, table)
    with zipfile.ZipFile(one) as source, zipfile.ZipFile(two, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "xl/workbook.xml":
                data = data.replace(b"</sheets>", b'<sheet name="my copy" sheetId="2" r:id="rId8"/></sheets>')
            target.writestr(name, data)
    assert run_import(tmp_path, two)[0] == 0
    out = capsys.readouterr().out
    assert "the workbook has 2 sheets" in out and "'review'" in out and "'my copy'" in out
    assert run_import(tmp_path, one)[0] == 0 and "the workbook has" not in capsys.readouterr().out


def test_header_key_and_cell_references():
    assert review._header_key("source — الرسالة باللهجة") == "source" and review._header_key(" Reviewed_by (المراجع)") == "reviewed_by"
    assert review._header_key("source-الرسالة") == "source" and review._header_key("must_keep – أسماء") == "must_keep"
    assert [review._column_index(r) for r in ("A1", "Z9", "AA10", "AB7")] == [0, 25, 26, 27]


# ------------------------------- corpus download ---------------------------- #
@pytest.fixture
def served(tmp_path):
    """A local web server with a file laid out like the published corpus (the sentences are written for the test)."""
    folder = tmp_path / "www"
    folder.mkdir()
    with open(folder / "corpus.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Modern Standard Arabic", "Saudi Dialect", "Egyptian Dialect", "Iraqi Dialect", "Levantine Dialect", "Moroccan Dialect"])
        w.writerow(["أريد غرفة هادئة.", "- Saudi: ابغى غرفة هادية.", "", "", "", ""])
        w.writerow(["أين المحطة؟", "- Saudi: وين المحطة؟", "", "", "", ""])
    data = (folder / "corpus.csv").read_bytes()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/corpus.csv", hashlib.md5(data).hexdigest(), len(data)
    server.shutdown()


def test_download_checks_size_and_md5(tmp_path, served):
    url, md5, size = served
    dest = tmp_path / "raw" / "corpus.csv"
    assert corpus.download(url, dest, md5, size) == {"bytes": size, "md5": md5}
    with pytest.raises(ValueError, match="MD5"):
        corpus.download(url, tmp_path / "raw" / "other.csv", "0" * 32, size)
    with pytest.raises(ValueError, match="size"):
        corpus.download(url, tmp_path / "raw" / "other.csv", md5, size + 1)
    assert sorted(p.name for p in (tmp_path / "raw").iterdir()) == ["corpus.csv"]  # nothing half-downloaded is left


def test_download_cli(tmp_path, served, capsys):
    url, md5, size = served
    dest = tmp_path / "raw" / "corpus.csv"
    args = ["--url", url, "--out", str(dest), "--expected-md5", md5, "--expected-bytes", str(size)]
    assert corpus.main(args) == 0
    out = capsys.readouterr().out
    assert "Saudi Dialect" in out and "rows: 2" in out and "(removed on loading): 2" in out and "ابغى غرفة هادية.  ->  أريد غرفة هادئة." in out
    assert corpus.main(args) == 0 and "already there and matches" in capsys.readouterr().out
    assert corpus.main(args[:4] + ["--expected-md5", "0" * 32, "--expected-bytes", str(size)]) == 1
    assert "not the expected file" in capsys.readouterr().out
    assert corpus.main(["--url", url + ".missing", "--out", str(tmp_path / "raw" / "none.csv")]) == 1
    assert "by hand" in capsys.readouterr().out


def test_download_refuses_a_response_that_stops_early(tmp_path, capsys):
    body = b"Modern Standard Arabic,Saudi Dialect\n" + b"x,- Saudi: y\n" * 50

    class Cut(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body) * 3))
            self.end_headers()
            self.wfile.write(body)  # a third of what was announced, then the connection closes

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Cut)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/corpus.csv"
        dest = tmp_path / "raw" / "corpus.csv"
        with pytest.raises((ValueError, http.client.HTTPException), match="stopped early|IncompleteRead"):
            corpus.download(url, dest)  # no expected size or MD5, as with --no-verify
        assert not dest.exists() and list((tmp_path / "raw").iterdir()) == []
        assert corpus.main(["--url", url, "--out", str(dest), "--no-verify"]) == 1
        assert "by hand" in capsys.readouterr().out and not dest.exists()
    finally:
        server.shutdown()


def test_published_checksum_is_the_one_recorded():
    # Read from the Zenodo API on 2026-11-19; the dataset card quotes the same values.
    assert (corpus.EXPECTED_BYTES, corpus.EXPECTED_MD5) == (18375663, "67eea3fcb2c7671963afff33787f8dd8")
    assert corpus.URL == "https://zenodo.org/records/17776617/files/multidialectal_travel_corpus.csv?download=1"
