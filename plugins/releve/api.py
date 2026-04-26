"""
api/releve.py — Consignes de passation persistées avec accusé de réception.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database import get_db
from app.models import Consigne

router = APIRouter()


class ConsigneCreate(BaseModel):
    pour: str
    texte: str

class ConsigneOut(BaseModel):
    id: int
    timestamp: datetime
    pour: str
    texte: str
    accuse: bool
    accuse_at: Optional[datetime]
    accuse_par: Optional[str] = None
    class Config:
        from_attributes = True


@router.post("/post", response_model=ConsigneOut)
def create_consigne(c: ConsigneCreate, db: Session = Depends(get_db)):
    new_c = Consigne(**c.dict())
    db.add(new_c)
    db.commit()
    db.refresh(new_c)
    return new_c


@router.get("/history", response_model=List[ConsigneOut])
def get_consignes(db: Session = Depends(get_db)):
    return db.query(Consigne).order_by(Consigne.timestamp.desc()).all()


class AccuseRequest(BaseModel):
    prenom: str = ""

@router.put("/{consigne_id}/accuser")
def accuser_reception(consigne_id: int, body: AccuseRequest = AccuseRequest(), db: Session = Depends(get_db)):
    c = db.query(Consigne).filter(Consigne.id == consigne_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Consigne non trouvée")
    if c.accuse:
        return {"status": "already_acked", "accuse_at": c.accuse_at, "accuse_par": c.accuse_par}
    c.accuse = True
    c.accuse_at = datetime.now(timezone.utc)
    c.accuse_par = body.prenom.strip() or "Anonyme"
    db.commit()
    return {"status": "acked", "accuse_at": c.accuse_at, "accuse_par": c.accuse_par}


@router.delete("/{consigne_id}")
def delete_consigne(consigne_id: int, db: Session = Depends(get_db)):
    c = db.query(Consigne).filter(Consigne.id == consigne_id).first()
    if c:
        db.delete(c)
        db.commit()
    return {"status": "deleted"}
