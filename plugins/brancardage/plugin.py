"""
plugins/brancardage/plugin.py — SCRIBE v2.2.3
Plugin BRANCARDAGE : Coordination des transports de patients intra-hospitaliers.
Pas de données nominatives — identifiant libre uniquement (ex: "Ch.12A").
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "brancardage",
    "label":       "BRANCARDAGE",
    "icon":        "🛏",
    "order":       85,
    "description": "Coordination des transports de patients (brancardage intra-hospitalier)",
    "requires":    [],
    "api_prefix":  "/api/v1/brancardage",
    "tab_id":      "tab-brancardage",
    "has_tab":     True,
    "legacy":      False,
    # v3.4 (h34) — Restriction RGPD : seul le rôle soignant (et l'admin) voit
    # cet onglet. La cellule de crise n'a pas un besoin légitime d'accéder
    # aux flux patient nominatifs internes.
    "allowed_roles": ["soignant", "cadre_sante", "admin"],
}


def register(app: FastAPI) -> None:
    """Enregistre les routes API + UI et crée les tables SQL si absentes."""
    from plugins.brancardage.models import Base as BrcBase
    from app.database import engine
    BrcBase.metadata.create_all(bind=engine, checkfirst=True)
    from plugins.brancardage.routes import router
    from plugins.brancardage.ui import ui_router
    app.include_router(router,    prefix="/api/v1/brancardage", tags=["BRANCARDAGE"])
    app.include_router(ui_router, prefix="/api/v1/brancardage", tags=["BRANCARDAGE UI"])
