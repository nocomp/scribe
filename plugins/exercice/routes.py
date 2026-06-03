"""
plugins/exercice/routes.py — API REST du plugin Exercice de crise
Toutes les routes sont préfixées /api/v1/exercice/
"""
import json
import os
import uuid
import zipfile
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, require_admin
from app.models import User
from plugins.exercice.models import (
    ExoScenario, ExoSession, ExoInjection, ExoJoueur, ExoActionLog
)
import plugins.exercice.injector as injector
from plugins.exercice import generator

logger = logging.getLogger("scribe.exercice.routes")

router = APIRouter()

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_base_urls(session: ExoSession) -> dict:
    """Construit le dict {sigle: url} depuis les sites actifs de la session."""
    EXO_PORTS = {
        "DEMO1": 8660, "DEMO2": 8661, "DEMO5": 8662,
        "DEMO6": 8663, "DEMO7": 8664, "DEMO5": 8665, "DEMO6": 8666,
    }
    host = os.getenv("SCRIBE_EXO_HOST", "http://localhost")
    sites = json.loads(session.sites_actifs or "[]")
    return {s: f"{host}:{EXO_PORTS.get(s, 8660)}" for s in sites}

def _get_token(request: Request, db: Session) -> str:
    """Récupère le token animateur pour les appels inter-instances."""
    # Token admin depuis env ou DB
    return os.getenv("SCRIBE_EXO_ANIM_TOKEN", "")

def _current_session(db: Session) -> Optional[ExoSession]:
    return db.query(ExoSession).filter(
        ExoSession.status.in_(["EN_COURS", "PAUSE", "PRET"])
    ).order_by(ExoSession.created_at.desc()).first()


# ── Schémas Pydantic ──────────────────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    titre: str
    description: Optional[str] = ""
    duree_min: int = 60
    duree_reel_min: int = 240
    complexite: str = "MOYEN"
    type_crise: str = "SANITAIRE"
    sujet: Optional[str] = ""
    contenu_json: dict  # JSON complet du scénario

class ScenarioGenerate(BaseModel):
    sujet: str
    nb_sites: int = 1
    sites: List[str] = ["DEMO1"]
    duree_exercice_min: int = 60
    duree_reel_min: int = 240
    complexite: str = "MOYEN"
    type_crise: str = "SANITAIRE"
    langue: str = "fr"

class SessionStart(BaseModel):
    scenario_id: str
    sites_actifs: List[str]
    animateur: Optional[str] = ""

class JoueurCreate(BaseModel):
    session_uid: str
    username: str
    display_name: str
    role_exercice: str
    sigle_site: str
    port_site: int
    password_tmp: Optional[str] = "Exercice2026!"

class ActionLogCreate(BaseModel):
    session_uid: str
    action_type: str
    action_detail: Optional[str] = ""
    ref_id: Optional[int] = None
    stimulus_id: Optional[str] = None

class SessionArchive(BaseModel):
    notes_animateur: Optional[str] = ""


# ── SCÉNARIOS ─────────────────────────────────────────────────────────────────

@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401)
    scenarios = db.query(ExoScenario).filter(ExoScenario.archive == False).order_by(
        ExoScenario.created_at.desc()
    ).all()
    return [
        {
            "id": s.id,
            "scenario_id": s.scenario_id,
            "titre": s.titre,
            "description": s.description,
            "duree_min": s.duree_min,
            "duree_reel_min": s.duree_reel_min,
            "complexite": s.complexite,
            "type_crise": s.type_crise,
            "nb_sites": s.nb_sites,
            "genere_par_ia": s.genere_par_ia,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in scenarios
    ]


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401)
    s = db.query(ExoScenario).filter(ExoScenario.scenario_id == scenario_id).first()
    if not s:
        raise HTTPException(404, "Scénario non trouvé")
    return {"scenario": json.loads(s.contenu_json), "meta_db": {
        "id": s.id, "created_at": s.created_at.isoformat() if s.created_at else None,
        "genere_par_ia": s.genere_par_ia,
    }}


@router.post("/scenarios")
def create_scenario(body: ScenarioCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sid = body.contenu_json.get("meta", {}).get("id") or f"exo_{uuid.uuid4().hex[:8]}"
    existing = db.query(ExoScenario).filter(ExoScenario.scenario_id == sid).first()
    if existing:
        raise HTTPException(409, f"Scénario {sid} existe déjà")
    s = ExoScenario(
        scenario_id=sid,
        titre=body.titre,
        description=body.description,
        duree_min=body.duree_min,
        duree_reel_min=body.duree_reel_min,
        ratio_compression=round(body.duree_reel_min / body.duree_min, 1),
        complexite=body.complexite,
        type_crise=body.type_crise,
        sujet=body.sujet,
        nb_sites=len(body.contenu_json.get("acteurs", [])) or 1,
        contenu_json=json.dumps(body.contenu_json, ensure_ascii=False),
        genere_par_ia=False,
        created_by=user.username,
    )
    db.add(s); db.commit(); db.refresh(s)
    return {"ok": True, "scenario_id": s.scenario_id, "id": s.id}


@router.post("/scenarios/generate")
async def generate_scenario_ia(
    body: ScenarioGenerate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Génère un scénario via Albert IA."""
    result = await generator.generate_scenario(
        sujet=body.sujet,
        nb_sites=body.nb_sites,
        sites=body.sites,
        duree_exercice_min=body.duree_exercice_min,
        duree_reel_min=body.duree_reel_min,
        complexite=body.complexite,
        type_crise=body.type_crise,
        langue=body.langue,
    )
    if not result["ok"]:
        raise HTTPException(500, result.get("error", "Erreur IA"))

    scenario = result["scenario"]
    meta = scenario.get("meta", {})
    sid = meta.get("id") or f"exo_ia_{uuid.uuid4().hex[:8]}"

    s = ExoScenario(
        scenario_id=sid,
        titre=meta.get("titre", "Scénario IA"),
        description=meta.get("description", ""),
        duree_min=meta.get("duree_min", body.duree_exercice_min),
        duree_reel_min=meta.get("duree_reel_min", body.duree_reel_min),
        ratio_compression=meta.get("ratio_compression", 4.0),
        complexite=meta.get("complexite", body.complexite),
        type_crise=meta.get("type_crise", body.type_crise),
        sujet=body.sujet,
        nb_sites=body.nb_sites,
        contenu_json=json.dumps(scenario, ensure_ascii=False),
        genere_par_ia=True,
        prompt_ia=body.sujet,
        created_by=user.username,
    )
    db.add(s); db.commit(); db.refresh(s)
    return {"ok": True, "scenario_id": s.scenario_id, "scenario": scenario}


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    s = db.query(ExoScenario).filter(ExoScenario.scenario_id == scenario_id).first()
    if not s:
        raise HTTPException(404)
    s.archive = True
    db.commit()
    return {"ok": True}


# ── SESSION ───────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401)
    session = _current_session(db)
    inj_state = injector.get_state()
    return {
        "session": {
            "uid": session.session_uid,
            "status": session.status,
            "scenario_titre": session.scenario_titre,
            "sites_actifs": json.loads(session.sites_actifs or "[]"),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "animateur": session.animateur,
        } if session else None,
        "injector": inj_state,
        "exercice_mode": os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1",
    }


@router.post("/start")
def start_session(
    body: SessionStart,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if injector.get_state()["running"]:
        raise HTTPException(409, "Un exercice est déjà en cours")

    s = db.query(ExoScenario).filter(ExoScenario.scenario_id == body.scenario_id).first()
    if not s:
        raise HTTPException(404, "Scénario non trouvé")

    scenario = json.loads(s.contenu_json)
    session_uid = f"exo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    session = ExoSession(
        session_uid=session_uid,
        scenario_id=body.scenario_id,
        scenario_titre=s.titre,
        status="EN_COURS",
        started_at=datetime.now(timezone.utc),
        sites_actifs=json.dumps(body.sites_actifs),
        animateur=body.animateur or user.username,
        ratio_compression=s.ratio_compression,
    )
    db.add(session); db.commit()

    token = _get_token(request, db)
    base_urls = _get_base_urls(session)
    injector.start(scenario, session_uid, token, base_urls)

    logger.info(f"Session {session_uid} démarrée par {user.username}")
    return {"ok": True, "session_uid": session_uid}


@router.post("/pause")
def pause_session(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    session = _current_session(db)
    if not session or session.status != "EN_COURS":
        raise HTTPException(400, "Aucune session en cours")
    ok = injector.pause()
    if ok:
        session.status = "PAUSE"
        session.paused_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": ok}


@router.post("/resume")
def resume_session(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    session = _current_session(db)
    if not session or session.status != "PAUSE":
        raise HTTPException(400, "Aucune session en pause")
    ok = injector.resume()
    if ok:
        session.status = "EN_COURS"
        db.commit()
    return {"ok": ok}


@router.post("/stop")
def stop_session(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    session = _current_session(db)
    if not session:
        raise HTTPException(400, "Aucune session active")
    injector.stop()
    session.status = "TERMINE"
    session.stopped_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "session_uid": session.session_uid}


@router.post("/inject/{stimulus_id}")
async def inject_manual(
    stimulus_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Injection manuelle d'un stimulus par l'animateur."""
    session = _current_session(db)
    if not session:
        raise HTTPException(400, "Aucune session active")
    token = _get_token(request, db)
    base_urls = _get_base_urls(session)
    result = await injector.inject_one(stimulus_id, token, base_urls)
    if result.get("ok"):
        db.add(ExoInjection(
            session_uid=session.session_uid,
            stimulus_id=stimulus_id,
            stimulus_type="manuel",
            cible_sigle="ANIMATEUR",
            cible_port=0,
            t_min_prevu=0,
            injected_at=datetime.now(timezone.utc),
            success=True,
            manuel=True,
        ))
        db.commit()
    return result


# ── BILAN ─────────────────────────────────────────────────────────────────────

@router.get("/bilan/{session_uid}")
async def get_bilan(
    session_uid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)
    session = db.query(ExoSession).filter(ExoSession.session_uid == session_uid).first()
    if not session:
        raise HTTPException(404)

    # Si bilan déjà généré → retourner le cache
    if session.bilan_ia:
        return {"ok": True, "bilan": json.loads(session.bilan_ia), "cached": True}

    # Sinon générer via IA
    scenario_db = db.query(ExoScenario).filter(ExoScenario.scenario_id == session.scenario_id).first()
    if not scenario_db:
        raise HTTPException(404, "Scénario introuvable")

    scenario = json.loads(scenario_db.contenu_json)
    injections = db.query(ExoInjection).filter(ExoInjection.session_uid == session_uid).all()
    actions = db.query(ExoActionLog).filter(ExoActionLog.session_uid == session_uid).all()

    result = await generator.generate_bilan(session_uid, scenario, injections, actions)
    if result["ok"]:
        session.bilan_ia = json.dumps(result["bilan"], ensure_ascii=False)
        session.bilan_at = datetime.now(timezone.utc)
        db.commit()

    return result


# ── ARCHIVE ───────────────────────────────────────────────────────────────────

@router.post("/archive/{session_uid}")
def archive_session(
    session_uid: str,
    body: SessionArchive,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Archive une session terminée : ZIP contenant toutes les données."""
    session = db.query(ExoSession).filter(ExoSession.session_uid == session_uid).first()
    if not session:
        raise HTTPException(404)
    if session.status not in ["TERMINE", "PAUSE"]:
        raise HTTPException(400, "Seules les sessions terminées peuvent être archivées")

    # Construire les données d'archive
    injections = db.query(ExoInjection).filter(ExoInjection.session_uid == session_uid).all()
    actions = db.query(ExoActionLog).filter(ExoActionLog.session_uid == session_uid).all()
    joueurs = db.query(ExoJoueur).filter(ExoJoueur.session_uid == session_uid).all()

    archive_data = {
        "session": {
            "uid": session.session_uid,
            "scenario_id": session.scenario_id,
            "scenario_titre": session.scenario_titre,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
            "sites_actifs": json.loads(session.sites_actifs or "[]"),
            "animateur": session.animateur,
            "notes_animateur": body.notes_animateur,
        },
        "bilan_ia": json.loads(session.bilan_ia) if session.bilan_ia else None,
        "injections": [
            {
                "stimulus_id": i.stimulus_id, "type": i.stimulus_type,
                "cible": i.cible_sigle, "t_min_prevu": i.t_min_prevu,
                "injected_at": i.injected_at.isoformat() if i.injected_at else None,
                "success": i.success, "manuel": i.manuel,
            }
            for i in injections
        ],
        "actions": [
            {
                "t_s": a.t_exercice_s, "site": a.sigle_site,
                "auteur": a.username, "type": a.action_type, "detail": a.action_detail,
            }
            for a in actions
        ],
        "joueurs": [
            {
                "username": j.username, "display_name": j.display_name,
                "role": j.role_exercice, "site": j.sigle_site,
            }
            for j in joueurs
        ],
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }

    # Créer le ZIP
    import tempfile
    zip_name = f"exercice_{session_uid}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("session.json", json.dumps(archive_data, ensure_ascii=False, indent=2))
        if session.bilan_ia:
            zf.writestr("bilan_ia.json", session.bilan_ia)

    session.archive = True
    session.archive_at = datetime.now(timezone.utc)
    session.archive_zip = zip_path
    session.status = "ARCHIVE"
    if body.notes_animateur:
        session.notes_animateur = body.notes_animateur
    db.commit()

    return {
        "ok": True,
        "zip_path": zip_path,
        "session_uid": session_uid,
        "message": f"Session archivée dans {zip_name}",
    }


# ── JOUEURS ───────────────────────────────────────────────────────────────────

@router.get("/joueurs/{session_uid}")
def list_joueurs(session_uid: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401)
    joueurs = db.query(ExoJoueur).filter(ExoJoueur.session_uid == session_uid).all()
    return [
        {
            "id": j.id, "username": j.username, "display_name": j.display_name,
            "role_exercice": j.role_exercice, "sigle_site": j.sigle_site,
            "port_site": j.port_site,
        }
        for j in joueurs
    ]


@router.post("/joueurs")
def create_joueur(body: JoueurCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    j = ExoJoueur(
        session_uid=body.session_uid,
        username=body.username,
        display_name=body.display_name,
        role_exercice=body.role_exercice,
        sigle_site=body.sigle_site,
        port_site=body.port_site,
        password_tmp=body.password_tmp,
    )
    db.add(j); db.commit(); db.refresh(j)
    return {"ok": True, "id": j.id}


@router.delete("/joueurs/{joueur_id}")
def delete_joueur(joueur_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    j = db.query(ExoJoueur).filter(ExoJoueur.id == joueur_id).first()
    if not j:
        raise HTTPException(404)
    db.delete(j); db.commit()
    return {"ok": True}


# ── LOG ACTIONS ───────────────────────────────────────────────────────────────

@router.post("/log-action")
def log_action(body: ActionLogCreate, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Les instances exercice appellent cette route pour logger les actions des joueurs."""
    if not user:
        raise HTTPException(401)
    session = db.query(ExoSession).filter(ExoSession.session_uid == body.session_uid).first()
    t_elapsed = 0
    if session and session.started_at:
        t_elapsed = int((datetime.now(timezone.utc) - session.started_at.replace(tzinfo=timezone.utc)).total_seconds())

    sigle = os.getenv("SCRIBE_EXO_SIGLE", "DEMO1")
    a = ExoActionLog(
        session_uid=body.session_uid,
        t_exercice_s=t_elapsed,
        sigle_site=sigle,
        username=user.username,
        action_type=body.action_type,
        action_detail=body.action_detail,
        ref_id=body.ref_id,
        stimulus_id=body.stimulus_id,
    )
    db.add(a); db.commit()
    return {"ok": True}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    sessions = db.query(ExoSession).order_by(ExoSession.created_at.desc()).limit(50).all()
    return [
        {
            "uid": s.session_uid, "scenario_titre": s.scenario_titre,
            "status": s.status, "animateur": s.animateur,
            "sites": json.loads(s.sites_actifs or "[]"),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "archive": s.archive,
        }
        for s in sessions
    ]
