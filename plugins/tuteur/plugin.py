"""
plugins/tuteur/plugin.py — SCRIBE Plugin Tuteur v0.5
=====================================================
Compagnon d'apprentissage transversal en gestion de crise.

Trois moments d'accompagnement :
  - AVANT  : co-construction du scénario via intention pédagogique (Hook 1)
  - PENDANT: rappel discret en mode exercice ET en mode prod (Hooks 2A/2B)
  - APRES  : debriefing personnalisé généré par l'IA (Hook 3)

Plugin transversal : observe et complète les autres plugins, ne modifie pas
le coeur de SCRIBE. Activable individuellement ou en équipe.

Préfixe tables SQL : plugin_tuteur_*
Préfixe API        : /api/v1/tuteur
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "tuteur",
    "label":       "MON COACH",
    "icon":        "🎓",
    "order":       115,
    "description": "Compagnon d'apprentissage : intention, rappels, debriefing IA",
    "api_prefix":  "/api/v1/tuteur",
    "tab_id":      "tab-tuteur",
    "has_tab":     False,  # v2.4.4 : désactivé tant que pas finalisé (plugin gardé en réserve)
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    """Enregistre les routes API + UI et crée les tables SQL si absentes."""
    # 1. Création des tables (Base isolée, idempotent grâce à checkfirst)
    from plugins.tuteur.models import Base as TuteurBase
    from app.database import engine
    TuteurBase.metadata.create_all(bind=engine, checkfirst=True)

    # 2. Routes API
    from plugins.tuteur.routes import router
    from plugins.tuteur.ui     import ui_router
    app.include_router(router,    prefix="/api/v1/tuteur", tags=["TUTEUR"])
    app.include_router(ui_router, prefix="/api/v1/tuteur", tags=["TUTEUR UI"])
