"""
plugins/federation/plugin.py — SCRIBE v2.0.6
Plugin SUPERVISION : Push collecteur + supervision
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "federation",
    "label":       "SUPERVISION",
    "icon":        "🗺",
    "order":       110,
    "description": "Push collecteur + supervision",
    "requires":    [],
    "api_prefix":  "/api/v1/federation",
    "tab_id":      None,
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    from plugins.federation.api import router
    app.include_router(router, prefix="/api/v1/federation", tags=["SUPERVISION"])


def start_background(app: FastAPI) -> None:
    """Lance les taches de fond du plugin (boucle federation)."""
    import asyncio
    from plugins.federation.api import federation_loop
    asyncio.create_task(federation_loop())
