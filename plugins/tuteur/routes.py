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
from app.models import (
    User, SitrepEntry, Task, Decision,
    TransfertPatient, DeclarationSituation,
)
from plugins.tuteur.models import (
    TuteurSession, TuteurObservation, TuteurRappel,
    TuteurDebriefing, TuteurEquipe, TuteurCoachMessage,
)
from plugins.tuteur.coach_rules import evaluate_all_rules

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
    user: Optional[User] = Depends(get_current_user),
):
    """Démarre une session de suivi pédagogique (début exercice ou shift prod).

    v3.0.0 — Idempotent : si l'utilisateur a déjà une session active
    (ended_at IS NULL), on la retourne au lieu d'en créer une nouvelle.
    Évite les duplications quand le frontend rappelle start() après un
    F5 ou un changement d'onglet."""
    if user is None:
        raise HTTPException(401, "Authentification requise")
    if payload.mode not in ("exercice", "prod"):
        raise HTTPException(400, "mode invalide (exercice|prod)")

    # Idempotence : réutiliser la session active existante
    existing = (
        db.query(TuteurSession)
        .filter(TuteurSession.user_id == user.id,
                TuteurSession.ended_at.is_(None))
        .order_by(TuteurSession.started_at.desc())
        .first()
    )
    if existing is not None:
        logger.info(f"tuteur.session.start réutilise session existante id={existing.id} "
                    f"user={user.username}")
        return _serialize_session(existing)

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
    user: Optional[User] = Depends(get_current_user),
):
    """Retourne les 50 dernières sessions de l'utilisateur connecté."""
    if user is None:
        # v3.0.0 — Pas authentifié : retourner liste vide plutôt que 500
        return []
    sessions = (
        db.query(TuteurSession)
        .filter_by(user_id=user.id)
        .order_by(TuteurSession.started_at.desc())
        .limit(50)
        .all()
    )
    return [_serialize_session(s) for s in sessions]


@router.get("/session/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3.0.0 — Récupère une session par ID. Utilisé par le frontend pour
    vérifier qu'une session restaurée depuis localStorage existe toujours
    en base (sinon il en démarre une nouvelle). Retourne 404 si introuvable
    ou n'appartient pas à l'utilisateur."""
    s = db.query(TuteurSession).filter_by(id=session_id).first()
    if not s:
        raise HTTPException(404, "Session introuvable")
    if user is not None and s.user_id is not None and s.user_id != user.id:
        raise HTTPException(403, "Cette session appartient à un autre utilisateur")
    return _serialize_session(s)


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


# ─────────────────────────────────────────────────────────────────────────────
# v3.0.0 — Coach proactif (widget flottant)
# ─────────────────────────────────────────────────────────────────────────────

class CoachAckIn(BaseModel):
    snooze_minutes: Optional[int] = None  # si fourni : snooze au lieu de dismiss


@router.get("/coach/check")
def coach_check(
    session_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3.0.0 — Évalue les règles du coach et retourne les messages actifs.

    Polling depuis le widget flottant côté joueur (toutes les ~60s).

    Si session_id n'est pas fourni, on prend la dernière session OUVERTE
    de l'utilisateur courant. Sans session active, retourne une liste vide.
    """
    # Résoudre la session active si non fournie
    _is_exo = os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1"
    if session_id is None:
        if user is None:
            return {"messages": [], "session_id": None}
        s = (db.query(TuteurSession)
             .filter(TuteurSession.user_id == user.id,
                     TuteurSession.ended_at.is_(None))
             .order_by(TuteurSession.started_at.desc())
             .first())
        if not s:
            # v3000h32 — Création automatique de session AUSSI EN PROD (Example Network).
            # L'Assistant est une fonctionnalité à part entière qui doit fonctionner
            # dans tous les modes. Avant h32, seul le mode exercice créait des
            # sessions automatiquement → le badge de la bulle 🎓 ne s'affichait
            # jamais en prod, et les règles ne s'évaluaient pas.
            inst_sigle = os.getenv("SCRIBE_SIGLE", "INSTANCE")
            session_mode = "exercice" if _is_exo else "prod"
            s = TuteurSession(
                user_id=user.id,
                username=user.username,
                instance_sigle=inst_sigle,
                mode=session_mode,
            )
            db.add(s)
            db.commit()
            db.refresh(s)
            logger.info(
                f"coach_check : session {session_mode} créée automatiquement "
                f"(id={s.id}, user={user.username}, sigle={inst_sigle})"
            )
        session_id = s.id

    # 1) Évaluer les règles → candidats à émettre
    try:
        candidats = evaluate_all_rules(db, session_id, is_exercice=_is_exo)
    except Exception as e:
        logger.warning(f"coach_check : évaluation règles a échoué : {e}")
        candidats = []

    # 2) Persister les nouveaux candidats (l'anti-spam des règles a déjà filtré)
    for c in candidats:
        try:
            msg = TuteurCoachMessage(
                session_id   = session_id,
                rule_id      = c["rule_id"],
                priorite     = c.get("priorite", 2),
                type_msg     = c.get("type_msg", "info"),
                niveau       = c.get("niveau", "marker"),  # v3.1.0
                message      = c["message"],
                actions_json = c.get("actions_json"),
                target_type  = c.get("target_type"),
                target_id    = c.get("target_id"),
            )
            db.add(msg)
        except Exception as e:
            logger.warning(f"coach_check : persistance candidat échouée : {e}")
    db.commit()

    # 3) Retourner tous les messages ACTIFS (non-ack, non-snoozés)
    now = datetime.now(timezone.utc)
    actifs = (
        db.query(TuteurCoachMessage)
        .filter(
            TuteurCoachMessage.session_id == session_id,
            TuteurCoachMessage.ack_at.is_(None),
        )
        .order_by(
            TuteurCoachMessage.priorite.desc(),
            TuteurCoachMessage.created_at.desc(),
        )
        .limit(10)
        .all()
    )
    # Filtrer les snoozés au niveau Python (snooze_until peut être None)
    out = []
    for m in actifs:
        if m.snooze_until is not None:
            su = m.snooze_until
            if su.tzinfo is None:
                su = su.replace(tzinfo=timezone.utc)
            if su > now:
                continue
        out.append({
            "id":          m.id,
            "rule_id":     m.rule_id,
            "priorite":    m.priorite,
            "type_msg":    m.type_msg,
            "niveau":      getattr(m, "niveau", None) or "marker",  # v3.1.0
            "message":     m.message,
            "actions":     m.actions_json or [],
            "target_type": m.target_type,
            "target_id":   m.target_id,
            "created_at":  m.created_at.isoformat() if m.created_at else None,
        })

    return {"messages": out, "session_id": session_id}


# v3.1.0 — Historique complet des messages (ack ou non, snoozés inclus).
# Permet l'onglet "Historique" du panneau Assistant.
@router.get("/coach/history")
def coach_history(
    session_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Retourne l'historique complet des messages de la session courante.

    Inclut les messages ack (avec leur ack_at) et les snoozés. Triés du plus
    récent au plus ancien.
    """
    if session_id is None:
        if user is None:
            return {"messages": [], "session_id": None}
        s = (db.query(TuteurSession)
             .filter(TuteurSession.user_id == user.id,
                     TuteurSession.ended_at.is_(None))
             .order_by(TuteurSession.started_at.desc())
             .first())
        if not s:
            return {"messages": [], "session_id": None}
        session_id = s.id

    msgs = (
        db.query(TuteurCoachMessage)
        .filter(TuteurCoachMessage.session_id == session_id)
        .order_by(TuteurCoachMessage.created_at.desc())
        .limit(max(1, min(200, limit)))
        .all()
    )
    out = []
    for m in msgs:
        out.append({
            "id":          m.id,
            "rule_id":     m.rule_id,
            "priorite":    m.priorite,
            "type_msg":    m.type_msg,
            "niveau":      getattr(m, "niveau", None) or "marker",
            "message":     m.message,
            "actions":     m.actions_json or [],
            "target_type": m.target_type,
            "target_id":   m.target_id,
            "created_at":  m.created_at.isoformat() if m.created_at else None,
            "ack_at":      m.ack_at.isoformat() if m.ack_at else None,
            "snooze_until": m.snooze_until.isoformat() if m.snooze_until else None,
        })
    return {"messages": out, "session_id": session_id}


@router.post("/coach/ack/{message_id}")
def coach_ack(
    message_id: int,
    payload: CoachAckIn,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3.0.0 — Marque un message coach comme lu (dismiss) ou snooze.

    - sans payload : dismiss définitif (ack_at = now)
    - avec snooze_minutes : ne plus afficher pendant N minutes
    """
    m = db.query(TuteurCoachMessage).filter_by(id=message_id).first()
    if not m:
        raise HTTPException(404, "Message coach introuvable")
    now = datetime.now(timezone.utc)
    if payload.snooze_minutes and payload.snooze_minutes > 0:
        m.snooze_until = now + timedelta(minutes=payload.snooze_minutes)
    else:
        m.ack_at = now
    db.commit()
    return {"ok": True, "id": message_id,
            "snoozed_until": m.snooze_until.isoformat() if m.snooze_until else None,
            "ack_at": m.ack_at.isoformat() if m.ack_at else None}


@router.post("/coach/mute")
def coach_mute(
    minutes: int = 10,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3.0.0 — Snooze TOUS les messages actifs pour la session courante.

    Utilisé par le bouton "Mute 10 min" dans le header du widget.
    """
    if user is None:
        raise HTTPException(401, "Authentification requise")
    s = (db.query(TuteurSession)
         .filter(TuteurSession.user_id == user.id,
                 TuteurSession.ended_at.is_(None))
         .order_by(TuteurSession.started_at.desc())
         .first())
    if not s:
        return {"ok": True, "muted_count": 0}
    until = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))
    actifs = (db.query(TuteurCoachMessage)
              .filter(TuteurCoachMessage.session_id == s.id,
                      TuteurCoachMessage.ack_at.is_(None))
              .all())
    for m in actifs:
        m.snooze_until = until
    db.commit()
    return {"ok": True, "muted_count": len(actifs),
            "until": until.isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# v3.0.0 — Génération de tâches Kanban depuis un incident via Albert
# ─────────────────────────────────────────────────────────────────────────────

class CoachSuggestPreviewOut(BaseModel):
    incident_id: int
    incident_titre: str
    actions: list[str]  # liste de 3 actions parsées
    source: str         # "albert" | "fallback"


class CoachCreateTasksIn(BaseModel):
    incident_id: int
    actions: list[str]  # actions validées par l'utilisateur (peuvent être éditées)
    priorite: Optional[int] = 3  # haute par défaut pour actions issues d'Assistant


def _strip_markdown(s: str) -> str:
    """Nettoie le markdown courant d'une chaîne pour usage final.

    Retire **gras**, *italique*, `code`, en gardant le contenu textuel.
    Ne touche pas aux caractères normaux.
    """
    import re
    if not s:
        return ""
    # Retirer **gras** et __gras__
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    # Retirer *italique* et _italique_ (mais éviter de casser les ** déjà traités)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", s)
    s = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", s)
    # Retirer `code`
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Retirer les guillemets " typographiques en début/fin
    s = s.strip().strip('"').strip("'").strip("«»").strip()
    return s


def _is_section_marker(line: str, label: str) -> bool:
    """Détecte si une ligne marque une section comme `ACTIONS:` ou `**ACTIONS:**`.

    Tolérant :
    - markdown **ACTIONS:**
    - sans deux-points : ACTIONS, **ACTIONS**
    - espaces autour : ACTIONS :, ACTIONS  :
    - majuscules ou non
    """
    import re
    if not line:
        return False
    # Normaliser : retirer markdown gras et espaces autour des deux-points
    cleaned = re.sub(r"\*\*", "", line).strip()
    cleaned = re.sub(r"\s*:\s*", ":", cleaned)
    upper = cleaned.upper()
    return upper == label or upper.startswith(label + ":") or upper.startswith(label + " :")


def _parse_actions_from_albert(text: str) -> list[str]:
    """Parse la liste d'actions retournée par /albert/analyser.

    v3000h17 — Réécrit pour tolérer le markdown gras/italique d'Albert :

        **ACTIONS :**
        1. **Action numéro un** : description...
        2. **Action numéro deux** : description...

    Stratégie :
    1. Repérer le marqueur ACTIONS (avec ou sans **).
    2. Lire les lignes suivantes en cherchant un numéro/puce de début.
    3. Pour chaque item, **nettoyer le markdown** dans le contenu final.
    4. S'arrêter au prochain marqueur de section connu.
    5. Fallback robuste si rien trouvé.
    """
    import re
    actions: list[str] = []
    in_actions = False
    other_sections = ("NOTIFIER", "RISQUE", "NIVEAU", "CONTEXTE", "CONCLUSION", "ANALYSE")

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Détecter le marqueur ACTIONS (tolérant)
        if _is_section_marker(line, "ACTIONS"):
            in_actions = True
            continue
        if in_actions:
            # Détecter une autre section qui marquerait la fin
            if any(_is_section_marker(line, lbl) for lbl in other_sections):
                break
            # Extraire item numéroté ou à puce. Regex tolérante :
            # - chiffre puis '.' ou ')'
            # - tiret/puce
            # - éventuellement **gras** autour
            m = re.match(r"^\s*(?:\*\*)?\s*(?:\d{1,2}[.)]\s+|[-•*]\s+)\s*(.+)$", line)
            if m:
                content = _strip_markdown(m.group(1).strip())
                if content and len(content) > 3:
                    actions.append(content[:250])
            # Si pas un item mais on est dans ACTIONS et l'item précédent existe,
            # c'est peut-être une continuation de l'item précédent (rare).
            # → on ignore pour éviter d'agréger des poubelles.

    # Fallback ultime : si rien parsé, prendre les 3 premières lignes substantielles
    if not actions and text:
        for raw_line in text.splitlines():
            line = _strip_markdown(raw_line.strip())
            # Skip headers et marqueurs vides
            if not line or line.endswith(":") or len(line) < 10:
                continue
            # Skip ce qui ressemble à un marqueur de section
            if any(_is_section_marker(raw_line, lbl) for lbl in (("ACTIONS",) + other_sections)):
                continue
            # Retirer numérotation éventuelle
            m = re.match(r"^\s*(?:\d{1,2}[.)]\s+|[-•*]\s+)?(.+)$", line)
            content = m.group(1) if m else line
            if len(content) >= 10:
                actions.append(content[:250])
            if len(actions) >= 3:
                break

    return actions[:3]


@router.post("/coach/suggest-tasks/{incident_id}")
async def coach_suggest_tasks(
    incident_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3.0.0 — Génère 3 actions concrètes pour un incident via Albert,
    sans créer les tâches en base (preview).

    L'utilisateur peut ensuite valider/éditer puis appeler /coach/create-tasks
    pour créer effectivement les tâches Kanban.
    """
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident introuvable")

    titre = (inc.fait or "")[:200]

    # Tenter Albert si configuré
    actions: list[str] = []
    source = "fallback"
    err = require_ia_configured()
    if not err:
        try:
            from app.api.albert import SYSTEM_CYBER, SYSTEM_SANITAIRE
            system = SYSTEM_CYBER if (inc.type_crise or "").upper() == "CYBER" else SYSTEM_SANITAIRE
            prompt = (
                f"FAIT DECLARE : {inc.fait}\n"
                f"ANALYSE D'IMPACT : {inc.analyse or 'Non renseignée'}\n\n"
                "En tant qu'expert gestion de crise hospitalière, propose 3 actions "
                "concrètes, courtes et opérationnelles à réaliser MAINTENANT face à "
                "cet incident.\n\n"
                "RÈGLES DE FORMAT — À RESPECTER ABSOLUMENT :\n"
                "- NE PAS utiliser de gras (pas de **astérisques**)\n"
                "- NE PAS utiliser de markdown\n"
                "- Texte BRUT uniquement\n"
                "- Une action par ligne, numérotée\n"
                "- Maximum 100 caractères par action\n\n"
                "FORMAT EXACT (recopie cette structure) :\n"
                "ACTIONS:\n"
                "1. Première action courte et actionnable\n"
                "2. Deuxième action\n"
                "3. Troisième action\n"
            )
            text, ai_source = await call_ai(system, prompt)
            actions = _parse_actions_from_albert(text)
            if actions:
                source = "albert"
        except Exception as e:
            logger.warning(f"coach/suggest-tasks : Albert indispo ({e}), fallback")

    # Fallback générique si Albert indisponible ou parsing échoué
    if not actions:
        type_crise = (inc.type_crise or "").upper()
        if type_crise == "CYBER":
            actions = [
                f"Isoler les systèmes concernés par : {titre[:60]}",
                "Alerter ANSSI / CERT-Santé et activer la cellule de crise cyber",
                "Préserver les preuves (logs, captures) pour analyse forensique",
            ]
        else:
            actions = [
                f"Évaluer l'impact patient lié à : {titre[:60]}",
                "Informer la direction et l'équipe soignante concernée",
                "Documenter la chronologie pour la main courante",
            ]
        source = "fallback"

    return {
        "incident_id":    incident_id,
        "incident_titre": titre,
        "actions":        actions,
        "source":         source,
    }


@router.post("/coach/create-tasks")
def coach_create_tasks(
    payload: CoachCreateTasksIn,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3.0.0 — Crée effectivement les tâches Kanban à partir des actions
    validées par l'utilisateur. Lie chaque tâche à l'incident concerné."""
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == payload.incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident introuvable")

    actions_clean = [a.strip() for a in (payload.actions or []) if a and a.strip()]
    if not actions_clean:
        raise HTTPException(400, "Aucune action fournie")

    priorite = max(1, min(4, payload.priorite or 3))
    created_ids: list[int] = []
    for action in actions_clean[:5]:  # garde-fou : max 5 tâches d'un coup
        t = Task(
            incident_id=payload.incident_id,
            titre=action[:200],
            description=f"Action proposée par l'Assistant SCRIBE\nIncident #{payload.incident_id} : {(inc.fait or '')[:120]}",
            priorite=priorite,
            colonne="BACKLOG",
        )
        db.add(t)
        db.flush()
        created_ids.append(t.id)
    db.commit()

    return {
        "ok":          True,
        "created":     len(created_ids),
        "task_ids":    created_ids,
        "incident_id": payload.incident_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# v3000h14 — Copilote stratégique : point de situation + question libre
# ─────────────────────────────────────────────────────────────────────────────

def _gather_situation_context(db: Session, max_age_hours: int = 24) -> dict:
    """Collecte tout le contexte nécessaire pour une synthèse stratégique.

    Retourne un dict avec compteurs et listes courtes (titres + statuts).
    Volontairement compact pour rester sous les limites de tokens de l'IA.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    # Incidents (non archivés)
    incidents = (
        db.query(SitrepEntry)
        .filter(SitrepEntry.archived == False)  # noqa: E712
        .order_by(SitrepEntry.timestamp.desc())
        .limit(50)
        .all()
    )
    incidents_actifs = [i for i in incidents if i.status != "RÉSOLU"]
    incidents_resolus = [i for i in incidents if i.status == "RÉSOLU"]

    # Tâches Kanban par colonne
    all_tasks = db.query(Task).all()
    tasks_par_colonne = {"BACKLOG": 0, "EN_COURS": 0, "EN_ATTENTE": 0, "TERMINÉ": 0}
    for t in all_tasks:
        col = (t.colonne or "BACKLOG").upper()
        if col in tasks_par_colonne:
            tasks_par_colonne[col] += 1

    # Décisions récentes
    decisions = (
        db.query(Decision)
        .order_by(Decision.timestamp.desc())
        .limit(20)
        .all()
    )

    # Transferts en cours
    transferts = (
        db.query(TransfertPatient)
        .filter(TransfertPatient.statut.in_(["DEMANDE", "ACCEPTE", "EN_COURS"]))
        .all()
    )

    # Déclarations de situation (la plus récente)
    derniere_decla = (
        db.query(DeclarationSituation)
        .order_by(DeclarationSituation.created_at.desc())
        .first()
    )

    # Durée depuis le premier incident
    duree_min = 0
    if incidents:
        oldest = min((i.timestamp for i in incidents if i.timestamp), default=None)
        if oldest:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            duree_min = int((datetime.now(timezone.utc) - oldest).total_seconds() / 60)

    return {
        "incidents_actifs":   incidents_actifs,
        "incidents_resolus":  incidents_resolus,
        "tasks_par_colonne":  tasks_par_colonne,
        "tasks_total":        len(all_tasks),
        "decisions":          decisions,
        "transferts":         transferts,
        "derniere_decla":     derniere_decla,
        "duree_min":          duree_min,
    }


def _build_situation_prompt(ctx: dict) -> str:
    """Construit le prompt utilisateur pour la synthèse IA."""
    incidents_lines = []
    for inc in ctx["incidents_actifs"][:15]:  # cap pour limiter tokens
        age_min = 0
        if inc.timestamp:
            ts = inc.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_min = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
        type_c = inc.type_crise or "?"
        urg = inc.urgency or 1
        status = inc.status or "?"
        fait = (inc.fait or "")[:100]
        incidents_lines.append(
            f"  - [#{inc.id}] {type_c} U{urg} {status} (il y a {age_min}min) : {fait}"
        )
    incidents_block = "\n".join(incidents_lines) if incidents_lines else "  (aucun)"

    dec_lines = []
    for d in ctx["decisions"][:10]:
        contenu = (d.contenu or "")[:80]
        dec_lines.append(f"  - {contenu}")
    dec_block = "\n".join(dec_lines) if dec_lines else "  (aucune)"

    tr_block = "\n".join(
        f"  - {t.etablissement_destination or '?'} ({t.statut})"
        for t in ctx["transferts"][:5]
    ) or "  (aucun)"

    decla = "non déclarée"
    if ctx["derniere_decla"]:
        d = ctx["derniere_decla"]
        decla = f"{d.niveau or '?'} — {(d.libelle or '')[:80]}"

    return (
        f"DURÉE DEPUIS DÉBUT : {ctx['duree_min']} min\n"
        f"\nINCIDENTS ACTIFS ({len(ctx['incidents_actifs'])}) :\n"
        f"{incidents_block}\n"
        f"\nINCIDENTS RÉSOLUS : {len(ctx['incidents_resolus'])}\n"
        f"\nDÉCISIONS PRISES ({len(ctx['decisions'])}) :\n"
        f"{dec_block}\n"
        f"\nTÂCHES KANBAN : "
        f"BACKLOG={ctx['tasks_par_colonne']['BACKLOG']}, "
        f"EN_COURS={ctx['tasks_par_colonne']['EN_COURS']}, "
        f"EN_ATTENTE={ctx['tasks_par_colonne']['EN_ATTENTE']}, "
        f"TERMINÉ={ctx['tasks_par_colonne']['TERMINÉ']}\n"
        f"\nTRANSFERTS EN COURS ({len(ctx['transferts'])}) :\n"
        f"{tr_block}\n"
        f"\nSITUATION DÉCLARÉE : {decla}\n"
        f"\nEn tant qu'expert gestion de crise hospitalière, fais une SYNTHÈSE "
        f"STRATÉGIQUE en français.\n"
        f"\nRÈGLES DE FORMAT — À RESPECTER ABSOLUMENT :\n"
        f"- TEXTE BRUT uniquement, AUCUN markdown (pas de **gras**, pas de *italique*, pas de `code`)\n"
        f"- Les marqueurs SITUATION:, COURT_TERME:, etc. doivent être en début de ligne sans astérisques\n"
        f"- Sous chaque marqueur, des phrases courtes ou des puces simples avec '- ' ou '1. '\n"
        f"\nFORMAT EXACT (recopie cette structure sans la modifier) :\n"
        f"\nSITUATION:\n[3-5 lignes : ce qui se passe maintenant, ce qui est sous contrôle, ce qui ne l'est pas]\n"
        f"\nCOURT_TERME:\n- [Risque ou action urgente dans les 30 prochaines minutes]\n- [...]\n"
        f"\nMOYEN_TERME:\n- [Risque à anticiper dans les 2h]\n- [...]\n"
        f"\nLONG_TERME:\n- [Implication stratégique 24h]\n"
        f"\nPRIORITES:\n1. [action prioritaire la plus urgente]\n"
        f"2. [seconde priorité]\n"
        f"3. [troisième priorité]\n"
    )


def _local_fallback_situation(ctx: dict) -> dict:
    """Synthèse heuristique si IA indisponible.

    Pas de projection prédictive sophistiquée, mais un état des lieux honnête
    + quelques règles métier basiques (ratio décisions/incidents, ancienneté).
    """
    nb_actifs = len(ctx["incidents_actifs"])
    nb_resolus = len(ctx["incidents_resolus"])
    nb_dec = len(ctx["decisions"])
    nb_transferts = len(ctx["transferts"])
    duree = ctx["duree_min"]

    # Situation
    situation_parts = []
    situation_parts.append(
        f"{nb_actifs} incident{'s' if nb_actifs > 1 else ''} actif{'s' if nb_actifs > 1 else ''} "
        f"({nb_resolus} résolu{'s' if nb_resolus > 1 else ''}) depuis {duree} min."
    )
    if nb_actifs > 0 and nb_dec == 0:
        situation_parts.append("Aucune décision formelle prise → traçabilité absente.")
    elif nb_dec < nb_actifs:
        situation_parts.append(
            f"Ratio décisions/incidents faible ({nb_dec}/{nb_actifs})."
        )
    if nb_transferts:
        situation_parts.append(f"{nb_transferts} transfert(s) en cours.")
    if not ctx["derniere_decla"]:
        situation_parts.append("Aucune déclaration de situation formelle.")
    situation = " ".join(situation_parts) if situation_parts else "Situation calme."

    # Court terme
    ct = []
    incidents_critiques = [i for i in ctx["incidents_actifs"] if (i.urgency or 1) >= 3]
    if incidents_critiques:
        ct.append(
            f"{len(incidents_critiques)} incident(s) critique(s) à traiter en priorité."
        )
    incidents_vieux = [
        i for i in ctx["incidents_actifs"]
        if i.timestamp and (
            datetime.now(timezone.utc) -
            (i.timestamp if i.timestamp.tzinfo else i.timestamp.replace(tzinfo=timezone.utc))
        ).total_seconds() / 60 > 15
    ]
    if incidents_vieux:
        ct.append(f"{len(incidents_vieux)} incident(s) ouvert(s) depuis plus de 15 min.")
    if ctx["tasks_par_colonne"]["BACKLOG"] > 5:
        ct.append(
            f"{ctx['tasks_par_colonne']['BACKLOG']} tâches en BACKLOG : à prioriser."
        )
    if not ct:
        ct.append("Aucun signal d'alerte court terme.")

    # Moyen terme
    mt = []
    types_actifs = {(i.type_crise or "?") for i in ctx["incidents_actifs"]}
    if "CYBER" in types_actifs:
        mt.append("Risque cyber : isolation systèmes, notifier ANSSI/CERT-Santé.")
    if "SANITAIRE" in types_actifs:
        mt.append("Risque sanitaire : anticiper capacités lits et personnel.")
    if nb_transferts == 0 and nb_actifs > 3:
        mt.append("Beaucoup d'incidents, aucun transfert : capacité interne à vérifier.")
    if not mt:
        mt.append("Pas de signal moyen terme particulier.")

    # Long terme
    lt = []
    if nb_actifs > 5:
        lt.append("Charge élevée : envisager renforts pour rotation 24h.")
    if not ctx["derniere_decla"] and nb_actifs >= 2:
        lt.append("Déclaration formelle à envisager (ARS) pour traçabilité.")
    if not lt:
        lt.append("Pas d'enjeu stratégique 24h identifié.")

    # Priorités
    pri = []
    if incidents_critiques:
        inc = incidents_critiques[0]
        pri.append(f"Traiter incident #{inc.id} ({(inc.fait or '')[:60]})")
    elif ctx["incidents_actifs"]:
        inc = ctx["incidents_actifs"][0]
        pri.append(f"Statuer sur incident #{inc.id} ({(inc.fait or '')[:60]})")
    if nb_dec == 0 and nb_actifs > 0:
        pri.append("Formaliser au moins une décision (Plan Blanc / cellule de crise)")
    if not ctx["derniere_decla"] and nb_actifs >= 2:
        pri.append("Émettre une déclaration de situation (niveau VEILLE ou ALERTE)")
    while len(pri) < 3:
        pri.append("(rien d'identifié)")
    pri = pri[:3]

    return {
        "situation":   situation,
        "court_terme": ct,
        "moyen_terme": mt,
        "long_terme":  lt,
        "priorites":   pri,
        "source":      "local",
    }


def _parse_ia_situation(text: str) -> dict:
    """Parse la réponse structurée de l'IA en sections.

    v3000h17 — Tolérant au markdown gras (**SITUATION:**) et variantes courantes.
    Si le parsing structuré échoue (sections vides), on retourne le texte brut
    dans 'situation' plutôt que "(non renseigné)" — pour qu'on voie au moins
    quelque chose à l'écran.
    """
    import re
    sections = {
        "SITUATION":   [],
        "COURT_TERME": [],
        "MOYEN_TERME": [],
        "LONG_TERME":  [],
        "PRIORITES":   [],
    }
    # Alias tolérants pour les variations courantes des marqueurs
    aliases = {
        "SITUATION":    ["SITUATION", "ÉTAT", "ETAT"],
        "COURT_TERME":  ["COURT_TERME", "COURT TERME", "30 MIN", "30MIN"],
        "MOYEN_TERME":  ["MOYEN_TERME", "MOYEN TERME", "2H", "2 H"],
        "LONG_TERME":   ["LONG_TERME", "LONG TERME", "24H", "24 H"],
        "PRIORITES":    ["PRIORITES", "PRIORITÉS", "PRIORITY", "ACTIONS PRIORITAIRES"],
    }

    def detect_section(line: str) -> str | None:
        # Retirer markdown + normaliser
        cleaned = re.sub(r"\*\*", "", line).strip()
        cleaned = re.sub(r"\s*:\s*", ":", cleaned)
        upper = cleaned.upper()
        for key, alts in aliases.items():
            for alt in alts:
                if upper == alt or upper.startswith(alt + ":"):
                    return key
        return None

    current = None
    other_marker_seen = False
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Détecter une section ?
        sect = detect_section(line)
        if sect is not None:
            current = sect
            other_marker_seen = True
            # Garder le reste de la ligne si quelque chose après ":"
            # ATTENTION : utiliser la ligne SANS markdown pour le split,
            # sinon on garde les ** parasites.
            cleaned_line = _strip_markdown(line)
            after = ""
            if ":" in cleaned_line:
                after = cleaned_line.split(":", 1)[1].strip()
            if after:
                sections[current].append(after)
            continue
        if current is None:
            continue
        # Nettoyer puces / numérotation / markdown
        cleaned_content = re.sub(r"^\s*(?:\d{1,2}[.)]\s+|[-•*]\s+)", "", line)
        cleaned_content = _strip_markdown(cleaned_content)
        # Filtrer les artefacts vides ou markdown solo (**, --, etc.)
        if cleaned_content and len(cleaned_content) > 1 and not re.match(r"^[*\-_]+$", cleaned_content):
            sections[current].append(cleaned_content[:300])

    # Si AUCUN marqueur n'a été trouvé : on a juste du texte brut → on le met en "situation"
    if not other_marker_seen and text:
        return {
            "situation":   _strip_markdown(text)[:1000],
            "court_terme": ["(non structuré par l'IA — voir Situation)"],
            "moyen_terme": ["(non structuré)"],
            "long_terme":  ["(non structuré)"],
            "priorites":   ["(non structuré)"],
            "source":      "ia",
        }

    return {
        "situation":   " ".join(sections["SITUATION"]) or "(synthèse incomplète — l'IA n'a pas fourni cette section)",
        "court_terme": sections["COURT_TERME"] or ["(non renseigné par l'IA)"],
        "moyen_terme": sections["MOYEN_TERME"] or ["(non renseigné par l'IA)"],
        "long_terme":  sections["LONG_TERME"]  or ["(non renseigné par l'IA)"],
        "priorites":   sections["PRIORITES"]   or ["(non renseigné par l'IA)"],
        "source":      "ia",
    }


@router.post("/coach/situation")
async def coach_situation(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3000h14 — Synthèse stratégique globale.

    Collecte tout le contexte de l'exercice/shift en cours et produit :
    - une synthèse de la situation
    - une projection court / moyen / long terme
    - 3 priorités d'action

    Utilise l'IA configurée (Albert ou autre) si disponible, sinon
    fallback heuristique local.
    """
    ctx = _gather_situation_context(db)

    # Tenter IA si configurée
    err = require_ia_configured()
    if not err:
        try:
            system = (
                "Tu es un copilote stratégique pour la gestion de crise hospitalière. "
                "Tu produis des synthèses concises, actionnables et structurées. "
                "Tu ne fais JAMAIS de remplissage et tu reconnais quand il y a peu d'éléments."
            )
            prompt = _build_situation_prompt(ctx)
            text, ai_source = await call_ai(system, prompt)
            parsed = _parse_ia_situation(text)
            parsed["ai_provider"] = ai_source
            parsed["duree_min"] = ctx["duree_min"]
            parsed["incidents_actifs"] = len(ctx["incidents_actifs"])
            parsed["decisions"] = len(ctx["decisions"])
            return parsed
        except Exception as e:
            logger.warning(f"coach/situation : IA indispo ({e}), fallback local")

    # Fallback
    fb = _local_fallback_situation(ctx)
    fb["duree_min"] = ctx["duree_min"]
    fb["incidents_actifs"] = len(ctx["incidents_actifs"])
    fb["decisions"] = len(ctx["decisions"])
    return fb


class CoachAskIn(BaseModel):
    question: str


@router.post("/coach/ask")
async def coach_ask(
    payload: CoachAskIn,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3000h14 — Question libre au copilote.

    L'utilisateur tape une question dans le panneau Assistant. On l'envoie
    à l'IA avec le contexte courant. Si IA indispo, on renvoie un message
    poli expliquant qu'il faut activer un fournisseur IA.
    """
    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(400, "Question vide")
    if len(q) > 500:
        q = q[:500]

    err = require_ia_configured()
    if err:
        return {
            "reponse": (
                "Le copilote IA n'est pas configuré sur cette instance. "
                "Configure un fournisseur (Albert, OpenAI…) dans les paramètres "
                "pour pouvoir poser des questions libres."
            ),
            "source": "config_missing",
        }

    ctx = _gather_situation_context(db)
    context_short = (
        f"Contexte exercice (durée {ctx['duree_min']}min) : "
        f"{len(ctx['incidents_actifs'])} incident(s) actif(s), "
        f"{len(ctx['decisions'])} décision(s), "
        f"{ctx['tasks_par_colonne']['EN_COURS']} tâche(s) en cours, "
        f"{len(ctx['transferts'])} transfert(s)."
    )
    if ctx["incidents_actifs"]:
        sample = ctx["incidents_actifs"][:5]
        context_short += "\nIncidents en cours :"
        for inc in sample:
            context_short += (
                f"\n- [#{inc.id}] {(inc.type_crise or '?')} : {(inc.fait or '')[:80]}"
            )

    try:
        system = (
            "Tu es un copilote stratégique pour la gestion de crise hospitalière. "
            "Tu réponds de manière concise (max 6 lignes), factuelle, actionnable. "
            "Si la question est hors crise ou hors champ, dis-le poliment."
        )
        prompt = f"{context_short}\n\nQUESTION DU DIRECTEUR DE CRISE :\n{q}"
        text, ai_source = await call_ai(system, prompt)
        return {
            "reponse":  text.strip(),
            "source":   "ia",
            "provider": ai_source,
        }
    except Exception as e:
        logger.warning(f"coach/ask : IA indispo ({e})")
        return {
            "reponse": f"Désolé, l'IA est indisponible ({type(e).__name__}). Réessaie dans un instant.",
            "source":  "error",
        }


# ─────────────────────────────────────────────────────────────────────────────
# v3.2.0 (S7) — Débriefing post-exercice
# ─────────────────────────────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse


def _resolve_active_session_id(
    db: Session, user: Optional[User], explicit: Optional[int],
) -> Optional[int]:
    """Trouve la session à débriefer : explicite > active courante > dernière fermée."""
    if explicit is not None:
        return explicit
    if user is None:
        return None
    # Session active de l'utilisateur
    s = (db.query(TuteurSession)
         .filter(TuteurSession.user_id == user.id)
         .order_by(TuteurSession.started_at.desc())
         .first())
    return s.id if s else None


@router.get("/debrief/{session_id}")
async def debrief_json(
    session_id: int,
    with_ia: bool = True,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Retourne le débriefing complet d'une session au format JSON.

    Inclut : chronologie, indicateurs, analyse (IA si dispo sinon locale).
    """
    from plugins.tuteur.debriefing import gather_debrief_data
    try:
        data = await gather_debrief_data(db, session_id, with_ia=with_ia)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"debrief_json : {e}")
        raise HTTPException(500, f"Erreur génération débrief : {e}")
    return data


@router.get("/debrief/{session_id}/docx")
async def debrief_docx(
    session_id: int,
    with_ia: bool = True,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Télécharge le brouillon REX au format DOCX."""
    from plugins.tuteur.debriefing import gather_debrief_data, generate_debrief_docx
    try:
        data = await gather_debrief_data(db, session_id, with_ia=with_ia)
        sigle = data.get("session_sigle") or ""
        buf = generate_debrief_docx(data, etablissement_sigle=sigle)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"debrief_docx : {e}")
        raise HTTPException(500, f"Erreur génération DOCX : {e}")

    filename = f"debrief_session_{session_id}.docx"
    return StreamingResponse(
        iter([buf]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/debrief")
async def debrief_current(
    with_ia: bool = True,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Raccourci : débrief de la session courante (ou dernière) de l'utilisateur."""
    sid = _resolve_active_session_id(db, user, None)
    if sid is None:
        raise HTTPException(404, "Aucune session à débriefer")
    return await debrief_json(sid, with_ia=with_ia, db=db, user=user)


# ─────────────────────────────────────────────────────────────────────────────
# v3000h18 — Aide réglementaire (KB) : obligation summary + modèle de message
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/kb/obligation/{obligation_id}")
def kb_obligation_summary(
    obligation_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3000h18 — Retourne le résumé d'une obligation réglementaire.

    Utilisé par le bouton "📞 Aide ARS / ANSSI / CNIL" du panneau Assistant.
    Affiche les coordonnées vérifiées, le délai légal, les risques.
    """
    from plugins.tuteur.knowledge_base import get_obligation_summary
    summary = get_obligation_summary(obligation_id)
    if not summary:
        raise HTTPException(404, f"Obligation '{obligation_id}' inconnue ou non vérifiée")
    return summary


class KbRenderIn(BaseModel):
    obligation_id: str
    incident_id: Optional[int] = None


@router.post("/kb/render-message")
def kb_render_message(
    payload: KbRenderIn,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """v3000h18 — Rend un modèle de message pré-rempli pour une obligation.

    Le bouton "📋 Copier modèle" du panneau Assistant appelle cette route.
    Le contexte (sigle, incident concerné, durée, etc.) est extrait de la
    DB pour pré-remplir les placeholders {sigle_etablissement} etc.
    """
    from plugins.tuteur.knowledge_base import render_message_template
    import os
    # Construire le contexte à partir de la DB et de l'environnement
    context = {
        "sigle_etablissement": os.getenv("SCRIBE_SIGLE", ""),
        "nom_etablissement":   os.getenv("SCRIBE_NOM_ETAB", ""),
        "finess_etablissement": os.getenv("SCRIBE_FINESS", ""),
    }
    if user:
        context["nom_dircrise"] = user.username
        context["role_declarant"] = (
            "Directeur de crise" if user.role in ("admin", "dircrise")
            else (user.role or "Référent")
        )

    if payload.incident_id:
        inc = db.query(SitrepEntry).filter(SitrepEntry.id == payload.incident_id).first()
        if inc:
            context["nature_incident"] = (inc.fait or "")[:200]
            context["type_crise"] = inc.type_crise or "?"
            context["heure_premier_incident"] = (
                inc.timestamp.strftime("%H:%M le %d/%m/%Y")
                if inc.timestamp else "?"
            )

    # Ajouter le nombre de critiques actifs et leurs UF
    from plugins.tuteur.coach_rules import _active_incidents
    actifs = _active_incidents(db)
    critiques = [i for i in actifs if (i.urgency or 1) >= 3]
    context["nb_critiques"] = str(len(critiques))
    ufs = sorted({(i.unite_fonctionnelle or "").strip() for i in critiques if i.unite_fonctionnelle})
    if ufs:
        context["services_impactes"] = ", ".join(ufs)
    # Décisions récentes
    decisions = (
        db.query(Decision)
        .order_by(Decision.timestamp.desc())
        .limit(5)
        .all()
    )
    if decisions:
        context["decisions_prises"] = " ; ".join(
            (d.contenu or "")[:100] for d in decisions
        )

    rendered = render_message_template(payload.obligation_id, context)
    if not rendered:
        raise HTTPException(404, f"Modèle pour '{payload.obligation_id}' indisponible")
    return rendered
