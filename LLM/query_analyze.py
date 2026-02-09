from pydantic import BaseModel
from fastapi import APIRouter
from LLM.utils import to_lc_messages
from LLM.make_llm import make_llm
from store.SessionStore import ChatMessage,ChatRequest
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, Request
from prompts.query_analyzer import QUERY_ANALYZER_PROMPT
from observability.metrics import LLM_LATENCY,LLM_ERRORS_TOTAL
import time
import logging
from API.config import settings
import json
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

router = APIRouter()
logger = logging.getLogger("orchestrator")

class QueryAnalyzeResponse(BaseModel):
    session_id: str
    analysis: Dict[str, Any]
    used_model: Optional[str] = None

@router.post("/query_analyze", response_model=QueryAnalyzeResponse)
async def query_analyze(req: ChatRequest, request: Request):
    new_msgs = to_lc_messages(req.messages)

    last_user: HumanMessage | None = None
    for m in reversed(new_msgs):
        if isinstance(m, HumanMessage):
            last_user = m
            break

    if not last_user or not (last_user.content or "").strip():
        raise HTTPException(status_code=400, detail="No user message found")

    # если фиксируешь модель/температуру на бэке — не бери из req
    llm = make_llm(None, 0)  # model=None => settings.DEFAULT_LLM_MODEL
    prompt = [
        SystemMessage(content=QUERY_ANALYZER_PROMPT),
        HumanMessage(content=f"user request: {last_user.content.strip()}"),
    ]

    llm_start = time.perf_counter()
    try:
        res = await llm.ainvoke(prompt)
        raw = (res.content or "").strip()
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM returned non-JSON response")
    except Exception as e:
        LLM_ERRORS_TOTAL.labels(model=settings.DEFAULT_LLM_MODEL, mode="query_analyze", error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        llm_elapsed = time.perf_counter() - llm_start
        LLM_LATENCY.labels(model=settings.DEFAULT_LLM_MODEL, mode="query_analyze").observe(llm_elapsed)

        logger.info("llm_call", extra={
            "request_id": getattr(request.state, "request_id", None),
            "session_id": req.session_id,
            "model": settings.DEFAULT_LLM_MODEL,
            "mode": "query_analyze",
            "llm_latency_s": round(llm_elapsed, 4),
        })

    return QueryAnalyzeResponse(
        session_id=req.session_id,
        analysis=analysis,
        used_model=settings.DEFAULT_LLM_MODEL,
    )



async def analyze_query(llm: ChatOllama, user_text: str) -> Dict[str, Any]:
    res = await llm.ainvoke([
        SystemMessage(content=QUERY_ANALYZER_PROMPT),
        HumanMessage(content=f"user request: {user_text.strip()}"),
    ])

    raw = (res.content or "").strip()
    clean_js = extract_json(raw)

    try:
        return json.loads(clean_js)
    except json.JSONDecodeError as e:
        raise ValueError(f"Query analyzer returned invalid JSON: {clean_js}") from e


def extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found")
    return text[start:end+1]
