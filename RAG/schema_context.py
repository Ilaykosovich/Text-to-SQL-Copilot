# app/rag/schema_context.py
"""
Builds schema_context for SQL generation from Chroma (schema RAG).

Assumptions about your indexed chunks (based on your build_chunks()):
- chunk_type in {"table_summary","table_comment","column","fk"}
- metadata fields:
  - table_summary/table_comment/column: schema_name, table_name
  - column: column_name
  - fk: from_schema, from_table, from_column, to_schema, to_table, to_column, constraint_name

Workflow:
1) Semantic search ONLY across table_summary chunks using analysis["search_queries"].
2) Pick top-N tables by best (lowest) distance.
3) For each selected table:
   - fetch all column chunks by metadata
   - fetch outgoing fk chunks by metadata
   - fetch table_comment by metadata (optional)
4) Return schema_context as a compact dict suitable for SQL-agent prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from RAG.chroma_store import ChromaStore
import logging



@dataclass
class RetrievalConfig:
    top_tables: int = 6                 # how many tables to include in schema_context
    per_query_summaries: int = 8        # how many summaries to fetch per search query
    max_columns_per_table: int = 150    # safety cap
    max_fks_per_table: int = 120        # safety cap


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _best_by_table(flat: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Dedupe by (schema_name, table_name) keeping the smallest distance.
    """
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for it in flat:
        key = (_safe_str(it.get("schema_name")), _safe_str(it.get("table_name")))
        if not key[0] or not key[1]:
            continue
        if key not in best or float(it["dist"]) < float(best[key]["dist"]):
            best[key] = it
    out = list(best.values())
    out.sort(key=lambda x: float(x["dist"]))
    return out


def retrieve_table_candidates(
    chroma: ChromaStore,
    analysis: Dict[str, Any],
    cfg: RetrievalConfig = RetrievalConfig(),
    extra_where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns table candidates:
    [{
      "schema_name": "...",
      "table_name": "...",
      "summary_doc": "...",
      "dist": 0.123
    }, ...]
    """
    search_queries = analysis.get("search_queries") or []
    if not search_queries:
        raise ValueError("analysis.search_queries is empty; cannot retrieve schema.")

    where = {"chunk_type": "table_summary"}
    if extra_where:
        where.update(extra_where)

    res = chroma.query(
        queries=search_queries,
        n_results=cfg.per_query_summaries,
        where=where,
    )

    flat: List[Dict[str, Any]] = []
    for qi in range(len(search_queries)):
        docs = (res.get("documents") or [[]])[qi]
        metas = (res.get("metadatas") or [[]])[qi]
        dists = (res.get("distances") or [[]])[qi]
        for doc, meta, dist in zip(docs, metas, dists):
            flat.append({
                "schema_name": meta.get("schema_name"),
                "table_name": meta.get("table_name"),
                "summary_doc": doc,
                "dist": float(dist),
            })

    best = _best_by_table(flat)
    return best[: cfg.top_tables]


def _first_table_comment_text(chroma: ChromaStore, schema: str, table: str) -> str:
    try:

        res = chroma.get_by_metadata(
            where={
                "chunk_type": "table_comment",
                "schema_name": schema,
                "table_name": table,
            },
            limit=10,
        )
    except Exception as e:
        logger = logging.getLogger("orchestrator")
        logger.warning(
            "chroma_get_failed",
            extra={
                "schema": schema,
                "table": table,
                "error": str(e),
            },
        )
        return ""

    docs = res.get("documents") or []
    return docs[0] if docs else ""



def _columns_for_table(chroma: ChromaStore, schema: str, table: str, limit: int) -> List[Dict[str, Any]]:
    res = chroma.get_by_metadata(
        where={"chunk_type": "column", "schema_name": schema, "table_name": table},
        limit=limit,
    )
    docs = res.get("documents") or []
    metas = res.get("metadatas") or []

    cols: List[Dict[str, Any]] = []
    for doc, meta in zip(docs, metas):
        cols.append({
            "column_name": meta.get("column_name"),
            "doc": doc,  # already includes type/nullable/default/description
        })

    # stable sort: by column_name
    cols.sort(key=lambda x: _safe_str(x.get("column_name")).lower())
    return cols


def _outgoing_fks_for_table(chroma: ChromaStore, schema: str, table: str, limit: int) -> List[Dict[str, Any]]:
    res = chroma.get_by_metadata(
        where={"chunk_type": "fk", "from_schema": schema, "from_table": table},
        limit=limit,
    )
    metas = res.get("metadatas") or []

    fks: List[Dict[str, Any]] = []
    for m in metas:
        fks.append({
            "from": f'{m.get("from_schema")}.{m.get("from_table")}.{m.get("from_column")}',
            "to": f'{m.get("to_schema")}.{m.get("to_table")}.{m.get("to_column")}',
            "constraint_name": m.get("constraint_name"),
        })
    return fks


def build_schema_context(
    chroma: ChromaStore,
    analysis: Dict[str, Any],
    cfg: RetrievalConfig = RetrievalConfig(),
    extra_where: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main entry point. Returns:
    {
      "tables": [
        {
          "name": "schema.table",
          "summary": "...",            # table_summary doc
          "description": "...",        # table_comment doc (optional)
          "columns": [{"column_name": "...", "doc": "..."}],
          "foreign_keys_outgoing": [{"from": "...", "to": "...", "constraint_name": "..."}]
        }
      ],
      "relationships": [...],         # flattened FK list
      "retrieval_debug": {
        "selected_tables": [{"schema_name":"...","table_name":"...","dist":0.12}]
      }
    }
    """
    table_candidates = retrieve_table_candidates(
        chroma=chroma,
        analysis=analysis,
        cfg=cfg,
        extra_where=extra_where,
    )

    schema_context: Dict[str, Any] = {
        "tables": [],
        "relationships": [],
        "retrieval_debug": {"selected_tables": []},
    }

    for cand in table_candidates:
        schema = _safe_str(cand["schema_name"])
        table = _safe_str(cand["table_name"])

        schema_context["retrieval_debug"]["selected_tables"].append({
            "schema_name": schema,
            "table_name": table,
            "dist": float(cand["dist"]),
        })

        description = _first_table_comment_text(chroma, schema, table)
        columns = _columns_for_table(chroma, schema, table, limit=cfg.max_columns_per_table)
        fks = _outgoing_fks_for_table(chroma, schema, table, limit=cfg.max_fks_per_table)

        schema_context["tables"].append({
            "name": f"{schema}.{table}",
            "summary": cand.get("summary_doc", ""),
            "description": description,
            "columns": columns,
            "foreign_keys_outgoing": fks,
        })

        schema_context["relationships"].extend(fks)

    return schema_context


def compact_for_prompt(schema_context: Dict[str, Any]) -> Dict[str, Any]:
    tables_out = []

    try:
        tables = schema_context.get("tables", {})
        # поддержка и list, и dict
        if isinstance(tables, dict):
            iterable = tables.values()
        else:
            iterable = tables

        for t in iterable:
            try:
                columns = []
                for c in (t.get("columns") or []):
                    # кладём ТОЛЬКО имя колонки
                    col_name = c.get("name")
                    if col_name:
                        columns.append(col_name)

                tables_out.append({
                    "name": f'{t.get("schema","")}.{t.get("name","")}'.strip("."),
                    "description": t.get("description", ""),
                    "summary": t.get("summary", ""),
                    "columns": columns,
                    "foreign_keys_outgoing": t.get("foreign_keys_outgoing", []),
                })
            except Exception:
                # пропускаем одну кривую таблицу, но не валим весь запрос
                continue

    except Exception:
        # вообще что-то пошло не так
        return {"tables": [], "relationships": []}

    return {
        "tables": tables_out,
        "relationships": schema_context.get("relationships", []),
    }


