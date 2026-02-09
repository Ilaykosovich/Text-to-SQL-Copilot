from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from observability.logger import setup_logger
from  API.chat import chat_router
from  API.history import history_router
from  API.ui import ui_router
from API.config import config_router
from observability.metrics import metrics_router
#from RAG.chroma_store import ChromaStore
#from API.config import settings

setup_logger()  # один раз



app = FastAPI(title="LLM Orchestrator (Ollama)")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat_router, tags=["chat"])
app.include_router(history_router, tags=["history"])
app.include_router(config_router, tags=["config"])
app.include_router(metrics_router, tags=["metrics"])


# @app.on_event("startup")
# def startup():
#     if not hasattr(app.state, "chroma"):
#         app.state.chroma = ChromaStore(
#             connection_string=settings.DATABASE_URL
#         )
#     elif app.state.chroma.count() == 0:
#         app.state.chroma.rebuild()


app.include_router(ui_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
