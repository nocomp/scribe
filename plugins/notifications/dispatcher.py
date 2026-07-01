"""
plugins/notifications/dispatcher.py — Orchestration des envois multi-canaux.

Point d'entrée unique depuis le reste de SCRIBE :

    from plugins.notifications.dispatcher import notify
    await notify(
        event_type="incident_created",
        title="Panne électrique bloc A",
        body="Groupes de secours ne démarrent pas",
        urgency=4,
        context={"incident_id": 42, "uf": "BLOC"},
    )

Responsabilités du dispatcher :
1. Lit les canaux activés (notif_channel.enabled=True)
2. Pour chaque user abonné, applique les filtres :
   - mode sourdine actif ? → silent SAUF urgency=4 (contrat de sécurité)
   - min_urgency user respecté ?
   - rate limit non dépassé ? (max 10 notifs/user/minute)
   - dedup : même event_type+ref_id déjà envoyé dans la dernière heure ?
3. Fan-out asyncio.gather vers les backends
4. Log exhaustif dans notif_log (audit "qui a reçu quoi")

Règles de sécurité :
- Une erreur d'envoi n'empêche JAMAIS de logger (on sait qui n'a pas reçu).
- Une erreur sur 1 canal n'empêche pas les autres canaux.
- `notify()` ne lève jamais : si toute l'infrastructure est down, on log
  et on rend la main à l'appelant. Un incident critique doit pouvoir être
  créé dans SCRIBE même si le SMTP est éteint.
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from plugins.notifications.backends import BACKENDS, NotifPayload, NotifResult

logger = logging.getLogger("scribe.notifications.dispatcher")

# Rate limiting en mémoire (par (user_id, minute))
_rate_bucket: Dict[tuple, int] = {}
_rate_bucket_window = None

# Dedup en mémoire (clé = event_type + event_ref_id + user_id, valeur = timestamp)
_dedup_cache: Dict[str, datetime] = {}
DEDUP_WINDOW_SEC = 3600  # 1h


def _apply_central_config(kind: str, cfg: dict) -> dict:
    """Comble la config d'un canal avec la config centrale (supervision) si le
    domaine y est activé. Précédence : config locale (cfg) > centrale > env.
    mail ← domaine 'smtp' ; sms ← domaine 'sms'. Jamais bloquant."""
    domain = {"mail": "smtp", "sms": "sms"}.get(kind)
    if not domain:
        return cfg
    try:
        from app.central_config import get_domain
        cc = get_domain(domain)
    except Exception:
        return cfg
    if not cc or not cc.get("enabled"):
        return cfg
    merged = dict(cfg or {})
    for k, v in cc.items():
        if k == "enabled" or v in (None, ""):
            continue
        if merged.get(k) in (None, ""):   # trou local → on comble avec le central
            merged[k] = v
    return merged


def _rate_check(user_id: int, limit_per_min: int = 10) -> bool:
    """True si l'user peut recevoir une nouvelle notif dans cette minute."""
    global _rate_bucket_window, _rate_bucket
    now_min = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    if now_min != _rate_bucket_window:
        _rate_bucket.clear()
        _rate_bucket_window = now_min
    key = (user_id, now_min)
    count = _rate_bucket.get(key, 0)
    if count >= limit_per_min:
        return False
    _rate_bucket[key] = count + 1
    return True


def _dedup_check(event_type: str, event_ref_id: Optional[int], user_id: int) -> bool:
    """True si l'event n'a pas déjà été notifié à ce user dans la fenêtre."""
    if not event_ref_id:
        return True  # pas d'ID → pas de dedup
    key = f"{event_type}:{event_ref_id}:{user_id}"
    now = datetime.now(timezone.utc)
    last = _dedup_cache.get(key)
    if last and (now - last).total_seconds() < DEDUP_WINDOW_SEC:
        return False
    _dedup_cache[key] = now
    # Nettoyage opportuniste du cache (garde taille raisonnable)
    if len(_dedup_cache) > 10000:
        cutoff = now - timedelta(seconds=DEDUP_WINDOW_SEC)
        for k, ts in list(_dedup_cache.items()):
            if ts < cutoff:
                _dedup_cache.pop(k, None)
    return True


def _is_silenced(db, user_id: int) -> bool:
    """True si l'utilisateur est en mode sourdine ACTIVE à l'instant."""
    from plugins.notifications.models import NotifSilence
    now = datetime.now(timezone.utc)
    sil = (db.query(NotifSilence)
             .filter(NotifSilence.user_id == user_id,
                     NotifSilence.active == True,
                     NotifSilence.lifted_at.is_(None))
             .order_by(NotifSilence.id.desc())
             .first())
    if not sil:
        return False
    if sil.until and sil.until < now:
        # Sourdine expirée, on la marque levée automatiquement
        sil.active = False
        sil.lifted_at = now
        try: db.commit()
        except Exception: db.rollback()
        return False
    return True


async def notify(
    event_type: str,
    title: str,
    body: str = "",
    urgency: int = 2,
    context: Optional[Dict[str, Any]] = None,
    target_users: Optional[list] = None,
) -> None:
    """Point d'entrée. Ne lève jamais — capture tout en interne.

    `target_users` : liste explicite d'user_id. Si None, on envoie à tous
    les abonnés dont les règles matchent.
    """
    try:
        await _notify_impl(event_type, title, body, urgency, context or {}, target_users)
    except Exception as e:
        logger.exception(f"[NOTIFY] Erreur interne : {e}")


async def _notify_impl(
    event_type: str, title: str, body: str, urgency: int,
    context: Dict[str, Any], target_users: Optional[list],
) -> None:
    from app.database import SessionLocal
    from plugins.notifications.models import (
        NotifChannel, NotifSubscription, NotifLog
    )

    db = SessionLocal()
    try:
        # 1. Charger les canaux activés
        channels = {c.kind: c for c in db.query(NotifChannel)
                                         .filter(NotifChannel.enabled == True).all()}
        if not channels:
            logger.info(f"[NOTIFY] Aucun canal activé, event {event_type} ignoré")
            return

        # 2. Charger les souscriptions cibles
        q = db.query(NotifSubscription).filter(
            NotifSubscription.active == True,
            NotifSubscription.min_urgency <= urgency,
            NotifSubscription.channel_kind.in_(channels.keys()),
        )
        if target_users:
            q = q.filter(NotifSubscription.user_id.in_(target_users))
        subs = q.all()

        if not subs:
            logger.info(f"[NOTIFY] Aucun abonné matchant pour {event_type} urgency={urgency}")
            return

        logger.info(f"[NOTIFY] Event {event_type} urgency={urgency} → "
                    f"{len(subs)} souscription(s) à traiter")

        # 3. Construire le payload une fois
        payload = NotifPayload(
            event_type=event_type,
            title=title,
            body=body,
            urgency=urgency,
            context=context,
        )
        event_ref_id = context.get("incident_id") or context.get("transfert_id") \
                       or context.get("decision_id")

        # 4. Instancier les backends
        backend_instances = {}
        for kind, channel in channels.items():
            cls = BACKENDS.get(kind)
            if not cls: continue
            try:
                cfg = json.loads(channel.config_json or "{}")
                cfg = _apply_central_config(kind, cfg)  # local > central > env
                inst = cls(cfg)
                if inst.is_configured():
                    backend_instances[kind] = inst
                else:
                    logger.warning(f"[NOTIFY] Backend {kind} activé mais mal configuré, skip")
            except Exception as e:
                logger.warning(f"[NOTIFY] Backend {kind} init échec: {e}")

        # 5. Fan-out pour chaque souscription
        tasks = []
        for sub in subs:
            # Mode sourdine (contrat : silencieux SAUF urgency=4)
            if urgency < 4 and _is_silenced(db, sub.user_id):
                _log_notif(db, event_type, event_ref_id, urgency, sub.user_id,
                           sub.channel_kind, sub.target[:200], title, body,
                           status="silenced", silenced=True)
                continue

            # Rate limit
            if not _rate_check(sub.user_id):
                _log_notif(db, event_type, event_ref_id, urgency, sub.user_id,
                           sub.channel_kind, sub.target[:200], title, body,
                           status="rate_limited")
                continue

            # Dedup
            if not _dedup_check(event_type, event_ref_id, sub.user_id):
                _log_notif(db, event_type, event_ref_id, urgency, sub.user_id,
                           sub.channel_kind, sub.target[:200], title, body,
                           status="deduped")
                continue

            backend = backend_instances.get(sub.channel_kind)
            if not backend: continue

            tasks.append(_send_one(db, backend, payload, sub, event_ref_id))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        db.close()


async def _send_one(db, backend, payload: NotifPayload, sub, event_ref_id) -> None:
    """Envoi + log audit trail."""
    try:
        result = await backend.send(payload, sub.target)
    except Exception as e:
        result = NotifResult(False, sub.target[:100], f"Exception: {e}")

    try:
        sub.last_used_at = datetime.now(timezone.utc)
        _log_notif(
            db, payload.event_type, event_ref_id, payload.urgency,
            sub.user_id, sub.channel_kind, result.target[:200],
            payload.title, payload.body,
            status="sent" if result.success else "failed",
            error=result.error,
        )
        # Désactivation auto des subscriptions push mortes
        if not result.success and sub.channel_kind == "webpush" and result.error:
            if "410" in result.error or "404" in result.error:
                sub.active = False
                logger.info(f"[NOTIFY] Subscription webpush {sub.id} désactivée (endpoint mort)")
        db.commit()
    except Exception as e:
        logger.warning(f"[NOTIFY] Log audit échec: {e}")
        try: db.rollback()
        except Exception: pass


def _log_notif(db, event_type, event_ref_id, urgency, user_id, channel_kind,
               target, title, body, status, error=None, silenced=False) -> None:
    from plugins.notifications.models import NotifLog
    try:
        entry = NotifLog(
            event_type=event_type,
            event_ref_id=event_ref_id,
            urgency=urgency,
            user_id=user_id,
            channel_kind=channel_kind,
            target=target[:200] if target else "",
            title=title[:200] if title else "",
            body=body[:2000] if body else "",
            status=status,
            error=(error or "")[:1000] if error else None,
            silenced=silenced,
        )
        db.add(entry)
    except Exception as e:
        logger.warning(f"[NOTIFY] Impossible de logger: {e}")


# Alias synchrone pour les appelants qui n'ont pas de loop asyncio disponible
def notify_sync(event_type: str, title: str, body: str = "", urgency: int = 2,
                context: Optional[Dict[str, Any]] = None, target_users=None) -> None:
    """Version sync : spawn un thread avec son event loop pour ne pas bloquer."""
    import threading
    def _run():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(notify(event_type, title, body, urgency,
                                           context, target_users))
        finally:
            loop.close()
    threading.Thread(target=_run, daemon=True).start()
