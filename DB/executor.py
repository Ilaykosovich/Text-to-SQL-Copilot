import re
import logging
from typing import Dict, Any, List

import psycopg
from psycopg.rows import dict_row
from psycopg.errors import QueryCanceled

from API.config import settings
from DB.format_pg_error import format_pg_error


class DBTimeoutError(RuntimeError):
    pass


def run_sql(sql: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Executes a SELECT query with a hard statement_timeout and an enforced LIMIT
    (added if missing). Returns a list of dicts.
    """
    logger = logging.getLogger("orchestrator")

    sql_clean = sql.strip().rstrip(";")

    # enforce LIMIT for safety
    if not re.search(r"\blimit\b", sql_clean, flags=re.IGNORECASE):
        sql_clean = f"{sql_clean} LIMIT {int(limit)}"

    logger.info("Executing SQL query")
    logger.debug("SQL: %s", sql_clean)
    logger.debug("statement_timeout_ms=%s", settings.PG_STATEMENT_TIMEOUT_MS)

    try:
        with psycopg.connect(settings.DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('statement_timeout', %s, true);",
                    (str(int(settings.PG_STATEMENT_TIMEOUT_MS)),)
                )
                cur.execute(sql_clean)
                rows = list(cur.fetchall())
                return rows

    except QueryCanceled as e:
        logger.warning(
            "SQL execution timed out (statement_timeout_ms=%s). Error: %s",
            settings.PG_STATEMENT_TIMEOUT_MS,
            format_pg_error(e),
        )
        raise DBTimeoutError(format_pg_error(e)) from e

    except Exception:
        logger.exception("Unexpected database error while executing SQL")
        raise


def db_healthcheck() -> dict:
    """
    Safe healthcheck: SELECT 1 + server version.
    """
    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.execute("SHOW server_version;")
                version = cur.fetchone()[0]
        return {"ok": True, "server_version": version}
    except Exception as e:
        return {"ok": False, "error": str(e)}
