# Reviewing and freezing golden test v3 (travel booking desk)

Do these steps in order. Nothing is trained and no model is run before step 6 is pushed: the commit date of the golden test is the proof that it was fixed before training. The training notebook refuses to start while `data/golden_test.jsonl` is still release v2.2.

## 1. Keep v2.2

```bash
git tag golden-v2.2 eb809eef46f2c9849f305478d7cd7e1c0846e91c
git push origin golden-v2.2
```

## 2. Review the 100 rows

Open `review/golden_v3_review.xlsx` in Excel or Google Sheets. Read `docs/annotation_guidelines.md` first (sections 2 to 4, and sections 8 and 9 on key facts and missing details).

- The reviewer reads the row, rewrites the message in his own dialect where it does not sound like a real customer, corrects `reference`, `key_facts`, `missing` and `must_keep`, then writes his name in `reviewed_by`.
- The confirmer reads the row again, fixes what is left and writes his name in `confirmed_by`.
- Each member writes his own name on his own rows. Nobody signs for someone else.
- Keep the header row and both label columns. The import refuses a sheet that has `key_facts` without `missing`.

The rows are in mixed order, so every 25 rows hold every kind of message. Split proposed. The team decides who takes which block, but each member reviews 25 rows and confirms 25 rows of another member: `tests/test_golden_release.py` checks this.

| Rows | Reviewer | Confirmer |
|---|---|---|
| t001 to t025 | Abdulrahman | Yasser |
| t026 to t050 | Yasser | Abdulrahman |
| t051 to t075 | Musaad | Mohammed |
| t076 to t100 | Mohammed | Musaad |

## 3. Import and validate

Start the replacement after the team reviews all rows and the instructor approves using V3 in place of the submitted evaluation set. Preserve the original release and record the approval alongside the new manifest.

Save the reviewed workbook over `review/golden_v3_review.xlsx` (one sheet, header row unchanged), then in Git Bash:

```bash
mkdir -p data/archive
git mv data/golden_test.jsonl data/archive/golden_test_v2.2.jsonl
git mv data/golden_test_review.json data/archive/golden_test_v2.2_review.json
git mv data/golden_test.sha256 data/archive/golden_test_v2.2.sha256
python scripts/golden_review.py import review/golden_v3_review.xlsx --draft data/golden_v3_draft.jsonl
python -m src.validate_golden data/golden_test.jsonl
python -c "import hashlib, pathlib; p = pathlib.Path('data/golden_test.jsonl'); pathlib.Path('data/golden_test.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest() + '  data/golden_test.jsonl\n', encoding='utf-8')"
```

The import writes nothing if a row does not validate. Fix the sheet and run it again. If it fails after the three `git mv` lines, the old files are in `data/archive/` and nothing is lost.

## 4. Update the release records

- `GOLDEN_RELEASE_MANIFEST.json`: `"release": "v3"`, `"sha256"`: the first word of `data/golden_test.sha256`, and the date. The fields about the five v2.2 changes no longer apply.
- `RELEASE_CHECKSUMS_SHA256.txt`: replace the first line with the content of `data/golden_test.sha256`.
- `SUBMISSION_MANIFEST.json`, `README.md` and `docs/DATASET_CARD.md`: the section on the golden test (what changed from the draft is in `data/golden_test_review.json`).
- A short changelog entry that names the instructor's feedback of 24 November 2026 as the reason for the new release.

## 5. Run the tests

```bash
python -m pytest -q
```

`tests/test_golden_release.py` recognises the release by the ids (`g` for v2.2, `t` for v3) and compares the golden file with `GOLDEN_RELEASE_MANIFEST.json` and `RELEASE_CHECKSUMS_SHA256.txt`. It fails until step 4 is done.

## 6. One commit, a check, then push

```bash
git add -A
git commit -m "Golden test v3: travel booking desk, key facts and missing details labelled"
python -c "import hashlib, subprocess; print(hashlib.sha256(subprocess.run(['git', 'show', 'HEAD:data/golden_test.jsonl'], capture_output=True).stdout).hexdigest())"
cat data/golden_test.sha256
```

The first line printed is the hash of the file as Git stores it; it must be the hash in `data/golden_test.sha256`. If the two differ, do not push: the file was changed after the import (an editor that re-saved it, or line ends changed on Windows). Run the import line and the checksum line of step 3 again, repeat step 4, and commit again.

```bash
git push
git log -1 --format="%H %cI" -- data/golden_test.jsonl
```

Write the commit id and date from the last line into `GOLDEN_RELEASE_MANIFEST.json` (`freeze_commit`), and the blob id that `git rev-parse HEAD:data/golden_test.jsonl` prints (`git_blob_sha`), in a second commit.

## 7. Only now

```bash
python scripts/download_corpus.py
python -m src.data_prep --golden data/golden_test.jsonl --corpus-csv data/raw/multidialectal_travel_corpus.csv --corpus-limit 8000 --synthetic-n 2000 --out data/processed
```

Read `data/processed/prep_report.json`: `overlap_remaining_after_filter` must be 0, and `dropped_from_corpus` shows how many corpus pairs were dropped for a fact mismatch. Then training in Colab.
