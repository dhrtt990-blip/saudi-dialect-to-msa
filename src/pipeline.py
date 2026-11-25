"""The dialect-to-MSA pipeline.

    message ──► missing-information check (a booking request without its date or destination, a request
                                           about a booking without its reference: ask, do not rewrite)
            ──► LLM rewriter      (Saudi dialect → formal MSA)
            ──► fact checker      (numbers, dates, times, e-mails, Latin words, days, listed places and names)
            ──► one repair attempt (the model is told which facts differ)
            ──► release, or withhold and hand back the original

Failure policy: a rewrite is released only when the model answered and the fact
checker found no difference. Otherwise the rewrite is withheld and the caller
receives the original message with a status explaining why. A rewrite with a
changed fact is never released silently. When a needed detail is missing the
caller receives the questions to ask; the model is not called, so it cannot
fill the gap with a guess.
"""
from __future__ import annotations

import re
import time
import zlib
from dataclasses import asdict, dataclass, field
from typing import Protocol

from .common import strip_marks
from .facts import compare_facts, extract_facts
from .lexicon import rule_based_rewrite
from .needs import find_missing, questions
from .prompts import build_messages, build_repair_messages

DEFAULT_HOST = "http://localhost:11434"
# The untuned model, converted with the same script and 8-bit setting as the tuned one (README, step 5).
# The `qwen3:1.7b` build in the Ollama library is a 4-bit file; using it as the baseline would mix
# quantisation with fine-tuning.
DEFAULT_BASE_MODEL = "d2m-qwen3-base"
DEFAULT_TUNED_MODEL = "d2m-qwen3-lora"

STATUS_OK = "OK"
STATUS_REPAIRED = "OK_AFTER_REPAIR"
STATUS_FACT_MISMATCH = "WITHHELD_FACT_MISMATCH"
STATUS_SUSPECT = "WITHHELD_SUSPECT_OUTPUT"
STATUS_MODEL_FAILURE = "WITHHELD_MODEL_FAILURE"
STATUS_TOO_LONG = "BLOCKED_INPUT_TOO_LONG"
STATUS_EMPTY = "EMPTY_INPUT"
STATUS_NEEDS_INFO = "NEEDS_INFO"

MESSAGES_AR = {
    STATUS_OK: "تمت إعادة الصياغة، ولم يجد الفاحص اختلافاً في الأرقام والتواريخ والأوقات والأيام والأماكن المدرجة. ما عدا ذلك لم يُفحص آلياً.",
    STATUS_REPAIRED: "رصد الفاحص اختلافاً في التفاصيل، فطُلب من النموذج التصحيح مرة واحدة ثم نجح الفحص.",
    STATUS_FACT_MISMATCH: "بقي اختلاف في التفاصيل بعد محاولة التصحيح. حُجبت إعادة الصياغة وأُعيدت الرسالة الأصلية، وتحتاج صياغة يدوية.",
    STATUS_SUSPECT: "مخرجات النموذج لا تشبه إعادة صياغة للرسالة (طول أو لغة غير متوقعة). حُجبت وأُعيدت الرسالة الأصلية.",
    STATUS_MODEL_FAILURE: "تعذّر الحصول على مخرجات من النموذج. أُعيدت الرسالة الأصلية كما هي.",
    STATUS_TOO_LONG: "الرسالة أطول من الحد المسموح. قسّمها إلى رسائل أقصر ثم أعد المحاولة.",
    STATUS_EMPTY: "لم يُدخل نص.",
    STATUS_NEEDS_INFO: "ينقص الرسالة تفصيل لازم لتنفيذ الطلب، والنظام لا يخمّنه. اسأل العميل عنه ثم أعد المحاولة.",
}


# --------------------------------------------------------------------------- #
# LLM clients
# --------------------------------------------------------------------------- #
class LLMUnavailable(RuntimeError):
    """The model server could not be reached or returned an unusable reply."""


class LLMClient(Protocol):
    name: str
    few_shot: bool

    def generate(self, messages: list[dict]) -> str:
        """Return the raw model reply for one chat."""


class OllamaClient:
    """Calls a model served locally by Ollama (`/api/chat`).

    `few_shot=True` is the baseline configuration: the untuned model with its
    own prompt and worked examples (`build_baseline_messages`). The tuned model uses `few_shot=False`,
    the format it was trained on.
    """

    def __init__(self, model: str, host: str = DEFAULT_HOST, few_shot: bool = False, timeout: float = 120.0) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.few_shot = few_shot
        self.timeout = timeout
        self.name = f"ollama:{model}" + ("+fewshot" if few_shot else "")

    def generate(self, messages: list[dict]) -> str:
        import requests

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,  # Qwen3 thinking mode is not needed for a rewrite and costs hundreds of tokens
            "options": {"temperature": 0, "seed": 0, "num_predict": 512},
        }
        url = f"{self.host}/api/chat"
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 400 and "think" in resp.text.lower():
                # A model imported from GGUF may not be registered as a thinking model.
                payload.pop("think")
                resp = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMUnavailable(f"cannot reach Ollama at {self.host}: {exc.__class__.__name__}") from None
        if resp.status_code != 200:
            raise LLMUnavailable(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            content = resp.json()["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise LLMUnavailable("unexpected response shape from Ollama") from None
        if not isinstance(content, str):
            raise LLMUnavailable("unexpected response shape from Ollama")
        return content

    def is_available(self) -> tuple[bool, str]:
        import requests

        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            names = {m.get("name", "") for m in resp.json().get("models", [])}
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            return False, f"Ollama is not reachable at {self.host}"
        if not (names & {self.model, f"{self.model}:latest"}):
            return False, f"model '{self.model}' is not installed in Ollama"
        return True, "ok"


_DIGITS = re.compile(r"\d+")
# level -> (leave every n-th dialect word, fact error when crc % m is in the set, m)
_MOCK_LEVELS = {
    "strong": (0, frozenset(), 1),
    "medium": (5, frozenset({0}), 5),
    "weak": (3, frozenset({0, 1}), 3),
}


class MockClient:
    """A rule-based stand-in for the model. It is NOT a model.

    It lets the pipeline, the evaluation, the safety check and the app run
    end to end on a machine without Ollama. Numbers produced with it say
    nothing about model quality, and every report made with it is labelled
    as a dry run.

    "strong" replaces the listed dialect words and keeps every fact.
    "medium" and "weak" leave some dialect words and drop or change the first
    number of some messages, so the checker and the error analysis have
    something to find. Asked to repair, they comply for three messages in four.
    """

    few_shot = False

    def __init__(self, level: str = "strong") -> None:
        if level not in _MOCK_LEVELS:
            raise ValueError(f"level must be one of {sorted(_MOCK_LEVELS)}")
        self.level = level
        self.name = f"mock-{level}"

    def generate(self, messages: list[dict]) -> str:
        repairing = len(messages) >= 3 and messages[-2]["role"] == "assistant"
        users = [m["content"] for m in messages if m["role"] == "user"]
        text = users[-2] if repairing else users[-1]
        crc = zlib.crc32(text.encode("utf-8"))
        skip_every, bad, modulo = _MOCK_LEVELS[self.level]
        if repairing:
            if self.level != "strong" and crc % 4 == 0:
                return messages[-2]["content"]  # repeats its mistake
            return rule_based_rewrite(text)
        out = rule_based_rewrite(text, skip_every=skip_every)
        if crc % modulo in bad:
            flat = strip_marks(out)
            m = _DIGITS.search(flat)
            if m and crc % 2 == 0:
                out = flat[:m.start()] + flat[m.end():]
            elif m:
                out = flat[:m.start()] + str(int(m.group(0)) + 1) + flat[m.end():]
        return out


class ScriptedClient:
    """Returns pre-written replies in order (used by the unit tests)."""

    few_shot = False

    def __init__(self, replies: list[str], name: str = "scripted") -> None:
        if not replies:
            raise ValueError("at least one reply is required")
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.name = name

    def generate(self, messages: list[dict]) -> str:
        reply = self.replies[len(self.calls) % len(self.replies)]
        self.calls.append(messages)
        return reply


def build_client(kind: str, model: str = DEFAULT_TUNED_MODEL, host: str = DEFAULT_HOST, few_shot: bool = False) -> LLMClient:
    """`kind` is "ollama", "mock" (strong), "mock-medium" or "mock-weak"."""
    if kind == "ollama":
        return OllamaClient(model=model, host=host, few_shot=few_shot)
    if kind == "mock":
        return MockClient("strong")
    if kind in ("mock-medium", "mock-weak"):
        return MockClient(kind.split("-", 1)[1])
    raise ValueError(f"unknown client kind: {kind!r}")


# --------------------------------------------------------------------------- #
# Model call and output clean-up (shared with the model-only evaluation)
# --------------------------------------------------------------------------- #
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_LABEL = re.compile(r"^(?:النص المحو[ّ]?ل|الفصحى|إعادة الصياغة|الصياغة الرسمية|الرسالة بالفصحى)\s*[:：]\s*")
_QUOTES = [('"', '"'), ("«", "»"), ("“", "”"), ("'", "'")]
_ARABIC_LETTER = re.compile(r"[ء-ي]")
_ANY_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_BIDI_CONTROLS = re.compile("[\u202a-\u202e\u2066-\u2069]")


def clean_output(raw: str) -> str:
    """Strip what a chat model wraps around its answer: thinking blocks, code
    fences, a leading label and one pair of surrounding quotes."""
    text = _THINK.sub("", raw or "")
    if "<think>" in text.lower():  # an unterminated thinking block: nothing usable follows
        text = text[: text.lower().index("<think>")]
    text = text.strip()
    text = _FENCE.sub("", text).strip()
    text = _LABEL.sub("", text).strip()
    for left, right in _QUOTES:
        only_pair = text.count(left) == 2 if left == right else text.count(left) == 1 and text.count(right) == 1
        if len(text) >= 2 and text.startswith(left) and text.endswith(right) and only_pair:
            text = text[1:-1].strip()
            break
    # Direction overrides and isolates can make digits display in another order than they are stored.
    text = _BIDI_CONTROLS.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def shape_problem(source: str, output: str) -> str | None:
    """Reason the output cannot be a rewrite of the source, or None.

    This is a coarse guard against a model that answers the message, follows an
    instruction hidden in it, or replies in another language."""
    if _ANY_LETTER.search(source) and not _ANY_LETTER.search(output):
        return "output contains no words"
    if len(output) > 3 * len(source) + 40:
        return "output is more than three times as long as the message"
    if len(source) >= 30 and len(output) < 0.34 * len(source):
        return "output is less than a third of the message"

    def arabic_share(t: str) -> float:
        letters = _ANY_LETTER.findall(t)
        return len(_ARABIC_LETTER.findall(t)) / len(letters) if letters else 1.0

    if arabic_share(source) >= 0.6 and arabic_share(output) < 0.5:
        return "output is mostly not Arabic"
    return None


@dataclass
class ModelRewrite:
    ok: bool                   # the model returned a non-empty answer
    output: str = ""           # cleaned answer
    raw: str = ""
    unavailable: bool = False  # the server could not be reached (not a model error)
    error: str | None = None


def run_model(client: LLMClient, messages: list[dict]) -> ModelRewrite:
    """One model call, no retry."""
    try:
        raw = client.generate(messages)
    except LLMUnavailable as exc:
        return ModelRewrite(ok=False, unavailable=True, error=str(exc))
    output = clean_output(raw)
    if not output:
        return ModelRewrite(ok=False, raw=raw or "", error="empty answer")
    return ModelRewrite(ok=True, output=output, raw=raw)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
@dataclass
class PipelineResult:
    status: str
    released: bool
    text: str                      # what the caller should use: the rewrite if released, else the original
    original: str
    candidate: str | None = None   # the last model answer, shown for review even when withheld
    first_candidate: str | None = None
    attempts: int = 0
    repaired: bool = False
    unavailable: bool = False
    check: dict = field(default_factory=dict)        # fact report of the last candidate
    first_check: dict = field(default_factory=dict)  # fact report before the repair
    shape: str | None = None
    missing_info: list = field(default_factory=list)   # needed details the message does not give (see src/needs.py)
    questions_ar: list = field(default_factory=list)   # one question per missing detail
    message_ar: str = ""
    error: str | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class RewritePipeline:
    def __init__(self, client: LLMClient, max_input_chars: int = 2000, repair: bool = True, ask: bool = True) -> None:
        self.client = client
        self.max_input_chars = max_input_chars
        self.repair = repair
        self.ask = ask  # stop and ask when a needed detail is missing

    def _done(self, t0: float, status: str, original: str, **kw) -> PipelineResult:
        released = status in (STATUS_OK, STATUS_REPAIRED)
        return PipelineResult(
            status=status,
            released=released,
            text=kw.get("candidate") if released else original,
            original=original,
            message_ar=MESSAGES_AR[status],
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            **kw,
        )

    def run(self, text: str, must_keep: tuple[str, ...] | list[str] = (), ask: bool | None = None) -> PipelineResult:
        """Rewrite one message. `ask=False` skips the missing-information check for this
        call: the user chose to go on. The fact checker still refuses an added number, date in digits, named day or
        month, listed place or code; it does not see a period given in words ("الأسبوع القادم") or a place outside its list."""
        t0 = time.perf_counter()
        original = text or ""
        message = original.strip()
        if not message:
            return self._done(t0, STATUS_EMPTY, original)
        if len(message) > self.max_input_chars:
            return self._done(t0, STATUS_TOO_LONG, original)
        if self.ask if ask is None else ask:
            needed = find_missing(message)
            if needed:
                return self._done(t0, STATUS_NEEDS_INFO, original, missing_info=needed, questions_ar=questions(needed))

        few_shot = getattr(self.client, "few_shot", False)
        first = run_model(self.client, build_messages(message, few_shot=few_shot))
        if not first.ok:
            return self._done(t0, STATUS_MODEL_FAILURE, original, attempts=1, unavailable=first.unavailable, error=first.error)

        shape = shape_problem(message, first.output)
        report = compare_facts(message, first.output, must_keep)
        if shape is None and report.ok:
            return self._done(t0, STATUS_OK, original, candidate=first.output, first_candidate=first.output,
                              attempts=1, check=report.to_dict(), first_check=report.to_dict())

        first_check = report.to_dict()
        if not self.repair:
            status = STATUS_SUSPECT if shape else STATUS_FACT_MISMATCH
            return self._done(t0, status, original, candidate=first.output, first_candidate=first.output,
                              attempts=1, check=first_check, first_check=first_check, shape=shape)

        # One repair attempt. The facts that must appear are taken from the
        # original message, so the model is never asked to copy its own mistake.
        missing = [f["value"] for f in report.missing] + list(report.must_keep_missing)
        added = [f["value"] for f in report.added]
        if shape and not missing and not added:
            missing = [f.raw for f in extract_facts(message)]
        second = run_model(self.client, build_repair_messages(message, first.output, missing, added, few_shot=few_shot))
        if not second.ok:
            return self._done(t0, STATUS_MODEL_FAILURE, original, candidate=first.output, first_candidate=first.output,
                              attempts=2, unavailable=second.unavailable, error=second.error,
                              check=first_check, first_check=first_check, shape=shape)

        shape2 = shape_problem(message, second.output)
        report2 = compare_facts(message, second.output, must_keep)
        common = dict(candidate=second.output, first_candidate=first.output, attempts=2,
                      check=report2.to_dict(), first_check=first_check, shape=shape2)
        if shape2 is None and report2.ok:
            return self._done(t0, STATUS_REPAIRED, original, repaired=True, **common)
        return self._done(t0, STATUS_SUSPECT if shape2 else STATUS_FACT_MISMATCH, original, **common)
