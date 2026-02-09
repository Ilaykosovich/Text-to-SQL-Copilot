# api/ui.py
from fastapi import APIRouter
from fastapi.responses import FileResponse

ui_router = APIRouter()

@ui_router.get("/")
def index():
    return FileResponse("static/index.html")
