"""`make prebake`: draft the acme-edge pack with the local LLM once, gate it, and cache it (BACKEND_SCHEMA.md §4.5).
Writes origin llm_cached when the model's YAML passes every gate, else the hand-authored pack as hand_authored."""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from app.aiparser.drafts import run_gates
from app.aiparser.prompt import drafting_prompt
from app.aiparser.sources import CACHE, DRAFT_TOKENS, strip_fences
from app.core import config
from app.ocsf.enums import Enums
from app.ocsf.validate import OcsfValidator
from app.search.llm import OllamaClient
from generator.br01 import HOLDOUT, build_br01_lines
from generator.formats import at
from generator.scenario import today_ist

FALLBACK = Path(__file__).with_name("acme-edge.fallback.yaml")


def gate_counts(res: dict) -> dict:
    return {k: res[k]["passed"] for k in ("holdout", "all", "roundtrip", "ocsf_valid")}


async def prebake(cfg=None) -> dict:
    cfg = cfg or config.load()
    enums, validate = Enums(), OcsfValidator()
    lines = build_br01_lines(at(today_ist(), 10, 14, 3))
    train = [ln for i, ln in enumerate(lines) if i not in HOLDOUT]
    prompt = drafting_prompt(train)
    llm = OllamaClient(cfg.ollama_url, cfg.ollama_model)
    out = await llm.complete("", prompt, 900, num_predict=DRAFT_TOKENS) if await llm.ready() else None
    entry = None
    if out:
        yaml_text = strip_fences(out)
        res = run_gates(yaml_text, lines, HOLDOUT, enums, validate)
        if res["promotable"]:
            entry = {"origin": "llm_cached", "model": cfg.ollama_model, "yaml": yaml_text, "gate_report": gate_counts(res)}
        else:
            failed = sorted({f["check"] for f in res["failures"]})
            print(f"LLM draft failed the gates ({', '.join(failed)}); using the hand-authored pack.")
    else:
        print("Local LLM not reachable; using the hand-authored pack.")
    if entry is None:
        yaml_text = FALLBACK.read_text(encoding="utf-8")
        entry = {"origin": "hand_authored", "model": None, "yaml": yaml_text,
                 "gate_report": gate_counts(run_gates(yaml_text, lines, HOLDOUT, enums, validate))}
    cache = {"group_shape": "EDGE|x12", "origin": entry["origin"], "model": entry["model"],
             "generated_at": int(time.time() * 1000), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
             "yaml": entry["yaml"], "gate_report": entry["gate_report"]}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    return cache


def main() -> int:
    cache = asyncio.run(prebake())
    g = cache["gate_report"]
    print(f"origin {cache['origin']} | held-out {g['holdout']}/6 | all {g['all']}/20 | round-trip {g['roundtrip']}/20"
          f" | OCSF {g['ocsf_valid']}/20 -> {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
