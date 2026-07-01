"""
plugins/lignes/plugin.py — SCRIBE
==================================
Plugin LIGNES : lignes d'information téléphoniques de crise (Twilio).

Concept :
  - On déclare N lignes (Médias, Familles, Patients…), chacune avec un numéro
    public et une annonce vocale par langue (multilingue → menu SVI).
  - Twilio rappelle un webhook TwiML public (/voice) et lit l'annonce en TTS.
  - En PRODUCTION on a PLUSIEURS lignes, normalement DORMANTES (actif=False),
    activées en deux clics le jour J — comme les presets de rappel du personnel.

Config Twilio :
  - éditable localement depuis le plugin (comme BlueFiles), secret chiffré au
    repos (Fernet) ;
  - OU gérée centralement en supervision (domaine "twilio") et redescendue aux
    instances synchronisées. Précédence « comble-trou » : local > central.

Conventions SCRIBE respectées :
  - Base partagée (app.database.Base) → create_all(checkfirst=True)
  - Le loader masque les erreurs → diagnostiquer via GET /api/v1/_debug/plugins
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "lignes",
    "label":       "LIGNES",
    "icon":        "📞",
    "order":       94,                      # juste après FICHIERS (92)
    "description": "Lignes d'information téléphoniques de crise (Twilio)",
    "requires":    [],
    "api_prefix":  "/api/v1/lignes",
    "tab_id":      "tab-lignes",
    "has_tab":     True,
    "legacy":      False,
    # Communication de crise : cellule + admin. (Lecture publique = webhook TwiML
    # non authentifié, géré à part dans routes.py.)
    "allowed_roles": ["admin", "cellule_crise"],
}


def register(app: FastAPI) -> None:
    """Crée les tables et enregistre les routes API + UI."""
    from app.database import engine, Base
    from plugins.lignes import models as _models  # noqa: F401  (découverte tables)

    Base.metadata.create_all(bind=engine, checkfirst=True)

    from plugins.lignes.routes import router
    from plugins.lignes.ui import ui_router
    app.include_router(router,    prefix="/api/v1/lignes", tags=["LIGNES"])
    app.include_router(ui_router, prefix="/api/v1/lignes", tags=["LIGNES UI"])
