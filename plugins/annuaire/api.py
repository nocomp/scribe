"""
plugins/annuaire/api.py — SCRIBE v2.0.6
Annuaire contacts urgence.
Sert les endpoints /api/v1/annuaire depuis app/api/v140 (migration progressive).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.auth import get_current_user

router = APIRouter()

# L annuaire est configure dans config.xml et rendu par le frontend.
# Les endpoints REST sont dans v140 pour l instant.
# Ce plugin expose le point d activation/desactivation.

@router.get("/status")
def annuaire_status(user=Depends(get_current_user)):
    """Verifie que le plugin annuaire est actif."""
    if not user: raise HTTPException(401)
    return {"ok": True, "plugin": "annuaire"}
