"""
plugins/rex/plugin.py — SCRIBE v2.0.6
Plugin REX : Retour d'experience post-crise
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "rex",
    "label":       "REX",
    "icon":        "🔍",
    "order":       80,
    "description": "Retour d'experience post-crise",
    "requires":    [],
    "api_prefix":  "/api/v1/rex",
    "tab_id":      "tab-rex",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.rex.api import router
    app.include_router(router, prefix="/api/v1/rex", tags=["REX"])
