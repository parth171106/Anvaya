"""SearchService.answer (TRD.md §12.1, FL-07): template match → LLM (guarded) → template fallback → 422."""
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.search import sql_guard
from app.search.llm import clean_sql
from app.search.prompt import SYSTEM, user_message
from app.search.templates import match_template

log = logging.getLogger("anvaya.search")


class Unanswerable(Exception):
    pass


class QueryTimeout(Exception):
    pass


class SearchService:
    def __init__(self, repo, llm, clock, cfg):
        self.repo, self.llm, self.clock, self.cfg = repo, llm, clock, cfg

    def caption(self, now_ms: int) -> str:
        t = datetime.fromtimestamp(now_ms / 1000, ZoneInfo(self.cfg.display_tz))
        return f"now = {t:%H:%M:%S} IST ({self.clock.label()})"

    async def answer(self, question: str) -> dict:
        t0 = time.perf_counter()
        hit = match_template(question)
        now = self.clock.now_ms()
        result = None
        if await self.llm.ready():
            raw = await self.llm.complete(SYSTEM, user_message(question), self.cfg.llm_timeout_s)
            if raw:
                g = sql_guard.check(clean_sql(raw))
                if g.ok:
                    try:
                        cols, rows = self.repo.execute_readonly(g.normalized_sql, {"now_ms": now}, 2.0)
                        result = ("llm", self.cfg.ollama_model, g.normalized_sql, cols, rows)
                    except Exception as e:
                        log.info("llm sql failed to execute: %s", e)
                else:
                    log.info("llm sql rejected by guard: %s", g.reason)
        if result is None and hit is not None:
            try:
                cols, rows = self.repo.execute_readonly(hit.sql, {"now_ms": now}, 2.0)
            except TimeoutError:
                raise QueryTimeout()
            result = ("template", None, hit.sql, cols, rows)
        if result is None:
            raise Unanswerable()
        engine, model, sql, cols, rows = result
        out = {"question": question, "engine": engine, "model": model, "sql": sql, "params": {"now_ms": now},
               "clock_caption": self.caption(now), "columns": cols, "rows": rows, "row_count": len(rows),
               "took_ms": round((time.perf_counter() - t0) * 1000)}
        self.repo.audit(self.clock.now_ms(), "analyst@ntro-demo", "search.ask", None,
                        {"question": question, "engine": engine, "sql": sql, "row_count": len(rows)})
        return out

