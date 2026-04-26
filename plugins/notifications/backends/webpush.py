"""
plugins/notifications/backends/webpush.py — Backend Web Push via VAPID.

Utilise la lib `pywebpush` (à installer : `pip install pywebpush`).
Sans VAPID keys configurées, le backend est no-op.

Génération des clés VAPID (à faire une fois, stocker en DB notif_channel) :
  from py_vapid import Vapid
  vapid = Vapid()
  vapid.generate_keys()
  vapid.save_key("vapid_private.pem")
  public_key_b64 = vapid.public_key_bytes_to_b64urlsafe(...)

Config attendue :
  {
    "vapid_public_key":  "BN...",       # base64url
    "vapid_private_key": "...",          # base64url ou PEM
    "subject":           "mailto:rssi@ch-nord.fr",  # requis par VAPID
    "ttl":               86400,          # sec. Durée de vie du push en attente.
  }

Target (dans NotifSubscription.target) = JSON sérialisé du `PushSubscription`
récupéré côté navigateur :
  {
    "endpoint": "https://fcm.googleapis.com/fcm/send/...",
    "keys": {"p256dh": "...", "auth": "..."}
  }
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Dict, Any

from plugins.notifications.backends.base import NotificationBackend, NotifPayload, NotifResult

logger = logging.getLogger("scribe.notifications.webpush")

try:
    from pywebpush import webpush, WebPushException  # type: ignore
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    PYWEBPUSH_AVAILABLE = False


class WebPushBackend(NotificationBackend):
    kind = "webpush"

    def is_configured(self) -> bool:
        if not PYWEBPUSH_AVAILABLE:
            return False
        c = self.config
        return bool(c.get("vapid_private_key")) and bool(c.get("subject"))

    def _build_push_data(self, payload: NotifPayload) -> Dict[str, Any]:
        """Construit le JSON envoyé dans le push.

        Le service worker SCRIBE lit ce JSON et affiche la notification.
        """
        url = payload.context.get("url", "/")
        return {
            "title": f"{payload.severity_emoji()} {payload.title}"[:120],
            "body":  payload.body[:200],
            "urgency": payload.urgency,
            "event_type": payload.event_type,
            "url":   url,
            "tag":   f"{payload.event_type}_{payload.context.get('incident_id', '')}",
                # tag = déduplication côté navigateur : si le user a déjà
                # une notif avec même tag, elle est remplacée au lieu d'empiler.
            "requireInteraction": payload.urgency >= 3,
                # Urgency 3+ = notif reste à l'écran jusqu'à click user.
            "silent": False,
            "timestamp": int(__import__("time").time() * 1000),
        }

    async def send(self, payload: NotifPayload, target: str) -> NotifResult:
        if not PYWEBPUSH_AVAILABLE:
            return NotifResult(False, "(push)",
                               "Lib pywebpush non installée (pip install pywebpush)")
        if not self.is_configured():
            return NotifResult(False, "(push)",
                               "Backend webpush non configuré (VAPID keys manquantes)")
        try:
            subscription = json.loads(target) if isinstance(target, str) else target
            endpoint_short = str(subscription.get("endpoint", ""))[:60] + "..."

            data = self._build_push_data(payload)

            # pywebpush est synchrone, on l'envoie dans un thread pour ne pas
            # bloquer l'event loop FastAPI.
            def _send():
                webpush(
                    subscription_info=subscription,
                    data=json.dumps(data),
                    vapid_private_key=self.config["vapid_private_key"],
                    vapid_claims={
                        "sub": self.config.get("subject", "mailto:admin@scribe.local"),
                    },
                    ttl=int(self.config.get("ttl", 86400)),
                )

            await asyncio.get_event_loop().run_in_executor(None, _send)
            return NotifResult(True, endpoint_short)
        except WebPushException as e:
            # Le push peut échouer pour de bonnes raisons (abonnement expiré).
            # Dans ce cas, on retourne l'erreur — l'appelant (dispatcher)
            # désactive la subscription.
            err = f"WebPush HTTP {getattr(e.response, 'status_code', '?')}"
            return NotifResult(False, "(push)", err)
        except Exception as e:
            logger.warning(f"WebPush échec: {e}")
            return NotifResult(False, "(push)", str(e))
