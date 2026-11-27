"""Build the fine-tuning data and keep it apart from the golden test.

    python scripts/download_corpus.py
    python -m src.data_prep --golden data/golden_v3_r2.jsonl \
        --corpus-csv data/raw/multidialectal_travel_corpus.csv --corpus-limit 8000 \
        --synthetic-n 2000 --out data/processed

Sources
  corpus     the multidialectal parallel corpus (Almeman 2025, Zenodo 17776617): Saudi-MSA pairs.
             Short travel sentences; almost none contains a number.
  synthetic  template pairs for a travel booking desk with numbers, dates, times, days, places,
             booking codes and names, generated here with a fixed seed. They are the only training
             pairs that teach the model to keep facts and not to add a detail the message lacks.
  team       pairs written by the team (JSONL with "dialect" and "msa")

Guarantee: no training or validation pair equals, nearly equals or contains a
golden source or reference, and none carries an e-mail address, link, code or
long number that appears in the golden test. The text check is repeated on the
final files, and the run fails if anything is left.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .common import char_shingles, normalize_for_dedup, read_jsonl, sha256_file, strip_marks, write_jsonl
from .facts import compare_facts, extract_facts
from .prompts import FEW_SHOT_EXAMPLES, build_training_example
from .validate_golden import validate_rows

MIN_CHARS, MAX_CHARS = 8, 400
MIN_CONTAINMENT_CHARS = 10


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
class CorpusFormatError(ValueError):
    pass


# Every dialect cell of the published corpus starts with a label such as "- Saudi: ".
# The labels are the ones in the corpus's own PromptsExampleAndPatterns.txt.
_LABEL = re.compile(
    r"^\s*-?\s*(?:saudi|egyptian|iraqi|levantine|shami|moroccan|السعودية|المصرية|العراقية|الشامية|المغربية"
    r"|لهجة\s+\S+|الدارجة\s+\S+)\s*:\s*",
    re.IGNORECASE,
)


def detect_columns(headers: list[str]) -> tuple[str, str]:
    """Pick the Saudi-dialect and MSA columns from the CSV header.

    The published header is: Modern Standard Arabic, Saudi Dialect, Egyptian
    Dialect, Iraqi Dialect, Levantine Dialect, Moroccan Dialect. The choice is
    made by name and fails loudly when it is not unambiguous.
    """
    def pick(needles: tuple[str, ...]) -> list[str]:
        return [h for h in headers if any(n in h.strip().lower() for n in needles)]

    dialect = pick(("saudi", "سعود"))
    msa = pick(("msa", "standard", "فصح"))
    if len(dialect) == 1 and len(msa) == 1:
        return dialect[0], msa[0]
    raise CorpusFormatError(
        "could not tell which columns hold the Saudi dialect and the MSA text. "
        f"Columns found: {headers}. Pass --dialect-col and --msa-col."
    )


def _cell(value: str | None) -> str:
    """Trim a cell and collapse runs of spaces (the corpus has both)."""
    return " ".join((value or "").split())


def load_corpus_csv(path: str, dialect_col: str | None = None, msa_col: str | None = None) -> list[dict]:
    """Read the dialect and MSA columns. `label_stripped` records whether the
    dialect cell carried a "- Saudi: " style label that was removed."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise CorpusFormatError(f"{path}: no header row")
        if dialect_col is None or msa_col is None:
            auto_d, auto_m = detect_columns(headers)
            dialect_col, msa_col = dialect_col or auto_d, msa_col or auto_m
        for col in (dialect_col, msa_col):
            if col not in headers:
                raise CorpusFormatError(f"{path}: column '{col}' not found. Columns: {headers}")
        pairs = []
        for row in reader:
            raw = _cell(row.get(dialect_col))
            dialect = _LABEL.sub("", raw, count=1)
            pairs.append({"dialect": dialect, "msa": _cell(row.get(msa_col)), "source": "corpus", "label_stripped": dialect != raw})
        return pairs


def load_team_jsonl(paths: list[str]) -> list[dict]:
    pairs = []
    for path in paths:
        for n, row in enumerate(read_jsonl(path), 1):
            if not isinstance(row.get("dialect"), str) or not isinstance(row.get("msa"), str):
                raise ValueError(f"{path}: row {n} needs string fields 'dialect' and 'msa'")
            pairs.append({"dialect": _cell(row["dialect"]), "msa": _cell(row["msa"]), "source": "team"})
    return pairs


# --------------------------------------------------------------------------- #
# Synthetic pairs with facts (every name, number and address is invented)
# --------------------------------------------------------------------------- #
# Men's first names only: the templates that take a name are written in the masculine ("الموظف", "اسمه", "وعدني").
_NAMES = ["نواف", "هشام", "طلال", "مشعل", "بدر", "تركي", "راكان", "فيصل", "ثامر", "زياد"]
_CITIES = ["الرياض", "جدة", "الدمام", "أبها", "تبوك", "حائل", "بريدة", "الطائف", "الخبر", "ينبع", "نجران", "جازان", "الأحساء"]
_ABROAD = ["دبي", "القاهرة", "إسطنبول", "الدوحة", "المنامة", "الكويت", "مسقط", "كوالالمبور", "جاكرتا", "بانكوك", "لندن", "باريس",
           "تبليسي", "باكو", "المالديف"]
_VISA_PLACES = ["لندن", "باريس", "روما", "مدريد", "ميونخ", "فيينا", "جنيف"]   # places a traveller from the Gulf asks a visa for
_PACKAGE_PRICES = [2900, 3750, 4800, 6400, 7600, 9800, 12000, 15000]
# (as typed in dialect, formal spelling). The fact checker reads both spellings as the same day.
_WEEKDAYS = [("السبت", "السبت"), ("الاحد", "الأحد"), ("الاثنين", "الاثنين"), ("الثلوث", "الثلاثاء"), ("الثلاثاء", "الثلاثاء"),
             ("الربوع", "الأربعاء"), ("الاربعاء", "الأربعاء"), ("الخميس", "الخميس"), ("الجمعة", "الجمعة")]
_RELATIVE_DAYS = [("بكره", "غداً"), ("بعد بكره", "بعد غد"), ("اليوم", "اليوم")]
_PAYMENT = ["Mada", "Apple Pay", "STC Pay"]            # ways to pay
_MAILBOXES = ["support", "info", "billing", "tickets", "service", "help", "sales", "travel"]
_ARABIC_INDIC = str.maketrans("0123456789,%", "٠١٢٣٤٥٦٧٨٩٬٪")   # with the Arabic thousands separator and percent sign
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")
_HAS_LATIN = re.compile(r"[A-Za-z]")

# (dialect template, MSA template) for a travel booking desk. Both sides carry exactly the same slots.
# {lcity} and {ldest} are the place with "ل" attached, as it is typed ("لجدة", "للرياض").
# The last group asks for something without giving a needed detail: the MSA side adds none.
_TEMPLATES = [
    ("ودي اسافر {lcity} يوم {day_d} {d}، فيه مقاعد على رحلة {t}؟", "أود السفر إلى {city} يوم {day_m} {d}، فهل توجد مقاعد على رحلة الساعة {t}؟"),
    ("دبروا لنا {n} مقاعد على رحلة {day_d} من {city} {lcity2}", "وفّروا لنا {n} مقاعد على رحلة {day_m} من {city} إلى {city2}."),
    ("وش صار على الحجز {pnr}؟ دفعت {sar} ريال من {n} ايام وما جاني تأكيد", "ماذا حدث للحجز {pnr}؟ دفعتُ {sar} {riyal} منذ {n} أيام ولم يصلني تأكيد."),
    ("الحين انا في {city} وابي أأجل رجعتي لين {d}، رقم الحجز {ref}", "أنا الآن في {city} وأريد تأجيل عودتي إلى {d}، ورقم الحجز {ref}."),
    ("ليش الفاتورة {sar2} والسعر اللي قلتوه {sar}؟ الحجز {ref}", "لماذا الفاتورة {sar2} والسعر الذي ذكرتموه {sar}؟ رقم الحجز {ref}."),
    ("ودي اكلم الموظف {name} بخصوص الحجز {ref}", "أود التحدث مع الموظف {name} بخصوص الحجز {ref}."),
    ("وين استلم السيارة اللي حجزتها في {city}؟ رقم الحجز {ref}", "أين أستلم السيارة التي حجزتها في {city}؟ رقم الحجز {ref}."),
    ("مو معقول ننتظر {n} ساعات في المطار والرحلة كانت {t}", "ليس معقولاً أن ننتظر {n} ساعات في المطار والرحلة كانت الساعة {t}."),
    ("الرحلة انلغت من عندكم، عشان كذا ابغى ترجعون لي {sar} ريال قبل {d}، الحجز {pnr}", "أُلغيت الرحلة من جهتكم، لذلك أريد أن تعيدوا إليّ {sar} {riyal} قبل {d}، رقم الحجز {pnr}."),
    ("اللي كلمني اسمه {name} وقال الرحلة {rel_d} الساعة {t}", "الذي حدثني اسمه {name}، وقال إن الرحلة {rel_m} الساعة {t}."),
    ("لسا ما وصلتني التذاكر على {email} من {n} ايام", "لم تصلني التذاكر على {email} منذ {n} أيام."),
    ("يرجى تأكيد الحجز قبل {d} الساعة {t}.", "يرجى تأكيد الحجز قبل {d} الساعة {t}."),
    ("ابي اعرف كم باقي علي في الحجز {ref}، دفعت {sar} من اصل {sar2}", "أريد أن أعرف كم بقي عليّ في الحجز {ref}، فقد دفعتُ {sar} من أصل {sar2}."),
    ("ارسلوا لي تأكيد الحجز على {email} قبل {d}", "أرسلوا إليّ تأكيد الحجز على {email} قبل {d}."),
    ("سجلوا عندكم رقم الحجز {pnr} عشان ما اضطر اعيده كل مره", "سجّلوا لديكم رقم الحجز {pnr} حتى لا أضطر إلى إعادته في كل مرة."),
    ("متى يجي الباص؟ قالوا بين {t} و {t2} وما جا احد", "متى تأتي الحافلة؟ قالوا بين {t} و {t2} ولم يأتِ أحد."),
    ("سجلت في الرحلة اللي تطلع {d} ودفعت {sar} ريال، متى توصلني التذاكر؟", "سجّلتُ في الرحلة التي تنطلق في {d} ودفعتُ {sar} {riyal}، فمتى تصلني التذاكر؟"),
    ("الفندق في {dest} بعيد عن المطار {n} كيلو ولا اكثر؟", "هل يبعد الفندق في {dest} عن المطار {n} كيلومترات أم أكثر؟"),
    ("المسافر {name} ينتظر عند البوابة من الساعة {t} ومحد استقبله", "المسافر {name} ينتظر عند البوابة منذ الساعة {t} ولم يستقبله أحد."),
    ("ابغى ادفع {sar} ريال الحين والباقي {sar2} قبل السفر", "أريد أن أدفع {sar} {riyal} الآن والباقي {sar2} قبل السفر."),
    ("مكتبكم في {city} يقفل الساعة {t} ولا {t2}؟", "هل يغلق مكتبكم في {city} الساعة {t} أم {t2}؟"),
    ("الحجز فيه {n} مسافرين وحنا {n2} بس", "في الحجز {n} مسافرين ونحن {n2} فقط."),
    ("رقم الحجز {pnr} وتاريخ السفر {d}، ابي اعرف هل تأكد ولا لا", "رقم الحجز {pnr} وتاريخ السفر {d}، وأريد أن أعرف هل أُكِّد الحجز أم لا."),
    ("الخصم مكتوب {pct} وانتم حسبتوه {pct2}", "الخصم المكتوب {pct} وأنتم حسبتموه {pct2}."),
    ("كلمت {name} يوم {d} ووعدني يرسل العرض خلال {n} ايام وللحين ما ارسل", "تحدثتُ مع {name} يوم {d} ووعدني بإرسال العرض خلال {n} أيام ولم يرسله حتى الآن."),
    ("نفيدكم بأن موعد الرحلة إلى {city} هو {d} الساعة {t}.", "نفيدكم بأن موعد الرحلة إلى {city} هو {d} الساعة {t}."),
    ("الرابط اللي ارسلتوه للدفع ما يفتح، ارسلوه مره ثانيه على {email}", "رابط الدفع الذي أرسلتموه لا يفتح، فأرسلوه مرة أخرى على {email}."),
    ("السعر في العرض {sar} وفي الفاتورة {sar2}، ايهم الصح؟", "السعر في العرض {sar} وفي الفاتورة {sar2}، فأيهما الصحيح؟"),
    ("لي {n} شهور اطالب بتعويض الرحلة الملغية ومحد عطاني وجه، رقمها {ref}", "منذ {n} أشهر وأنا أطالب بتعويض الرحلة الملغاة ولم يهتم بي أحد، ورقمها {ref}."),
    ("ابغى انقل حجزي {ref} من {city} الى {city2} بنفس التاريخ {d}", "أريد نقل حجزي {ref} من {city} إلى {city2} في التاريخ نفسه {d}."),
    ("نبي {n} غرف في {dest} من {d} لمدة {n2} ليالي", "نريد {n} غرف في {dest} من {d} لمدة {n2} ليالٍ."),
    ("فيه رحلة {ldest} {rel_d} بعد الساعة {t}؟", "هل توجد رحلة إلى {dest} {rel_m} بعد الساعة {t}؟"),
    ("الرحلة من {city} {ldest} تأخرت {n} ساعات، وش التعويض؟", "تأخرت الرحلة من {city} إلى {dest} {n} ساعات، فما التعويض؟"),
    ("دفعت {sar} ريال من {pay} وما وصلني تأكيد الحجز", "دفعتُ {sar} {riyal} عن طريق {pay} ولم يصلني تأكيد الحجز."),
    ("جوازي ينتهي {d}، يمديني اسافر {ldest} ولا لازم اجدده؟", "ينتهي جواز سفري في {d}، فهل يمكنني السفر إلى {dest} أم يجب أن أجدده؟"),
    ("حجزنا {n} تذاكر والنظام طلع {n2} بس، الحجز {pnr}", "حجزنا {n} تذاكر وأظهر النظام {n2} فقط، رقم الحجز {pnr}."),
    ("التأشيرة حقت {visa} تاخذ {n} ايام ولا اكثر؟", "هل تستغرق تأشيرة {visa} {n} أيام أم أكثر؟"),
    ("الباقة حقت {dest} بـ {big2} ريال وانا شفتها في موقعكم بـ {big}", "سعر باقة {dest} {big2} {riyal_big2}، وقد رأيتها في موقعكم بـ {big}."),
    # A needed detail is not given, and the MSA side does not supply it.
    ("ودنا نسافر {ldest} بس ما حددنا متى، وش تنصحونا؟", "نود السفر إلى {dest} لكننا لم نحدد الموعد، فبماذا تنصحوننا؟"),
    ("ابي اطلع رحلة يوم {day_d} بس ما قررت وين", "أريد السفر في رحلة يوم {day_m} لكنني لم أقرر الوجهة."),
    ("ابغى اكنسل رحلة {dest} وماني حافظ رقم الحجز", "أريد إلغاء رحلة {dest} ولا أحفظ رقم الحجز."),
    ("نبي فندق لـ {n} اشخاص، وما عندنا مكان محدد ولا تاريخ", "نريد فندقاً لـ {n} أشخاص، وليس لدينا مكان محدد ولا تاريخ."),
    ("ابغى اعدل اسم المسافر {name} ورقم الحجز مو عندي الحين", "أريد تعديل اسم المسافر {name} ورقم الحجز ليس معي الآن."),
]


def _amount(rng: random.Random) -> str:
    kind = rng.random()
    if kind < 0.45:
        return str(rng.choice([35, 50, 75, 120, 180, 250, 399, 640, 875, 980]))
    if kind < 0.85:
        value = rng.choice([1200, 1450, 2500, 3750, 4800, 7600, 12000, 15000, 23500])
        return f"{value:,}" if rng.random() < 0.6 else str(value)
    return f"{rng.randint(20, 900)}.{rng.choice(['50', '75', '25', '99'])}"


def _date(rng: random.Random, formal: bool = False) -> str:
    """A date as people type it. The year-first form is kept for the messages that are already formal:
    nobody types it in a chat."""
    day, month, kind = rng.randint(1, 28), rng.randint(1, 12), rng.random()
    if kind < 0.55:
        return f"{day}/{month}"
    if kind < 0.9 or not formal:
        return f"{day}/{month}/{rng.choice([2026, 2027])}"
    return f"{rng.choice([2026, 2027])}-{month:02d}-{day:02d}"


_MINUTES = ["00", "05", "10", "15", "20", "30", "40", "45", "50"]


def _time(rng: random.Random) -> str:
    return f"{rng.randint(1, 12)}:{rng.choice(_MINUTES)}"


def _later(rng: random.Random, clock: str) -> str:
    """A time one to four hours after `clock` on a 12-hour dial, so that a window reads in order ("11:10", then "1:40")."""
    hour = (int(clock.split(":")[0]) - 1 + rng.randint(1, 4)) % 12 + 1
    return f"{hour}:{rng.choice(_MINUTES)}"


def _pnr(rng: random.Random) -> str:
    """A six-character booking code with at least one letter and one digit, such as "QX7T2M"."""
    while True:
        code = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        if any(ch.isdigit() for ch in code) and any(ch.isalpha() for ch in code):
            return code


def _to(place: str) -> str:
    """The place with "ل" attached, as it is typed: "لجدة", "للرياض"."""
    return "لل" + place[2:] if place.startswith("ال") else "ل" + place


def _value(number: str) -> float:
    return float(number.replace(",", "").rstrip("%"))


def _two(rng: random.Random, make, key=str) -> tuple[str, str]:
    """Two values from the same maker that differ under `key` ("2500" and "2,500" are one amount)."""
    first = make(rng)
    second = make(rng)
    while key(second) == key(first):
        second = make(rng)
    return first, second


def _riyal(amount: str) -> str:
    """The MSA form of "ريال" after an amount in digits: 3 to 10 ريالات, 11 to 99 ريالاً, and
    ريال after whole hundreds and thousands. The rule follows the last two digits. An amount with
    a decimal part takes the plain form."""
    if "." in amount:
        return "ريال"
    last_two = int(amount.replace(",", "")) % 100
    if 3 <= last_two <= 10:
        return "ريالات"
    if 11 <= last_two <= 99:
        return "ريالاً"
    return "ريال"


def generate_synthetic(n: int, seed: int) -> list[dict]:
    """`n` template pairs carrying numbers, dates, times, days, places, booking codes, e-mails and names.

    Reproducible from `seed`. About one pair in five without Latin text is
    written in Arabic-Indic digits on both sides."""
    rng = random.Random(seed)
    pairs = []
    for _ in range(n):
        dialect_t, msa_t = rng.choice(_TEMPLATES)
        # Ordered so the sentences make sense: the part before the whole, the earlier time first, the larger share first.
        sar, sar2 = sorted(_two(rng, _amount, _value), key=_value)
        t = _time(rng)
        t2 = _later(rng, t)
        pct2, pct = sorted(_two(rng, lambda r: f"{r.choice([5, 10, 15, 20, 25, 30, 40, 50, 70])}%"), key=_value)
        city, city2 = rng.sample(_CITIES, 2)
        dest = rng.choice(_ABROAD)
        big, big2 = sorted(rng.sample(_PACKAGE_PRICES, 2))
        day_d, day_m = rng.choice(_WEEKDAYS)
        rel_d, rel_m = rng.choice(_RELATIVE_DAYS)
        # 3 to 10 only: the templates use plural nouns ("أيام", "ساعات"), which is the right form for these numbers.
        n1, n2 = sorted(rng.sample(range(3, 11), 2), reverse=True)
        slots = {
            "n": str(n1), "n2": str(n2), "d": _date(rng, formal=dialect_t == msa_t), "t": t, "t2": t2, "sar": sar, "sar2": sar2,
            "riyal": _riyal(sar), "big": str(big), "big2": str(big2), "riyal_big2": _riyal(str(big2)), "visa": rng.choice(_VISA_PLACES),
            "pct": pct, "pct2": pct2, "name": rng.choice(_NAMES), "city": city, "city2": city2,
            "lcity": _to(city), "lcity2": _to(city2), "dest": dest, "ldest": _to(dest), "day_d": day_d, "day_m": day_m,
            "rel_d": rel_d, "rel_m": rel_m, "pay": rng.choice(_PAYMENT),
            "ref": str(rng.randint(10000, 99999999)), "pnr": _pnr(rng),
            "email": f"{rng.choice(_MAILBOXES)}@example.{rng.choice(['com', 'org', 'net'])}",
        }
        dialect, msa = dialect_t.format(**slots), msa_t.format(**slots)
        if rng.random() < 0.2 and not _HAS_LATIN.search(dialect):
            dialect, msa = (_DECIMAL_POINT.sub("٫", text).translate(_ARABIC_INDIC) for text in (dialect, msa))
        pairs.append({"dialect": dialect, "msa": msa, "source": "synthetic"})
    return pairs


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #
def _same_text(a: str, b: str) -> bool:
    """Equal up to diacritics and spacing."""
    return " ".join(strip_marks(a).split()) == " ".join(strip_marks(b).split())


def clean_pairs(pairs: list[dict], max_identical_frac: float = 0.05, seed: int = 13) -> tuple[list[dict], Counter]:
    """Drop unusable pairs. Returns the kept pairs and a count per reason.

    fact_mismatch: the MSA side does not carry the same numbers, dates and
    Latin words as the dialect side. Training on such a pair would teach the
    model the very error the checker exists to catch.
    """
    dropped: Counter = Counter()
    seen: set[str] = set()
    kept, identical = [], []
    for pair in pairs:
        d, m = pair["dialect"], pair["msa"]
        key = normalize_for_dedup(d)
        if not d or not m:
            dropped["empty"] += 1
        elif not (MIN_CHARS <= len(d) <= MAX_CHARS and MIN_CHARS <= len(m) <= MAX_CHARS):
            dropped["length"] += 1
        elif key in seen:
            dropped["duplicate"] += 1
        elif not compare_facts(d, m).ok:
            dropped["fact_mismatch"] += 1
        else:
            seen.add(key)
            # A pair that only fixes hamza or ta marbuta is a real, if small, rewrite and is kept as one.
            (identical if _same_text(d, m) else kept).append(pair)
    # A few pairs that are already MSA teach rule 4 of the prompt; too many teach copying.
    allowed = int(max_identical_frac * len(kept) / (1 - max_identical_frac)) if kept else 0
    random.Random(seed).shuffle(identical)
    over = max(0, len(identical) - allowed)
    if over:
        dropped["identical_over_cap"] += over
    return kept + identical[:allowed], dropped


# --------------------------------------------------------------------------- #
# Separation from the golden test
# --------------------------------------------------------------------------- #
class GoldenIndex:
    """Decides whether a text collides with a golden source or reference.

    exact           equal after normalisation, or equal with all spaces removed
    contained       one is a substring of the other (also with spaces removed)
    near_duplicate  Jaccard similarity of character 5-grams >= `threshold`
    shared_content  the shorter text shares >= `shared_threshold` of its
                    5-grams with the longer one

    Known limit: a sentence that keeps only the frame of a golden sentence and
    replaces its numbers and names can share less than the threshold and pass.
    """

    def __init__(self, golden_rows: list[dict], threshold: float = 0.8, shared_threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.shared_threshold = shared_threshold
        self.items = []
        for row in golden_rows:
            for side in ("source", "reference"):
                norm = normalize_for_dedup(row[side])
                self.items.append((f"{row.get('id', '?')}:{side}", norm, char_shingles(norm), norm.replace(" ", "")))
        self.exact = {norm: gid for gid, norm, _, _ in self.items}
        self.spaceless = {squeezed: gid for gid, _, _, squeezed in self.items}

    def scan(self, text: str) -> tuple[dict | None, float, str | None]:
        """(collision or None, highest shared-content score seen, the golden text it was seen with)."""
        norm = normalize_for_dedup(text)
        if norm in self.exact:
            return {"golden": self.exact[norm], "kind": "exact", "score": 1.0}, 1.0, self.exact[norm]
        squeezed = norm.replace(" ", "")
        if squeezed in self.spaceless:
            return {"golden": self.spaceless[squeezed], "kind": "exact", "score": 1.0}, 1.0, self.spaceless[squeezed]
        shingles = char_shingles(norm)
        best, best_id = 0.0, None
        for gid, g_norm, g_shingles, g_squeezed in self.items:
            if min(len(g_norm), len(norm)) >= MIN_CONTAINMENT_CHARS and (g_norm in norm or norm in g_norm):
                return {"golden": gid, "kind": "contained", "score": 1.0}, 1.0, gid
            if min(len(g_squeezed), len(squeezed)) >= MIN_CONTAINMENT_CHARS and (g_squeezed in squeezed or squeezed in g_squeezed):
                return {"golden": gid, "kind": "contained", "score": 1.0}, 1.0, gid
            if not shingles or not g_shingles:
                continue
            shared = len(shingles & g_shingles)
            score = shared / (len(shingles) + len(g_shingles) - shared)
            if score >= self.threshold:
                return {"golden": gid, "kind": "near_duplicate", "score": round(score, 3)}, score, gid
            coverage = shared / min(len(shingles), len(g_shingles))
            if coverage >= self.shared_threshold:
                return {"golden": gid, "kind": "shared_content", "score": round(coverage, 3)}, coverage, gid
            if coverage > best:
                best, best_id = coverage, gid
        return None, best, best_id

    def match(self, text: str) -> dict | None:
        return self.scan(text)[0]

    def match_pair(self, pair: dict) -> dict | None:
        return self.match(pair["dialect"]) or self.match(pair["msa"])


def remove_golden_overlap(pairs: list[dict], index: GoldenIndex, with_scores: bool = False):
    """Split `pairs` into kept and removed. With `with_scores`, also return for
    every kept pair how close it came to the golden test: (score, golden id)."""
    kept, removed, scores = [], [], []
    for pair in pairs:
        hit_d, score_d, id_d = index.scan(pair["dialect"])
        hit_m, score_m, id_m = (None, 0.0, None) if hit_d else index.scan(pair["msa"])
        hit = hit_d or hit_m
        if hit:
            removed.append({"source": pair["source"], "dialect": pair["dialect"], **hit})
        else:
            kept.append(pair)
            scores.append((score_d, id_d) if score_d >= score_m else (score_m, id_m))
    return (kept, removed, scores) if with_scores else (kept, removed)


_DIGIT_GROUPS = re.compile(r"\d[\d \-]{7,}\d")
_SPLIT_CODE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,8})[ _\-]{1,2}(\d{2,})(?!\d)")


def distinctive_facts(text: str) -> set[tuple[str, str]]:
    """Facts specific enough to identify a message: e-mail addresses, links,
    codes that mix letters and digits, and numbers of five digits or more.

    The keys are looser than the fact checker's, so that the same string in
    another dress is still found: a link without "https://" or "www.", a code
    in another case, without its hyphen or with a space ("J-20481", "j20481",
    "J 20481", "SAVE 20" for "SAVE20"), a long number written in groups or with
    a country code (the last nine digits)."""
    found = set()
    for fact in extract_facts(text):
        digits = "".join(ch for ch in fact.value if ch.isdigit())
        if fact.kind == "email":
            found.add(("email", fact.value.lower()))
        elif fact.kind == "url":
            found.add(("url", re.sub(r"^(?:https?://)?(?:www\.)?", "", fact.value.lower()).rstrip("/")))
        elif fact.kind == "latin" and digits:
            found.add(("code", re.sub(r"[^A-Za-z0-9]", "", fact.value).upper()))
            if len(digits) >= 5:
                found.add(("number", digits))
        elif fact.kind == "number" and len(digits) >= 5:
            found.add(("number", digits))
            if len(digits) >= 9:
                found.add(("number", digits[-9:]))
    plain = strip_marks(text)
    for match in _DIGIT_GROUPS.finditer(plain):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 9:
            found.add(("number", digits[-9:]))
    for match in _SPLIT_CODE.finditer(plain):
        found.add(("code", (match.group(1) + match.group(2)).upper()))
    return found


def remove_shared_facts(pairs: list[dict], golden_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop training pairs that carry an address, link, code or long number of
    the golden test, so that no test-specific string can be memorised."""
    golden_facts: set[tuple[str, str]] = set()
    for row in golden_rows:
        golden_facts |= distinctive_facts(row["source"]) | distinctive_facts(row["reference"])
    kept, removed = [], []
    for pair in pairs:
        shared = (distinctive_facts(pair["dialect"]) | distinctive_facts(pair["msa"])) & golden_facts
        if shared:
            removed.append({"source": pair["source"], "dialect": pair["dialect"], "shared": sorted(value for _, value in shared)})
        else:
            kept.append(pair)
    return kept, removed


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def prepare(args: argparse.Namespace) -> dict:
    if not 0 <= args.max_identical_frac < 1:
        raise SystemExit("--max-identical-frac must be at least 0 and below 1")
    if args.corpus_limit < 0 or args.synthetic_n < 0:
        raise SystemExit("--corpus-limit and --synthetic-n cannot be negative (0 means all of the corpus, and no template pairs)")
    golden = read_jsonl(args.golden)
    errors, _, _ = validate_rows(golden, args.min_golden_rows, not args.allow_unreviewed)
    if errors:
        raise SystemExit("the golden test does not validate; run `python -m src.validate_golden` and fix it first:\n  "
                         + "\n  ".join(errors[:10]))
    index = GoldenIndex(golden, args.near_dup_threshold, args.shared_content_threshold)

    for source, target in FEW_SHOT_EXAMPLES:
        hit = index.match(source) or index.match(target)
        if hit:
            raise SystemExit(f"a few-shot example in src/prompts.py collides with the golden test ({hit}); change one of them")

    pairs: list[dict] = []
    loaded: Counter = Counter()
    labels_stripped = 0
    if args.corpus_csv:
        corpus = load_corpus_csv(args.corpus_csv, args.dialect_col, args.msa_col)
        labels_stripped = sum(1 for p in corpus if p.pop("label_stripped", False))
        loaded["corpus_rows_in_file"] = len(corpus)
        # Clean before limiting, so the limit counts usable, distinct pairs.
        corpus, corpus_dropped = clean_pairs(corpus, args.max_identical_frac, args.seed)
        if args.corpus_limit and len(corpus) > args.corpus_limit:
            random.Random(args.seed).shuffle(corpus)
            corpus = corpus[: args.corpus_limit]
        pairs += corpus
        loaded["corpus"] = len(corpus)
    else:
        corpus_dropped = Counter()
    if args.team_jsonl:
        team = load_team_jsonl(args.team_jsonl)
        pairs += team
        loaded["team"] = len(team)
    if args.synthetic_n:
        synthetic = generate_synthetic(args.synthetic_n, args.seed)
        pairs += synthetic
        loaded["synthetic"] = len(synthetic)
    if not pairs:
        raise SystemExit("no training source given; pass --corpus-csv, --team-jsonl or --synthetic-n")

    cleaned, dropped = clean_pairs(pairs, args.max_identical_frac, args.seed)
    cleaned, shared_fact = remove_shared_facts(cleaned, golden)
    kept, removed, scores = remove_golden_overlap(cleaned, index, with_scores=True)
    if len(kept) < 2:
        raise SystemExit("fewer than two usable pairs are left after cleaning and overlap removal")
    closest = sorted(zip(scores, kept, strict=True), key=lambda item: -item[0][0])[:5]

    rng = random.Random(args.seed)
    rng.shuffle(kept)
    n_val = max(1, int(len(kept) * args.val_frac))
    val, train = kept[:n_val], kept[n_val:]

    def to_row(pair: dict) -> dict:
        row = build_training_example(pair["dialect"], pair["msa"])
        row["meta"] = {"source": pair["source"]}
        return row

    out = Path(args.out)
    write_jsonl(out / "train.jsonl", [to_row(p) for p in train])
    write_jsonl(out / "val.jsonl", [to_row(p) for p in val])

    # Verify on what was actually written.
    remaining = 0
    for name in ("train.jsonl", "val.jsonl"):
        for row in read_jsonl(out / name):
            user, assistant = row["messages"][1]["content"], row["messages"][2]["content"]
            if index.match(user) or index.match(assistant):
                remaining += 1
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "golden_file": str(args.golden),
        "golden_sha256": sha256_file(args.golden),
        "golden_rows": len(golden),
        "corpus_file_sha256": sha256_file(args.corpus_csv) if args.corpus_csv else None,
        "corpus_labels_stripped": labels_stripped,
        "loaded": dict(loaded),
        "dropped_from_corpus": dict(corpus_dropped),
        "dropped_in_cleaning": dict(dropped),
        "removed_for_golden_overlap": len(removed),
        "removed_examples": removed[:50],
        "removed_for_shared_fact": len(shared_fact),
        "removed_shared_fact_examples": shared_fact[:10],
        "train": len(train),
        "val": len(val),
        "train_sha256": sha256_file(out / "train.jsonl"),
        "val_sha256": sha256_file(out / "val.jsonl"),
        "by_source": dict(Counter(p["source"] for p in kept)),
        "pairs_with_facts": sum(1 for p in kept if extract_facts(p["dialect"])),
        "overlap_remaining_after_filter": remaining,
        "closest_kept_pairs": [
            {"shared_content": round(score, 3), "golden": gid, "source": pair["source"], "dialect": pair["dialect"]}
            for (score, gid), pair in closest
        ],
        "thresholds": {"near_duplicate": args.near_dup_threshold, "shared_content": args.shared_content_threshold},
    }
    (out / "prep_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if remaining:
        raise SystemExit(f"{remaining} written rows still overlap the golden test; do not train on these files")
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prepare training data and keep it apart from the golden test.")
    p.add_argument("--golden", required=True)
    p.add_argument("--out", default="data/processed")
    p.add_argument("--corpus-csv", help="the parallel corpus CSV (see scripts/download_corpus.py)")
    p.add_argument("--dialect-col", help="CSV column with the Saudi dialect text (detected by name if omitted)")
    p.add_argument("--msa-col", help="CSV column with the MSA text (detected by name if omitted)")
    p.add_argument("--corpus-limit", type=int, default=0, help="use at most this many cleaned corpus pairs (0 = all)")
    p.add_argument("--team-jsonl", nargs="*", default=[])
    p.add_argument("--synthetic-n", type=int, default=0)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--val-frac", type=float, default=0.1)
    p.add_argument("--max-identical-frac", type=float, default=0.05)
    p.add_argument("--near-dup-threshold", type=float, default=0.8)
    p.add_argument("--shared-content-threshold", type=float, default=0.6)
    p.add_argument("--min-golden-rows", type=int, default=100)
    p.add_argument("--allow-unreviewed", action="store_true", help="draft or template only: skip the two-member check on the golden test")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare(args)
    except (CorpusFormatError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    quiet = ("removed_examples", "removed_shared_fact_examples")
    print(json.dumps({k: v for k, v in report.items() if k not in quiet}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
