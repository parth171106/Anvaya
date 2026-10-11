"""DraftSource implementations (TRD.md §4): cached draft in DEMO_MODE, live Ollama otherwise."""
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.aiparser.prompt import drafting_prompt
from app.search.llm import clean_sql

CACHE = Path(__file__).with_name("cache") / "acme-edge.json"
DRAFT_TOKENS = 2048  # a complete pack is ~1,000 tokens


class DraftUnavailable(Exception):
    pass


@dataclass
class ParserDraft:
    origin: str              # llm_live | llm_cached | hand_authored
    model: str | None
    generated_at: int | None
    yaml: str


def strip_fences(text: str) -> str:
    return clean_sql(text)  # same cleanup: trim, drop ``` fences


class CachedDraftSource:
    def __init__(self, cache: Path = CACHE):
        self.cache = cache

    async def draft(self, group_id: str, train_lines: list[str], shape_signature: str = "") -> ParserDraft:
        if not self.cache.exists():
            raise DraftUnavailable("No cached draft. Run `make prebake` before recording.")
        d = json.loads(self.cache.read_text(encoding="utf-8"))
        if shape_signature and d.get("group_shape") != shape_signature:
            raise DraftUnavailable(f"No cached draft for shape {shape_signature}.")
        return ParserDraft(d["origin"], d.get("model"), d.get("generated_at"), d["yaml"])


class LlmDraftSource:
    def __init__(self, llm, timeout_s: float = 300):
        self.llm, self.timeout_s = llm, timeout_s

    async def draft(self, group_id: str, train_lines: list[str], shape_signature: str = "") -> ParserDraft:
        out = await self.llm.complete("", drafting_prompt(train_lines), self.timeout_s, num_predict=DRAFT_TOKENS)
        if not out:
            raise DraftUnavailable("The local LLM did not return a draft.")
        return ParserDraft("llm_live", self.llm.model, int(time.time() * 1000), strip_fences(out))
