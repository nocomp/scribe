"""
plugins/exercice/plugin.py — SCRIBE Exercice de Crise v1.0
Plugin de simulation multi-sites et multi-GHT pour exercices de crise hospitalière.
Ports dédiés : 8660-8666 (instances) + 8565 (collecteur exercice)
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "exercice",
    "label":       "EXERCICE",
    "icon":        "🎯",
    "order":       88,
    "description": "Simulation et exercices de crise multi-sites — injection de stimuli scénarisés",
    "api_prefix":  "/api/v1/exercice",
    "tab_id":      "tab-exercice",
    "has_tab":     True,
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    """Enregistre les routes API + UI et crée les tables SQL si absentes."""
    from plugins.exercice.models import Base as ExoBase
    from app.database import engine
    ExoBase.metadata.create_all(bind=engine, checkfirst=True)

    from plugins.exercice.routes import router
    from plugins.exercice.ui import ui_router
    app.include_router(router,    prefix="/api/v1/exercice", tags=["EXERCICE"])
    app.include_router(ui_router, prefix="/api/v1/exercice", tags=["EXERCICE UI"])

    # Middleware : bannière MODE EXERCICE injectée dans les headers
    import os
    if os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1":
        @app.middleware("http")
        async def exercice_header(request, call_next):
            response = await call_next(request)
            response.headers["X-Scribe-Exercice"] = "1"
            return response
