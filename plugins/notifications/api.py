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
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user, require_admin
from app.models import User
from plugins.notifications.models import (
    NotifChannel, NotifSubscription, NotifSilence, NotifLog, NotifSettings
)
from plugins.notifications.backends import BACKENDS, NotifPayload
from plugins.notifications.dispatcher import notify


def _utc_iso(dt):
    """h75 — Sérialise un datetime en ISO 8601 avec fuseau UTC explicite.
    Les datetimes relus depuis SQLite sont naïfs (sans tzinfo) mais représentent
    de l'UTC. Sans marqueur de fuseau, le front les interprète en heure LOCALE,
    d'où un décalage (ex. journal SMS 2 h en retard en été). On force donc UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        from datetime import timezone as _tz
        dt = dt.replace(tzinfo=_tz.utc)
    return dt.isoformat()

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
        "created_at": _utc_iso(s.created_at),
        "last_used_at": _utc_iso(s.last_used_at),
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
    return {"ok": True, "id": s.id, "until": _utc_iso(until)}


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
        "until": _utc_iso(s.until),
        "reason": s.reason,
        "started_at": _utc_iso(s.created_at),
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

    # h78 — Test SPÉCIFIQUE au canal : envoi DIRECT via le backend du canal testé,
    # sans passer par notify() (qui diffusait à TOUS les canaux abonnés — un test
    # SMS arrivait aussi par mail). On teste exactement le canal demandé.
    from plugins.notifications.dispatcher import _apply_central_config, _log_notif
    cfg = _apply_central_config(kind, json.loads(channel.config_json or "{}"))
    backend_cls = BACKENDS.get(kind)
    if not backend_cls:
        raise HTTPException(400, f"Backend {kind} indisponible")
    backend = backend_cls(cfg)
    if not backend.is_configured():
        raise HTTPException(400, f"Canal {kind} mal configuré")
    payload = NotifPayload(
        event_type="test",
        title="Test SCRIBE — Notification de diagnostic",
        body=("Si vous recevez ce message sur votre canal " + kind +
              ", la configuration est opérationnelle. Heure du test : " +
              datetime.now(timezone.utc).isoformat()),
        urgency=4, context={},
    )
    try:
        res = await backend.send(payload, sub.target)
        ok, err = res.success, res.error
    except Exception as e:
        ok, err = False, str(e)
    _log_notif(db, "test", None, 4, user.id, kind, (sub.target or "")[:200],
               payload.title, payload.body,
               status=("sent" if ok else "failed"), error=err)
    try:
        db.commit()
    except Exception:
        db.rollback()
    if not ok:
        raise HTTPException(502, f"Échec envoi {kind} : {err}")
    return {"ok": True, "target_preview": (sub.target or "")[:40]}


class RappelIn(BaseModel):
    titre:   Optional[str] = None
    message: Optional[str] = None
    roles:   Optional[list] = None   # ex. ["admin"] pour restreindre la cible


@router.post("/rappel-personnel")
async def rappel_personnel(body: RappelIn, db: Session = Depends(get_db),
                           admin=Depends(require_admin)):
    """Rappel du personnel : notifie (SMS/mail selon souscriptions) TOUS les
    comptes actifs disposant d'un téléphone. `roles` optionnel pour restreindre
    (ex. ["admin"]). Réservé aux administrateurs."""
    q = db.query(User).filter(
        User.active == True,                 # noqa: E712
        User.telephone.isnot(None),
        User.telephone != "",
    )
    if body.roles:
        q = q.filter(User.role.in_(body.roles))
    ids = [u.id for u in q.all()]
    if not ids:
        return {"ok": True, "destinataires": 0,
                "message": "Aucun compte actif avec téléphone renseigné"}
    await notify(
        event_type="rappel_personnel",
        title=(body.titre or "Rappel du personnel — SCRIBE").strip()[:120],
        body=(body.message or "Activation de la cellule de crise. Merci de vous "
              "connecter à SCRIBE et de rejoindre votre poste.").strip()[:480],
        urgency=4,
        context={"motif": "rappel_personnel"},
        target_users=ids,
    )
    return {"ok": True, "destinataires": len(ids)}


# ── Notification SMS sélective sur incident ──────────────────────────────────

@router.get("/sms-recipients")
def sms_recipients(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """h73 — Liste des comptes actifs disposant d'un téléphone configuré.
    Sert au sélecteur de destinataires SMS d'un incident : on ne propose QUE
    les utilisateurs joignables par SMS. Le numéro est masqué (vie privée)."""
    rows = (db.query(User)
              .filter(User.active == True,                     # noqa: E712
                      User.telephone.isnot(None),
                      User.telephone != "")
              .order_by(User.display_name).all())

    def _mask(t: str) -> str:
        t = (t or "").strip()
        return (t[:3] + "…" + t[-2:]) if len(t) > 5 else "•••"

    return [{"id": u.id,
             "display_name": u.display_name or u.username,
             "role": u.role,
             "telephone_masque": _mask(u.telephone)} for u in rows]


class IncidentSmsIn(BaseModel):
    incident_id: Optional[int] = None
    titre:       Optional[str] = None
    message:     Optional[str] = None
    user_ids:    list[int]


@router.post("/incident-sms")
async def incident_sms(body: IncidentSmsIn, request: Request,
                       db: Session = Depends(get_db),
                       admin=Depends(require_admin)):
    """h73 — Envoie un SMS d'incident aux utilisateurs SÉLECTIONNÉS, uniquement
    ceux ayant un téléphone configuré. Envoi DIRECT vers User.telephone (urgency
    4 pour passer le filtre SMS), en réutilisant la config du canal SMS activé.
    Chaque envoi est tracé dans le journal des notifications. Réservé admin."""
    if not body.user_ids:
        raise HTTPException(400, "Aucun destinataire sélectionné")

    ch = (db.query(NotifChannel)
            .filter(NotifChannel.kind == "sms", NotifChannel.enabled == True)  # noqa: E712
            .first())
    if not ch:
        raise HTTPException(400, "Canal SMS non activé côté serveur")

    from plugins.notifications.dispatcher import _apply_central_config, _log_notif
    cfg = _apply_central_config("sms", json.loads(ch.config_json or "{}"))
    backend_cls = BACKENDS.get("sms")
    if not backend_cls:
        raise HTTPException(400, "Backend SMS indisponible")
    backend = backend_cls(cfg)
    if not backend.is_configured():
        raise HTTPException(400, "Canal SMS mal configuré")

    targets = (db.query(User)
                 .filter(User.id.in_(body.user_ids),
                         User.active == True,                   # noqa: E712
                         User.telephone.isnot(None),
                         User.telephone != "")
                 .all())
    if not targets:
        raise HTTPException(400, "Aucun destinataire avec téléphone parmi la sélection")

    titre   = (body.titre or "Incident SCRIBE").strip()[:120]
    message = (body.message or "").strip()[:480]
    # h74 — Lien absolu vers l'incident (titre déjà dans `titre`). On ne le
    # construit que si un incident_id est fourni (incident enregistré).
    ctx = {}
    if body.incident_id:
        ctx = {"incident_id": body.incident_id,
               "url": f"/#incidents/{body.incident_id}",
               "base_url": str(request.base_url).rstrip("/")}
    payload = NotifPayload(
        event_type="incident_sms", title=titre, body=message, urgency=4, context=ctx,
    )

    resultats = []
    for u in targets:
        try:
            res = await backend.send(payload, u.telephone)
            ok, err = res.success, res.error
        except Exception as e:
            ok, err = False, str(e)
        _log_notif(db, "incident_sms", body.incident_id, 4, u.id, "sms",
                   (u.telephone or "")[:200], titre, message,
                   status=("sent" if ok else "failed"), error=err)
        resultats.append({"user_id": u.id,
                          "display_name": u.display_name or u.username,
                          "ok": ok, "error": err})
    try:
        db.commit()
    except Exception:
        db.rollback()

    n_ok = sum(1 for r in resultats if r["ok"])
    return {"ok": True, "envoyes": n_ok, "total": len(resultats), "resultats": resultats}


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
        "ts": _utc_iso(r.ts),
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


@router.get("/sent-incidents")
def sent_incidents(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """h76 — IDs des incidents ayant au moins une notification émise avec succès
    (statut 'sent'). Alimente l'indicateur visuel 🔔 « notifié » des cartes."""
    rows = (db.query(NotifLog.event_ref_id)
              .filter(NotifLog.event_ref_id.isnot(None), NotifLog.status == "sent")
              .distinct().all())
    return {"incident_ids": sorted({r[0] for r in rows if r[0] is not None})}


# ── Synchronisation config centrale → canaux opérationnels ──────────────────
def materialize_central_channels(db: Session = None) -> dict:
    """Crée/active les canaux mail + sms à partir de la config centrale diffusée
    (domaines 'smtp'/'sms' avec enabled=True ET config complète). Idempotent.

    Précédence locale respectée : si un canal a déjà une config LOCALE, on n'écrase
    pas. On ne matérialise que les canaux vides — ce qui résout le cas « instance
    qui tire la config mais n'a aucun canal » → « pas de canal configuré ».
    Renvoie l'état par canal pour le tableau de synchronisation.
    """
    own = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal(); own = True
    report = {}
    try:
        from app.central_config import get_domain
        for kind, domain in (("mail", "smtp"), ("sms", "sms")):
            try:
                cc = get_domain(domain) or {}
            except Exception:
                cc = {}
            diffused = bool(cc.get("enabled"))
            cfg = {k: v for k, v in cc.items() if k != "enabled" and v not in (None, "")}
            c = db.query(NotifChannel).filter(NotifChannel.kind == kind).first()
            has_local = bool(c and c.config_json and c.config_json not in ("", "{}"))
            if not diffused or kind not in BACKENDS:
                report[kind] = {"configured": has_local, "enabled": bool(c and c.enabled), "diffused": diffused}
                continue
            try:
                is_ok = BACKENDS[kind](cfg).is_configured()
            except Exception:
                is_ok = False
            if is_ok and not has_local:
                if not c:
                    c = NotifChannel(kind=kind); db.add(c)
                c.label = getattr(c, "label", None) or kind
                c.config_json = json.dumps(cfg, ensure_ascii=False)
                c.enabled = True
                c.updated_at = datetime.now(timezone.utc)
                db.commit()
                has_local = True
            report[kind] = {"configured": has_local, "enabled": bool(c and c.enabled), "diffused": True}
    finally:
        if own:
            db.close()
    return report


def _sync_auth(request: Request) -> str:
    """Auth des endpoints de synchronisation : accepte le token ADMIN de
    l'instance OU son propre token de FÉDÉRATION (celui que la supervision
    connaît et utilise pour pousser). Évite de partager un token admin entre
    collecteur et instances."""
    auth = request.headers.get("Authorization", "") or ""
    tok = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    if not tok:
        raise HTTPException(401, "Token requis")
    # 1) Token de fédération de CETTE instance (chemin supervision → instance)
    try:
        from app.central_config import _read_federation
        _, fedtok = _read_federation()
        if fedtok and tok == fedtok:
            return "federation"
    except Exception:
        pass
    # 2) Token admin (chemin admin local)
    try:
        from app.api.auth import decode_token
        payload = decode_token(tok) or {}
        if payload.get("role") in ("admin", "superadmin") or payload.get("is_admin"):
            return "admin"
    except Exception:
        pass
    raise HTTPException(401, "Non autorisé")


def _bf_sync_status() -> dict:
    """État opérationnel BlueFiles de l'instance (binaire CLI + identifiants,
    config locale OU centrale diffusée)."""
    try:
        from plugins.bluefiles.cli_sender import cli_available
        return {"configured": bool(cli_available())}
    except Exception:
        return {"configured": False}


@router.get("/sync-status")
def notif_sync_status(request: Request, db: Session = Depends(get_db)):
    """État opérationnel des canaux mail/SMS de CETTE instance, après tentative
    de matérialisation depuis la config centrale déjà tirée. Consommé par le
    tableau de synchronisation de la supervision."""
    _sync_auth(request)
    rep = materialize_central_channels(db)
    return {"ok": True, "channels": rep, "bluefiles": _bf_sync_status()}


@router.post("/sync-apply")
def notif_sync_apply(request: Request, db: Session = Depends(get_db)):
    """Force un pull de la config centrale PUIS matérialise les canaux. Renvoie
    l'état opérationnel par canal. Déclenché par le bouton « Synchroniser » de la
    supervision (push actif)."""
    _sync_auth(request)
    try:
        from app.central_config import pull_now
        pulled = pull_now(timeout=8.0)
    except Exception:
        pulled = False
    rep = materialize_central_channels(db)
    return {"ok": True, "pulled": pulled, "channels": rep, "bluefiles": _bf_sync_status()}
