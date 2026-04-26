"""
app/api/lang_admin.py — SCRIBE v2307
Endpoint admin pour changer la langue active de l'instance.

Inspiré du modèle WordPress : un menu déroulant dans l'admin permet à un
super-admin de choisir la langue par défaut de toute l'instance. Le
changement est persisté dans app/lang/_current.json et pris en compte
au prochain chargement de page côté client (les users voient la
nouvelle langue dès qu'ils F5).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.api.i18n import get_available_languages, get_current_lang, set_current_lang
from app.models import User

router = APIRouter(prefix="/api/v1/admin/lang", tags=["admin-lang"])


class LangChangeIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=5)


@router.get("/current")
def current(admin: User = Depends(require_admin)):
    """Retourne la langue actuelle + liste disponibles (pour sélecteur)."""
    return {
        "current": get_current_lang(),
        "available": get_available_languages(),
    }


@router.post("/set")
def change(body: LangChangeIn, admin: User = Depends(require_admin)):
    """Change la langue par défaut de l'instance."""
    try:
        set_current_lang(body.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "code": body.code}
