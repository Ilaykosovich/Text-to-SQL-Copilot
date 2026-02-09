from __future__ import annotations

from typing import Dict
import psycopg
import chromadb
from chromadb.config import Settings

# import these from your existing module
from DB.build_vector_store import Section, build_chunks, save_to_chroma
from chromadb.types import Database, Tenant, Collection
from typing import Any, Dict, List, Optional, Tuple

# Reuse your existing QUERIES dict exactly as before
QUERIES = {
    "tables": """
        select table_schema, table_name
        from information_schema.tables
        where table_type = 'BASE TABLE'
          and table_schema not in ('pg_catalog', 'information_schema')
        order by table_schema, table_name;
    """,
    "columns": """
        select
          table_schema,
          table_name,
          ordinal_position,
          column_name,
          data_type,
          is_nullable,
          column_default
        from information_schema.columns
        where table_schema not in ('pg_catalog', 'information_schema')
        order by table_schema, table_name, ordinal_position;
    """,
    "table_comments": """
        select
          n.nspname as schema_name,
          c.relname as table_name,
          obj_description(c.oid, 'pg_class') as table_description
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where c.relkind = 'r'
          and n.nspname not in ('pg_catalog', 'information_schema')
        order by schema_name, table_name;
    """,
    "column_comments": """
        select
          n.nspname as schema_name,
          c.relname as table_name,
          a.attname as column_name,
          col_description(c.oid, a.attnum) as column_description
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid
        where c.relkind = 'r'
          and n.nspname not in ('pg_catalog', 'information_schema')
          and a.attnum > 0
          and not a.attisdropped
        order by schema_name, table_name, a.attnum;
    """,
    "foreign_keys": """
        select
          n1.nspname as from_schema,
          c1.relname as from_table,
          a1.attname as from_column,
          n2.nspname as to_schema,
          c2.relname as to_table,
          a2.attname as to_column,
          con.conname as constraint_name
        from pg_constraint con
        join pg_class c1 on c1.oid = con.conrelid
        join pg_namespace n1 on n1.oid = c1.relnamespace
        join pg_class c2 on c2.oid = con.confrelid
        join pg_namespace n2 on n2.oid = c2.relnamespace
        join lateral unnest(con.conkey) with ordinality as k1(attnum, ord) on true
        join lateral unnest(con.confkey) with ordinality as k2(attnum, ord) on k1.ord = k2.ord
        join pg_attribute a1 on a1.attrelid = c1.oid and a1.attnum = k1.attnum
        join pg_attribute a2 on a2.attrelid = c2.oid and a2.attnum = k2.attnum
        where con.contype = 'f'
          and n1.nspname not in ('pg_catalog', 'information_schema')
        order by from_schema, from_table, constraint_name;
    """,
}


def _fetch_section(conn: psycopg.Connection, section_name: str, sql: str) -> Section:
    with conn.cursor() as cur:
        cur.execute(sql)
        colnames = [d.name for d in cur.description]
        rows = cur.fetchall()

    # build_chunks expects rows as List[List[str]]
    str_rows = [["" if v is None else str(v) for v in row] for row in rows]
    return Section(name=section_name, columns=colnames, rows=str_rows)


def _fetch_all(conn: psycopg.Connection, sql: str) -> List[Tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()

def build_schema_context_from_db(
    pg_url: str,
    *,
    statement_timeout_seconds: int = 30,
) -> Dict[str, Any]:
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"set statement_timeout = '{statement_timeout_seconds}s';")

        tables = _fetch_all(conn, QUERIES["tables"])
        columns = _fetch_all(conn, QUERIES["columns"])
        table_comments = _fetch_all(conn, QUERIES["table_comments"])
        column_comments = _fetch_all(conn, QUERIES["column_comments"])
        fks = _fetch_all(conn, QUERIES["foreign_keys"])

    # индексы комментариев для быстрого маппинга
    tbl_desc: Dict[Tuple[str, str], Optional[str]] = {
        (s, t): d for (s, t, d) in table_comments
    }
    col_desc: Dict[Tuple[str, str, str], Optional[str]] = {
        (s, t, c): d for (s, t, c, d) in column_comments
    }

    # соберём таблицы
    tables_map: Dict[str, Any] = {}
    for (schema, table) in tables:
        fq = f"{schema}.{table}"
        tables_map[fq] = {
            "schema": schema,
            "name": table,
            "description": tbl_desc.get((schema, table)),
            "columns": [],
        }

    # добавим колонки
    for (schema, table, pos, col, dtype, is_nullable, default) in columns:
        fq = f"{schema}.{table}"
        if fq not in tables_map:
            continue
        tables_map[fq]["columns"].append({
            "ordinal_position": int(pos),
            "name": col,
            "type": dtype,
            "nullable": (is_nullable == "YES"),
            "default": default,
            "description": col_desc.get((schema, table, col)),
        })

    foreign_keys: List[Dict[str, str]] = []
    for (fs, ft, fc, ts, tt, tc, cn) in fks:
        foreign_keys.append({
            "from": f"{fs}.{ft}",
            "from_column": fc,
            "to": f"{ts}.{tt}",
            "to_column": tc,
            "constraint": cn,
        })

    return {
        "tables": tables_map,
        "foreign_keys": foreign_keys,
    }







def build_chroma_from_pg_url(
    pg_url: str,
    *,
    persist_dir: str = "./chroma_db",
    collection_name: str = "pg_schema",
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    statement_timeout_seconds: int = 30,
    reset_collection: bool = False,
) -> Collection:
    """
    Connects to Postgres using a URL/DSN string, exports schema metadata in-memory,
    builds chunks, and saves them into a persistent ChromaDB collection.
    """

    # 1) Connect to Postgres using the URL string
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"set statement_timeout = '{statement_timeout_seconds}s';")

        # 2) Build sections directly (no TXT)
        sections: Dict[str, Section] = {}
        for name, sql in QUERIES.items():
            sections[name.lower()] = _fetch_section(conn, name.lower(), sql)

    # 3) Chunk + embed + save to Chroma
    chunks = build_chunks(sections)

    # Optional: reset collection to avoid duplicate embeddings on repeated runs
    if reset_collection:
        client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass  # collection may not exist yet

    save_to_chroma(
        chunks=chunks,
        persist_dir=persist_dir,
        collection_name=collection_name,
        embedding_model=embedding_model,
    )

    # Optional: quick sanity check
    client = chromadb.PersistentClient(path=persist_dir, settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection(name=collection_name)
