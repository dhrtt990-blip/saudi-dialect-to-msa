"""Fact extraction and comparison: the checker behind the pipeline.

A "fact" is a piece of the message that a rewrite must carry over unchanged:

    number   55, 1,500, 3.50, -5, 50%   (digits; Arabic-Indic digits are equal to ASCII;
                                         a percent sign is part of the number)
    time     9:30
    date     12/3/2026, 2026-03-12, 12/3
    email    name@example.com
    url      https://example.com/x
    latin    words written in Latin script (product names, codes)

The checker compares the facts of the original with the facts of the rewrite as
multisets. It is deliberately strict: when in doubt it reports a difference,
because a wrongly withheld message costs a manual rewrite, while a wrongly
released one carries a wrong appointment or amount.

Known limits (reported in the README and tested by the safety check):
  * numbers written as words ("خمسة") are not facts, so a changed number word
    is not caught; and a digit rewritten as a word is reported as dropped;
  * the order of the facts is not checked;
  * a number written with spaces ("055 123 4567") is read as three numbers, so
    joining it is reported as a change;
  * decimals are compared as written, so "3.50" rewritten as "3.5" is reported;
  * a time written with a dot ("10.30") is a number, so rewriting it as "10:30"
    is reported as a change;
  * "15%" rewritten as "15 بالمئة" is reported as a change;
  * proper names are checked only when the caller lists them in `must_keep`.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from .common import strip_marks

_EMAIL = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"
_URL = r"(?:https?://|www\.)[^\s؀-ۿ]+"
_TIME = r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)"
# Three-part dates with "/" or "-" (same separator twice); two-part dates only
# with "/", so a range such as "5-10" stays two numbers.
_DATE = r"(?<!\d)\d{1,4}(?P<dsep>[/\-])\d{1,2}(?P=dsep)\d{1,4}(?!\d)|(?<!\d)\d{1,2}/\d{1,2}(?!\d)(?!/)"
# A minus sign counts only when it starts a token ("-5"), so a range ("5-10") stays two positive numbers.
_NUMBER = (r"(?:(?<![\w\-−])[\-−])?(?:\d+(?:[,٬]\d{3})+(?:[.٫]\d+)?|\d+(?:[.٫]\d+)?)"
           r"(?:\s?[%٪])?")
_LATIN = r"[A-Za-z][A-Za-z0-9_\-']*"
_URL_TAIL = ".,;:!?)]}>\"'»”’،؛؟"

_SCANNER = re.compile(
    f"(?P<email>{_EMAIL})|(?P<url>{_URL})|(?P<time>{_TIME})|(?P<date>{_DATE})|(?P<number>{_NUMBER})|(?P<latin>{_LATIN})"
)
_KINDS = ("email", "url", "time", "date", "number", "latin")


@dataclass(frozen=True)
class Fact:
    kind: str
    value: str  # canonical form, used for comparison
    raw: str    # as written in the text

    def key(self) -> tuple[str, str]:
        return (self.kind, self.value)


def _canonical(kind: str, raw: str) -> str:
    if kind == "number":
        v = raw.replace(",", "").replace("٬", "").replace("٫", ".").replace("−", "-")
        v = v.replace("٪", "%").replace(" ", "").replace(" ", "")
        return v
    if kind == "time":
        parts = raw.split(":")
        return ":".join([str(int(parts[0]))] + parts[1:])
    if kind == "date":
        return "/".join(str(int(p)) for p in re.split(r"[/\-]", raw))
    if kind == "url":
        v = raw.rstrip(_URL_TAIL)
        m = re.match(r"((?:https?://)?[^/?#]*)(.*)", v, re.IGNORECASE | re.DOTALL)
        return m.group(1).lower() + m.group(2)  # host is case-insensitive, the path is not
    if kind == "latin":
        return raw if any(c.isdigit() for c in raw) else raw.lower()  # codes keep their case
    return raw.lower()


def extract_facts(text: str) -> list[Fact]:
    """All facts in `text`, in order of appearance."""
    clean = strip_marks(text)
    facts = []
    for m in _SCANNER.finditer(clean):
        kind = next(k for k in _KINDS if m.group(k) is not None)
        raw = m.group(0)
        if kind == "url":
            raw = raw.rstrip(_URL_TAIL)
        facts.append(Fact(kind, _canonical(kind, raw), raw.strip()))
    return facts


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #
_HAMZA = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه"})
_TOKEN = re.compile(r"[^\W_]+(?:[ً-ٰٟـ][^\W_]*)*", re.UNICODE)
_PREFIXES = ("", "و", "ف", "ب", "ل", "ك", "وب", "ول", "وك", "فب", "فل")
_FATHATAN = "ً"


def _name_words(text: str) -> list[tuple[str, bool]]:
    """Words of `text` in a light normal form, with whether each carried a fathatan.

    Hamza forms and ta marbuta are unified. Final ى and ي are NOT, so the name
    "علي" is not found in the preposition "على"."""
    words = []
    for m in _TOKEN.finditer(unicodedata.normalize("NFKC", text)):
        raw = m.group(0)
        words.append((strip_marks(raw).translate(_HAMZA).lower(), _FATHATAN in raw))
    return words


def _word_matches(word: str, tanween: bool, target: str, first: bool, last: bool) -> bool:
    candidates = {word}
    if last and tanween and word.endswith("ا"):
        candidates.add(word[:-1])  # فهداً
    for cand in candidates:
        if cand == target:
            return True
        if first:
            for prefix in _PREFIXES[1:]:
                if cand == prefix + target:
                    return True
            if target.startswith("ال") and cand in ("لل" + target[2:], "ولل" + target[2:], "فلل" + target[2:]):
                return True
    return False


def contains_name(text: str, name: str) -> bool:
    """True if `name` appears in `text` as whole words (one attached particle allowed)."""
    target = [w for w, _ in _name_words(name)]
    if not target:
        return False
    words = _name_words(text)
    n = len(target)
    for i in range(len(words) - n + 1):
        if all(_word_matches(words[i + j][0], words[i + j][1], target[j], j == 0, j == n - 1) for j in range(n)):
            return True
    return False


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
@dataclass
class FactReport:
    ok: bool
    missing: list[dict] = field(default_factory=list)       # in the original, not in the rewrite
    added: list[dict] = field(default_factory=list)         # in the rewrite, not in the original
    must_keep_missing: list[str] = field(default_factory=list)
    source_facts: int = 0

    @property
    def kind(self) -> str:
        """One label for the error analysis."""
        if self.ok:
            return "ok"
        if self.missing and self.added:
            return "changed_fact"
        if self.missing:
            return "dropped_fact"
        if self.added:
            return "added_fact"
        return "name_lost"

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "missing": self.missing,
            "added": self.added,
            "must_keep_missing": self.must_keep_missing,
            "source_facts": self.source_facts,
        }


def _as_dicts(counter: Counter, raw_by_key: dict) -> list[dict]:
    """`value` is the fact as written; `canonical` is the form that was compared."""
    out = []
    for key in sorted(counter):
        for _ in range(counter[key]):
            out.append({"kind": key[0], "value": raw_by_key.get(key, key[1]), "canonical": key[1]})
    return out


def compare_facts(source: str, rewrite: str, must_keep: tuple[str, ...] | list[str] = ()) -> FactReport:
    """Compare the facts of `source` and `rewrite`.

    `must_keep` lists strings (usually proper names) that must appear in the
    rewrite as whole words.
    """
    src, out = extract_facts(source), extract_facts(rewrite)
    src_count, out_count = Counter(f.key() for f in src), Counter(f.key() for f in out)
    src_raw = {f.key(): f.raw for f in src}
    out_raw = {f.key(): f.raw for f in out}
    missing = src_count - out_count
    added = out_count - src_count
    lost = [term for term in must_keep if term.strip() and not contains_name(rewrite, term)]
    return FactReport(
        ok=not missing and not added and not lost,
        missing=_as_dicts(missing, src_raw),
        added=_as_dicts(added, out_raw),
        must_keep_missing=lost,
        source_facts=len(src),
    )
