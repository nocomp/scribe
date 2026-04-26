"""
api/cellule.py — Présences horodatées + Décisions, persistées en base.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import Presence, Decision

router = APIRouter()


# ── Présences ─────────────────────────────────────────────

class PresenceCreate(BaseModel):
    nom: str
    role: Optional[str] = ""
    action: str  # ENTRÉE | SORTIE

class PresenceOut(BaseModel):
    id: int
    timestamp: datetime
    nom: str
    role: Optional[str]
    action: str
    class Config:
        from_attributes = True

@router.post("/presences", response_model=PresenceOut)
def log_presence(p: PresenceCreate, db: Session = Depends(get_db)):
    new_p = Presence(**p.dict())
    db.add(new_p)
    db.commit()
    db.refresh(new_p)
    return new_p

@router.get("/presences", response_model=List[PresenceOut])
def get_presences(db: Session = Depends(get_db)):
    return db.query(Presence).order_by(Presence.timestamp.desc()).limit(100).all()

@router.delete("/presences/{presence_id}")
def delete_presence(presence_id: int, db: Session = Depends(get_db)):
    p = db.query(Presence).filter(Presence.id == presence_id).first()
    if p:
        db.delete(p)
        db.commit()
    return {"status": "deleted"}


# ── Décisions ─────────────────────────────────────────────

class DecisionCreate(BaseModel):
    contenu: str
    responsable: Optional[str] = ""
    base_reglementaire: Optional[str] = "Plan Blanc"

class DecisionOut(BaseModel):
    id: int
    timestamp: datetime
    contenu: str
    responsable: Optional[str]
    base_reglementaire: Optional[str]
    statut_validation: str
    class Config:
        from_attributes = True

@router.post("/decisions", response_model=DecisionOut)
def create_decision(dec: DecisionCreate, db: Session = Depends(get_db)):
    new_dec = Decision(**dec.dict())
    db.add(new_dec)
    db.commit()
    db.refresh(new_dec)
    return new_dec

@router.get("/decisions", response_model=List[DecisionOut])
def get_decisions(db: Session = Depends(get_db)):
    return db.query(Decision).order_by(Decision.timestamp.desc()).all()

@router.delete("/decisions/{decision_id}")
def delete_decision(decision_id: int, db: Session = Depends(get_db)):
    d = db.query(Decision).filter(Decision.id == decision_id).first()
    if d:
        db.delete(d)
        db.commit()
    return {"status": "deleted"}
