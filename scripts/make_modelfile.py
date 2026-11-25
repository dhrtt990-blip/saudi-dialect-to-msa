"""Write an Ollama Modelfile for a GGUF file exported by the notebook, and check the prompt Ollama builds from it.

    python scripts/make_modelfile.py --gguf models/qwen3-1.7b-base-q8_0.gguf --name d2m-qwen3-base --out Modelfile.base
    ollama create d2m-qwen3-base -f Modelfile.base
    python scripts/make_modelfile.py --gguf models/d2m-qwen3-1.7b-q8_0.gguf
    ollama create d2m-qwen3-lora -f Modelfile
    python scripts/make_modelfile.py --check d2m-qwen3-base d2m-qwen3-lora

The Modelfile has no TEMPLATE line. Ollama then builds the prompt with the chat
template stored inside the GGUF file, which is the template of the tokenizer the
adapter was trained with. With thinking switched off (the pipeline sends
`think: false`) the prompt is, character for character, the text the model saw
in training. The untuned base is served the same way, so that it differs from
the tuned model only by the adapter.

Why not the Modelfile of the library model `qwen3:1.7b`, which this script
copied until 24 November 2026: on Ollama 0.40.18 its template adds ` /no_think`
to the user's message and an empty line after `<|im_start|>system`. Neither is
in the training data, and for a model whose job is to rewrite the user's message
an extra word in that message is not harmless by default.

`--check` asks Ollama for the prompt it would send for the four kinds of request
the pipeline makes (the tuned model's request, the baseline's request with its
worked examples, and the repair request of each) and compares each with the
training format. Nothing is generated. Run it once on every machine after
`ollama create`: which template Ollama picks depends on its version, and this
was tested on Ollama 0.40.18 on Linux only. If Ollama refuses `think: false`,
the check reports the HTTP error; the pipeline would then retry without it, and
the prompt would no longer be the training format.

The check also fails if the model was created with another repeat penalty,
because the pipeline does not send one. It does not look at the temperature
(the pipeline sends 0 with every request) or at the stop parameters (a model
created without them still stopped at the end of its answer).

Give every GGUF file one Ollama model. Two models made from the same file with
different templates were seen to share one running server, and the second one
was then served with the template of the first. If the check fails right after
a model was created again from the same file, run `ollama stop MODEL` and check
once more.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import DEFAULT_HOST  # noqa: E402
from src.prompts import build_messages, build_repair_messages  # noqa: E402

# No repeat penalty: the model has to repeat most of its input, the Hugging Face generation the notebook compares
# with uses none, and a penalty of 1.1 changed the output on the one message it was tried on. The pipeline does not
# send this parameter, so the Modelfile sets it instead of leaving it to the default of the installed Ollama version,
# and the check looks at it.
MODELFILE_PARAMETERS = {"temperature": "0", "repeat_penalty": "1"}
CHECKED_PARAMETERS = {"repeat_penalty": 1.0}
STOPS = ("<|im_start|>", "<|im_end|>")
CHECK_MESSAGE = "ابغى اغير موعدي من يوم 5/3 الى 9/3 ورقم الطلب 48213"   # invented; any message would do
CHECK_PREVIOUS = "أريد تغيير موعدي."                                    # a rewrite that lost its facts, for the repair requests


def build_modelfile(gguf_path: str) -> str:
    lines = [f"FROM {gguf_path}"]
    lines += [f"PARAMETER {name} {value}" for name, value in MODELFILE_PARAMETERS.items()]
    lines += [f"PARAMETER stop {stop}" for stop in STOPS]
    return "\n".join(lines) + "\n"


def expected_prompt(messages: list[dict]) -> str:
    """The Qwen3 chat format with thinking switched off, as the Hugging Face tokenizer of
    `Qwen/Qwen3-1.7B` renders these messages (`enable_thinking=False`). The training text is this
    prompt followed by the rewrite."""
    turns = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages)
    return turns + "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def check_cases() -> dict[str, list[dict]]:
    """One request of each kind the pipeline sends."""
    return {
        "tuned model's request": build_messages(CHECK_MESSAGE),
        "baseline request with worked examples": build_messages(CHECK_MESSAGE, few_shot=True),
        "tuned model's repair request": build_repair_messages(CHECK_MESSAGE, CHECK_PREVIOUS, ["5/3"], ["7"]),
        "baseline repair request": build_repair_messages(CHECK_MESSAGE, CHECK_PREVIOUS, ["5/3"], ["7"], few_shot=True),
    }


def first_difference(expected: str, actual: str, context: int = 30) -> str:
    i = next((k for k, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))
    lo = max(0, i - context)
    return f"at character {i}: expected {expected[lo:i + context]!r}, Ollama built {actual[lo:i + context]!r}"


def parameter_problems(parameters: str | None) -> list[str]:
    """`parameters` is the text Ollama returns from /api/show: one `name value` pair per line."""
    found = dict(line.split(None, 1) for line in (parameters or "").splitlines() if len(line.split(None, 1)) == 2)
    problems = []
    for name, wanted in CHECKED_PARAMETERS.items():
        value = found.get(name, "").strip().strip('"')
        try:
            ok = float(value) == wanted
        except ValueError:
            ok = False
        if not ok:
            problems.append(f"{name} is {value or 'not set'}, expected {wanted:g}")
    return problems


def check_model(model: str, host: str = DEFAULT_HOST) -> list[str]:
    """Reasons to doubt that the model is served in the training format (empty list if none was found)."""
    import requests

    host = host.rstrip("/")
    try:
        shown = requests.post(f"{host}/api/show", json={"model": model}, timeout=30)
    except requests.RequestException as exc:
        return [f"cannot reach Ollama at {host}: {exc.__class__.__name__}"]
    if shown.status_code != 200:
        return [f"Ollama does not have a model named '{model}' (HTTP {shown.status_code}). Create it first."]
    try:
        problems = parameter_problems(shown.json().get("parameters"))
    except (ValueError, AttributeError):
        return ["unexpected answer from Ollama to /api/show"]
    for name, messages in check_cases().items():
        payload = {"model": model, "messages": messages, "stream": False, "think": False,
                   "_debug_render_only": True, "options": {"num_predict": 1}}
        try:
            resp = requests.post(f"{host}/api/chat", json=payload, timeout=300)
        except requests.RequestException as exc:
            return [*problems, f"cannot reach Ollama at {host}: {exc.__class__.__name__}"]
        if resp.status_code != 200:
            problems.append(f"{name}: Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")
            continue
        try:
            rendered = resp.json()["_debug_info"]["rendered_template"]
        except (ValueError, KeyError, TypeError):
            return [*problems, ("this Ollama version does not report the prompt it builds, so the format cannot be checked. "
                                "Update Ollama (tested with 0.40.18) and run the check again.")]
        expected = expected_prompt(messages)
        if rendered != expected:
            problems.append(f"{name}: the prompt differs from the training format {first_difference(expected, rendered)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Write the Modelfile for an exported GGUF file, or check that Ollama builds a model's prompts in the training format.")
    p.add_argument("--gguf", help="path to the exported GGUF file")
    p.add_argument("--out", default="Modelfile")
    p.add_argument("--name", default="d2m-qwen3-lora", help="the name the model will get in Ollama; only used in the hint printed at the end")
    p.add_argument("--check", nargs="+", metavar="MODEL", help="Ollama model names to check instead of writing a Modelfile")
    p.add_argument("--host", default=DEFAULT_HOST)
    args = p.parse_args(argv)

    if args.check:
        failed = False
        for model in args.check:
            problems = check_model(model, args.host)
            failed = failed or bool(problems)
            print(f"{model}: " + ("OK, Ollama builds the prompt in the training format" if not problems else "NOT OK"))
            for problem in problems:
                print(f"  - {problem}")
            if any("differs from the training format" in problem for problem in problems):
                print(f"  If this model was just created again from the same GGUF file, run `ollama stop {model}` and check once more.")
        return 1 if failed else 0

    if not args.gguf:
        p.error("give --gguf to write a Modelfile, or --check to check models that already exist")
    gguf = Path(args.gguf)
    if not gguf.is_file():
        print(f"ERROR: {gguf} not found. Download the GGUF file from your Hub repository first.")
        return 1
    Path(args.out).write_text(build_modelfile(str(gguf.resolve())), encoding="utf-8")
    print(f"wrote {args.out}. Next: ollama create {args.name} -f {args.out}\n"
          f"Then: python scripts/make_modelfile.py --check {args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
