"""
plugins/messagerie/api.py — SCRIBE v2.0.6
Messagerie interne SCRIBE.
Importe le router depuis app/api/v140 (migration progressive).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.api.auth import get_current_user
from app.models import MessageInterne, User, Notification

router = APIRouter()


class MessageIn(BaseModel):
    destinataire_id: int
    sujet:    str
    contenu:  str
    reply_to: Optional[int] = None


@router.get("")
def get_messages(boite: str = "reception", db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if boite == "all":
        # Tous les messages impliquant cet utilisateur (pour afficher les threads)
        msgs = db.query(MessageInterne).filter(
            (MessageInterne.destinataire_id == user.id) |
            (MessageInterne.expediteur_id   == user.id)
        ).order_by(MessageInterne.created_at.asc()).limit(500).all()
    elif boite == "envoi":
        msgs = db.query(MessageInterne).filter(
            MessageInterne.expediteur_id == user.id
        ).order_by(MessageInterne.created_at.desc()).limit(100).all()
    else:  # reception
        msgs = db.query(MessageInterne).filter(
            MessageInterne.destinataire_id == user.id
        ).order_by(MessageInterne.created_at.desc()).limit(100).all()
    return [_fmt(m, user.id) for m in msgs]


@router.get("/non-lus")
def non_lus_count(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: return {"count": 0}
    c = db.query(MessageInterne).filter(
        MessageInterne.destinataire_id == user.id,
        MessageInterne.lu == False
    ).count()
    return {"count": c}


@router.post("")
def send_message(body: MessageIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    dest = db.query(User).filter(User.id == body.destinataire_id, User.active == True).first()
    if not dest: raise HTTPException(404, "Destinataire inconnu")
    msg = MessageInterne(
        expediteur_id   = user.id,
        expediteur_nom  = user.display_name or user.username,
        destinataire_id = body.destinataire_id,
        destinataire_nom= dest.display_name or dest.username,
        sujet           = body.sujet,
        contenu         = body.contenu,
        reply_to        = body.reply_to,
    )
    db.add(msg); db.commit(); db.refresh(msg)
    # Notification inbox
    db.add(Notification(
        user_id    = body.destinataire_id,
        titre      = f"Message de {msg.expediteur_nom}",
        message    = body.sujet,
        type_notif = "MESSAGE",
    ))
    db.commit()
    return _fmt(msg, user.id)


class MessageBroadcastIn(BaseModel):
    """Message entrant depuis un acteur externe (ARS, CERT, SAMU...).

    Utilisé principalement en mode exercice par le collecteur animateur
    pour injecter des stimuli de type 'message' qui atterrissent dans la
    vraie messagerie interne (pas dans un salon de chat).
    """
    expediteur_nom: str     # "ARS", "CERT Santé", "SAMU 74", etc.
    sujet:          str
    contenu:        str
    # Destinataires : cibler par role_exercice (liste) ou username (liste).
    # Si vide → broadcast à tous les directeurs + cadres + RSSI actifs.
    destinataire_usernames: Optional[list] = None
    destinataire_roles:     Optional[list] = None   # ["admin", "directeur"]


@router.post("/broadcast-externe")
def broadcast_externe(body: MessageBroadcastIn, db: Session = Depends(get_db),
                      user=Depends(get_current_user)):
    """Route réservée aux stimuli d'exercice et aux intégrations externes
    (webhook ARS, CERT Santé, etc.) pour injecter un message externe dans
    la messagerie interne de SCRIBE.

    v2.3.88 — Ajouté pour séparer proprement :
      - Incidents → onglet INCIDENTS + badge (pas de message)
      - Messages externes → vraie messagerie inbox + notification MESSAGE
    """
    if not user: raise HTTPException(401)
    # Le collecteur-animateur se logue avec 'dircrise' qui est admin.
    # On refuse ce canal aux users non-admin pour éviter les usurpations.
    # v2307-hotfix — Ajout "collaborateur" qui est le nouveau nom du rôle
    # "directeur" après migration (cf. main.py::_run_migrations ligne 305).
    # Le compte dircrise doit pouvoir broadcaster les stimuli d'exercice
    # même après migration ; sinon les messages ARS/CERT/SAMU n'arrivent
    # jamais dans l'inbox des joueurs (HTTP 403 silencieux côté collecteur).
    if user.role not in ("admin", "directeur", "collaborateur"):
        raise HTTPException(403, "Broadcast messagerie réservé aux administrateurs/directeurs")

    # Sélection des destinataires
    q = db.query(User).filter(User.active == True)
    if body.destinataire_usernames:
        q = q.filter(User.username.in_(body.destinataire_usernames))
    elif body.destinataire_roles:
        q = q.filter(User.role.in_(body.destinataire_roles))
    else:
        # Par défaut : admin + directeur + collaborateur (pas les soignants
        # ni observateurs qui seraient noyés par les stimuli animateur).
        q = q.filter(User.role.in_(["admin", "directeur", "collaborateur"]))
    destinataires = q.all()
    if not destinataires:
        return {"ok": True, "created": 0, "note": "Aucun destinataire trouvé"}

    prefix = f"[{body.expediteur_nom}]"
    sujet = f"{prefix} {body.sujet}"[:200]
    created = 0
    for d in destinataires:
        msg = MessageInterne(
            expediteur_id   = user.id,           # le compte qui relaie
            expediteur_nom  = body.expediteur_nom,   # nom externe affiché
            destinataire_id = d.id,
            destinataire_nom= d.display_name or d.username,
            sujet           = sujet,
            contenu         = body.contenu,
            reply_to        = None,
        )
        db.add(msg)
        db.add(Notification(
            user_id    = d.id,
            titre      = f"Message externe : {body.expediteur_nom}",
            message    = body.sujet[:200],
            type_notif = "MESSAGE",
        ))
        created += 1
    db.commit()
    # v2305 — Notifier via le plugin notifications multi-canal.
    # Les messages externes ARS/CERT/SAMU sont de niveau alerte (3) car
    # ils viennent d'acteurs officiels de gestion de crise. Fail-safe.
    try:
        from plugins.notifications.dispatcher import notify_sync
        user_ids = [d.id for d in destinataires]
        notify_sync(
            event_type="external_message",
            title=f"✉️ Message externe : {body.expediteur_nom}",
            body=body.sujet[:150] + ("\n\n" + body.contenu[:300] if body.contenu else ""),
            urgency=3,
            context={
                "url": "/#messagerie",
                "expediteur": body.expediteur_nom,
            },
            target_users=user_ids,
        )
    except Exception:
        pass
    return {"ok": True, "created": created,
            "destinataires": [d.username for d in destinataires]}


@router.put("/{msg_id}/lire")
def marquer_lu(msg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    m = db.query(MessageInterne).filter(
        MessageInterne.id == msg_id,
        MessageInterne.destinataire_id == user.id
    ).first()
    if m: m.lu = True; db.commit()
    return {"ok": True}


def _fmt(m, uid):
    return {
        "id": m.id, "sujet": m.sujet, "contenu": m.contenu,
        "expediteur_id": m.expediteur_id, "expediteur_nom": getattr(m, "expediteur_nom", ""),
        "destinataire_id": m.destinataire_id, "destinataire_nom": getattr(m, "destinataire_nom", ""),
        "lu": m.lu,
        "reply_to": getattr(m, "reply_to", None),
        "ght_source": getattr(m, "ght_source", None),
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "is_mine": m.expediteur_id == uid,
    }
