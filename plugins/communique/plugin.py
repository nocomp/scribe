"""
plugins/communique/plugin.py — SCRIBE v2.0.6
Plugin COMMUNIQUE : Communiques et page /status
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "communique",
    "label":       "COMMUNIQUE",
    "icon":        "📣",
    "order":       60,
    "description": "Communiques et page /status",
    "requires":    [],
    "api_prefix":  "/api/v1/status",
    "tab_id":      "tab-communique",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.communique.api import router
    app.include_router(router, prefix="/api/v1/status", tags=["COMMUNIQUE"])
