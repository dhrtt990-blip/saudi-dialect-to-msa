"""Write an Ollama Modelfile for a GGUF file exported by the notebook.

    ollama pull qwen3:1.7b
    python scripts/make_modelfile.py --gguf models/qwen3-1.7b-base-q8_0.gguf --name d2m-qwen3-base --out Modelfile.base
    ollama create d2m-qwen3-base -f Modelfile.base
    python scripts/make_modelfile.py --gguf models/d2m-qwen3-1.7b-q8_0.gguf
    ollama create d2m-qwen3-lora -f Modelfile

A GGUF file imported on its own may be served without the right chat template.
Both exported files use the chat format of Qwen3, so this script takes the
Modelfile of `qwen3:1.7b` from Ollama and only swaps the weights. The untuned
base is served this way too, so that it differs from the tuned model only by
the adapter: the library build of `qwen3:1.7b` is a 4-bit file, the exported
files are 8-bit.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def build_modelfile(base_modelfile: str, gguf_path: str) -> str:
    lines = []
    replaced = False
    for line in base_modelfile.splitlines():
        if line.strip().upper().startswith("FROM ") and not replaced:
            lines.append(f"FROM {gguf_path}")
            replaced = True
        elif line.strip().upper().startswith("PARAMETER TEMPERATURE"):
            continue
        else:
            lines.append(line)
    if not replaced:
        raise ValueError("the base Modelfile has no FROM line")
    lines.append("PARAMETER temperature 0")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Create a Modelfile that serves an exported GGUF file with the chat template of the Ollama library model.")
    p.add_argument("--gguf", required=True, help="path to the exported GGUF file")
    p.add_argument("--base", default="qwen3:1.7b", help="Ollama model whose template and parameters are reused")
    p.add_argument("--out", default="Modelfile")
    p.add_argument("--name", default="d2m-qwen3-lora", help="the name the model will get in Ollama; only used in the hint printed at the end")
    args = p.parse_args(argv)

    gguf = Path(args.gguf)
    if not gguf.is_file():
        print(f"ERROR: {gguf} not found. Download the GGUF file from your Hub repository first.")
        return 1
    try:
        shown = subprocess.run(["ollama", "show", args.base, "--modelfile"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("ERROR: the 'ollama' command was not found. Install Ollama first.")
        return 1
    if shown.returncode != 0:
        print(f"ERROR: could not read the Modelfile of '{args.base}'. Run `ollama pull {args.base}` first.\n{shown.stderr.strip()}")
        return 1
    try:
        content = build_modelfile(shown.stdout, str(gguf.resolve()))
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    Path(args.out).write_text(content, encoding="utf-8")
    print(f"wrote {args.out}. Next: ollama create {args.name} -f {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
