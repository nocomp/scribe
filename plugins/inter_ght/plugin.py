"""
plugins/inter_ght/plugin.py — SCRIBE v2.0.6
Plugin INTER-GHT : Demandes et declarations inter-GHT
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "inter_ght",
    "label":       "INTER-GHT",
    "icon":        "🔗",
    "order":       100,
    "description": "Demandes et declarations inter-GHT",
    "requires":    [],
    "api_prefix":  "/api/v1/interght",
    "tab_id":      "tab-interght",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.inter_ght.api import router
    app.include_router(router, prefix="/api/v1/interght", tags=["INTER-GHT"])
