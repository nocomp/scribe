"""
plugins/fichiers/plugin.py — SCRIBE
====================================
Plugin FICHIERS : drive interne SCRIBE.

  - Drive perso (upload streaming, dossiers, corbeille, favoris, recherche)
  - Partage ÉPHÉMÈRE à jeton : le fichier est délivré une seule fois puis
    automatiquement effacé.
  - UI « Suite numérique », multilingue (24 langues UE).

Activé par défaut (config.PLUGINS["fichiers"] = True).

Conventions SCRIBE respectées :
  - Base SQLAlchemy partagée (app.database.Base) → create_all(checkfirst=True)
  - Migration douce idempotente (ALTER TABLE) si la table préexistait
  - Stockage des blobs hors build, sous SCRIBE_DATA_DIR
  - Le loader masque les erreurs → tester via GET /api/v1/_debug/plugins
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "fichiers",
    "label":       "FICHIERS",
    "icon":        "📁",
    "order":       92,                     # juste après MESSAGERIE (90)
    "description": "Drive interne — partage de fichiers, mode éphémère",
    "requires":    [],
    "api_prefix":  "/api/v1/fichiers",
    "tab_id":      "tab-fichiers",
    "has_tab":     True,
    "legacy":      False,
    # Tous les rôles disposent de leur drive perso.
    "allowed_roles": ["admin", "cellule_crise", "soignant", "cadre_sante"],
}


def register(app: FastAPI) -> None:
    """Crée les tables, applique les migrations douces, enregistre les routes."""
    from app.database import engine
    from plugins.fichiers import models as _models  # noqa: F401  (découverte tables)

    # Base partagée : create_all crée uniquement les tables manquantes.
    from app.database import Base
    Base.metadata.create_all(bind=engine, checkfirst=True)

    # Migration douce idempotente : si une table plugin_fichiers_* existait déjà
    # sans une colonne ajoutée plus tard, create_all ne l'altère pas.
    try:
        _migrations = {
            "plugin_fichiers_fichiers": {
                "contient_donnees_patient": "BOOLEAN DEFAULT 0",
                "tags":   "VARCHAR(400) DEFAULT ''",
                "favori": "BOOLEAN DEFAULT 0",
                "ephemere": "BOOLEAN DEFAULT 0",
                "download_restreint": "BOOLEAN DEFAULT 1",
            },
            "plugin_fichiers_partages": {
                "ephemere":      "BOOLEAN DEFAULT 0",
                "telecharge":    "BOOLEAN DEFAULT 0",
                "telecharge_at": "DATETIME",
                "expire_at":     "DATETIME",
                "restreint":     "BOOLEAN DEFAULT 0",
                "destinataires_uids": "VARCHAR(600) DEFAULT ''",
                "protege":       "BOOLEAN DEFAULT 0",
                "mdp_hash":      "VARCHAR(120) DEFAULT ''",
                "tentatives":    "INTEGER DEFAULT 0",
                "contact_externe": "VARCHAR(60) DEFAULT ''",
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
                    continue  # table absente : create_all l'a déjà créée à jour
                for col, typ in cols.items():
                    if col not in existing:
                        try:
                            conn.exec_driver_sql(
                                f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                        except Exception:
                            pass
    except Exception:
        import logging
        logging.getLogger("scribe.plugins.fichiers").warning(
            "Migration douce fichiers non appliquée", exc_info=True)

    from plugins.fichiers.routes import router
    from plugins.fichiers.ui import ui_router
    app.include_router(router,    prefix="/api/v1/fichiers", tags=["FICHIERS"])
    app.include_router(ui_router, prefix="/api/v1/fichiers", tags=["FICHIERS UI"])

    # Purge des blobs orphelins au démarrage (RGPD : pas de binaire résiduel).
    try:
        from app.database import SessionLocal
        from plugins.fichiers import storage
        from plugins.fichiers.models import FichierBlob
        s = SessionLocal()
        try:
            referenced = {b.checksum for b in s.query(FichierBlob).all()}
            storage.purge_orphans(referenced)
        finally:
            s.close()
    except Exception:
        pass
