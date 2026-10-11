"""Structural allow-list for LLM-written SQL (TRD.md §12.3), enforced on the sqlglot AST, not by regex."""
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.tokens import Tokenizer

COLUMNS = {"time", "device", "vendor", "class_uid", "class_name", "src_ip", "src_port", "dst_ip", "dst_port",
           "user_name", "action", "status", "severity", "title"}
FUNCS = (exp.Count, exp.Sum, exp.Min, exp.Max, exp.Avg, exp.Lower, exp.Upper, exp.Substring, exp.Length, exp.Coalesce)
ANON_FUNCS = {"STRFTIME", "DATETIME", "SUBSTR"}
BANNED = {"PRAGMA", "ATTACH", "DETACH", "VACUUM", "INSERT", "UPDATE", "DELETE", "REPLACE", "DROP", "CREATE", "ALTER"}
MAX_LIMIT = 200


@dataclass
class GuardResult:
    ok: bool
    reason: str | None
    normalized_sql: str | None


def _fail(reason: str) -> GuardResult:
    return GuardResult(False, reason, None)


def check(sql: str) -> GuardResult:
    try:
        words = {t.text.upper() for t in Tokenizer().tokenize(sql) if t.token_type != sqlglot.TokenType.STRING}
    except Exception as e:
        return _fail(f"tokenize: {e}")
    if hit := words & BANNED:
        return _fail(f"keyword not allowed: {sorted(hit)[0]}")
    try:
        stmts = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as e:
        return _fail(f"parse: {str(e)[:120]}")
    if len(stmts) != 1:
        return _fail("exactly one statement is allowed")
    tree = stmts[0]
    if not isinstance(tree, exp.Select):
        return _fail("only SELECT is allowed")
    with_ = tree.args.get("with")
    if with_ is not None and with_.args.get("recursive"):
        return _fail("WITH RECURSIVE is not allowed")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        if t.name not in ({"events"} | ctes) or t.args.get("db") or t.args.get("catalog"):
            return _fail(f"table not allowed: {t.sql()}")
    if not any(t.name == "events" for t in tree.find_all(exp.Table)):
        return _fail("must read from events")
    aliases = {a.alias for a in tree.find_all(exp.Alias)}
    for col in tree.find_all(exp.Column):
        if col.table and col.table not in ({"events"} | ctes):
            return _fail(f"unknown table qualifier: {col.table}")
        if col.name not in COLUMNS and col.name not in aliases:
            return _fail(f"column not allowed: {col.name}")
    for star in tree.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            return _fail("SELECT * is not allowed; name the columns")
    for f in tree.find_all(exp.Func):
        if isinstance(f, (exp.Connector, exp.Binary)) or isinstance(f, FUNCS):
            continue
        if isinstance(f, exp.Anonymous) and f.name.upper() in ANON_FUNCS:
            continue
        return _fail(f"function not allowed: {f.sql_name() if not isinstance(f, exp.Anonymous) else f.name}")
    for p in tree.find_all(exp.Placeholder, exp.Parameter):
        if p.name != "now_ms":
            return _fail(f"parameter not allowed: {p.sql()}")
    limit = tree.args.get("limit")
    n = None
    if limit is not None:
        try:
            n = int(limit.expression.this) if limit.expression else None
        except (TypeError, ValueError):
            n = None
    if n is not None and 0 <= n <= MAX_LIMIT:
        return GuardResult(True, None, sql.strip().rstrip(";").strip())
    return GuardResult(True, None, tree.limit(MAX_LIMIT).sql(dialect="sqlite"))
