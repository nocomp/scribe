"""
plugins/releve/plugin.py — SCRIBE v2.0.6
Plugin RELEVE : Releve de garde inter-equipes
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "releve",
    "label":       "RELEVE",
    "icon":        "📋",
    "order":       40,
    "description": "Releve de garde inter-equipes",
    "requires":    [],
    "api_prefix":  "/api/v1/releve",
    "tab_id":      "tab-releve",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.releve.api import router
    app.include_router(router, prefix="/api/v1/releve", tags=["RELEVE"])
