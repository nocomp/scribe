"""
plugins/annuaire/plugin.py — SCRIBE v2.0.6
Plugin ANNUAIRE : Annuaire contacts urgence
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "annuaire",
    "label":       "ANNUAIRE",
    "icon":        "📞",
    "order":       70,
    "description": "Annuaire contacts urgence",
    "requires":    [],
    "api_prefix":  "/api/v1/annuaire",
    "tab_id":      "tab-annuaire",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.annuaire.api import router
    app.include_router(router, prefix="/api/v1/annuaire", tags=["ANNUAIRE"])
