"""Sample DB and database tool tests (T-10): FR-30, NFR-6, NFR-10."""

import sqlite3
import time
from datetime import date

import pytest

from app import sample_data
from app.tools import database
from app.tools.base import ToolError

SEED_DATE = date(2026, 11, 10)
TABLES = ["users", "products", "orders", "order_items"]

# Computed once when the seeder was written (seed date 2026-11-10, seed 7) and
# fixed here, so this test fails if the seed data ever changes (AC-36).
GOLDEN_OCTOBER_ORDERS = 40


@pytest.fixture
def sample_db(tmp_path):
    path = tmp_path / "sample.db"
    sample_data.seed_if_missing(path, SEED_DATE)
    return path


def dump(path):
    """Every row of every table, to compare two databases."""
    with sqlite3.connect(path) as conn:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in TABLES}


def counts(path):
    with sqlite3.connect(path) as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def test_ac_36_database_query(sample_db, tmp_path):
    tool = database.make_tool(sample_db)
    output = tool.run(
        sql="SELECT COUNT(*) FROM orders "
        "WHERE order_date >= '2026-10-01' AND order_date < '2026-11-01'"
    )
    assert output == {
        "columns": ["COUNT(*)"],
        "rows": [[GOLDEN_OCTOBER_ORDERS]],
        "row_count": 1,
        "truncated": False,
    }

    # Same seed date in a fresh file: identical data.
    other = tmp_path / "other.db"
    sample_data.seed_if_missing(other, SEED_DATE)
    assert dump(other) == dump(sample_db)

    # Orders cover the 12 months before the seed date (NFR-10).
    first, last = tool.run(sql="SELECT MIN(order_date), MAX(order_date) FROM orders")["rows"][0]
    assert "2025-11-10" <= first and last <= "2026-11-10"


def test_nfr_10_seeds_only_when_missing(sample_db):
    before = dump(sample_db)
    # An existing file is left alone, even with another seed date.
    sample_data.seed_if_missing(sample_db, date(2020, 1, 1))
    assert dump(sample_db) == before


def test_nfr_10_sample_sizes(sample_db):
    sizes = counts(sample_db)
    assert sizes["users"] == 50
    assert sizes["products"] == 30
    assert sizes["orders"] == 500
    assert sizes["order_items"] >= sizes["orders"]  # every order has at least one item


def test_ac_37_database_row_limit(sample_db):
    output = database.make_tool(sample_db).run(sql="SELECT * FROM orders")
    assert len(output["rows"]) == 100
    assert output["row_count"] == 100
    assert output["truncated"] is True
    assert output["columns"] == ["id", "user_id", "order_date", "status", "total"]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (name, email, country, created_at) VALUES ('x', 'x', 'x', 'x')",
        "UPDATE orders SET total = 0",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "CREATE TABLE evil (id INTEGER)",
        "ATTACH DATABASE 'app.db' AS app",
        "PRAGMA table_info(users)",
        "SELECT 1; SELECT 2",
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x < 3) "
        "SELECT count(*) FROM c",
        "SELECT * FROM conversations",
    ],
)
def test_ac_38_database_security(sample_db, sql):
    before = counts(sample_db)
    with pytest.raises(ToolError):
        database.make_tool(sample_db).run(sql=sql)
    assert counts(sample_db) == before


def test_ac_39_database_query_timeout(sample_db):
    start = time.perf_counter()
    with pytest.raises(ToolError) as exc:
        database.make_tool(sample_db).run(
            sql="SELECT count(*) FROM orders a, orders b, orders c, orders d"
        )
    assert time.perf_counter() - start < 3
    assert "2s" in str(exc.value)


def test_fr_30_relative_dates_work(sample_db):
    # date('now') needs the FUNCTION permission (D4).
    output = database.make_tool(sample_db).run(sql="SELECT date('now') IS NOT NULL")
    assert output["rows"] == [[1]]


def test_fr_30_tool_definition(sample_db):
    tool = database.make_tool(sample_db)
    assert tool.name == "database_query"
    assert tool.parameters["required"] == ["sql"]
    assert tool.parameters["properties"]["sql"]["maxLength"] == 2000
    for table in TABLES:
        assert table in tool.description


def test_fr_30_app_seeds_sample_db(tmp_path):
    from app.config import Settings
    from app.main import create_app

    def fixed_clock():
        from datetime import datetime, timezone

        return datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)

    app = create_app(Settings(data_dir=tmp_path), clock=fixed_clock)
    # The app seeds with the clock's date, so the data equals the test seed.
    expected = tmp_path / "expected.db"
    sample_data.seed_if_missing(expected, SEED_DATE)
    assert dump(tmp_path / "sample.db") == dump(expected)
    assert app.state.registry.get("database_query") is not None


def test_nfr_6_connection_is_read_only_by_itself(sample_db):
    # Layer 2 of D4 on its own (no authorizer): SQLite still refuses the write.
    from contextlib import closing

    with closing(database.open_read_only(sample_db)) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM orders")
    assert counts(sample_db)["orders"] == 500
