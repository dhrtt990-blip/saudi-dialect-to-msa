"""Word lists for facts that are written in words: days, months and place names.

The fact checker compares days, months and places between a message and its rewrite.
The missing-information check uses the same lists to see whether a message
already says when and where.

The lists are short on purpose and cover a travel desk in Saudi Arabia. A word
that is not listed is simply not seen: the checker cannot notice its loss, and
the missing-information check may ask for a destination that is in the message.
Both effects are measured on the golden test and reported.
"""
from __future__ import annotations

import re
import unicodedata

from .common import strip_marks

_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه"})
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)
# One attached particle is allowed in front of a listed word (و ف ب ل ك, and "لل" for words that begin with "ال").
# A word that begins with "ال" is also read with the dialect "ها" or "ع" in front of it: "هالخميس" is
# "هذا الخميس" and "عالرياض" is "على الرياض".
_PARTICLES = "وفبلك"


def words(text: str) -> list[str]:
    """Arabic and Latin words of `text` in a light normal form (no diacritics, one alef, final ه for ة)."""
    clean = strip_marks(unicodedata.normalize("NFKC", text or ""))
    return [w.translate(_FOLD).lower() for w in _TOKEN.findall(clean)]


def _first_word_forms(word: str) -> set[str]:
    forms = {word}
    for particle in _PARTICLES:
        forms.add(particle + word)
        forms.add("و" + particle + word)
    if word.startswith("ال"):
        forms.update({"لل" + word[2:], "ولل" + word[2:], "فلل" + word[2:]})
        forms.update({prefix + "ه" + word for prefix in ("", "و", "ب", "ل")})
        forms.update({"ع" + word, "وع" + word})
    return forms


def _index(table: dict[str, tuple[str, ...]]) -> dict[tuple[str, ...], str]:
    """Every accepted spelling, with its particles, mapped to the canonical name."""
    index: dict[tuple[str, ...], str] = {}
    for canonical, variants in table.items():
        for variant in (canonical, *variants):
            parts = tuple(words(variant))
            if not parts:
                continue
            for first in _first_word_forms(parts[0]):
                index.setdefault((first, *parts[1:]), canonical)
    return index


def _find(text: str, index: dict[tuple[str, ...], str], longest: int) -> list[tuple[str, int]]:
    """(canonical name, position of its first word) for every listed name in `text`.
    The longest spelling wins, and each stretch of words is used once."""
    tokens = words(text)
    found, i = [], 0
    while i < len(tokens):
        for n in range(min(longest, len(tokens) - i), 0, -1):
            hit = index.get(tuple(tokens[i:i + n]))
            if hit:
                found.append((hit, i))
                i += n
                break
        else:
            i += 1
    return found


# --------------------------------------------------------------------------- #
# Days: weekdays and relative days. The formal spelling is the key; the tuple
# holds the spellings people type and the other formal ways to say it.
# --------------------------------------------------------------------------- #
DAYS: dict[str, tuple[str, ...]] = {
    "السبت": (),
    "الأحد": (),
    "الاثنين": ("الإثنين",),
    "الثلاثاء": ("الثلاثا", "الثلوث"),
    "الأربعاء": ("الاربعا", "الربوع"),
    "الخميس": (),
    "الجمعة": (),
    "اليوم": ("هاليوم",),
    "غداً": ("غد", "الغد", "بكره", "بكرة", "بكرا", "باكر"),
    "بعد غد": ("بعد الغد", "بعد غداً", "بعد يوم غد", "بعد بكره", "بعد بكرة", "بعد بكرا", "بعد باكر", "عقب بكره", "عقب باكر"),
    "أمس": ("الأمس", "البارح", "البارحة", "امبارح"),
    "أول أمس": ("أول من أمس", "قبل أمس", "اول البارح", "قبل البارح"),
}
# Months by name. Two are left out because the word is nearly always something else at a travel desk:
# "صفر" (zero) and "محرم" (the male relative a woman travels with).
MONTHS: dict[str, tuple[str, ...]] = {
    "يناير": (), "فبراير": (), "مارس": (), "أبريل": ("ابريل",), "مايو": (), "يونيو": (), "يوليو": (), "أغسطس": (),
    "سبتمبر": (), "أكتوبر": (), "نوفمبر": (), "ديسمبر": (),
    "ربيع الأول": (), "ربيع الآخر": ("ربيع الثاني",), "جمادى الأولى": (), "جمادى الآخرة": ("جمادى الثانية",),
    "رجب": (), "شعبان": (), "رمضان": (), "شوال": (), "ذو القعدة": ("ذي القعدة",), "ذو الحجة": ("ذي الحجة",),
}
# Other ways a message says when, without a date in digits. Used only by the missing-information check.
_WHEN_HINTS = (
    "الأسبوع الجاي", "الأسبوع القادم", "الأسبوع المقبل", "الشهر الجاي", "الشهر القادم", "الشهر المقبل",
    "نهاية الأسبوع", "نهاية الشهر", "آخر الشهر", "أول الشهر", "العيد", "الليلة",
)

# --------------------------------------------------------------------------- #
# Places: Saudi cities, then the destinations a Saudi travel desk sells most.
# Left out on purpose because the word is usually something else:
# "المغرب" (sunset) and "بالي" (my mind).
# "المدينة" alone is read as المدينة المنورة, which is what a traveller usually means by it. Where it only
# means "the city" ("وسط المدينة") it is still read, on both sides alike, so a rewrite that keeps the word passes.
# --------------------------------------------------------------------------- #
PLACES: dict[str, tuple[str, ...]] = {
    "الرياض": (), "جدة": (), "مكة": (), "المدينة المنورة": ("المدينة",), "الدمام": (), "الخبر": (), "الظهران": (),
    "الأحساء": ("الحسا", "الاحسا"), "الجبيل": (), "الطائف": ("الطايف",), "أبها": (), "خميس مشيط": (),
    "جازان": ("جيزان",), "نجران": (), "الباحة": (), "تبوك": (), "حائل": ("حايل",), "بريدة": (), "عنيزة": (),
    "القصيم": (), "ينبع": (), "العلا": (), "نيوم": (), "عرعر": (), "سكاكا": (), "حفر الباطن": (), "الخرج": (),
    "دبي": (), "أبوظبي": ("ابو ظبي",), "الشارقة": (), "الإمارات": (), "الدوحة": (), "قطر": (), "المنامة": (),
    "البحرين": (), "الكويت": (), "مسقط": (), "عمان": (), "صلالة": (), "القاهرة": (), "مصر": (), "شرم الشيخ": (),
    "الإسكندرية": (), "الأردن": (), "بيروت": (), "لبنان": (), "تونس": (), "مراكش": (), "الدار البيضاء": (),
    "إسطنبول": ("استانبول", "اسطمبول"), "تركيا": (), "طرابزون": (), "أنطاليا": (),
    "لندن": (), "بريطانيا": (), "باريس": (), "فرنسا": (), "جنيف": (), "زيورخ": (), "سويسرا": (), "ميونخ": (),
    "ألمانيا": (), "فيينا": (), "النمسا": (), "روما": (), "ميلان": ("ميلانو",), "إيطاليا": (), "مدريد": (),
    "برشلونة": (), "إسبانيا": (), "اليونان": (), "موسكو": (), "تبليسي": (), "جورجيا": (), "باكو": (),
    "أذربيجان": (), "سراييفو": (), "البوسنة": (), "كوالالمبور": (), "ماليزيا": (), "جاكرتا": (),
    "إندونيسيا": (), "بانكوك": (), "تايلند": ("تايلاند",), "المالديف": (), "سنغافورة": (), "الهند": (),
    "الفلبين": (), "سريلانكا": (), "الصين": (), "اليابان": (), "طوكيو": (), "أمريكا": (), "نيويورك": (), "كندا": (),
}

_DAY_INDEX = _index(DAYS)
_MONTH_INDEX = _index(MONTHS)
_PLACE_INDEX = _index(PLACES)
_HINT_INDEX = _index({hint: () for hint in _WHEN_HINTS})
_LONGEST = 3  # words in the longest listed spelling


# "فطور وغدا وعشا": next to a meal, "غدا" is lunch and not tomorrow.
_MEALS = frozenset({"فطور", "وفطور", "الفطور", "افطار", "وافطار", "عشا", "وعشا", "عشاء", "وعشاء", "سحور", "وجبه", "وجبات", "وجبتين"})


def find_days(text: str) -> list[str]:
    """Weekdays and relative days named in `text`, in the formal spelling ("بكره" gives "غداً")."""
    tokens = words(text)
    days = []
    for name, i in _find(text, _DAY_INDEX, _LONGEST):
        lunch = tokens[i].endswith("غدا") and (tokens[i - 1:i] + tokens[i + 1:i + 2]) and any(
            near in _MEALS for near in tokens[max(0, i - 1):i] + tokens[i + 1:i + 2])
        if not lunch:
            days.append(name)
    return days


def find_months(text: str) -> list[str]:
    """Months named in `text`, in the formal spelling."""
    return [name for name, _ in _find(text, _MONTH_INDEX, _LONGEST)]


def find_places(text: str) -> list[str]:
    """Listed places named in `text`, in the formal spelling."""
    return [name for name, _ in _find(text, _PLACE_INDEX, _LONGEST)]


def find_destinations_at(text: str) -> list[tuple[str, int]]:
    """Listed places that are not introduced by "من" (from), each with the position of its first word."""
    tokens = words(text)
    return [(name, i) for name, i in _find(text, _PLACE_INDEX, _LONGEST) if i == 0 or tokens[i - 1] != "من"]


def find_destinations(text: str) -> list[str]:
    """Listed places that are not introduced by "من" (from): the place the traveller is going to or staying in."""
    return [name for name, _ in find_destinations_at(text)]


def says_when(text: str) -> bool:
    """True if the message names a day or a period in words: a weekday, "غداً", a month, "الأسبوع القادم"."""
    return bool(_find(text, _DAY_INDEX, _LONGEST) or _find(text, _MONTH_INDEX, _LONGEST) or _find(text, _HINT_INDEX, _LONGEST))
