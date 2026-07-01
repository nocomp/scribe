"""
plugins/rapport/plugin.py — SCRIBE v2.0.6
Plugin RAPPORT : Archivage ZIP et exports
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "rapport",
    "label":       "RAPPORT",
    "icon":        "📦",
    "order":       65,
    "description": "Archivage ZIP et exports",
    "requires":    [],
    "api_prefix":  "/api/v1/rapport",
    "tab_id":      None,
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.rapport.api import router
    from fastapi import Depends as _Depends
    from app.api.auth import require_user as _require_user
    app.include_router(router, prefix="/api/v1/rapport", tags=["RAPPORT"], dependencies=[_Depends(_require_user)])
