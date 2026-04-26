"""plugins/exercice/ui.py — Sert l'interface HTML du plugin exercice."""
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()
_HTML_PATH = os.path.join(os.path.dirname(__file__), "exercice.html")

@ui_router.get("/ui", response_class=HTMLResponse)
def exercice_ui():
    with open(_HTML_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())
