"""Download the training corpus from Zenodo and check it.

    python scripts/download_corpus.py

Record: https://zenodo.org/records/17776617
        "a Multidialectal Parallel Arabic Corpus - LLM", Khalid Almeman (see docs/DATASET_CARD.md for the licence).

The CSV (18.4 MB) is saved to data/raw/, which is git-ignored. Its size and MD5
are compared with the values Zenodo publishes for the file, and the columns the
project uses are printed. Only the Python standard library is needed.

If the download is refused or the address has changed, open the record page in
a browser, download `multidialectal_travel_corpus.csv` and put it in data/raw/.
Then run this script again: it checks the file that is already there.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_prep import CorpusFormatError, load_corpus_csv  # noqa: E402

FILENAME = "multidialectal_travel_corpus.csv"
URL = "https://zenodo.org/records/17776617/files/multidialectal_travel_corpus.csv?download=1"
# Size and checksum of this file as listed by the Zenodo API on 2026-11-19.
EXPECTED_BYTES = 18375663
EXPECTED_MD5 = "67eea3fcb2c7671963afff33787f8dd8"


def md5_file(path: str | Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_file(path: str | Path, expected_md5: str | None, expected_bytes: int | None) -> list[str]:
    """Reasons the file is not the expected one (empty list if it is)."""
    problems = []
    size = Path(path).stat().st_size
    if expected_bytes is not None and size != expected_bytes:
        problems.append(f"size is {size} bytes, expected {expected_bytes}")
    if expected_md5 is not None:
        actual = md5_file(path)
        if actual != expected_md5:
            problems.append(f"MD5 is {actual}, expected {expected_md5}")
    return problems


def download(url: str, dest: str | Path, expected_md5: str | None = None, expected_bytes: int | None = None, timeout: float = 120.0) -> dict:
    """Download `url` to `dest` through a temporary file.

    Raises ValueError if the transfer stopped early or the size or MD5 differs.
    Whatever goes wrong, the temporary file is removed and `dest` is left as it was."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "dialect2msa-course-project (python urllib)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(part, "wb") as fh:
            announced = response.headers.get("Content-Length")
            for chunk in iter(lambda: response.read(1 << 16), b""):
                fh.write(chunk)
        # A connection that closes early ends the loop without an error, so the length is checked here.
        received = part.stat().st_size
        if announced is not None and announced.strip().isdigit() and int(announced) != received:
            raise ValueError(f"the download stopped early: {received} of {int(announced)} bytes arrived")
        problems = check_file(part, expected_md5, expected_bytes)
        if problems:
            raise ValueError("the downloaded file is not the expected one: " + "; ".join(problems))
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
    return {"bytes": dest.stat().st_size, "md5": md5_file(dest)}


def describe(path: str | Path) -> dict:
    """Header, row count and the two columns the project reads."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh), [])
    pairs = load_corpus_csv(str(path))
    return {
        "header": header,
        "rows": len(pairs),
        "labels_stripped": sum(1 for p in pairs if p["label_stripped"]),
        "first_pairs": [(p["dialect"], p["msa"]) for p in pairs[:3]],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Download and check the Zenodo corpus used for training.")
    p.add_argument("--out", default=str(ROOT / "data" / "raw" / FILENAME))
    p.add_argument("--url", default=URL)
    p.add_argument("--expected-md5", default=EXPECTED_MD5)
    p.add_argument("--expected-bytes", type=int, default=EXPECTED_BYTES)
    p.add_argument("--no-verify", action="store_true", help="accept the file whatever its size and checksum")
    p.add_argument("--force", action="store_true", help="download again even if the file is already there")
    args = p.parse_args(argv)
    md5, size = (None, None) if args.no_verify else (args.expected_md5, args.expected_bytes)
    dest = Path(args.out)

    if dest.is_file() and not args.force:
        problems = check_file(dest, md5, size)
        if problems:
            print(f"ERROR: {dest} is already there but is not the expected file: {'; '.join(problems)}.")
            print("       Use --force to download it again, or --no-verify if Zenodo has published a new version.")
            return 1
        print(f"{dest} is already there" + ("" if args.no_verify else " and matches the published size and MD5") + ".")
    else:
        print(f"downloading {args.url}")
        try:
            info = download(args.url, dest, md5, size)
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as exc:
            print(f"ERROR: {exc}")
            print(f"       Download the file by hand from https://zenodo.org/records/17776617 and save it as {dest}.")
            return 1
        print(f"saved {dest}: {info['bytes']} bytes, MD5 {info['md5']}")

    try:
        info = describe(dest)
    except (CorpusFormatError, OSError, ValueError) as exc:
        print(f"ERROR: the file was saved but could not be read as the corpus: {exc}")
        return 1
    print(f"columns: {info['header']}")
    print(f"rows: {info['rows']}; dialect cells that carried a label such as '- Saudi:' (removed on loading): {info['labels_stripped']}")
    for dialect, msa in info["first_pairs"]:
        print(f"  {dialect}  ->  {msa}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
