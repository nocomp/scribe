"""
plugins/bluefiles/ui.py — v3.5.0-alpha1
========================================
UI server-side du plugin Bluefiles.

En v1 : l'UI principale (modal d'envoi, affichage des envois liés) vit
dans app/static/index.html et app/static/js/scribe.js — pas de page UI
server-side à part.

Ce module existe juste pour respecter le pattern plugin SCRIBE et
prépare l'ajout futur d'une page d'admin/audit dédiée.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.api.auth import require_admin

from plugins.bluefiles.client import current_mode, is_live_mode

ui_router = APIRouter()


@ui_router.get("/admin/health")
def admin_health(
    admin: User = Depends(require_admin),
    db:    Session = Depends(get_db),
):
    """Page admin minimale (JSON) : santé du plugin + compteurs audit.
    Une vraie page HTML viendra en v1.3.
    """
    from plugins.bluefiles.models import BluefilesEnvoi
    total       = db.query(BluefilesEnvoi).count()
    delivered   = db.query(BluefilesEnvoi).filter_by(statut="delivered").count()
    read        = db.query(BluefilesEnvoi).filter_by(statut="read").count()
    errors      = db.query(BluefilesEnvoi).filter_by(statut="error").count()
    return {
        "mode":      current_mode(),
        "ready":     True,
        "audit": {
            "total":     total,
            "delivered": delivered,
            "read":      read,
            "errors":    errors,
        },
        "hint": (
            "Mode DEV : aucun appel réel à Bluefiles. Cliquez sur ⚙ "
            "dans l'admin (Plugins → bluefiles) pour saisir l'URL de l'API, "
            "la clé, le compte et le secret webhook, et passer en mode LIVE. "
            "Les variables d'environnement SCRIBE_BLUEFILES_* restent acceptées "
            "comme repli."
            if not is_live_mode() else
            "Mode LIVE : envois réels via l'API Bluefiles."
        ),
    }
