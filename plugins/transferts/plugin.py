"""
plugins/transferts/plugin.py — SCRIBE v2.0.6
Plugin TRANSFERTS : Transferts patients inter-GHT
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "transferts",
    "label":       "TRANSFERTS",
    "icon":        "🚑",
    "order":       50,
    "description": "Transferts patients inter-GHT",
    "requires":    [],
    "api_prefix":  "/api/v1/transferts",
    "tab_id":      "tab-soins",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.transferts.api import router
    app.include_router(router, prefix="/api/v1/transferts", tags=["TRANSFERTS"])
