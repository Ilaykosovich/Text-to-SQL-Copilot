
from typing import Any, Dict, List, Optional, Tuple
import json
from langchain_core.messages import SystemMessage, HumanMessage


def _safe_json_loads(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None



async def select_relevant_schema_with_llm(
    llm,
    analysis: dict,
    schema_full: Dict[str, Any],
    *,
    max_tables: int = 20,
) -> Dict[str, Any]:

    def render_schema_brief(schema_full: Dict[str, Any]) -> str:
        lines = []
        for fq, t in schema_full["tables"].items():
            cols = t["columns"][:12]
            cols_s = ", ".join(f'{c["name"]}:{c["type"]}' for c in cols)
            desc = (t.get("description") or "").strip()
            if desc:
                lines.append(f"- {fq} — {desc} | cols: {cols_s}")
            else:
                lines.append(f"- {fq} | cols: {cols_s}")

        if schema_full.get("foreign_keys"):
            lines.append("\nForeign keys:")
            for fk in schema_full["foreign_keys"][:200]:
                lines.append(
                    f'- {fk["from"]}.{fk["from_column"]} -> '
                    f'{fk["to"]}.{fk["to_column"]}'
                )

        return "\n".join(lines)

    schema_text = render_schema_brief(schema_full)

    system_prompt = """
You are an expert SQL architect.

Your job is to select which database tables are relevant
for answering a user request.

You MUST return valid JSON and nothing else.
""".strip()

    human_prompt = f"""
analysis (JSON):
{json.dumps(analysis, ensure_ascii=False)}

database schema:
{schema_text}

Return STRICT JSON with this shape:
{{
  "tables": ["schema.table"],
  "also_consider": ["schema.table"],
  "reason": "short explanation",
  "confidence": 0.0
}}

Rules:
- Up to {max_tables} tables max
- Prefer core fact tables and required join tables
- If unsure, include fewer tables
""".strip()

    # 🔹 ВОТ ЗДЕСЬ НУЖНАЯ ЧАСТЬ 🔹
    res = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])

    # LangChain может вернуть AIMessage или строку
    llm_text = (
        res.content
        if hasattr(res, "content")
        else str(res)
    )

    # --- дальше без изменений ---
    try:
        obj = json.loads(llm_text)
    except Exception:
        obj = {}

    requested = obj.get("tables") or []
    also = obj.get("also_consider") or []

    all_tables = set(schema_full["tables"].keys())

    picked = [t for t in requested if t in all_tables]
    picked_also = [t for t in also if t in all_tables and t not in picked]

    if not picked:
        picked = list(all_tables)[:max_tables]

    keep = set(picked) | set(picked_also)

    filtered_tables = {
        fq: schema_full["tables"][fq]
        for fq in picked
    }

    filtered_fks = [
        fk for fk in schema_full.get("foreign_keys", [])
        if fk["from"] in keep and fk["to"] in keep
    ]

    return {
        "tables": filtered_tables,
        "foreign_keys": filtered_fks,
        "retrieval_debug": {
            "mode": "llm_schema_select",
            "llm_raw": llm_text,
            "picked": picked,
            "picked_also": picked_also,
            "confidence": obj.get("confidence"),
            "reason": obj.get("reason"),
        },
    }
