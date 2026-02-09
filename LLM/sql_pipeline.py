from langchain_core.messages import SystemMessage, HumanMessage
from DB.executor import run_sql, DBTimeoutError
from prompts.sql_generator import SQL_GENERATOR_PROMPT
from prompts.sql_fixer import SQL_FIXER_PROMPT
from langchain_core.language_models import BaseChatModel
import re
import json
import psycopg
from psycopg.errors import Error as PsycopgError
from typing import Dict, Any
from DB.format_pg_error import format_pg_error



def _is_select_only(sql: str) -> bool:
    s = sql.strip().lower()
    if not (s.startswith("select") or s.startswith("with")):
        return False
    banned = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke"]
    return not any(re.search(rf"\b{b}\b", s) for b in banned)


def _extract_json(text: str) -> str:
    text = (text or "").strip()

    # remove markdown fences if present
    if text.startswith("```"):
        text = text.split("```", 1)[1]
        text = text.rsplit("```", 1)[0]

    # fallback: extract first JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


async def _llm_generate(
    llm: BaseChatModel,
    user_text: str,
    schema_context: Dict[str, Any],
) -> Dict[str, Any]:
    res = await llm.ainvoke([
        SystemMessage(content=SQL_GENERATOR_PROMPT),
        HumanMessage(
            content=(
                "User request:\n"
                f"{user_text}\n\n"
                "schema_context:\n"
                f"{json.dumps(schema_context, ensure_ascii=False)}"
            )
        ),
    ])

    raw = (res.content or "").strip()
    clean = _extract_json(raw)

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"SQL generator returned invalid JSON.\nRaw:\n{raw}"
        ) from e


async def _llm_fix(
    llm: BaseChatModel,
    user_text: str,
    schema_context: Dict[str, Any],
    prev_sql: str,
    error_text: str,
) -> Dict[str, Any]:
    res = await llm.ainvoke([
        SystemMessage(content=SQL_FIXER_PROMPT),
        HumanMessage(
            content=(
                "User request:\n"
                f"{user_text}\n\n"
                "Schema context:\n"
                f"{json.dumps(schema_context, ensure_ascii=False)}\n\n"
                "Previous SQL:\n"
                f"{prev_sql}\n\n"
                "Database error:\n"
                f"{error_text}"
            )
        ),
    ])

    raw = (res.content or "").strip()
    clean = _extract_json(raw)

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"SQL fixer returned invalid JSON.\nRaw:\n{raw}"
        ) from e





async def execute_with_retries(
    llm: BaseChatModel,
    user_text: str,
    schema_context: Dict[str, Any],
    max_attempts: int = 5,
    preview_limit: int = 10,
    max_timeouts: int = 2,
) -> Dict[str, Any]:
    """
    Returns:
    {
      "ok": bool,
      "sql": "...",
      "rows_preview": [...],
      "attempts": [...],
      "error": "..."
    }
    """
    attempts = []
    timeouts = 0

    gen = await _llm_generate(llm, user_text, schema_context)

    sql = gen.get("sql_preview") or gen.get("sql") or gen.get("sql_full") or ""
    if not sql:
        return {"ok": False, "error": "LLM returned empty SQL.", "attempts": attempts}

    for _ in range(max_attempts):
        if not _is_select_only(sql):
            return {
                "ok": False,
                "error": "Refused: only SELECT or WITH queries are allowed.",
                "attempts": attempts,
            }

        try:
            rows = run_sql(sql, limit=preview_limit)
            return {
                "ok": True,
                "sql": sql,
                "rows_preview": rows[:10],
                "attempts": attempts,
            }

        except DBTimeoutError as e:
            timeouts += 1
            err = str(e)

            attempts.append({"sql": sql, "error": err})

            if timeouts >= max_timeouts:
                return {
                    "ok": False,
                    "error": "Query timed out. Please narrow filters or time range.",
                    "attempts": attempts,
                }

            fixed = await _llm_fix(llm, user_text, schema_context, sql, err)
            sql = fixed.get("sql") or sql
            attempts[-1]["fix_notes"] = fixed.get("fix_notes", "")

        except Exception as e:
            err = format_pg_error(e)
            attempts.append({"sql": sql, "error": err})

            if is_llm_fixable_sql_error(e):
                fixed = await _llm_fix(llm, user_text, schema_context, sql, err)
                sql = fixed.get("sql") or sql
                attempts[-1]["fix_notes"] = fixed.get("fix_notes", "")
            else:
                return {
                    "ok": False,
                    "error": err,
                    "attempts": attempts,
                }

    return {
        "ok": False,
        "error": "Failed after all retry attempts.",
        "attempts": attempts,
    }

def is_llm_fixable_sql_error(e: Exception) -> bool:
    """
    True if the error is likely caused by invalid SQL and can be fixed by rewriting it.
    """
    if isinstance(e, PsycopgError) and getattr(e, "sqlstate", None):
        return e.sqlstate[:2] in {
            "42",  # syntax error, undefined table/column
            "22",  # invalid input / type mismatch
            "23",  # constraint violation
        }
    return False




