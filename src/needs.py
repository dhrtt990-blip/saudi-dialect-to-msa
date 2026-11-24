"""Missing-information check: ask instead of guessing.

A customer message at the booking desk can ask for something the desk cannot do
without a detail the message does not give. The rewriter must not fill the gap,
so this check runs before the model is called and names what is missing.

    a request to book (a flight, a room, a package)      needs  the date and the destination
    a request about an existing booking (change,         needs  the booking reference
    cancel, refund, "my booking")

The formal request goes to a supplier (an airline, a hotel). For an existing
booking the booking reference is what identifies that supplier, which is why the
reference is the detail asked for; for a new booking the desk chooses the
supplier itself. The check does not ask for the departure city, the number of
travellers or their names: the desk collects those on its booking form.

The check reads words, not meaning. It is a short list of rules, and it will
miss a request worded in a way the rules do not cover (a complaint about a
service in progress, for example) and ask needlessly when a place is not in the
list of `src/gazetteer.py`. Both are counted on the golden test (`src.evaluate`,
section "Missing-information check").
"""
from __future__ import annotations

import re

from .common import strip_marks
from .facts import extract_facts
from .gazetteer import find_destinations_at, says_when, words

DETAILS = ("date", "destination", "booking_reference")
LABELS_AR = {"date": "تاريخ السفر أو الإقامة", "destination": "الوجهة", "booking_reference": "رقم الحجز"}
QUESTIONS_AR = {
    "date": "ما تاريخ السفر أو الإقامة المطلوب؟",
    "destination": "ما الوجهة أو المدينة المطلوبة؟",
    "booking_reference": "ما رقم الحجز؟",
}

# All patterns are applied to words in the normal form of `gazetteer.words` (one alef, ه for ة, no marks).
_END = r"(?:و|وا|ون|ي|ين)?"          # verb endings
_OBJ = r"(?:ه|ها|هم)?"               # attached pronoun
_BOOK = re.compile(rf"^[انتي]حجز{_END}(?:لي|لنا|له|لها|لهم|ه|ها)?$")            # احجز، تحجزون، احجزولي
_TRAVEL = re.compile(rf"^[انتي]سافر{_END}$")                                      # اسافر، نسافر
# Verbs that act on a booking the customer already has ...
_CANCEL = re.compile(rf"^(?:[انتي]لغ(?:ي|ى|و|وا|ون){_OBJ}|لغ(?:يت|ينا|و|وا){_OBJ}|[انتي]?كنسل(?:و|وا|ون|ت|نا)?{_OBJ})$")
_CHANGE = re.compile(rf"^(?:[انتي](?:غير|عدل|بدل|اجل|مدد){_END}{_OBJ}|(?:غير|عدل|بدل|اجل|مدد)(?:و|وا){_OBJ})$")
_REFUND = re.compile(rf"^[انتي]ستر(?:جع|د){_END}{_OBJ}$")                         # استرجع، تستردون
_GIVE_BACK = re.compile(rf"^(?:[تي]رجع{_END}(?:ه|ها|هم|لي)?|رجع(?:و|وا)(?:ه|ها|هم|لي)?)$")   # ترجعون، رجعوا لي
_RETURN = re.compile(rf"^[ان]رجع{_OBJ}$")                                         # "ارجع التذكرة": to hand it back
# ... and the nouns for the same acts, which also turn up in a question about a booking not made yet ("فيه الغاء مجاني؟").
_ACT_NOUN = re.compile(rf"^(?:ال)?(?:الغا[ءئ]|تغيير|تعديل|تبديل|تاجيل|تمديد|استرجاع|استرداد|ارجاع){_OBJ}$")
_MINE = re.compile(r"^(?:[بلك]|عن)?(?:حجز|تذكرت|تذاكر|رحلت)(?:ي|نا)$")            # حجزي، تذكرتنا، رحلتي
_WANT = frozenset({"ابي", "ابغى", "ابغي", "ابا", "نبي", "نبغى", "نبغي", "ودي", "ودنا", "بغيت", "بغينا", "اريد", "نريد", "ارغب", "نرغب",
                   "محتاج", "محتاجين", "احتاج", "نحتاج", "اطلب", "نطلب"})
# "ابي اعرف سعر التذكرة": a wish to know is a question, not a request to book.
_ASK = frozenset({"اعرف", "نعرف", "استفسر", "نستفسر", "اسال", "نسال", "اشوف", "نشوف", "افهم", "اتاكد", "نتاكد"})
_NEW_THING = frozenset({"حجز", "تذكره", "تذكرتين", "تذاكر", "غرفه", "غرفتين", "جناح", "فندق", "باقه", "رحله", "جوله", "سياره", "سواق", "سائق",
                        "تامين"})
_BOOKED_THING = ("حجز", "رحل", "تذكر", "تذاكر", "موعد", "تاريخ", "فندق", "غرف", "باق", "مقعد", "اقام")
_MONEY = ("فلوس", "مبلغ", "قيمه", "ريال")

# A booking reference: a code of three to twelve letters and digits that is not part of a date, a time, an amount
# with separators or an e-mail address. Whether it counts depends on the word that introduces it.
_CANDIDATE = re.compile(r"(?<![A-Za-z0-9@._/:,\-])[A-Za-z0-9]{3,12}(?![A-Za-z0-9]|[@._/:,\-][A-Za-z0-9])")
_BOOKING_WORD = re.compile(r"^(?:[وفبلك]|لل|بال|عن)?(?:(?:ال)?حجز(?:ي|نا|ه|ها|هم|كم)?|(?:ال)?مرجع\w*|(?:ال)?تاكيد\w*|رقم(?:ه|ها))$")
_OTHER_NUMBER = ("رحل", "غرف", "هوي", "جوال", "بلاغ", "مبلغ", "سعر", "دفع", "قيم", "خصم", "ريال", "فاتور", "اقام", "جواز", "ميزاني")
# "يوم 5", "5 الشهر", "شهر 7": a day or a month given as a bare number. "2 شهر" is a length of time, not a date.
_DAY_NUMBER = re.compile(r"(?:يوم|تاريخ|بتاريخ|ليوم|لتاريخ|شهر|لشهر|بشهر)\s+\d{1,2}(?!\d)|(?<!\d)\d{1,2}\s+(?:من\s+)?(?:ال|هال)شهر")


def _forms(word: str) -> tuple[str, ...]:
    """The word as typed, and without an attached "و"/"ف" and a dialect "ب"/"ح" in front of a verb."""
    out = [word]
    if word[:1] in "وف" and len(word) > 3:
        out.append(word[1:])
    for form in list(out):
        if form[:1] in "بح" and len(form) > 3:
            out.append(form[1:])
    return tuple(out)


def _first(pattern: re.Pattern, tokens: list[str]) -> int | None:
    """Position of the first word that matches, or None."""
    return next((i for i, token in enumerate(tokens) if any(pattern.match(form) for form in _forms(token))), None)


def _has(stems: tuple[str, ...], tokens: list[str]) -> bool:
    return any(stem in token for token in tokens for stem in stems)


def has_date(text: str) -> bool:
    clean = strip_marks(text)
    return any(f.kind == "date" for f in extract_facts(clean)) or says_when(clean) or bool(_DAY_NUMBER.search(clean))


def has_destination(text: str, after: int = -1) -> bool:
    """A listed place that is not introduced by "من" and comes after word number `after`
    (the booking verb: a city named before it is usually where the customer is)."""
    return any(position > after for _, position in find_destinations_at(text))


def _introduced_as(before: str) -> str | None:
    """How the last three words in front of a code introduce it: "booking", "other" (a flight, a room, an amount,
    an identity or phone number), or None when they say nothing. The nearest telling word decides."""
    for word in reversed(words(before)[-3:]):
        if _BOOKING_WORD.match(word):
            return "booking"
        if word == "ب" or any(stem in word for stem in _OTHER_NUMBER):   # "بـ 12000" is a price
            return "other"
    return None


def has_reference(text: str) -> bool:
    """True if the message gives a booking reference: a code introduced as the booking or reference number
    ("حجزي رقم 5512", "الحجز QX7T2M", "رقمها 70385"), or a code that mixes letters and digits or is six
    capital letters and is not introduced as something else. A bare number that nothing introduces is not one:
    it may be an amount or a phone number."""
    clean = strip_marks(text)
    for m in _CANDIDATE.finditer(clean):
        token = m.group(0)
        following = words(clean[m.end():])
        if token.isdigit() and following and following[0] in {"ريال", "ريالا", "دولار", "دولارا", "درهم"}:
            continue
        introduced = _introduced_as(clean[: m.start()])
        if introduced == "booking":
            return True
        looks_like_code = (len(token) >= 5 and any(c.isdigit() for c in token) and any(c.isalpha() for c in token)) or \
                          (len(token) == 6 and token.isalpha() and token.isupper())
        if introduced is None and looks_like_code:
            return True
    return False


def request_kinds(text: str) -> tuple[int | None, bool]:
    """(position of the word that asks for a new booking, or None; whether the message is about an existing booking)."""
    tokens = words(text)
    book = _first(_BOOK, tokens)
    acts = [_first(_CANCEL, tokens), _first(_REFUND, tokens)]
    if _has(_MONEY, tokens):
        acts.append(_first(_GIVE_BACK, tokens))
    if _has(_BOOKED_THING, tokens):
        acts.append(_first(_CHANGE, tokens))
    hand_back = _first(_RETURN, tokens)
    if hand_back is not None and hand_back + 1 < len(tokens) and _has(("تذكر", "تذاكر", "حجز"), tokens[hand_back + 1:hand_back + 2]):
        acts.append(hand_back)
    acts = [position for position in acts if position is not None]
    if book is not None:
        # The message asks for a new booking. A word about cancelling or changing that comes after the request is
        # usually a question about the new booking ("واذا فيه الغاء مجاني", "اقدر اغير التاريخ بعدين؟"), and "رحلتي"
        # is the trip being booked. An act is about a booking the customer already has when it is named before the
        # request, or when what it acts on is called his own ("والغي حجزي القديم", "وكنسلوا تذكرتي").
        mine = [i for i, token in enumerate(tokens) if any(_MINE.match(form) for form in _forms(token))]
        return book, any(position < book or any(i > position for i in mine) for position in acts)
    existing = bool(acts) or _first(_ACT_NOUN, tokens) is not None or _first(_MINE, tokens) is not None
    if existing:
        return None, True
    # "ابي تذكرة", "ودنا نسافر": a wish followed by the thing to book or by a travel verb. "ابي اعرف ..." is a question.
    wish = next((i for i, token in enumerate(tokens) if any(form in _WANT for form in _forms(token))), None)
    if wish is None or (wish + 1 < len(tokens) and any(form in _ASK for form in _forms(tokens[wish + 1]))):
        return None, False
    for position in range(wish + 1, len(tokens)):
        if any(form in _NEW_THING or _TRAVEL.match(form) for form in _forms(tokens[position])):
            return wish, False
    return None, False


def find_missing(text: str) -> list[str]:
    """The needed details the message does not give, in the order of DETAILS. Empty when nothing is missing."""
    new_at, existing = request_kinds(text)
    missing = []
    if new_at is not None and not has_date(text):
        missing.append("date")
    if new_at is not None and not has_destination(text, after=new_at):
        missing.append("destination")
    if existing and not has_reference(text):
        missing.append("booking_reference")
    return missing


def questions(missing: list[str]) -> list[str]:
    """The questions to put to the customer, one per missing detail."""
    return [QUESTIONS_AR[detail] for detail in missing]
