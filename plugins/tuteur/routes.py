"""
plugins/tuteur/routes.py — API REST du plugin Tuteur
======================================================
Squelette jour 1 : 9 routes, sans logique IA.
Les routes IA (rappel, debriefing) renvoient un stub explicite — implémentées
dans les jours 3-5 du plan de dev.

Toutes les routes sont préfixées /api/v1/tuteur/ (cf. plugin.py).
"""
import logging
import os
from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, require_admin
from app.api.ai_router import call_ai, get_ai_config, require_ia_configured
from app.models import User
from plugins.tuteur.models import (
    TuteurSession, TuteurObservation, TuteurRappel,
    TuteurDebriefing, TuteurEquipe,
)

logger = logging.getLogger("scribe.tuteur.routes")
router = APIRouter()


# ── Schémas Pydantic ─────────────────────────────────────────────────────────

class SessionStartIn(BaseModel):
    mode: str  # "exercice" | "prod"
    instance_sigle: str
    scenario_id: Optional[str] = None
    intention_pedago: Optional[str] = None


class SessionEndIn(BaseModel):
    session_id: int


class ObservationIn(BaseModel):
    session_id: int
    type_observation: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    detail: Optional[dict] = None
    latence_s: Optional[int] = None


class RappelAckIn(BaseModel):
    rappel_id: int
    action_apres: str  # COMPRIS | PAS_PERTINENT | DESACTIVE | PAS_MAINTENANT


class ConfigUpdateIn(BaseModel):
    seuil_inactivite_exercice_min: Optional[int] = None
    seuil_inactivite_prod_min:     Optional[int] = None
    actif_en_prod:                 Optional[bool] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_session(s: TuteurSession) -> dict:
    return {
        "id":               s.id,
        "user_id":          s.user_id,
        "username":         s.username,
        "instance_sigle":   s.instance_sigle,
        "mode":             s.mode,
        "scenario_id":      s.scenario_id,
        "intention_pedago": s.intention_pedago,
        "started_at":       s.started_at.isoformat() if s.started_at else None,
        "ended_at":         s.ended_at.isoformat()   if s.ended_at   else None,
    }


# ── Routes — sessions ────────────────────────────────────────────────────────

@router.post("/session/start")
def session_start(
    payload: SessionStartIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Démarre une session de suivi pédagogique (début exercice ou shift prod)."""
    if payload.mode not in ("exercice", "prod"):
        raise HTTPException(400, "mode invalide (exercice|prod)")

    s = TuteurSession(
        user_id          = user.id,
        username         = user.username,
        instance_sigle   = payload.instance_sigle,
        mode             = payload.mode,
        scenario_id      = payload.scenario_id,
        intention_pedago = payload.intention_pedago,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    logger.info(f"tuteur.session.start id={s.id} user={user.username} "
                f"mode={s.mode} scenario={s.scenario_id}")
    return _serialize_session(s)


@router.post("/session/end")
def session_end(
    payload: SessionEndIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Termine une session. Le debriefing est généré séparément (Hook 3)."""
    s = db.query(TuteurSession).filter_by(id=payload.session_id).first()
    if not s:
        raise HTTPException(404, "session introuvable")
    if s.ended_at is not None:
        return _serialize_session(s)  # idempotent

    s.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    logger.info(f"tuteur.session.end id={s.id} duree_s="
                f"{int((s.ended_at - s.started_at).total_seconds()) if s.started_at else 0}")
    return _serialize_session(s)


# ── Routes — observations ────────────────────────────────────────────────────

@router.post("/observation")
def add_observation(
    payload: ObservationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enregistre une observation. Appelé par les autres plugins via hooks (Jour 5)."""
    # Vérifier que la session existe et appartient à l'utilisateur courant
    # (sécurité de base : un user ne peut pas écrire dans la session d'un autre)
    s = db.query(TuteurSession).filter_by(id=payload.session_id).first()
    if not s:
        raise HTTPException(404, "session introuvable")
    if s.user_id is not None and s.user_id != user.id:
        # Un admin peut écrire dans n'importe quelle session
        if not getattr(user, "is_admin", False):
            raise HTTPException(403, "session appartient à un autre utilisateur")

    obs = TuteurObservation(
        session_id       = payload.session_id,
        type_observation = payload.type_observation,
        target_type      = payload.target_type,
        target_id        = payload.target_id,
        detail           = payload.detail,
        latence_s        = payload.latence_s,
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    return {"observation_id": obs.id, "session_id": obs.session_id}


# ── Hook 2A — Rappel discret pendant l'exercice (v2322) ──────────────────────

class RappelRequestIn(BaseModel):
    session_id: int
    contexte: Optional[dict] = None  # incidents_ouverts, dernieres_actions, minutes_inactivite


@router.post("/rappel")
async def generate_rappel(
    payload: RappelRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Génère un rappel pédagogique bienveillant via IA quand un utilisateur
    semble bloqué pendant un exercice. Anti-spam : refuse de générer si un
    rappel a déjà été émis dans les 10 dernières minutes pour cette session.
    """
    s = db.query(TuteurSession).filter_by(id=payload.session_id).first()
    if not s:
        raise HTTPException(404, "session introuvable")

    # Anti-spam : 1 rappel max toutes les 10 min par session
    recent_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
    recent = db.query(TuteurRappel).filter(
        TuteurRappel.session_id == payload.session_id,
        TuteurRappel.timestamp > recent_threshold,
    ).first()
    if recent:
        return {
            "skipped":   True,
            "reason":    "anti_spam",
            "message":   "Un rappel récent existe déjà",
            "rappel_id": recent.id,
        }

    # Vérifier qu'une IA est configurée
    err = require_ia_configured()
    if err:
        # Fallback : rappel statique générique sans IA
        contenu_fallback = (
            "💡 Petit point d'étape : prends un moment pour relire les incidents "
            "ouverts. Y a-t-il une action prioritaire à mener, une décision à acter, "
            "un transfert à organiser ? L'inaction face à une crise est souvent plus "
            "coûteuse qu'une action imparfaite mais rapide."
        )
        rappel = TuteurRappel(
            session_id=payload.session_id,
            contexte=payload.contexte,
            contenu=contenu_fallback,
            ack=False,
        )
        db.add(rappel); db.commit(); db.refresh(rappel)
        return {
            "rappel_id":   rappel.id,
            "contenu":     contenu_fallback,
            "ia_provider": None,
            "fallback":    True,
        }

    # Génération IA
    ctx = payload.contexte or {}
    incidents_ouverts = ctx.get("incidents_ouverts", [])
    minutes_inactif = ctx.get("minutes_inactivite", 0)

    incidents_txt = "\n".join([
        f"  - [{inc.get('urgency','?')}] {inc.get('fait','')[:120]} ({inc.get('type_crise','?')})"
        for inc in incidents_ouverts[:5]
    ]) or "(aucun)"

    intention = s.intention_pedago or "(pas d'intention pédagogique précisée)"

    prompt = f"""Tu es un compagnon d'apprentissage en gestion de crise hospitalière, bienveillant et pédagogue. Ton rôle n'est PAS de juger ni de critiquer : tu suggères, tu aiguilles, tu rassures.

CONTEXTE :
- Un apprenant joue un exercice de gestion de crise
- Son intention pédagogique pour cet exercice : {intention}
- Il est en mode exercice depuis {minutes_inactif} minutes sans action visible
- Incidents ouverts en ce moment :
{incidents_txt}

Écris un message court (3-4 phrases maximum, 250 caractères max), au tutoiement, qui :
- Reconnaît qu'une crise est intense et qu'on peut se sentir submergé
- Suggère 1 ou 2 pistes concrètes liées aux incidents ouverts (pas une liste exhaustive)
- Reste bienveillant, jamais culpabilisant
- N'utilise PAS d'exclamation forcée, pas de "courage !" ou "tu peux le faire !"

Réponds UNIQUEMENT avec le texte du message, sans préambule ni guillemets."""

    cfg = get_ai_config()
    system_msg = "Tu es un compagnon d'apprentissage en gestion de crise hospitalière, bienveillant et pédagogue. Tu écris en français, au tutoiement, sans culpabiliser."
    try:
        contenu_ia, _src = await call_ai(
            system=system_msg,
            prompt=prompt,
            max_tokens=200,
        )
        contenu_ia = (contenu_ia or "").strip().strip('"').strip()
        if len(contenu_ia) > 500:
            contenu_ia = contenu_ia[:497] + "…"
    except Exception as e:
        logger.warning(f"tuteur.rappel: IA indisponible, fallback ({e})")
        contenu_ia = (
            "💡 Une pause pour respirer : reprends les incidents ouverts un par un, "
            "et demande-toi quelle est la prochaine décision à acter. Une décision "
            "imparfaite vaut mieux qu'une attente prolongée."
        )

    rappel = TuteurRappel(
        session_id=payload.session_id,
        contexte=payload.contexte,
        contenu=contenu_ia,
        ack=False,
    )
    db.add(rappel); db.commit(); db.refresh(rappel)

    # Tracer l'observation
    obs = TuteurObservation(
        session_id=payload.session_id,
        type_observation="RAPPEL_AFFICHE",
        target_type="rappel",
        target_id=rappel.id,
        detail={"minutes_inactif": minutes_inactif},
    )
    db.add(obs); db.commit()

    return {
        "rappel_id":   rappel.id,
        "contenu":     contenu_ia,
        "ia_provider": cfg.provider,
        "fallback":    False,
    }


@router.post("/rappel/ack")
def ack_rappel(
    payload: RappelAckIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Acquitte un rappel (action_apres : COMPRIS|PAS_PERTINENT|DESACTIVE|PAS_MAINTENANT)."""
    valid_actions = {"COMPRIS", "PAS_PERTINENT", "DESACTIVE", "PAS_MAINTENANT"}
    if payload.action_apres not in valid_actions:
        raise HTTPException(400, f"action_apres doit être l'un de {valid_actions}")

    rappel = db.query(TuteurRappel).filter_by(id=payload.rappel_id).first()
    if not rappel:
        raise HTTPException(404, "rappel introuvable")

    rappel.ack = True
    rappel.ack_at = datetime.now(timezone.utc)
    rappel.action_apres = payload.action_apres
    db.commit()
    return {"ok": True, "rappel_id": rappel.id, "action_apres": payload.action_apres}


# ── Hook 3 — Debriefing post-exercice (v2322) ────────────────────────────────

@router.post("/debriefing/{session_id}")
async def generate_debriefing(
    session_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Génère un debriefing structuré post-exercice via IA :
    - synthèse globale
    - points forts (3-5 items)
    - axes d'amélioration (3-5 items)
    - recommandations pour le prochain exercice (2-4 items)
    - score global indicatif (0-100)

    Si un debriefing existe déjà pour cette session, le retourne tel quel,
    sauf si force=true.
    """
    s = db.query(TuteurSession).filter_by(id=session_id).first()
    if not s:
        raise HTTPException(404, "session introuvable")

    # Existe déjà ?
    existing = db.query(TuteurDebriefing).filter_by(session_id=session_id).first()
    if existing and not force:
        return _serialize_debriefing(existing)

    # Vérifier IA
    err = require_ia_configured()
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Récolter les éléments observés pendant la session
    obs_list = db.query(TuteurObservation).filter_by(session_id=session_id)\
        .order_by(TuteurObservation.timestamp.asc()).all()

    nb_actions    = sum(1 for o in obs_list if o.type_observation in ("ACTION","DECISION","INCIDENT_CREE","TRANSFERT","MESSAGE_ENVOYE"))
    nb_decisions  = sum(1 for o in obs_list if o.type_observation == "DECISION")
    nb_incidents  = sum(1 for o in obs_list if o.type_observation == "INCIDENT_CREE")
    nb_transferts = sum(1 for o in obs_list if o.type_observation == "TRANSFERT")
    nb_messages   = sum(1 for o in obs_list if o.type_observation == "MESSAGE_ENVOYE")
    nb_rappels    = sum(1 for o in obs_list if o.type_observation == "RAPPEL_AFFICHE")

    # Durée
    duree_s = 0
    if s.started_at and s.ended_at:
        duree_s = int((s.ended_at - s.started_at).total_seconds())
    elif s.started_at:
        duree_s = int((datetime.now(timezone.utc) - s.started_at).total_seconds())

    # Construire la timeline résumée pour l'IA (top 30 obs max)
    timeline = []
    for o in obs_list[:30]:
        ts = o.timestamp.strftime("%H:%M") if o.timestamp else "?"
        line = f"  [{ts}] {o.type_observation}"
        if o.target_type and o.target_id:
            line += f" {o.target_type}#{o.target_id}"
        if o.detail and isinstance(o.detail, dict):
            d_str = ", ".join(f"{k}={v}" for k,v in list(o.detail.items())[:3])
            if d_str:
                line += f" ({d_str})"
        timeline.append(line)
    timeline_txt = "\n".join(timeline) or "  (aucune observation enregistrée)"

    intention = s.intention_pedago or "(intention pédagogique non précisée)"
    duree_min = duree_s // 60

    prompt = f"""Tu es un coach pédagogique en gestion de crise hospitalière. Tu rédiges un debriefing constructif et bienveillant pour un apprenant qui vient de jouer un exercice.

CONTEXTE DE L'EXERCICE :
- Intention pédagogique de l'apprenant : {intention}
- Durée jouée : {duree_min} minutes
- Mode : {s.mode}

ACTIVITÉ OBSERVÉE :
- {nb_actions} actions au total
- {nb_incidents} incidents créés
- {nb_decisions} décisions actées
- {nb_transferts} transferts gérés
- {nb_messages} messages envoyés
- {nb_rappels} rappel(s) du tuteur affiché(s)

TIMELINE DES PRINCIPALES OBSERVATIONS (UTC) :
{timeline_txt}

CONSIGNES :
- Tu dois RÉPONDRE EN JSON UNIQUEMENT, sans préambule, sans markdown.
- Sois bienveillant : tu parles à quelqu'un qui apprend.
- Sois concret : appuie-toi sur les chiffres et la timeline réelle.
- Ne juge JAMAIS l'apprenant. Tu observes, tu suggères, tu encourages.
- Tutoiement systématique.

FORMAT JSON ATTENDU (respecte exactement les clés) :
{{
  "synthese": "2-3 phrases qui résument l'exercice et le ressenti probable de l'apprenant",
  "points_forts": ["3 à 5 points forts concrets, formulés positivement"],
  "axes_amelioration": ["3 à 5 axes d'amélioration formulés comme des suggestions, pas des reproches"],
  "recommandations": ["2 à 4 recommandations concrètes pour le prochain exercice"],
  "score_global": un entier entre 30 et 95 reflétant l'engagement et la cohérence des actions, pas la performance pure
}}

Réponds maintenant avec UNIQUEMENT le JSON."""

    cfg = get_ai_config()
    import json as _json

    debrief_system = "Tu es un coach pédagogique en gestion de crise hospitalière, bienveillant. Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans préambule. Tutoiement systématique. Jamais de jugement."
    try:
        raw, _src = await call_ai(
            system=debrief_system,
            prompt=prompt,
            max_tokens=1200,
        )
        raw = (raw or "").strip()
        # Retirer un éventuel ```json ... ```
        if raw.startswith("```"):
            raw = raw.split("```")[1] if "```" in raw[3:] else raw[3:]
            if raw.lstrip().startswith("json"):
                raw = raw.lstrip()[4:]
        raw = raw.strip()
        # Ne garder que le premier objet JSON
        first_brace = raw.find("{")
        last_brace = raw.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            raw = raw[first_brace:last_brace+1]

        parsed = _json.loads(raw)
    except HTTPException:
        # call_ai a déjà levé une HTTPException claire (401/503/504) — on la relance
        raise
    except _json.JSONDecodeError as e:
        logger.error(f"tuteur.debriefing: JSON IA invalide ({e}). Raw: {raw[:300] if 'raw' in dir() else '?'}")
        raise HTTPException(503, f"L'IA n'a pas retourné un JSON valide. Réessaie dans quelques secondes.")
    except Exception as e:
        logger.error(f"tuteur.debriefing: parsing IA échoué ({e}). Raw: {raw[:300] if 'raw' in dir() else '?'}")
        raise HTTPException(503, f"Génération IA échouée : {str(e)[:200]}")

    # Validation des clés
    synthese          = (parsed.get("synthese") or "")[:2000]
    points_forts      = parsed.get("points_forts") or []
    axes_amelioration = parsed.get("axes_amelioration") or []
    recommandations   = parsed.get("recommandations") or []
    score_global      = parsed.get("score_global")
    if not isinstance(score_global, int):
        try:    score_global = int(score_global)
        except: score_global = None

    # Sauver (remplace si force=true)
    if existing and force:
        db.delete(existing)
        db.commit()

    deb = TuteurDebriefing(
        session_id        = session_id,
        synthese          = synthese,
        points_forts      = points_forts,
        axes_amelioration = axes_amelioration,
        recommandations   = recommandations,
        score_global      = score_global,
        ia_provider       = cfg.provider,
    )
    db.add(deb); db.commit(); db.refresh(deb)
    logger.info(f"tuteur.debriefing.generated session={session_id} score={score_global} provider={cfg.provider}")
    return _serialize_debriefing(deb)


def _serialize_debriefing(deb: TuteurDebriefing) -> dict:
    return {
        "id":                deb.id,
        "session_id":        deb.session_id,
        "generated_at":      deb.generated_at.isoformat() if deb.generated_at else None,
        "synthese":          deb.synthese,
        "points_forts":      deb.points_forts or [],
        "axes_amelioration": deb.axes_amelioration or [],
        "recommandations":   deb.recommandations or [],
        "score_global":      deb.score_global,
        "ia_provider":       deb.ia_provider,
    }


@router.get("/debriefing/{session_id}")
def get_debriefing(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne le debriefing s'il existe, 404 sinon."""
    deb = db.query(TuteurDebriefing).filter_by(session_id=session_id).first()
    if not deb:
        raise HTTPException(404, "Aucun debriefing pour cette session")
    return _serialize_debriefing(deb)



# ── Routes — historique ──────────────────────────────────────────────────────

@router.get("/historique")
def historique(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne les 50 dernières sessions de l'utilisateur connecté."""
    sessions = (
        db.query(TuteurSession)
        .filter_by(user_id=user.id)
        .order_by(TuteurSession.started_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize_session(s) for s in sessions]


@router.get("/equipe/{exercice_id}")
def equipe(
    exercice_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bilan équipe d'un exercice multi-joueurs. À implémenter au Jour 6 (bonus)."""
    return {
        "todo":        "Implémenté au Jour 6 (bonus) — mode équipe",
        "exercice_id": exercice_id,
    }


# ── Routes — config ──────────────────────────────────────────────────────────

@router.get("/config")
def get_config(user: User = Depends(get_current_user)):
    """Retourne la config tuteur (seuils d'inactivité, activation prod)."""
    return {
        "seuil_inactivite_exercice_min": int(os.getenv("SCRIBE_TUTEUR_SEUIL_EXO",  "8")),
        "seuil_inactivite_prod_min":     int(os.getenv("SCRIBE_TUTEUR_SEUIL_PROD", "12")),
        "actif_en_prod": os.getenv("SCRIBE_TUTEUR_PROD", "0") == "1",
        "version":       "0.5-alpha",
    }


@router.put("/config")
def put_config(
    payload: ConfigUpdateIn,
    user: User = Depends(require_admin),
):
    """Modifie la config tuteur. À implémenter complètement au Jour 4."""
    return {
        "todo":   "Persistance config implémentée au Jour 4 (Hook 2B)",
        "received": payload.dict(exclude_none=True),
    }
