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
    "label":       "MON ASSISTANT",
    "icon":        "🎓",
    "order":       115,
    "description": "Compagnon d'apprentissage : intention, rappels, debriefing IA",
    "api_prefix":  "/api/v1/tuteur",
    "tab_id":      "tab-tuteur",
    "has_tab":     True,   # v3.0.0 : onglet MON ASSISTANT activé (compagnon d'apprentissage)
    "legacy":      False,
}


def register(app: FastAPI) -> None:
    """Enregistre les routes API + UI et crée les tables SQL si absentes."""
    # 1. Création des tables (Base isolée, idempotent grâce à checkfirst)
    from plugins.tuteur.models import Base as TuteurBase
    from app.database import engine
    TuteurBase.metadata.create_all(bind=engine, checkfirst=True)

    # 1bis. v3.1.0 — Migration légère SQLite : ajouter la colonne `niveau`
    # à plugin_tuteur_coach_messages si une DB existante ne l'a pas encore.
    # Idempotent : si la colonne existe déjà, on ne fait rien.
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)
        if "plugin_tuteur_coach_messages" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("plugin_tuteur_coach_messages")}
            if "niveau" not in cols:
                with engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE plugin_tuteur_coach_messages "
                        "ADD COLUMN niveau VARCHAR(10) DEFAULT 'marker' NOT NULL"
                    ))
    except Exception as e:
        # Migration non bloquante : si elle échoue, la table reste utilisable
        # via les valeurs par défaut SQLAlchemy.
        import logging
        logging.getLogger("scribe.tuteur.plugin").warning(
            f"Migration niveau: {e}"
        )

    # 2. Routes API
    from plugins.tuteur.routes import router
    from plugins.tuteur.ui     import ui_router
    app.include_router(router,    prefix="/api/v1/tuteur", tags=["TUTEUR"])
    app.include_router(ui_router, prefix="/api/v1/tuteur", tags=["TUTEUR UI"])
