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

    from plugins.bluefiles.routes import router
    from plugins.bluefiles.ui import ui_router
    app.include_router(router,    prefix="/api/v1/bluefiles", tags=["BLUEFILES"])
    app.include_router(ui_router, prefix="/api/v1/bluefiles", tags=["BLUEFILES UI"])
