"""
plugins/albert/plugin.py — SCRIBE v2.0.4
Plugin IA Albert : analyse des incidents par LLM gouvernemental français.
Nécessite une clé API configurée dans config.xml (<ia><cle_api>…).
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "albert",
    "label":       "ANALYSE IA",
    "icon":        "🤖",
    "order":       120,
    "description": "Analyse des incidents par Albert, le LLM du gouvernement français.",
    "requires":    [],                  # pas de dépendances inter-plugins
    "api_prefix":  "/api/v1/albert",
    "tab_id":      None,                # pas d'onglet propre — bouton dans SOINS
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    """Enregistre les routes du plugin Albert dans l'application FastAPI."""
    from plugins.albert.api import router
    from fastapi import Depends as _Depends
    from app.api.auth import require_user as _require_user
    app.include_router(router, prefix="/api/v1/albert", tags=["Albert AI"], dependencies=[_Depends(_require_user)])
