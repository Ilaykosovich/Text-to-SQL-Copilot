import pytest

from RAG.chroma_store import ChromaStore
from RAG.schema_context import build_schema_context, RetrievalConfig
from pathlib import Path

@pytest.mark.integration
def test_build_schema_context_returns_tables():
    ROOT = Path(__file__).resolve().parents[1]  # .../Orchestrator
    PERSIST_DIR = ROOT / "chroma_db"  # .../Orchestrator/chroma_db
    print("persist_dir:", PERSIST_DIR)
    print("exists:", PERSIST_DIR.exists())
    chroma = ChromaStore(persist_dir=PERSIST_DIR, collection_name="pg_schema")
    count = chroma._collection.count()
    print("CHROMA COUNT:", count)
    assert count > 0, "Chroma collection is empty"

    analysis = {
        "entities": [
            {"aliases": ["Аэрофлот", "Аэрофлот SU"], "confidence": 0.98, "type": "airline", "value": "SU"},
            {"aliases": ["SU"], "confidence": 0.98, "type": "code", "value": "SU"},
        ],
        "intent": "schedule",
        "keywords": ["расписание", "рейсы", "авиакомпания", "SU", "Аэрофлот", "timetable", "schedule"],
        "metrics": {"dimension": None, "type": "none", "value": None},
        "search_queries": [
            "flight schedule airline SU carrier_code departure_date timetable",
            "FlightSchedules carrier_code SU",
            "HistoryFlights Airline SU",
        ],
        "time_range": {"from": None, "raw": "до даты 2026-03-13", "to": "2026-03-13", "type": "absolute"},
    }

    cfg = RetrievalConfig(top_tables=5, per_query_summaries=10)

    schema_full = build_schema_context(chroma, analysis, cfg=cfg)

    # Если пусто — покажем, что именно выбрал retriever (очень помогает дебажить)
    if not schema_full.get("tables"):
        debug = schema_full.get("retrieval_debug", {})
        pytest.fail(f"No tables returned. retrieval_debug={debug}")

    # Минимальные sanity checks
    assert isinstance(schema_full["tables"], list)
    assert len(schema_full["tables"]) > 0
    assert "name" in schema_full["tables"][0]

if __name__ == "__main__":
    test_build_schema_context_returns_tables()

