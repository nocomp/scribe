"""
plugins/messagerie/plugin.py — SCRIBE v2.0.6
Plugin MESSAGERIE : Messagerie interne SCRIBE
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "messagerie",
    "label":       "MESSAGERIE",
    "icon":        "✉️",
    "order":       90,
    "description": "Messagerie interne SCRIBE",
    "requires":    [],
    "api_prefix":  "/api/v1/messagerie",
    "tab_id":      "tab-messagerie",
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.messagerie.api import router
    app.include_router(router, prefix="/api/v1/messagerie", tags=["MESSAGERIE"])
