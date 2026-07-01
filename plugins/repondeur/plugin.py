"""
plugins/repondeur/plugin.py — SCRIBE
=====================================
Plugin RÉPONDEUR : lignes d'information de crise via Twilio.

  - Déclarez N lignes (Médias, Familles, Patients…), chacune avec un numéro
    Twilio et un message multilingue.
  - À chaque appel, Twilio interroge le webhook /api/v1/repondeur/voice/{id}
    qui répond en TwiML <Say> le message courant → mettre à jour le texte en
    base suffit (rien n'est « poussé » chez Twilio).
  - Config Twilio : éditable depuis le plugin (⚙) OU poussée depuis la
    supervision (domaine central « twilio »). Précédence local > central > env.

Mode DEV (sans identifiants Twilio) : l'UI et les webhooks fonctionnent, aucun
appel réseau réel n'est tenté.
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "repondeur",
    "label":       "RÉPONDEUR",
    "icon":        "☎️",
    "order":       96,                      # après FICHIERS (92), NOTIFICATIONS (95)
    "description": "Lignes d'information de crise (répondeur vocal Twilio)",
    "requires":    [],
    "api_prefix":  "/api/v1/repondeur",
    "tab_id":      "tab-repondeur",
    "has_tab":     True,
    "legacy":      False,
    "allowed_roles": ["admin", "cellule_crise"],
}


def register(app: FastAPI) -> None:
    """Crée les tables et enregistre les routes (API + UI)."""
    from app.database import engine, Base
    from plugins.repondeur import models as _models  # noqa: F401  (découverte tables)

    Base.metadata.create_all(bind=engine, checkfirst=True)

    # Migration douce idempotente (si une table préexistait sans une colonne).
    try:
        _migrations = {
            "plugin_repondeur_lignes": {
                "voice":   "VARCHAR(80)",
                "langues": "VARCHAR(200) DEFAULT ''",
            },
            "plugin_repondeur_config": {
                "public_url":    "VARCHAR(300)",
                "default_voice": "VARCHAR(80)",
                "provider":      "VARCHAR(10) DEFAULT 'twilio'",
                "ovh_endpoint":        "VARCHAR(20)",
                "ovh_app_key":         "VARCHAR(120)",
                "ovh_app_secret":      "VARCHAR(300)",
                "ovh_consumer_key":    "VARCHAR(300)",
                "ovh_billing_account": "VARCHAR(60)",
                "ovh_service":         "VARCHAR(60)",
            },
        }
        with engine.begin() as conn:
            for table, cols in _migrations.items():
                try:
                    existing = {row[1] for row in conn.exec_driver_sql(
                        f"PRAGMA table_info({table})").fetchall()}
                except Exception:
                    existing = set()
                if not existing:
                    continue
                for col, typ in cols.items():
                    if col not in existing:
                        try:
                            conn.exec_driver_sql(
                                f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                        except Exception:
                            pass
    except Exception:
        import logging
        logging.getLogger("scribe.plugins.repondeur").warning(
            "Migration douce repondeur non appliquée", exc_info=True)

    from plugins.repondeur.routes import router
    from plugins.repondeur.ui import ui_router
    app.include_router(router,    prefix="/api/v1/repondeur", tags=["REPONDEUR"])
    app.include_router(ui_router, prefix="/api/v1/repondeur", tags=["REPONDEUR UI"])
