"""
plugins/brancardage/routes.py — API REST brancardage SCRIBE v2.2.6
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

def _log_mc(db, user, action: str, detail: str):
    try:
        from app.models import MainCourante
        from datetime import datetime, timezone
        entry = MainCourante(
            horodatage=datetime.now(timezone.utc),
            auteur=getattr(user,'display_name',None) or getattr(user,'username','?'),
            urgence=1, type_incident="MIXTE",
            fait=f"🛏 BRANCARDAGE — {action} : {detail}",
            consequence="", action="", responsable=""
        )
        db.add(entry); db.commit()
    except Exception:
        pass
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, require_role
from plugins.brancardage.models import BrcMission, BrcHistorique

router = APIRouter()

# v3.4 (h34) — Toutes les routes brancardage sont réservées au rôle 'soignant'
# (et à l'admin via court-circuit dans require_role). La cellule de crise n'a
# pas un besoin légitime au sens RGPD de voir les flux patient nominatifs.
# Pour ouvrir l'accès à la cellule de crise, ajouter "cellule_crise" dans
# require_role(...) — à valider avec la DPO.
_require_branc = require_role("soignant", "cadre_sante")

STATUTS = ["EN_ATTENTE", "EN_COURS", "TERMINE", "ANNULE"]
STATUT_LABELS = {"EN_ATTENTE": "En attente", "EN_COURS": "En cours",
                 "TERMINE": "Terminée", "ANNULE": "Annulée"}
PRIORITE_LABELS = {"P1": "Urgente", "P2": "Normale", "P3": "Différable"}

class MissionCreate(BaseModel):
    ref_type:         str = "REF"
    ref_patient:      str
    uf_origine:       str
    chambre_depart:   Optional[str] = None
    uf_destination:   str
    etab_destination: Optional[str] = None
    chambre_arrivee:  Optional[str] = None
    type_transport:   str = "BRANCARD"
    priorite:         str = "P2"
    motif:            Optional[str] = None
    commentaire:      Optional[str] = None
    programmee:       int = 0
    heure_prevue:     Optional[str] = None
    avec_retour:      int = 0
    heure_retour:     Optional[str] = None

class PriseEnCharge(BaseModel):
    agent_nom: str
    agent_tel: Optional[str] = None

class MissionPatch(BaseModel):
    statut:      str
    commentaire: Optional[str] = None

class ArriveeIn(BaseModel):
    commentaire: Optional[str] = None

def _fmt(m):
    return {
        "id": m.id, "ref_type": getattr(m,"ref_type","REF"),
        "ref_patient": m.ref_patient,
        "uf_origine": m.uf_origine, "chambre_depart": m.chambre_depart,
        "uf_destination": m.uf_destination,
        "etab_destination": getattr(m,"etab_destination",None),
        "chambre_arrivee": m.chambre_arrivee,
        "type_transport": m.type_transport,
        "priorite": m.priorite, "priorite_label": PRIORITE_LABELS.get(m.priorite,m.priorite),
        "motif": m.motif, "commentaire": m.commentaire,
        "programmee": m.programmee, "heure_prevue": m.heure_prevue,
        "avec_retour": m.avec_retour, "heure_retour": m.heure_retour,
        "statut": m.statut, "statut_label": STATUT_LABELS.get(m.statut,m.statut),
        "agent_id": m.agent_id, "agent_nom": m.agent_nom,
        "agent_tel": getattr(m,"agent_tel",None),
        "demandeur_id": m.demandeur_id, "demandeur_nom": m.demandeur_nom,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        "prise_en_charge_at": m.prise_en_charge_at.isoformat() if m.prise_en_charge_at else None,
        "termine_at": m.termine_at.isoformat() if m.termine_at else None,
    }

def _log(db, mid, ancien, nouveau, par="", comment=""):
    db.add(BrcHistorique(mission_id=mid, ancien_stat=ancien, nouveau_stat=nouveau,
                         par_user=par, commentaire=comment))

def _notif(db, m, user):
    try:
        from app.models import User, Notification
        agents = db.query(User).filter(
            (User.perimetre.ilike("%brancardier%")) | (User.username.ilike("%brancard%"))
        ).all()
        for a in agents:
            db.add(Notification(user_id=a.id,
                titre=f"🛏 Mission [{m.priorite}] {m.uf_origine}→{m.uf_destination}",
                message=f"{m.ref_patient} · {m.type_transport}", type_notif="BRANCARDAGE"))
        db.commit()
    except Exception: pass

def _creer_transfert(db, m, user):
    if m.type_transport != "AMBULANCE" or not getattr(m,"etab_destination",None): return
    try:
        from app.models import TransfertPatient
        db.add(TransfertPatient(
            etablissement_origine=user.username,
            etablissement_destination=m.etab_destination,
            site_destination=m.etab_destination,
            unite_origine=m.uf_origine, unite_destination=m.uf_destination,
            statut="EN_PREPARATION",
            commentaire=f"[BRANCARDAGE #{m.id}] {m.ref_patient} — {m.motif or ''}",
            horodatage_creation=datetime.now(timezone.utc),
            ght_destinataire=m.etab_destination,
        ))
        db.commit()
    except Exception: pass

@router.get("/missions")
def list_missions(statut: Optional[str]=None, db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    q = db.query(BrcMission)
    if statut: q = q.filter(BrcMission.statut==statut)
    else:      q = q.filter(BrcMission.statut.notin_(["TERMINE","ANNULE"]))
    return [_fmt(m) for m in q.order_by(BrcMission.priorite.asc(), BrcMission.created_at.asc()).all()]

@router.get("/missions/all")
def list_all(limit: int=200, db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    return [_fmt(m) for m in db.query(BrcMission).order_by(BrcMission.created_at.desc()).limit(limit).all()]

@router.get("/missions/{mission_id}")
def get_mission(mission_id: int, db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    m = db.query(BrcMission).filter(BrcMission.id==mission_id).first()
    if not m: raise HTTPException(404)
    return _fmt(m)

@router.get("/missions/{mission_id}/historique")
def get_historique(mission_id: int, db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    rows = db.query(BrcHistorique).filter(BrcHistorique.mission_id==mission_id).order_by(BrcHistorique.created_at.asc()).all()
    return [{"id":h.id,"ancien":h.ancien_stat,"nouveau":h.nouveau_stat,
             "nouveau_label":STATUT_LABELS.get(h.nouveau_stat,h.nouveau_stat),
             "par":h.par_user,"commentaire":h.commentaire,
             "at":h.created_at.isoformat() if h.created_at else None} for h in rows]

@router.post("/missions")
def create_mission(body: MissionCreate, db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    if not body.ref_patient.strip(): raise HTTPException(400,"Référence patient requise")
    if not body.uf_origine.strip() or not body.uf_destination.strip():
        raise HTTPException(400,"UF origine et destination requises")
    m = BrcMission(ref_patient=body.ref_patient.strip(),
        uf_origine=body.uf_origine.strip(), chambre_depart=body.chambre_depart,
        uf_destination=body.uf_destination.strip(), chambre_arrivee=body.chambre_arrivee,
        type_transport=body.type_transport, priorite=body.priorite,
        motif=body.motif, commentaire=body.commentaire,
        programmee=body.programmee, heure_prevue=body.heure_prevue,
        avec_retour=body.avec_retour, heure_retour=body.heure_retour,
        demandeur_id=user.username, demandeur_nom=user.display_name or user.username)
    if hasattr(m,"ref_type"):        m.ref_type=body.ref_type
    if hasattr(m,"etab_destination"): m.etab_destination=body.etab_destination
    db.add(m); db.flush()
    _log(db,m.id,None,"EN_ATTENTE",user.username,"Création"); db.commit(); db.refresh(m)
    _notif(db,m,user); _creer_transfert(db,m,user)
    _log_mc(db, user, "CRÉATION", f"Réf:{m.ref_patient} {m.uf_origine}→{m.uf_destination}")
    if body.avec_retour and body.uf_destination:
        mr = BrcMission(ref_patient=body.ref_patient.strip(),
            uf_origine=body.uf_destination.strip(), chambre_depart=body.chambre_arrivee,
            uf_destination=body.uf_origine.strip(), chambre_arrivee=body.chambre_depart,
            type_transport=body.type_transport, priorite=body.priorite,
            motif=(body.motif or "")+" [RETOUR]",
            programmee=1 if body.heure_retour else 0, heure_prevue=body.heure_retour,
            demandeur_id=user.username, demandeur_nom=user.display_name or user.username)
        db.add(mr); db.flush(); _log(db,mr.id,None,"EN_ATTENTE",user.username,"Retour"); db.commit()
    return _fmt(m)

@router.post("/missions/{mission_id}/prendre_en_charge")
def prendre_en_charge(mission_id: int, body: PriseEnCharge,
                      db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    m = db.query(BrcMission).filter(BrcMission.id==mission_id).first()
    if not m: raise HTTPException(404)
    if m.statut not in ("EN_ATTENTE",):
        raise HTTPException(400,f"Statut '{m.statut}' invalide pour prise en charge")
    ancien=m.statut; m.agent_id=user.username; m.agent_nom=body.agent_nom
    if hasattr(m,"agent_tel"): m.agent_tel=body.agent_tel
    m.statut="EN_COURS"; m.prise_en_charge_at=datetime.now(timezone.utc)
    m.updated_at=datetime.now(timezone.utc)
    comment=f"Pris en charge par {body.agent_nom}"
    if body.agent_tel: comment+=f" — {body.agent_tel}"
    _log(db,mission_id,ancien,"EN_COURS",user.username,comment); db.commit()
    return _fmt(m)

@router.patch("/missions/{mission_id}")
def update_status(mission_id: int, body: MissionPatch,
                  db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    m = db.query(BrcMission).filter(BrcMission.id==mission_id).first()
    if not m: raise HTTPException(404)
    nouveau=body.statut.upper()
    if nouveau not in STATUTS: raise HTTPException(400,f"Statut invalide: {nouveau}")
    ancien=m.statut; m.statut=nouveau; m.updated_at=datetime.now(timezone.utc)
    if nouveau in ("TERMINE","ANNULE"): m.termine_at=datetime.now(timezone.utc)
    _log(db,mission_id,ancien,nouveau,user.username,body.commentaire or ""); db.commit()
    _log_mc(db, user, f"STATUT → {nouveau}", f"Mission #{mission_id} Réf:{m.ref_patient}")
    return _fmt(m)

@router.post("/missions/{mission_id}/arrivee")
def accuser_arrivee(mission_id: int, body: ArriveeIn,
                    db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    m = db.query(BrcMission).filter(BrcMission.id==mission_id).first()
    if not m: raise HTTPException(404)
    ancien=m.statut; m.statut="TERMINE"; m.termine_at=datetime.now(timezone.utc)
    m.updated_at=datetime.now(timezone.utc)
    _log(db,mission_id,ancien,"TERMINE",user.username,
         "Arrivée confirmée"+(f" — {body.commentaire}" if body.commentaire else ""))
    db.commit(); return _fmt(m)

@router.get("/sync")
def sync_missions(db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    q = db.query(BrcMission).filter(BrcMission.type_transport=="AMBULANCE",
                                     BrcMission.statut.notin_(["TERMINE","ANNULE"]))
    return [_fmt(m) for m in q.order_by(BrcMission.created_at.desc()).limit(50).all()]

@router.get("/stats")
def get_stats(db: Session=Depends(get_db), user=Depends(_require_branc)):
    if not user: raise HTTPException(401)
    today=datetime.now(timezone.utc).date().isoformat()
    return {"total":db.query(BrcMission).count(),
            "actives":db.query(BrcMission).filter(BrcMission.statut.notin_(["TERMINE","ANNULE"])).count(),
            "urgentes":db.query(BrcMission).filter(BrcMission.statut.notin_(["TERMINE","ANNULE"]),BrcMission.priorite=="P1").count(),
            "terminees_jour":db.query(BrcMission).filter(BrcMission.statut=="TERMINE",BrcMission.updated_at>=today).count(),
            "en_cours":db.query(BrcMission).filter(BrcMission.statut=="EN_COURS").count()}
