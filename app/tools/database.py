"""Database query tool (FR-30, NFR-6, D4, S1:201-208).

The LLM turns the user's question into ONE SQLite SELECT, and this tool runs
it on `sample.db` (decision C1: S1 says "natural language" as input; here the
LLM is the translator). Security comes in layers (D4), so one mistake isn't
enough to change data:

1. `sample.db` is a separate file: the app's conversations are not in it.
2. The connection is read-only (`mode=ro`): SQLite refuses every write.
3. An authorizer callback: SQLite asks it before every action a statement
   would do, and only SELECT, READ and FUNCTION are allowed. So INSERT,
   UPDATE, DELETE, DROP, CREATE, ATTACH, PRAGMA (and recursive queries)
   are rejected before they run.
4. Python's `sqlite3` refuses more than one statement per `execute`.
5. At most 100 rows, and a 2 s time limit through the progress handler.

Each call opens its own connection, so calls on different threads (the
executor's pool) never share one.
"""

import sqlite3
import time
from contextlib import closing
from pathlib import Path

from app.tools.base import Tool, ToolError

ROW_LIMIT = 100
TIME_LIMIT_S = 2
ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}

DESCRIPTION = (
    "Run ONE read-only SQLite SELECT on the store database. Tables: "
    "users(id, name, email, country, created_at), products(id, name, category, price), "
    "orders(id, user_id, order_date, status, total), "
    "order_items(id, order_id, product_id, quantity, unit_price). "
    "Use date('now', ...) for relative dates."
)


def _authorizer(action, *args):
    return sqlite3.SQLITE_OK if action in ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Layer 2: a connection that refuses every write, even without the authorizer."""
    # A URI turns on `mode=ro`. as_uri() also escapes spaces in the path.
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def run_query(sql: str, db_path: Path) -> dict:
    deadline = time.monotonic() + TIME_LIMIT_S
    timed_out = False

    def stop_if_too_slow():
        # SQLite calls this every 1000 steps; a true value aborts the query.
        nonlocal timed_out
        timed_out = time.monotonic() > deadline
        return timed_out

    try:
        with closing(open_read_only(db_path)) as conn:
            conn.set_authorizer(_authorizer)
            conn.set_progress_handler(stop_if_too_slow, 1000)
            cursor = conn.execute(sql)
            # One row more than the limit tells us whether more exist.
            rows = cursor.fetchmany(ROW_LIMIT + 1)
            columns = [col[0] for col in cursor.description or []]
    except sqlite3.Error as exc:
        if timed_out:
            raise ToolError(f"Query took longer than {TIME_LIMIT_S}s and was stopped") from None
        if "not authorized" in str(exc):
            raise ToolError("Query rejected: only one read-only SELECT is allowed") from None
        raise ToolError(f"Query failed: {exc}") from None

    truncated = len(rows) > ROW_LIMIT
    rows = [list(row) for row in rows[:ROW_LIMIT]]
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}


def make_tool(db_path: Path) -> Tool:
    """The tool for one sample DB file. app/main.py passes the configured path."""

    def run(sql: str) -> dict:
        return run_query(sql, db_path)

    return Tool(
        name="database_query",
        description=DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "One SQLite SELECT statement",
                    "maxLength": 2000,
                }
            },
            "required": ["sql"],
        },
        run=run,
    )
