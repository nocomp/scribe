"""
plugins/bluefiles/plugin.py — SCRIBE v3.5.0-alpha1
====================================================
Plugin BLUEFILES : transfert sécurisé HDS via Bluefiles
(Forecomm / Orange Healthcare).

Cas d'usage v1 :
  - Joindre un dossier patient à un transfert inter-établissement
    avec chiffrement bout-en-bout côté client.

Modes de fonctionnement :
  - LIVE  (clé API Bluefiles configurée) : appels réels à l'API
  - DEV   (pas de clé) : simulation locale, ZÉRO appel réseau.
          Permet de développer/démontrer l'UX sans abonnement.

Sécurité :
  - Aucune copie de fichier sur disque SCRIBE (streaming uniquement)
  - Audit en DB : QUI a envoyé QUOI à QUI, JAMAIS le contenu
  - MdP destinataire généré côté SCRIBE et affiché 1 seule fois
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "bluefiles",
    "label":       "BLUEFILES",
    "icon":        "🔒",
    "order":       105,                 # juste après inter_ght (100)
    "description": "Transfert sécurisé HDS via Bluefiles",
    "requires":    [],
    "api_prefix":  "/api/v1/bluefiles",
    # Pas d'onglet dédié — le plugin s'intègre dans Transferts (v1),
    # Communiqués (v1.1), Cellule (v1.2), REX (v1.3) via boutons contextuels.
    "tab_id":      None,
    "has_tab":     False,
    "legacy":      False,
    # RGPD : seuls les profils habilités à manipuler des données patient
    # peuvent envoyer un dossier sécurisé. Admin inclus pour la config.
    "allowed_roles": ["soignant", "cellule_crise", "admin"],
}


def register(app: FastAPI) -> None:
    """Enregistre les routes API + UI et crée les tables SQL si absentes."""
    from plugins.bluefiles.models import Base as BfBase
    from app.database import engine
    BfBase.metadata.create_all(bind=engine, checkfirst=True)

    # v3000h135 — Migration douce : ajoute les colonnes CLI si la table existait
    # déjà sans elles (create_all n'altère pas une table existante).
    try:
        from sqlalchemy import text as _sql_text
        _cli_cols = {
            "cli_login":       "VARCHAR(200)",
            "cli_password":    "VARCHAR(300)",
            "cli_server":      "VARCHAR(200)",
            "cli_impersonate": "VARCHAR(200)",
        }
        with engine.begin() as conn:
            existing = {row[1] for row in conn.exec_driver_sql(
                "PRAGMA table_info(plugin_bluefiles_config)").fetchall()}
            for col, typ in _cli_cols.items():
                if col not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE plugin_bluefiles_config ADD COLUMN {col} {typ}")
    except Exception:
        import logging
        logging.getLogger("scribe.plugins.bluefiles").warning(
            "Migration colonnes CLI bluefiles non appliquée", exc_info=True)

    from plugins.bluefiles.routes import router
    from plugins.bluefiles.ui import ui_router
    app.include_router(router,    prefix="/api/v1/bluefiles", tags=["BLUEFILES"])
    app.include_router(ui_router, prefix="/api/v1/bluefiles", tags=["BLUEFILES UI"])

<<<<<<< HEAD
    # Restaurer le bit exécutable du binaire CLI (peut sauter à l'extraction du
    # ZIP / copie). Sinon cli_available() → False → bascule silencieuse en
    # simulation (cause historique du bug « envoyé mais jamais reçu »).
    try:
        from plugins.bluefiles import cli_sender as _cs
        _cs.ensure_binary_exec()
    except Exception:
        pass

=======
>>>>>>> 42014cc0f1f987ee0564de52890336b067151060
    # v3000h136 (audit cyber) — Purge des fichiers résiduels dans data/ : en
    # fonctionnement normal ils sont supprimés après chaque envoi, mais un crash
    # entre l'écriture et la purge pourrait laisser des données patient sur
    # disque (HDS/RGPD). On supprime tout fichier de plus d'une heure au boot.
    try:
        import time as _time
        from plugins.bluefiles.cli_sender import DATA_DIR as _DD
        if _DD.exists():
            now = _time.time()
            for f in _DD.iterdir():
                if f.name == ".gitkeep" or not f.is_file():
                    continue
                try:
                    if now - f.stat().st_mtime > 3600:
                        f.unlink()
                except Exception:
                    pass
    except Exception:
        pass
