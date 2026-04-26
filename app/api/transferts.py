"""
app/api/transferts.py — API transferts patients inter-services/inter-établissements

Règle RGPD/HDS : les données nominatives (nom, prénom, ipp, date_naissance)
NE remontent JAMAIS dans le collecteur territorial.
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TransfertPatient
from app.api.auth import get_current_user

router = APIRouter(prefix="/transferts", tags=["transferts"])


class TransfertCreate(BaseModel):
    nom:                      Optional[str] = None
    prenom:                   Optional[str] = None
    nom_jeune_fille:          Optional[str] = None
    ipp:                      Optional[str] = None
    date_naissance:           Optional[str] = None
    unite_origine:            str
    etablissement_origine:    str
    unite_destination:        str
    etablissement_destination: str
    redacteur:                str
    commentaire:              Optional[str] = None
    statut:                   str = "EN_PREPARATION"


class StatutUpdate(BaseModel):
    statut: str


STATUTS_VALIDES = {"EN_PREPARATION", "EN_COURS", "ARRIVE", "ANNULE"}


def _serialize(t: TransfertPatient) -> dict:
    return {
        "id":                       t.id,
        "nom":                      t.nom,
        "prenom":                   t.prenom,
        "nom_jeune_fille":          t.nom_jeune_fille,
        "ipp":                      t.ipp,
        "date_naissance":           t.date_naissance,
        "unite_origine":            t.unite_origine,
        "etablissement_origine":    t.etablissement_origine,
        "unite_destination":        t.unite_destination,
        "etablissement_destination": t.etablissement_destination,
        "statut":                   t.statut,
        "horodatage_creation":      t.horodatage_creation.isoformat() if t.horodatage_creation else None,
        "horodatage_depart":        t.horodatage_depart.isoformat() if t.horodatage_depart else None,
        "horodatage_arrivee":       t.horodatage_arrivee.isoformat() if t.horodatage_arrivee else None,
        "redacteur":                t.redacteur,
        "commentaire":              t.commentaire,
    }


@router.get("")
def list_transferts(db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    items = db.query(TransfertPatient).order_by(TransfertPatient.horodatage_creation.desc()).all()
    return [_serialize(t) for t in items]


@router.post("", status_code=201)
def create_transfert(body: TransfertCreate, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    if body.statut not in STATUTS_VALIDES:
        raise HTTPException(400, f"Statut invalide : {body.statut}")
    t = TransfertPatient(**body.dict())
    db.add(t); db.commit(); db.refresh(t)
    return _serialize(t)


@router.put("/{tid}")
def update_transfert(tid: int, body: TransfertCreate, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    t = db.query(TransfertPatient).filter(TransfertPatient.id == tid).first()
    if not t: raise HTTPException(404, "Transfert introuvable")
    for k, v in body.dict().items():
        setattr(t, k, v)
    db.commit(); db.refresh(t)
    return _serialize(t)


@router.patch("/{tid}/statut")
def update_statut(tid: int, body: StatutUpdate, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    if body.statut not in STATUTS_VALIDES:
        raise HTTPException(400, f"Statut invalide : {body.statut}")
    t = db.query(TransfertPatient).filter(TransfertPatient.id == tid).first()
    if not t: raise HTTPException(404, "Transfert introuvable")
    t.statut = body.statut
    now = datetime.now(timezone.utc)
    if body.statut == "EN_COURS"  and not t.horodatage_depart:   t.horodatage_depart   = now
    if body.statut == "ARRIVE"    and not t.horodatage_arrivee:  t.horodatage_arrivee  = now
    _log_mc(db, current_user, "TRANSFERT", f"STATUT→{body.statut}", f"#{tid} {t.unite_origine}→{t.unite_destination}")
    db.commit(); db.refresh(t)
    return _serialize(t)


@router.delete("/{tid}")
def delete_transfert(tid: int, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    t = db.query(TransfertPatient).filter(TransfertPatient.id == tid).first()
    if not t: raise HTTPException(404, "Transfert introuvable")
    db.delete(t); db.commit()
    return {"ok": True}


@router.get("/anonymes")
def list_transferts_anonymes(db: Session = Depends(get_db)):
    """Flux anonymisés pour le collecteur — AUCUNE donnée patient."""
    items = db.query(TransfertPatient).filter(
        TransfertPatient.statut.in_(["EN_PREPARATION", "EN_COURS"])
    ).all()
    return [{
        "id":                        t.id,
        "unite_origine":             t.unite_origine,
        "etablissement_origine":     t.etablissement_origine,
        "unite_destination":         t.unite_destination,
        "etablissement_destination": t.etablissement_destination,
        "statut":                    t.statut,
        "horodatage_depart":         t.horodatage_depart.isoformat() if t.horodatage_depart else None,
    } for t in items]
