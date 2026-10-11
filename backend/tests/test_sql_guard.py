import pytest

from app.search.sql_guard import check
from app.search.templates import SUGGESTIONS, match_template


@pytest.mark.parametrize("sql", [
    "DROP TABLE events",
    "UPDATE events SET device = 'x'",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA table_info(events)",
    "SELECT time FROM events; SELECT time FROM events",
    "SELECT time FROM raw_events",
    "SELECT name FROM sqlite_master",
    "SELECT ocsf_json FROM events",
    "SELECT * FROM events",
    "SELECT time FROM events WHERE device = :other",
    "SELECT CAST(time AS TEXT) FROM events",
    "SELECT load_extension('x') FROM events",
    "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT x FROM r",
    "SELECT time FROM events e JOIN raw_events r ON e.time = r.received_at",
    "DELETE FROM events",
    "SELECT time FROM main.events",
])
def test_rejects(sql):
    assert not check(sql).ok


def test_allows_template_sql_unchanged():
    for q in SUGGESTIONS + ["How many events did each device send?"]:
        sql = match_template(q).sql
        g = check(sql)
        assert g.ok and g.normalized_sql == sql, (q, g.reason)


def test_enforces_limit_200():
    assert check("SELECT time, device FROM events").normalized_sql.endswith("LIMIT 200")
    assert check("SELECT time FROM events LIMIT 5000").normalized_sql.endswith("LIMIT 200")
    assert check("SELECT time FROM events LIMIT 10").normalized_sql == "SELECT time FROM events LIMIT 10"


def test_allows_functions_aliases_and_strings_with_keywords():
    assert check("SELECT device, COUNT(*) AS n, MAX(time) FROM events WHERE title LIKE '%DROP%' GROUP BY device"
                 " ORDER BY n DESC LIMIT 5").ok
    assert check("SELECT STRFTIME('%H', time / 1000, 'unixepoch') AS h, COUNT(*) AS n FROM events GROUP BY h").ok
    assert check("WITH x AS (SELECT src_ip FROM events) SELECT src_ip FROM x").ok
