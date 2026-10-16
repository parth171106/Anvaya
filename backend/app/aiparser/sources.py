"""Draft sources with explicit provenance; bundled templates never masquerade as AI output."""
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.aiparser.prompt import drafting_prompt
from app.search.llm import clean_sql

CACHE = Path(__file__).with_name("cache") / "acme-edge.json"
EDGE_TEMPLATE = Path(__file__).with_name("acme-edge.fallback.yaml")
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
            raise DraftUnavailable("The local parser-drafting model did not return a draft. Check Ollama and its "
                                   "configured model, then retry. Gemini search is a separate feature; "
                                   "quarantined records remain sealed.")
        return ParserDraft("llm_live", self.llm.model, int(time.time() * 1000), strip_fences(out))


class LiveDraftSource:
    """Offer the known EDGE template locally; other formats require configured Ollama."""

    def __init__(self, llm):
        self.llm = llm

    async def draft(self, group_id: str, train_lines: list[str], shape_signature: str = "") -> ParserDraft:
        if shape_signature == "EDGE|x12" and train_lines and all(self._edge_line(line) for line in train_lines):
            # Explicit known-format mapping, not inference from delimiter/field count alone.
            text = EDGE_TEMPLATE.read_text(encoding="utf-8").replace("origin: ai_draft", "origin: user", 1)
            return ParserDraft("hand_authored", None, None, text)
        if not await self.llm.ready():
            raise DraftUnavailable("No bundled parser template matches this format, and the local parser-drafting "
                                   "model is unavailable. Configure Ollama and its model on the ANVAYA server, "
                                   "then retry. Gemini search does not draft parsers. Your records remain sealed.")
        return await LlmDraftSource(self.llm).draft(group_id, train_lines, shape_signature)

    @staticmethod
    def _edge_line(line: str) -> bool:
        fields = line.split("|")
        return (len(fields) == 12 and fields[0] == "EDGE" and fields[3] == "SESSION"
                and fields[4] in {"ALLOW", "DENY"} and fields[10].startswith("bytes=")
                and fields[11].startswith("rule="))
