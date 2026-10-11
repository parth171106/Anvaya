"""Local LLM via Ollama (TRD.md §12.2). Never in the ingest path; every failure returns None."""
import logging
import re
import time

import httpx

log = logging.getLogger("anvaya.llm")
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def clean_sql(text: str) -> str:
    s = _FENCE.sub("", text.strip()).strip()
    if s.upper().startswith("SQL:"):
        s = s[4:].strip()
    return s


class OllamaClient:
    def __init__(self, url: str, model: str, ready_ttl_s: float = 5.0):
        self.url, self.model, self.ttl = url.rstrip("/"), model, ready_ttl_s
        self._ready: tuple[float, bool] = (0.0, False)

    async def ready(self) -> bool:
        """True if Ollama answers and has the model. Cached for a few seconds so search never waits on it."""
        at, ok = self._ready
        if time.monotonic() - at < self.ttl:
            return ok
        try:
            async with httpx.AsyncClient(timeout=0.5) as client:
                r = await client.get(f"{self.url}/api/tags")
            names = {m.get("name") for m in r.json().get("models", [])}
            ok = r.status_code == 200 and (self.model in names or f"{self.model}:latest" in names)
        except Exception:
            ok = False
        self._ready = (time.monotonic(), ok)
        return ok

    async def complete(self, system: str, user: str, timeout_s: float, num_predict: int = 256) -> str | None:
        """num_predict 256 is TRD §12.2's limit for search SQL; parser drafting passes a larger budget."""
        body = {"model": self.model, "messages": [{"role": "system", "content": system},
                                                  {"role": "user", "content": user}],
                "stream": False, "options": {"temperature": 0, "num_predict": num_predict}, "keep_alive": "30m"}
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(f"{self.url}/api/chat", json=body)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            log.info("llm unavailable: %s", type(e).__name__)
            return None

    async def warmup(self) -> None:
        from app.search.prompt import SYSTEM, user_message
        if await self.ready():
            await self.complete(SYSTEM, user_message("How many events did each device send?"), 60)
