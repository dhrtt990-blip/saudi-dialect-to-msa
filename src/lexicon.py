"""A small Saudi-dialect word list.

It has two uses:

1. `find_dialect_words` flags dialect words left in a rewrite. This is one of
   the three correctness checks in the evaluation. The list is short on
   purpose: every word in `STRONG` is rarely anything but dialect. Words that
   are also ordinary MSA words ("ابي" = "I want" or "my father") are in
   `AMBIGUOUS`; they are reported for the human reviewer and never counted
   automatically.
2. `MockClient` uses `TO_MSA` as a rule-based stand-in for the model, so the
   pipeline, the evaluation and the app can be exercised without a model.

The list is a team-maintained resource: add words as the error analysis finds
them, and record the change, because it changes the "dialect left" counts.
All keys are in the normal form produced by `common.normalize_word`.
"""
from __future__ import annotations

import re

from .common import normalize_word

# dialect word (normal form) -> an MSA rendering used only by the mock client
TO_MSA = {
    "ابغي": "أريد", "ابغا": "أريد", "نبغي": "نريد", "نبغا": "نريد", "تبغي": "تريد", "تبغا": "تريد",
    "يبغي": "يريد", "يبغا": "يريد", "يبي": "يريد", "تبي": "تريد", "تبون": "تريدون", "يبون": "يريدون",
    "وش": "ماذا", "ايش": "ماذا", "وشو": "ماذا", "ويش": "ماذا", "شنو": "ماذا", "ليش": "لماذا", "ليه": "لماذا",
    "وين": "أين", "فين": "أين", "شلون": "كيف", "مين": "من",
    "كذا": "هكذا", "كذه": "هكذا",
    "الحين": "الآن", "دحين": "الآن", "ذحين": "الآن", "ذلحين": "الآن", "للحين": "حتى الآن",
    "بكره": "غداً", "بعدين": "لاحقاً", "توني": "للتو", "توي": "للتو", "توه": "للتو",
    "عشان": "لأجل", "علشان": "لأجل",
    "مو": "ليس", "مب": "ليس", "مهو": "ليس", "مهوب": "ليس", "ماني": "لست", "مانيب": "لست",
    "مافي": "لا يوجد", "محد": "لا أحد",
    "ودي": "أود", "لسا": "ما زال", "لسه": "ما زال",
    "شوي": "قليلاً", "شويه": "قليلاً", "وايد": "كثيراً",
    "اللي": "الذي", "ايوه": "نعم", "كمان": "أيضاً", "برضو": "أيضاً", "برضه": "أيضاً", "بس": "لكن",
    "هذي": "هذه", "هذولا": "هؤلاء", "ذولا": "هؤلاء",
    "مدري": "لا أدري", "معليش": "عذراً", "ياخي": "يا أخي", "ترا": "علماً بأن",
    "شفت": "رأيت", "اشوف": "أرى", "نشوف": "نرى", "تشوف": "ترى", "يشوف": "يرى",
    "يمدي": "يمكن", "يمديني": "يمكنني", "يمديك": "يمكنك", "يمدينا": "يمكننا",
    "مويه": "ماء", "ابد": "إطلاقاً",
}
# "ابد", "كذا" and "ودي" are MSA as well ("وكذا", "مبلغ قدره كذا", "حل ودي", "حوار ودي"), so they are not markers.
STRONG = frozenset(TO_MSA) - {"ابد", "كذا", "ودي"}

# Dialect in some sentences, ordinary MSA in others. Reported, never counted.
AMBIGUOUS = frozenset({"ابي", "نبي", "زي", "مره", "خلاص", "حق", "عاد", "لين", "راح", "قاعد", "طيب", "ايه", "شي", "كذا", "ودي"})

_WORD = re.compile(r"[ء-يً-ٟـ]+")
_PROCLITICS = "وفبل"
# With one of these particles attached, the word is something else in MSA and is not looked up:
# "لبس" (to wear), "بوش" (a brand name), "لتوه" and "لتوي" (MSA "just now"), "فتوى" (a ruling),
# "ليبي" (Libyan), "بترا" (Petra).
_NO_PREFIX = {"بس": "بل", "وش": "ب", "توه": "لف", "توي": "لف", "يبي": "ل", "ترا": "ب"}
# Ordinary MSA after these words: "ذلك الحين", "بين الحين والآخر", "بين الحين والحين" (the time).
_MSA_AFTER = {"الحين": frozenset({"ذلك", "ذاك", "بين", "الحين"})}


def _bare(norm: str) -> str:
    """`norm` without one attached particle: "وبين" -> "بين"."""
    return norm[1:] if len(norm) > 2 and norm[0] in _PROCLITICS else norm


def _lookup(word: str, table) -> str | None:
    """Return the table key matched by `word`, allowing one attached particle."""
    norm = normalize_word(word)
    if norm in table:
        return norm
    if len(norm) > 2 and norm[0] in _PROCLITICS and norm[1:] in table:
        if norm[0] in _NO_PREFIX.get(norm[1:], ""):
            return None
        return norm[1:]
    return None


def find_dialect_words(text: str) -> dict:
    """Dialect words found in `text`: {"strong": [...], "ambiguous": [...]} as written."""
    strong, ambiguous = [], []
    previous = ""
    for m in _WORD.finditer(text):
        word = m.group(0)
        key = _lookup(word, STRONG)
        if key and not ({previous, _bare(previous)} & _MSA_AFTER.get(key, frozenset())):
            strong.append(word)
        elif not key and normalize_word(word) in AMBIGUOUS:
            ambiguous.append(word)
        previous = normalize_word(word)
    return {"strong": strong, "ambiguous": ambiguous}


def rule_based_rewrite(text: str, skip_every: int = 0) -> str:
    """Replace listed dialect words by their MSA rendering (mock client only).

    With `skip_every=n`, every n-th listed word is left as it is, which gives
    the weak mock something to get wrong.
    """
    seen = 0

    def repl(m: re.Match) -> str:
        nonlocal seen
        word = m.group(0)
        key = _lookup(word, TO_MSA)
        if key is None:
            return word
        seen += 1
        if skip_every and seen % skip_every == 0:
            return word
        norm = normalize_word(word)
        prefix = norm[0] if norm != key else ""
        return prefix + TO_MSA[key]

    return _WORD.sub(repl, text)
