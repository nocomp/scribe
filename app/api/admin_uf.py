"""Routes d'administration des Unités Fonctionnelles (UF).

v2.4.7 : permet aux admins de l'instance d'éditer le référentiel UF :
  - Activer / désactiver une UF (champ `actif`)
  - Modifier libellé / code / pôle
  - Ajouter / supprimer une UF (rarement utilisé, l'import xlsx est privilégié)

Une UF désactivée :
  - reste en DB (pour préserver l'intégrité référentielle des incidents historiques)
  - n'apparaît plus dans les dropdowns VEILLE / CAPACITÉ
  - peut être réactivée à tout moment

Sécurité : toutes les routes requièrent le rôle admin (`require_admin`).
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import UniteFonctionnelle, Hospital, CapaciteReferentiel, ContactMobilisation
from app.api.auth import require_admin

router = APIRouter(prefix="/api/v1/admin/uf", tags=["admin-uf"])


class UfOut(BaseModel):
    id: int
    code_uf: str
    libelle: str
    pole: Optional[str] = None
    hospital_id: int
    hospital_nom: Optional[str] = None
    actif: bool
    reassigned_contacts: int = 0
    reassigned_capacite: int = 0


class UfUpdate(BaseModel):
    code_uf:  Optional[str] = None
    libelle:  Optional[str] = None
    pole:     Optional[str] = None
    actif:    Optional[bool] = None


class UfCreate(BaseModel):
    code_uf:     str
    libelle:     str
    pole:        Optional[str] = None
    hospital_id: Optional[int] = None  # défaut : premier Hospital


@router.get("", response_model=List[UfOut])
def list_uf(
    db: Session = Depends(get_db),
    include_inactive: bool = True,
    _user=Depends(require_admin),
):
    """Liste toutes les UF avec leur état (actives + inactives par défaut)."""
    q = db.query(UniteFonctionnelle, Hospital).outerjoin(
        Hospital, UniteFonctionnelle.hospital_id == Hospital.id
    )
    if not include_inactive:
        q = q.filter(UniteFonctionnelle.actif == True)
    rows = q.order_by(UniteFonctionnelle.pole, UniteFonctionnelle.libelle).all()
    out = []
    for uf, h in rows:
        out.append(UfOut(
            id=uf.id,
            code_uf=uf.code_uf or "",
            libelle=uf.libelle or "",
            pole=uf.pole,
            hospital_id=uf.hospital_id,
            hospital_nom=h.nom if h else None,
            actif=bool(uf.actif if uf.actif is not None else True),
        ))
    return out


@router.put("/{uf_id}", response_model=UfOut)
def update_uf(
    uf_id: int,
    body: UfUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """Met à jour une UF (champs optionnels)."""
    uf = db.query(UniteFonctionnelle).filter(UniteFonctionnelle.id == uf_id).first()
    if not uf:
        raise HTTPException(404, "UF introuvable")
    reassigned_contacts = 0
    reassigned_capacite = 0
    if body.code_uf is not None and body.code_uf.strip() and body.code_uf.strip() != (uf.code_uf or ""):
        old_code = uf.code_uf or ""
        new_code = body.code_uf.strip()
        dup = db.query(UniteFonctionnelle).filter(
            UniteFonctionnelle.hospital_id == uf.hospital_id,
            UniteFonctionnelle.code_uf == new_code,
            UniteFonctionnelle.id != uf.id,
        ).first()
        if dup:
            raise HTTPException(409, f"Code UF '{new_code}' déjà existant pour cet établissement.")
        uf.code_uf = new_code
        # Cascade : ré-affecter les références qui stockent le code UF.
        if old_code:
            reassigned_capacite = db.query(CapaciteReferentiel).filter(
                CapaciteReferentiel.uf_code == old_code
            ).update({CapaciteReferentiel.uf_code: new_code}, synchronize_session=False)
            reassigned_contacts = db.query(ContactMobilisation).filter(
                ContactMobilisation.uf == old_code
            ).update({ContactMobilisation.uf: new_code}, synchronize_session=False)
    if body.libelle is not None:
        uf.libelle = body.libelle.strip()
    if body.pole is not None:
        uf.pole = body.pole.strip() or None
    if body.actif is not None:
        uf.actif = bool(body.actif)
    db.commit(); db.refresh(uf)
    h = db.query(Hospital).filter(Hospital.id == uf.hospital_id).first()
    return UfOut(
        id=uf.id, code_uf=uf.code_uf or "", libelle=uf.libelle or "",
        pole=uf.pole, hospital_id=uf.hospital_id,
        hospital_nom=h.nom if h else None,
        actif=bool(uf.actif if uf.actif is not None else True),
        reassigned_contacts=reassigned_contacts,
        reassigned_capacite=reassigned_capacite,
    )


@router.post("", response_model=UfOut, status_code=201)
def create_uf(
    body: UfCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """Crée une nouvelle UF."""
    hospital_id = body.hospital_id
    if not hospital_id:
        h = db.query(Hospital).order_by(Hospital.id).first()
        if not h:
            raise HTTPException(400, "Aucun Hospital configuré.")
        hospital_id = h.id
    # Vérif unicité code+hospital
    existing = db.query(UniteFonctionnelle).filter_by(
        code_uf=body.code_uf.strip(), hospital_id=hospital_id
    ).first()
    if existing:
        raise HTTPException(409, f"Code UF '{body.code_uf}' déjà existant pour cet établissement.")
    uf = UniteFonctionnelle(
        code_uf=body.code_uf.strip(),
        libelle=body.libelle.strip(),
        pole=body.pole.strip() if body.pole else None,
        hospital_id=hospital_id,
        actif=True,
    )
    db.add(uf); db.commit(); db.refresh(uf)
    h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    return UfOut(
        id=uf.id, code_uf=uf.code_uf, libelle=uf.libelle,
        pole=uf.pole, hospital_id=uf.hospital_id,
        hospital_nom=h.nom if h else None,
        actif=True,
    )


@router.delete("/{uf_id}", status_code=204)
def delete_uf(
    uf_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """Supprime une UF. Préférer la désactivation (PUT actif=False) en cas
    d'incidents historiques liés."""
    uf = db.query(UniteFonctionnelle).filter(UniteFonctionnelle.id == uf_id).first()
    if not uf:
        raise HTTPException(404, "UF introuvable")
    code = uf.code_uf or ""
    if code:
        nb_capa = db.query(CapaciteReferentiel).filter(CapaciteReferentiel.uf_code == code).count()
        nb_contacts = db.query(ContactMobilisation).filter(ContactMobilisation.uf == code).count()
        if nb_capa or nb_contacts:
            raise HTTPException(409,
                f"UF référencée ({nb_capa} ligne(s) capacité, {nb_contacts} contact(s)). "
                "Désactivez-la plutôt que de la supprimer, ou ré-affectez d'abord ces références.")
    db.delete(uf); db.commit()
    return None


@router.post("/bulk-toggle", response_model=List[UfOut])
def bulk_toggle(
    payload: List[dict],  # [{"id": 1, "actif": false}, ...]
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """Active/désactive plusieurs UF en une requête (gain de perf UI)."""
    ids = [item.get("id") for item in payload if item.get("id") is not None]
    if not ids:
        return []
    ufs = db.query(UniteFonctionnelle).filter(UniteFonctionnelle.id.in_(ids)).all()
    by_id = {u.id: u for u in ufs}
    for item in payload:
        uf = by_id.get(item.get("id"))
        if uf is not None and "actif" in item:
            uf.actif = bool(item["actif"])
    db.commit()
    # Retourner état mis à jour
    out = []
    for uf in ufs:
        h = db.query(Hospital).filter(Hospital.id == uf.hospital_id).first()
        out.append(UfOut(
            id=uf.id, code_uf=uf.code_uf or "", libelle=uf.libelle or "",
            pole=uf.pole, hospital_id=uf.hospital_id,
            hospital_nom=h.nom if h else None,
            actif=bool(uf.actif if uf.actif is not None else True),
        ))
    return out
