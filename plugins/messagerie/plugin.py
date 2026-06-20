"""
plugins/messagerie/plugin.py — v3.6.0-alpha2 (Phase 1 patch)
=============================================================
Plugin MESSAGERIE refondu avec protection contre dépendances manquantes :
  - Modèle Message unifié (canal interne | mail | sms — v1 = interne)
  - Dossiers virtuels + dossiers personnels
  - Reply / Reply-all / Forward + PJ locales (multipart)
  - Migration auto depuis MessageInterne au premier boot
  - Architecture prête pour mail/SMS (Phase 3) et Bluefiles (Phase 4)

v3.6.0-alpha2 : robustesse du chargement, log clair si python-multipart
absent (qui est requis par les routes /messages multipart).
"""
import logging
from fastapi import FastAPI

logger = logging.getLogger("scribe.plugins.messagerie")


MANIFEST = {
    "id":          "messagerie",
    "label":       "MESSAGERIE",
    "icon":        "✉️",
    "order":       90,
    "description": "Messagerie multi-canal (interne/mail/sms) avec PJ et dossiers",
    "requires":    [],
    "api_prefix":  "/api/v1/messagerie",
    "tab_id":      "tab-messagerie",
    "has_tab":     True,
    "legacy":      False,
    "allowed_roles": ["cellule_crise", "soignant", "admin"],
}


def register(app: FastAPI) -> None:
    """Enregistre tables + router + migration auto.

    Si une dépendance Python manque (python-multipart pour les uploads),
    le router ne peut pas être enregistré → on log un message d'erreur très
    clair pour faciliter le diagnostic côté admin.
    """
    # 1. Vérif dépendance critique : python-multipart est requise par les
    #    routes UploadFile/Form. Sans elle, le router plante au chargement
    #    et tout le plugin part en cascade d'erreurs 404/500.
    try:
        import multipart  # noqa: F401  (python-multipart, alias 'multipart')
    except ImportError:
        logger.error(
            "============================================================\n"
            "[messagerie] DÉPENDANCE MANQUANTE : python-multipart\n"
            "Le plugin messagerie ne peut pas démarrer sans cette lib.\n"
            "→ Installer : pip install python-multipart\n"
            "→ Ou complet : pip install -r requirements.txt\n"
            "Le plugin reste désactivé tant que cette dépendance manque.\n"
            "============================================================"
        )
        return  # Pas d'enregistrement = plugin désactivé proprement

    # 2. Création des nouvelles tables (idempotent)
    try:
        # IMPORTANT : on importe app.models AVANT plugins.messagerie.models
        # pour que la table `users` soit enregistrée dans la Base partagée
        # avant que nos FK ne s'y réfèrent (sinon NoReferencedTableError).
        from app import models as _app_models  # noqa: F401
        from app.database import engine, SessionLocal
        from plugins.messagerie.models import Base as MsgBase, migrate_from_legacy

        MsgBase.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("[messagerie] Tables créées/vérifiées : messagerie_messages, "
                    "messagerie_folders, messagerie_attachments")
    except Exception as e:
        logger.error(f"[messagerie] Erreur création tables : {e}", exc_info=True)
        return

    # 3. Migration auto depuis MessageInterne
    try:
        db = SessionLocal()
        try:
            n = migrate_from_legacy(db)
            if n > 0:
                logger.info(f"[messagerie] Migration auto : {n} messages copiés")
            else:
                logger.info("[messagerie] Migration auto : rien à migrer (déjà fait ou table vide)")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[messagerie] Migration auto a échoué (non bloquant) : {e}")

    # 4. Router (avec protection contre erreurs d'import)
    try:
        from plugins.messagerie.routes import router
        app.include_router(router, prefix="/api/v1/messagerie", tags=["MESSAGERIE"])
        logger.info("[messagerie] Router /api/v1/messagerie enregistré")
        logger.info("[messagerie] Plugin v3.6.0-alpha2 (Phase 1) chargé ✓")
    except Exception as e:
        logger.error(
            f"[messagerie] Erreur enregistrement router : {e}\n"
            "Les routes /api/v1/messagerie/* retourneront 404. "
            "Vérifier les logs ci-dessus pour la cause exacte.",
            exc_info=True
        )
