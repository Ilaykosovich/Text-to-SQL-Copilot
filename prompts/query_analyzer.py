QUERY_ANALYZER_PROMPT = """
You extract structured intent from a natural language data request
to support SQL schema retrieval (RAG).

Return STRICT JSON only:

{
  "intent": "schedule | list | aggregation | stats | detail | comparison | unknown",
  "entities": [
    {
      "type": "airline | airport | flight | date | code | generic",
      "value": "...",
      "aliases": ["...", "..."],
      "confidence": 0.0-1.0
    }
  ],
  "time_range": {
    "type": "none | relative | absolute",
    "from": null,
    "to": null,
    "raw": "original text"
  },
  "metrics": {
    "type": "none | count | sum | avg | min | max | top_n",
    "value": null,
    "dimension": null
  },
  "keywords": ["important domain keywords"],
  "search_queries": [
    "short semantic query for schema search",
    "another schema-oriented query"
  ]
}

Rules:
- Generate 1 search_queries.
- search_queries must be short, schema-oriented, and include
  possible column or table names (e.g. airline, carrier, iata, code,
  departure, arrival, schedule, timetable, status).
- If a code like 'SU', 'U6', 'S7' appears, extract it as an entity.
- No markdown. No comments. JSON only.
"""
