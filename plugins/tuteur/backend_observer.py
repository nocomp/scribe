"""
plugins/tuteur/backend_observer.py — v3.0.0

Permet aux routes API backend (ex: sitrep/post, transferts, etc.) d'enregistrer
des observations tuteur SANS dépendre du navigateur joueur.

Contexte : l'intercepteur tuteur frontend (apiFetch dans scribe.js) ne capture
les actions QUE quand un navigateur joueur est ouvert ET fait la requête.
Pour les stimuli injectés par le collecteur exercice (port 8565), aucun
navigateur n'est dans la boucle → l'incident est créé côté backend mais
aucune observation tuteur n'est enregistrée → l'Assistant ne voit rien.

Ce module comble le trou : appelé en fin de création d'incident/decision/etc.,
il crée une observation tuteur attachée à la session active du compte courant
(typiquement le compte dircrise en mode exercice).

Conçu pour être FAIL-SAFE : aucune exception ne doit casser la requête
métier (la création d'incident etc.). Toutes les erreurs sont avalées et
loggées en debug.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def observe_backend(
    db: Session,
    type_observation: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> None:
    """Enregistre une observation tuteur côté serveur.

    - Cherche la session active du user_id fourni (ou de l'admin par défaut)
    - Crée une observation rattachée à cette session
    - Crée la session à la volée si en mode exercice et aucune n'existe

    Aucune exception remontée : tout est avalé pour ne pas casser la requête
    métier appelante.
    """
    try:
        from plugins.tuteur.models import TuteurObservation, TuteurSession
    except Exception as e:
        logger.debug(f"backend_observer : modèles tuteur indisponibles ({e})")
        return

    try:
        # Résoudre user_id : si non fourni, prendre l'admin (cas typique exercice)
        if user_id is None:
            try:
                from app.models import User
                admin = db.query(User).filter(User.role == "admin",
                                              User.active == True).first()
                if admin:
                    user_id = admin.id
            except Exception:
                pass

        if user_id is None:
            logger.debug("backend_observer : aucun user résolu, observation ignorée")
            return

        # Chercher la session active
        s = (db.query(TuteurSession)
             .filter(TuteurSession.user_id == user_id,
                     TuteurSession.ended_at.is_(None))
             .order_by(TuteurSession.started_at.desc())
             .first())

        # Créer une session si absente, en mode exercice uniquement
        if s is None:
            is_exo = os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1"
            if not is_exo:
                logger.debug("backend_observer : pas de session et pas en exo, ignore")
                return
            inst_sigle = os.getenv("SCRIBE_SIGLE", "INSTANCE")
            try:
                from app.models import User
                user = db.query(User).filter(User.id == user_id).first()
                username = user.username if user else "?"
            except Exception:
                username = "?"
            s = TuteurSession(
                user_id=user_id,
                username=username,
                instance_sigle=inst_sigle,
                mode="exercice",
            )
            db.add(s)
            db.commit()
            db.refresh(s)
            logger.info(f"backend_observer : session exercice créée auto "
                        f"(id={s.id}, user_id={user_id}, sigle={inst_sigle})")

        # Créer l'observation
        obs = TuteurObservation(
            session_id=s.id,
            type_observation=type_observation,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
        )
        db.add(obs)
        db.commit()
        logger.debug(f"backend_observer : {type_observation} sur "
                     f"{target_type}#{target_id} (session {s.id})")

    except Exception as e:
        # Fail-safe : log debug, ne lève rien
        logger.debug(f"backend_observer a échoué (ignoré) : {e}")
        try:
            db.rollback()
        except Exception:
            pass
