"""
plugins/capacite/plugin.py — SCRIBE v2.0.6
Plugin CAPACITE : Monitoring capacite lits par pole
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "capacite",
    "label":       "CAPACITE",
    "icon":        "🛏",
    "order":       20,
    "description": "Monitoring capacite lits par pole",
    "requires":    [],
    "api_prefix":  "/api/v1/capacite",
    "tab_id":      "tab-capacite",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.capacite.api import router
    app.include_router(router, prefix="/api/v1/capacite", tags=["CAPACITE"])
