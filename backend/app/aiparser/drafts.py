"""Draft → test gates → approve/reject (TRD.md API 15–19, FL-08 steps 3–5)."""
import json

from app.core.ids import seq_id
from app.parsers.registry import Pack, PackError
from app.parsers.syslog_header import split
from app.pipeline.worker import normalize
from generator.br01 import HOLDOUT


class DraftError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _no_validate(_):
    return None


def run_gates(yaml_text: str, lines: list[str], holdout, enums, validate) -> dict:
    """The four checks: held-out lines, all lines, round-trip, OCSF validity. promotable only if all are 100%."""
    n, hold = len(lines), [i for i in holdout if i < len(lines)]
    failures, samples, parse_ok, rt_ok, ocsf_ok, coverages = [], [], set(), set(), set(), []
    try:
        pack = Pack(yaml_text)
    except PackError as e:
        failures.append({"index": -1, "check": "load", "detail": str(e)})
        pack = None
    for i, line in enumerate(lines if pack else []):
        data = line.encode("utf-8")
        if not pack.detects(split(line), line):
            failures.append({"index": i, "check": "detect", "detail": "the draft's detect block does not match"})
            continue
        out = normalize(data, "r-000000000000", i + 1, 0, "utf-8", None, enums, _no_validate, pack=pack)
        if out.event is None:
            failures.append({"index": i, "check": "parse", "detail": f"{out.reason}: {out.detail}"})
            continue
        parse_ok.add(i)
        rt = out.event.anvaya.roundtrip
        coverages.append(rt.coverage)
        if rt.ok:
            rt_ok.add(i)
        else:
            failures.append({"index": i, "check": "roundtrip", "detail": f"{rt.model_dump()}"})
        err = validate(out.event.ocsf)
        if err is None:
            ocsf_ok.add(i)
        else:
            failures.append({"index": i, "check": "ocsf", "detail": err})
        if i in hold:
            samples.append({"index": i, "raw": line, "ocsf": out.event.ocsf,
                            "lineage": [e.model_dump() for e in out.event.anvaya.lineage]})
    good = parse_ok & rt_ok & ocsf_ok
    res = {"holdout": {"passed": len(good & set(hold)), "total": len(hold)},
           "all": {"passed": len(good), "total": n},
           "roundtrip": {"passed": len(rt_ok), "total": n, "min_coverage": min(coverages, default=0.0)},
           "ocsf_valid": {"passed": len(ocsf_ok), "total": n}, "failures": failures, "samples": samples}
    res["promotable"] = n > 0 and all(res[k]["passed"] == res[k]["total"] for k in ("holdout", "all", "roundtrip",
                                                                                     "ocsf_valid"))
    return res


class DraftService:
    def __init__(self, c, source):
        self.c, self.source = c, source

    def _row(self, draft_id: str):
        r = self.c.repo.con.execute("SELECT * FROM parser_drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if r is None:
            raise DraftError(404, "not_found", "Draft not found")
        return r

    def _lines(self, group_id: str) -> list[str]:
        ids = self.c.repo.quarantine_raw_ids(group_id)
        return [self.c.store.read(r).decode("utf-8", "replace") for r in ids]

    def view(self, draft_id: str) -> dict:
        r = self._row(draft_id)
        hold = json.loads(r["holdout_indexes"])
        test = json.loads(r["test_result"]) if r["test_result"] else None
        total = test["all"]["total"] if test else len(self.c.repo.quarantine_raw_ids(r["group_id"]))
        return {"draft_id": r["draft_id"], "group_id": r["group_id"], "status": r["status"], "origin": r["origin"],
                "model": r["model"], "generated_at": r["generated_at"], "yaml": r["yaml"],
                "train_count": total - len(hold), "holdout_count": len(hold), "holdout_indexes": hold,
                "test": test}

    async def create(self, group_id: str) -> dict:
        repo = self.c.repo
        groups = {g["group_id"]: g for g in repo.quarantine_groups()}
        if group_id not in groups:
            raise DraftError(404, "not_found", "Quarantine group not found")
        if repo.con.execute("SELECT 1 FROM parser_drafts WHERE group_id=? AND status IN ('drafted','tested')",
                            (group_id,)).fetchone():
            raise DraftError(409, "conflict", "A draft already exists for this group")
        lines = self._lines(group_id)
        hold = [i for i in HOLDOUT if i < len(lines)]
        train = [ln for i, ln in enumerate(lines) if i not in hold]
        d = await self.source.draft(group_id, train, groups[group_id]["shape_signature"])
        n = repo.con.execute("SELECT COUNT(*) FROM parser_drafts").fetchone()[0] + 1
        draft_id = seq_id("dr", n)
        repo.con.execute("INSERT INTO parser_drafts(draft_id, group_id, status, origin, model, generated_at, yaml,"
                         " holdout_indexes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (draft_id, group_id, "drafted", d.origin, d.model, d.generated_at, d.yaml, json.dumps(hold),
                          self.c.clock.now_ms()))
        out = self.view(draft_id)
        out.pop("test")
        return out

    def test(self, draft_id: str) -> dict:
        r = self._row(draft_id)
        if r["status"] in ("approved", "rejected"):
            raise DraftError(409, "conflict", f"Draft is {r['status']}")
        res = {"draft_id": draft_id, **run_gates(r["yaml"], self._lines(r["group_id"]),
                                                 json.loads(r["holdout_indexes"]), self.c.enums, self.c.validate)}
        self.c.repo.con.execute("UPDATE parser_drafts SET status='tested', test_result=?, promotable=? WHERE draft_id=?",
                                (json.dumps(res, separators=(",", ":")), int(res["promotable"]), draft_id))
        return res

    def approve(self, draft_id: str, approved_by: str) -> dict:
        c, r = self.c, self._row(draft_id)
        if r["status"] != "tested" or not r["promotable"]:
            raise DraftError(409, "not_promotable", "All four checks must pass 100% before approval.")
        pack = Pack(r["yaml"])
        packs_dir = c.cfg.data_dir / "packs"
        packs_dir.mkdir(parents=True, exist_ok=True)
        (packs_dir / f"{pack.name}.yaml").write_text(r["yaml"], encoding="utf-8")
        c.registry.reload()
        now = c.clock.now_ms()
        with c.repo.tx():
            c.repo.upsert_parser(pack, "ai_draft", approved_by, now)
            c.repo.con.execute("UPDATE parser_drafts SET status='approved', decided_by=?, decided_at=? WHERE draft_id=?",
                               (approved_by, now, draft_id))
            c.repo.audit(now, approved_by, "parser.approve", pack.id, {"draft_id": draft_id, "group_id": r["group_id"]})
        replay_id, queued = c.replays.start(c.repo.quarantine_raw_ids(r["group_id"]))
        c.publish("parser.approved", {"name": pack.name, "version": pack.version, "group_id": r["group_id"],
                                      "replay_id": replay_id})
        return {"parser": {"name": pack.name, "version": pack.version, "status": "active"}, "replay_id": replay_id,
                "queued": queued}

    def reject(self, draft_id: str, reason: str) -> dict:
        r = self._row(draft_id)
        if r["status"] in ("approved", "rejected"):
            raise DraftError(409, "conflict", f"Draft is already {r['status']}")
        now = self.c.clock.now_ms()
        with self.c.repo.tx():
            self.c.repo.con.execute("UPDATE parser_drafts SET status='rejected', reject_reason=?, decided_by=?,"
                                    " decided_at=? WHERE draft_id=?", (reason, "analyst@ntro-demo", now, draft_id))
            self.c.repo.audit(now, "analyst@ntro-demo", "parser.reject", draft_id, {"reason": reason})
        return {"draft_id": draft_id, "status": "rejected"}

