from fastapi import APIRouter, HTTPException
from store.SessionStore import session_store


history_router = APIRouter()

@history_router.get("/history/{session_id}")
def history(session_id: str):
    # удобно для дебага
    hist = session_store.get_history(session_id)
    return {
        "session_id": session_id,
        "messages": [{"type": m.type, "content": m.content} for m in hist]
    }