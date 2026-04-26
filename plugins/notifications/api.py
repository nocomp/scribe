"""
plugins/notifications/api.py — Routes REST du plugin Notifications.

Endpoints :
  GET  /api/v1/notifications/config             : État global + canaux activés
  POST /api/v1/notifications/channel/{kind}     : Configurer/activer un canal
  POST /api/v1/notifications/subscribe          : S'abonner à un canal
  DELETE /api/v1/notifications/subscribe/{id}   : Se désabonner
  GET  /api/v1/notifications/subscriptions/me   : Mes souscriptions
  POST /api/v1/notifications/silence            : Activer sourdine
  DELETE /api/v1/notifications/silence          : Lever sourdine
  GET  /api/v1/notifications/silence            : État sourdine
  POST /api/v1/notifications/test/{kind}        : Envoi test sur un canal
  GET  /api/v1/notifications/log                : Historique (admin only)
  GET  /api/v1/notifications/vapid-public-key   : Clé publique VAPID pour navigateur
"""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, require_admin
from plugins.notifications.models import (
    NotifChannel, NotifSubscription, NotifSilence, NotifLog, NotifSettings
)
from plugins.notifications.backends import BACKENDS, NotifPayload
from plugins.notifications.dispatcher import notify

router = APIRouter()


@router.get("/ui", response_class=None)
def notifications_ui():
    """Sert la page d'admin/config du plugin notifications."""
    from fastapi.responses import FileResponse
    import pathlib
    p = pathlib.Path(__file__).parent / "notifications.html"
    if not p.exists():
        raise HTTPException(404, "UI non trouvée")
    return FileResponse(str(p), media_type="text/html")


# ── Config générale ──────────────────────────────────────────────────────────

@router.get("/config")
def get_config(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """État global des canaux (sans secrets)."""
    channels = db.query(NotifChannel).all()
    return {
        "channels": [{
            "id": c.id, "kind": c.kind, "label": c.label,
            "enabled": c.enabled,
            "configured": bool(c.config_json and c.config_json != "{}"),
        } for c in channels],
        "available_kinds": list(BACKENDS.keys()),
    }


class ChannelConfigIn(BaseModel):
    label:    str = ""
    enabled:  bool = False
    config:   dict = {}


@router.post("/channel/{kind}")
def save_channel(kind: str, body: ChannelConfigIn,
                 db: Session = Depends(get_db),
                 admin=Depends(require_admin)):
    """Configure/active un canal (admin only).

    Vérifie que le backend est bien connu, instancie-le avec la config
    pour valider is_configured() avant d'activer.
    """
    if kind not in BACKENDS:
        raise HTTPException(400, f"Canal inconnu. Valides: {list(BACKENDS.keys())}")

    # Validation config via is_configured()
    backend_cls = BACKENDS[kind]
    try:
        test_inst = backend_cls(body.config)
        is_ok = test_inst.is_configured()
    except Exception as e:
        raise HTTPException(400, f"Config invalide: {e}")

    if body.enabled and not is_ok:
        raise HTTPException(400, f"Config incomplète pour activer le canal {kind}")

    c = db.query(NotifChannel).filter(NotifChannel.kind == kind).first()
    if not c:
        c = NotifChannel(kind=kind)
        db.add(c)
    c.label = body.label or kind
    c.enabled = body.enabled
    c.config_json = json.dumps(body.config, ensure_ascii=False)
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": c.id, "configured": is_ok}


# ── Souscriptions utilisateur ────────────────────────────────────────────────

class SubscribeIn(BaseModel):
    channel_kind: str           # "mail" | "webpush" | "sms"
    target:       str           # mail / numéro / JSON subscription push
    label:        str = ""
    min_urgency:  int = 2


@router.post("/subscribe")
def subscribe(body: SubscribeIn, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    if body.channel_kind not in BACKENDS:
        raise HTTPException(400, "Canal inconnu")
    if body.min_urgency not in (1, 2, 3, 4):
        raise HTTPException(400, "min_urgency doit être 1-4")

    # Pour webpush : parse le JSON et dédup sur endpoint
    if body.channel_kind == "webpush":
        try:
            sub_data = json.loads(body.target)
            endpoint = sub_data.get("endpoint", "")
            if not endpoint:
                raise ValueError("endpoint manquant")
            existing = (db.query(NotifSubscription)
                          .filter(NotifSubscription.user_id == user.id,
                                  NotifSubscription.channel_kind == "webpush",
                                  NotifSubscription.target.like(f"%{endpoint[-50:]}%"))
                          .first())
            if existing:
                existing.active = True
                existing.target = body.target
                existing.min_urgency = body.min_urgency
                db.commit()
                return {"ok": True, "id": existing.id, "updated": True}
        except Exception as e:
            raise HTTPException(400, f"JSON webpush invalide: {e}")

    s = NotifSubscription(
        user_id=user.id,
        channel_kind=body.channel_kind,
        target=body.target,
        label=body.label or body.channel_kind,
        min_urgency=body.min_urgency,
    )
    db.add(s)
    db.commit()
    return {"ok": True, "id": s.id}


@router.delete("/subscribe/{sub_id}")
def unsubscribe(sub_id: int, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    s = db.query(NotifSubscription).filter(
        NotifSubscription.id == sub_id,
        NotifSubscription.user_id == user.id,
    ).first()
    if not s:
        raise HTTPException(404, "Souscription non trouvée")
    s.active = False
    db.commit()
    return {"ok": True}


@router.get("/subscriptions/me")
def my_subscriptions(db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    subs = db.query(NotifSubscription).filter(
        NotifSubscription.user_id == user.id,
        NotifSubscription.active == True,
    ).all()
    return [{
        "id": s.id, "channel_kind": s.channel_kind, "label": s.label,
        "target_preview": s.target[:40] + ("..." if len(s.target) > 40 else ""),
        "min_urgency": s.min_urgency,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
    } for s in subs]


# ── Mode sourdine ────────────────────────────────────────────────────────────

class SilenceIn(BaseModel):
    duration_min: Optional[int] = None   # None = jusqu'à levée manuelle
    reason:       str = ""


@router.post("/silence")
def silence(body: SilenceIn, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    # Lever une sourdine précédente si existe
    prev = db.query(NotifSilence).filter(
        NotifSilence.user_id == user.id,
        NotifSilence.active == True,
        NotifSilence.lifted_at.is_(None),
    ).all()
    for p in prev:
        p.active = False
        p.lifted_at = datetime.now(timezone.utc)

    until = None
    if body.duration_min:
        until = datetime.now(timezone.utc) + timedelta(minutes=body.duration_min)

    s = NotifSilence(user_id=user.id, active=True, until=until, reason=body.reason)
    db.add(s)
    db.commit()
    return {"ok": True, "id": s.id, "until": until.isoformat() if until else None}


@router.delete("/silence")
def lift_silence(db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    active = db.query(NotifSilence).filter(
        NotifSilence.user_id == user.id,
        NotifSilence.active == True,
    ).all()
    now = datetime.now(timezone.utc)
    for a in active:
        a.active = False
        a.lifted_at = now
    db.commit()
    return {"ok": True, "lifted": len(active)}


@router.get("/silence")
def get_silence(db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    s = db.query(NotifSilence).filter(
        NotifSilence.user_id == user.id,
        NotifSilence.active == True,
    ).order_by(NotifSilence.id.desc()).first()
    if not s:
        return {"active": False}
    now = datetime.now(timezone.utc)
    if s.until and s.until < now:
        s.active = False
        s.lifted_at = now
        db.commit()
        return {"active": False}
    return {
        "active": True,
        "until": s.until.isoformat() if s.until else None,
        "reason": s.reason,
        "started_at": s.created_at.isoformat() if s.created_at else None,
    }


# ── Test d'envoi ─────────────────────────────────────────────────────────────

@router.post("/test/{kind}")
async def test_channel(kind: str, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    """Envoie une notif test sur le canal `kind` à l'utilisateur courant.

    Utilise la 1re souscription active de l'user sur ce canal.
    """
    sub = db.query(NotifSubscription).filter(
        NotifSubscription.user_id == user.id,
        NotifSubscription.channel_kind == kind,
        NotifSubscription.active == True,
    ).first()
    if not sub:
        raise HTTPException(404, f"Pas de souscription active {kind} pour vous")
    channel = db.query(NotifChannel).filter(NotifChannel.kind == kind).first()
    if not channel or not channel.enabled:
        raise HTTPException(400, f"Canal {kind} non activé côté serveur")

    # On passe par le dispatcher (même chemin que la vraie notif) pour
    # tester aussi les règles (rate, dedup, silence).
    await notify(
        event_type="test",
        title="Test SCRIBE — Notification de diagnostic",
        body=f"Si vous recevez ce message sur votre canal {kind}, la configuration est opérationnelle. Heure du test : " + datetime.now(timezone.utc).isoformat(),
        urgency=2,
        context={},
        target_users=[user.id],
    )
    return {"ok": True, "target_preview": sub.target[:40]}


# ── Audit trail ──────────────────────────────────────────────────────────────

@router.get("/log")
def get_log(limit: int = Query(100, le=500),
            event_type: Optional[str] = None,
            user_id: Optional[int] = None,
            status: Optional[str] = None,
            db: Session = Depends(get_db),
            admin=Depends(require_admin)):
    """Historique des notifications émises (admin only).

    Utilisé pour répondre à "le Dr X a-t-il été prévenu ?" après incident.
    """
    q = db.query(NotifLog).order_by(NotifLog.ts.desc())
    if event_type: q = q.filter(NotifLog.event_type == event_type)
    if user_id:    q = q.filter(NotifLog.user_id == user_id)
    if status:     q = q.filter(NotifLog.status == status)
    rows = q.limit(limit).all()
    return [{
        "id": r.id,
        "ts": r.ts.isoformat() if r.ts else None,
        "event_type": r.event_type,
        "event_ref_id": r.event_ref_id,
        "urgency": r.urgency,
        "user_id": r.user_id,
        "channel_kind": r.channel_kind,
        "target": r.target,
        "title": r.title,
        "status": r.status,
        "error": r.error,
        "silenced": r.silenced,
    } for r in rows]


# ── VAPID public key (pour le navigateur) ────────────────────────────────────

@router.get("/vapid-public-key")
def get_vapid_public(db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    """Retourne la clé publique VAPID pour que le navigateur s'abonne.

    Cette route est appelée par le JS avant de créer une PushSubscription.
    """
    c = db.query(NotifChannel).filter(NotifChannel.kind == "webpush").first()
    if not c or not c.enabled:
        raise HTTPException(404, "Web Push non configuré")
    try:
        cfg = json.loads(c.config_json or "{}")
        pub = cfg.get("vapid_public_key")
        if not pub:
            raise HTTPException(500, "vapid_public_key absente de la config")
        return {"public_key": pub}
    except json.JSONDecodeError:
        raise HTTPException(500, "Config webpush corrompue")


@router.post("/generate-vapid")
def generate_vapid_keys(admin=Depends(require_admin)):
    """Génère une nouvelle paire de clés VAPID (admin only).

    v2.3.90 — Remplace la procédure manuelle qui exigeait de lancer un
    script Python depuis le shell. Ici l'admin clique un bouton dans l'UI
    et obtient les deux clés directement dans le formulaire.

    IMPORTANT : les clés ne sont PAS stockées automatiquement. L'admin
    doit ensuite coller les clés retournées dans le formulaire et cliquer
    "Enregistrer" pour les persister dans notif_channel.
    """
    try:
        from py_vapid import Vapid
        from cryptography.hazmat.primitives import serialization
        import base64
    except ImportError:
        raise HTTPException(500,
            "Dépendances manquantes : pip install pywebpush py_vapid cryptography")

    try:
        v = Vapid()
        v.generate_keys()

        # Clé publique : X962 uncompressed point, base64url sans padding
        pub_bytes = v.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip("=")

        # Clé privée : PEM PKCS8 sans chiffrement
        priv_pem = v.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        return {
            "public_key": pub_b64,
            "private_key": priv_pem,
            "note": "Collez ces clés dans le formulaire puis cliquez Enregistrer. "
                    "La clé privée doit rester secrète.",
        }
    except Exception as e:
        raise HTTPException(500, f"Génération VAPID échouée : {e}")
