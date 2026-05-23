"""
api/cartographie.py — Sites hospitaliers et Unités Fonctionnelles.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import Hospital, UniteFonctionnelle, ServiceStatus

router = APIRouter()


class HospitalOut(BaseModel):
    id: int
    nom: str
    code_finess: Optional[str]
    latitude: float
    longitude: float
    adresse: Optional[str]
    telephone_garde: Optional[str]
    class Config:
        from_attributes = True

class UFOut(BaseModel):
    id: int
    code_uf: str
    libelle: str
    pole: Optional[str]
    class Config:
        from_attributes = True


@router.get("/sites", response_model=List[HospitalOut])
def get_sites(db: Session = Depends(get_db)):
    return db.query(Hospital).all()


@router.get("/{hospital_name}/units", response_model=List[UFOut])
def get_units(hospital_name: str, db: Session = Depends(get_db)):
    h = db.query(Hospital).filter(Hospital.nom == hospital_name).first()
    if not h:
        return []
    # v2.4.7 : ne renvoie que les UF actives (les inactives restent en DB
    # pour préserver l'intégrité référentielle des incidents historiques,
    # mais elles n'apparaissent plus dans les dropdowns VEILLE/CAPACITÉ)
    return (
        db.query(UniteFonctionnelle)
        .filter(UniteFonctionnelle.hospital_id == h.id)
        .filter((UniteFonctionnelle.actif == True) | (UniteFonctionnelle.actif == None))
        .order_by(UniteFonctionnelle.libelle)
        .all()
    )


@router.get("/poles")
def get_poles(db: Session = Depends(get_db)):
    """Liste des pôles actifs (hors UF supprimées/désactivées)."""
    from sqlalchemy import func as sqlfunc
    poles = (
        db.query(UniteFonctionnelle.pole, sqlfunc.count().label("n"))
        .filter(UniteFonctionnelle.pole != "", UniteFonctionnelle.pole != None,
                ~UniteFonctionnelle.pole.like("RAPPEL%"))
        .filter((UniteFonctionnelle.actif == True) | (UniteFonctionnelle.actif == None))  # v2.4.7
        .group_by(UniteFonctionnelle.pole)
        .order_by(UniteFonctionnelle.pole)
        .all()
    )
    return [{"pole": p.pole, "count": p.n} for p in poles]


@router.get("/uf-to-pole")
def get_uf_to_pole(db: Session = Depends(get_db)):
    """Retourne la map code_uf -> pole basée sur les libellés des UF."""
    all_ufs = db.query(
        UniteFonctionnelle.code_uf,
        UniteFonctionnelle.libelle,
        UniteFonctionnelle.pole
    ).distinct().all()

    POLE_KEYWORDS = {
        'CANCEROLOGIE':                   ['CANCERO','ONCOL','RADIOTHER','HDJ CANC','3C 74'],
        'CARDIOVASCULAIRE':               ['CARDIO','CORONAR','USIC','VASCU','AORTIQUE'],
        'CHIRURGIE ANESTHESIE':           ['CHIRUR','ANESTHES','BLOC','ORTHO','TRAUMA','VISCERAL','ORL','OPHTALMOL','OPHTAL','NEUROCHIR','PLASTIQUE','UROLOG','THORAC'],
        'DNA':                            ['DNA','DPI','ARCHIV'],
        'FME':                            ['MATERNIT','GYNECO','NEONAT','OBSTETR','SAGE FEMME','ACCOUCHEMENT','FME','PEDIATR','NOURRISSON','GRAND ENFANT','KANGOUROU'],
        'GERIATRIE':                      ['GERIATR','EHPAD','USLD','SOINS PALLIAT','GERONTOL','UHR','UCC','SMR'],
        'MEDECINE':                       ['ALLERGO','PNEUMOL','NEUROLOG','HEPATO','GASTRO','ENDOCRIN','DIABETOL','RHUMATO','DERMATO','INFECTI','NEPHROL','HEMODIALYS','HEMATO','MEDECINE INTERNE','MEDECINE POLYV','MEDECINE SOINS'],
        'MEDICO-TECHNIQUE ET REEDUCATION':['LABORATOIR','BIOCHIM','MICROBIOL','IMAGERIE','SCANNER','IRM','PHARMA','REEDUCATION','KINESITH','ORTHOPH','ERGOTHER','RADIOLOG'],
        'SANTE MENTALE':                  ['PSYCHIATR','SANTE MENTALE','ADDICTOL','UPUP','MONET','PICASSO','GAUGUIN','PSY ','UNITE PSY'],
        'SANTE PUBLIQUE ET COMMUNAUTAIRE':['HAD ','PMSI','PREVENTION','HYGIENE','EPIDEMIO','SANTE PUBLIQUE'],
        'SOINS CRITIQUES':                ['REANIM','REA ','USIP','SOINS CRITIQUES','SIPO','USC ','USI ','SOINS INTENSIF'],
        'URGENCES':                       ['URGENCE','SAU ','SMUR','SAMU','UHCD','UPUM','ACCUEIL URGENCE','SOINS URGENTS'],
        'IFSI':                           ['IFSI','FORMATION INFIRM'],
        'SUPPORT':                        ['DIRECTION','DSI','INFORMATIQ','LOGISTIQ','BRANCARDIER','CUISINE','RESTAUR','BLANCHISS','STANDARD','SECURITE','DRH','DAF','ADMINIST'],
    }

    # Pôles valides — correspondent exactement aux cartes de l'onglet SOINS
    VALID_POLES = {
        'CANCEROLOGIE','CARDIOVASCULAIRE','CHIRURGIE ANESTHESIE','DNA','FME',
        'GERIATRIE','MEDECINE','MEDICO-TECHNIQUE ET REEDUCATION','SANTE MENTALE',
        'SANTE PUBLIQUE ET COMMUNAUTAIRE','SOINS CRITIQUES','URGENCES','IFSI','SUPPORT'
    }

    uf_to_pole = {}
    for uf in all_ufs:
        lib = (uf.libelle or '').upper()
        # Priorité 1 : détection par mots-clés dans le libellé (plus fiable que FICOM)
        matched = None
        for pole, kws in POLE_KEYWORDS.items():
            if any(kw in lib for kw in kws):
                matched = pole
                break
        if matched:
            uf_to_pole[uf.code_uf] = matched
            continue
        # Priorité 2 : pôle de la base s'il est valide (pas de "Total...", "RAPPEL...")
        if uf.pole and uf.pole in VALID_POLES:
            uf_to_pole[uf.code_uf] = uf.pole

    return uf_to_pole


# ── SERVICE STATUS (Sécurité physique, Logistique, …) ─────────────────────────

# Services transverses fixes — indépendants des pôles cliniques
SERVICES_TRANSVERSES = [
    {"service_id": "securite_physique", "libelle": "Sécurité physique"},
    {"service_id": "logistique",        "libelle": "Logistique"},
]

class ServiceStatusOut(BaseModel):
    service_id:  str
    libelle:     str
    statut:      str
    commentaire: Optional[str]
    updated_at:  Optional[str]
    class Config:
        from_attributes = True

class ServiceStatusUpdate(BaseModel):
    statut:      str                  # OK | DEGRADE | CRITIQUE
    commentaire: Optional[str] = ""


def _ensure_services(db: Session):
    """Crée les lignes par défaut si elles n'existent pas encore."""
    for s in SERVICES_TRANSVERSES:
        if not db.query(ServiceStatus).filter_by(service_id=s["service_id"]).first():
            db.add(ServiceStatus(service_id=s["service_id"], libelle=s["libelle"], statut="OK"))
    db.commit()


@router.get("/service-status")
def get_service_status(db: Session = Depends(get_db)):
    """Retourne le statut de tous les services transverses."""
    _ensure_services(db)
    rows = db.query(ServiceStatus).order_by(ServiceStatus.id).all()
    return [
        {
            "service_id":  r.service_id,
            "libelle":     r.libelle,
            "statut":      r.statut,
            "commentaire": r.commentaire or "",
            "updated_at":  r.updated_at.isoformat() if r.updated_at else "",
        }
        for r in rows
    ]


@router.put("/service-status/{service_id}")
def update_service_status(service_id: str, body: ServiceStatusUpdate, db: Session = Depends(get_db)):
    """Met à jour le statut d'un service transverse."""
    _ensure_services(db)
    row = db.query(ServiceStatus).filter_by(service_id=service_id).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Service inconnu : {service_id}")
    if body.statut not in ("OK", "DEGRADE", "CRITIQUE"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="statut doit être OK | DEGRADE | CRITIQUE")
    row.statut      = body.statut
    row.commentaire = body.commentaire or ""
    db.commit()
    return {"ok": True, "service_id": service_id, "statut": row.statut}


@router.get("/ufs")
def get_ufs_by_site(site: str = "", db: Session = Depends(get_db)):
    """Retourne les services/UF d'un site depuis le référentiel capacitaire."""
    from app.models import CapaciteReferentiel, UniteFonctionnelle, Hospital
    
    # D'abord essayer CapaciteReferentiel (source principale DEMO)
    q = db.query(CapaciteReferentiel)
    if site:
        q = q.filter(CapaciteReferentiel.site == site)
    refs = q.order_by(CapaciteReferentiel.pole, CapaciteReferentiel.service_nom).all()
    
    if refs:
        seen = set()
        result = []
        for r in refs:
            key = r.service_nom
            if key not in seen:
                seen.add(key)
                result.append({"code": r.uf_code or "", "libelle": r.service_nom, "pole": r.pole or ""})
        return result
    
    # Fallback: UniteFonctionnelle
    q2 = db.query(UniteFonctionnelle)
    if site:
        h = db.query(Hospital).filter(Hospital.nom == site).first()
        if h:
            q2 = q2.filter(UniteFonctionnelle.hospital_id == h.id)
    ufs = q2.order_by(UniteFonctionnelle.pole, UniteFonctionnelle.libelle).all()
    if ufs:
        return [{"code": u.code_uf or "", "libelle": u.libelle, "pole": u.pole or ""} for u in ufs]
    
    # Dernier recours: services génériques
    return [
        {"code": "", "libelle": "Urgences", "pole": "Urgences"},
        {"code": "", "libelle": "Réanimation", "pole": "Soins critiques"},
        {"code": "", "libelle": "Médecine interne", "pole": "Médecine"},
        {"code": "", "libelle": "Chirurgie", "pole": "Chirurgie"},
        {"code": "", "libelle": "Maternité", "pole": "Femme-Mère-Enfant"},
        {"code": "", "libelle": "Pédiatrie", "pole": "Femme-Mère-Enfant"},
        {"code": "", "libelle": "Cardiologie", "pole": "Médecine"},
        {"code": "", "libelle": "Psychiatrie", "pole": "Psychiatrie"},
        {"code": "", "libelle": "SAMU / SMUR", "pole": "Urgences"},
        {"code": "", "libelle": "Pharmacie", "pole": "Pharmacie"},
        {"code": "", "libelle": "Radiologie", "pole": "Médico-technique"},
        {"code": "", "libelle": "Bloc opératoire", "pole": "Chirurgie"},
        {"code": "", "libelle": "Stérilisation", "pole": "Chirurgie"},
        {"code": "", "libelle": "Laboratoire", "pole": "Médico-technique"},
        {"code": "", "libelle": "Direction", "pole": "Administration"},
        {"code": "", "libelle": "DSI", "pole": "Administration"},
    ]
