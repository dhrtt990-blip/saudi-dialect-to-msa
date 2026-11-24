"""Shared text utilities for the dialect-to-MSA project.

Everything here is pure standard library so it runs anywhere (laptop, Colab, CI).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------- #
# Normalisation (used for comparison only, never for display)
# --------------------------------------------------------------------------- #
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
ZERO_WIDTH = "​‌‍‎‏⁠﻿؜"
_ZERO_WIDTH_RE = re.compile(f"[{ZERO_WIDTH}]")
DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_LETTER_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
     "\u06cc": "ي", "\u06a9": "ك", "\u06d5": "ه", "\u06c0": "ه", "\u06c1": "ه"})
_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def strip_marks(text: str) -> str:
    """Remove diacritics, tatweel and zero-width characters; map digits to ASCII."""
    t = unicodedata.normalize("NFKC", text)
    t = _ZERO_WIDTH_RE.sub("", t).replace(TATWEEL, "")
    t = _DIACRITICS.sub("", t)
    return t.translate(DIGIT_MAP)


def normalize_word(word: str) -> str:
    """Normal form of one Arabic word for lexicon lookup."""
    return strip_marks(word).translate(_LETTER_MAP)


def normalize_for_dedup(text: str) -> str:
    """Aggressive normalisation so trivially edited copies compare equal."""
    t = strip_marks(text).translate(_LETTER_MAP)
    t = _NON_ALNUM.sub(" ", t).replace("_", " ")
    return _WS.sub(" ", t).strip().lower()


def char_shingles(norm_text: str, n: int = 5) -> frozenset[str]:
    if len(norm_text) <= n:
        return frozenset({norm_text}) if norm_text else frozenset()
    return frozenset(norm_text[i:i + n] for i in range(len(norm_text) - n + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of character 5-grams after normalisation (1.0 if equal)."""
    na, nb = normalize_for_dedup(a), normalize_for_dedup(b)
    if na == nb:
        return 1.0
    return jaccard(char_shingles(na), char_shingles(nb))


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: line {n} is not valid JSON ({exc.msg})") from None
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Bytes, not text: on Windows a text file gets "\r\n" line ends, and the SHA-256 recorded for the golden
    # test would then differ from the file Git stores.
    with open(path, "wb") as fh:
        for row in rows:
            fh.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
