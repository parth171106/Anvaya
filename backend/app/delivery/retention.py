"""CERT-In retention report (SIM: fixed wording, real counts). It says "supports" and never claims certification."""

STATEMENT = "ANVAYA's tamper-evident retention supports CERT-In's 180-day log retention requirement."
NOTE = "Synthetic lab data. Coverage reflects records held in this vault."


def build_report(repo, now_ms: int, demo_mode: bool = True) -> dict:
    sources = [{"device": r["device"], "oldest": r["oldest"], "newest": r["newest"], "records": r["records"],
                "sealed": r["unsealed"] == 0} for r in repo.con.execute(
        "SELECT e.device, MIN(e.time) AS oldest, MAX(e.time) AS newest, COUNT(*) AS records,"
        " SUM(r.batch_id IS NULL) AS unsealed FROM events e JOIN raw_events r USING(raw_id)"
        " GROUP BY e.device ORDER BY e.device")]
    last = repo.get_meta("last_verify")
    return {"generated": now_ms, "statement": STATEMENT, "retention_target_days": 180, "sources": sources,
            "ledger": {"verdict": last["verdict"] if last else None, "last_verified": last["at"] if last else None},
            "note": NOTE if demo_mode else "Live ingestion. Coverage reflects records held in this vault; the retention target is not an enforced retention policy."}
