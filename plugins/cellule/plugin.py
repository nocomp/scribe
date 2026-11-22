"""
plugins/cellule/plugin.py — SCRIBE v2.0.6
Plugin CELLULE : Kanban, presences, decisions
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "cellule",
    "label":       "CELLULE",
    "icon":        "🏛️",
    "order":       30,
    "description": "Kanban, presences, decisions",
    "requires":    [],
    "api_prefix":  "/api/v1/cellule",
    "tab_id":      "tab-cellule",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.cellule.api import router
    from fastapi import Depends as _Depends
    from app.api.auth import require_user as _require_user
    app.include_router(router, prefix="/api/v1/cellule", tags=["CELLULE"], dependencies=[_Depends(_require_user)])
