"""plugins/chat/ui.py"""
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()

_HTML_PATH = os.path.join(os.path.dirname(__file__), "chat.html")

def _get_html() -> str:
    with open(_HTML_PATH, encoding="utf-8") as f:
        return f.read()

@ui_router.get("/ui", response_class=HTMLResponse)
def chat_ui():
    return HTMLResponse(_get_html())

@ui_router.get("/ui/popout", response_class=HTMLResponse)
def chat_ui_popout():
    return HTMLResponse(_get_html())
