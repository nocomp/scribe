"""
plugins/notifications/backends/sms.py — Backend SMS multi-provider.

Providers supportés (via httpx, pas de SDK lourd) :
- ovh   : API OVH SMS (France, ~0,06€/SMS, reconnu par l'ANSSI pour le public)
- twilio: API Twilio (international, ~0,07€/SMS, fiable)
- free  : API Free Mobile perso (gratuit, 1 compte = 1 numéro, pour tests uniquement)

Config attendue selon le provider :

  OVH :
  {
    "provider":  "ovh",
    "endpoint":  "ovh-eu",
    "app_key":    "...",
    "app_secret": "...",
    "consumer_key": "...",
    "service_name": "sms-xxxx-1",    # nom du service SMS dans OVH
    "sender": "SCRIBE"                # max 11 chars alphanum
  }

  Twilio :
  {
    "provider":   "twilio",
    "account_sid":"AC...",
    "auth_token": "...",
    "sender":     "+33...",           # numéro émetteur acheté
  }

  Free Mobile (pour tests uniquement) :
  {
    "provider": "free",
    "user":     "12345678",
    "api_key":  "xxx",
  }
"""
from __future__ import annotations
import logging
from typing import Dict, Any
import httpx

from plugins.notifications.backends.base import NotificationBackend, NotifPayload, NotifResult

logger = logging.getLogger("scribe.notifications.sms")


class SmsBackend(NotificationBackend):
    kind = "sms"

    def is_configured(self) -> bool:
        c = self.config
        p = c.get("provider", "").lower()
        if p == "ovh":
            return all(c.get(k) for k in ("app_key","app_secret","consumer_key","service_name"))
        if p == "twilio":
            return all(c.get(k) for k in ("account_sid","auth_token","sender"))
        if p == "free":
            return all(c.get(k) for k in ("user","api_key"))
        return False

    def _build_message(self, payload: NotifPayload) -> str:
        """Construit le texte SMS : « [SCRIBE 🔴] TITRE — corps » + lien cliquable.

        h74 — Si le contexte fournit un lien (base_url + url relatif, ex. la notif
        d'incident porte url='/#incidents/42'), on l'ajoute en clair à la fin et on
        garantit qu'il n'est jamais tronqué. Sans lien : 1 SMS (160). Avec lien :
        on autorise jusqu'à ~2 segments concaténés (306) pour préserver l'URL."""
        emoji = payload.severity_emoji()
        prefix = f"[SCRIBE {emoji}] "
        ctx = payload.context or {}
        base = (ctx.get("base_url") or "").rstrip("/")
        rel = ctx.get("url") or ""
        link = ""
        if base and rel:
            link = base + rel if rel.startswith("/") else f"{base}/{rel}"
        tail = ("\n" + link) if link else ""
        hard_max = 306 if link else 160   # 2 segments si lien, sinon 1 SMS
        text = f"{prefix}{payload.title}"
        if payload.body:
            avail = hard_max - len(tail) - len(text) - 3
            if avail > 10:
                text += " — " + payload.body[:avail]
        text += tail
        return text[:hard_max]
<<<<<<< HEAD

    async def send_raw(self, text: str, target: str) -> NotifResult:
        """Envoi BRUT d'un SMS : pas de préfixe « [SCRIBE …] », pas de filtre
        d'urgence. Utilisé pour des messages hors-incident (ex. mot de passe d'un
        pli sécurisé envoyé par un canal séparé). Le texte est envoyé tel quel."""
        if not self.is_configured():
            return NotifResult(False, target,
                               f"Backend SMS non configuré ({self.config.get('provider','?')})")
        provider = self.config.get("provider", "").lower()
        try:
            if provider == "ovh":
                return await self._send_ovh(text, target)
            if provider == "twilio":
                return await self._send_twilio(text, target)
            if provider == "free":
                return await self._send_free(text, target)
            return NotifResult(False, target, f"Provider '{provider}' inconnu")
        except Exception as e:
            logger.warning(f"SMS raw {provider} → {target}: {e}")
            return NotifResult(False, target, str(e))
=======
>>>>>>> 42014cc0f1f987ee0564de52890336b067151060

    async def send(self, payload: NotifPayload, target: str) -> NotifResult:
        if not self.is_configured():
            return NotifResult(False, target,
                               f"Backend SMS non configuré ({self.config.get('provider','?')})")
        # Filtre sécurité : SMS seulement urgency ≥ 3 par défaut
        # (l'appelant peut override via context, mais on garde un garde-fou).
        if payload.urgency < int(self.config.get("min_urgency_sms", 3)):
            return NotifResult(False, target, f"SMS filtré (urgency {payload.urgency} < seuil)")

        provider = self.config.get("provider", "").lower()
        text = self._build_message(payload)
        try:
            if provider == "ovh":
                return await self._send_ovh(text, target)
            if provider == "twilio":
                return await self._send_twilio(text, target)
            if provider == "free":
                return await self._send_free(text, target)
            return NotifResult(False, target, f"Provider '{provider}' inconnu")
        except Exception as e:
            logger.warning(f"SMS {provider} → {target}: {e}")
            return NotifResult(False, target, str(e))

    async def _send_ovh(self, text: str, to: str) -> NotifResult:
        """Envoi via API OVH SMS.

        Doc: https://help.ovhcloud.com/csm/fr-sms-api
        """
        import hashlib, time
        c = self.config
        endpoint = {
            "ovh-eu":"https://eu.api.ovh.com/1.0",
            "ovh-ca":"https://ca.api.ovh.com/1.0",
        }.get(c.get("endpoint","ovh-eu"), "https://eu.api.ovh.com/1.0")
        method = "POST"
        url = f"{endpoint}/sms/{c['service_name']}/jobs"
        body_json = {
            "message":    text,
            "sender":     c.get("sender", "SCRIBE"),
            "receivers":  [to],
            "noStopClause": True,    # hors alertes commerciales, pas de "STOP"
        }
        import json as _j
        body_str = _j.dumps(body_json)
        # Signature OVH : SHA1("$as+$ck+$method+$url+$body+$ts")
        async with httpx.AsyncClient(timeout=15.0) as client:
            t = await client.get(f"{endpoint}/auth/time")
            ts = t.text
            sig_raw = f"{c['app_secret']}+{c['consumer_key']}+{method}+{url}+{body_str}+{ts}"
            sig = "$1$" + hashlib.sha1(sig_raw.encode()).hexdigest()
            r = await client.post(url, content=body_str, headers={
                "X-Ovh-Application": c["app_key"],
                "X-Ovh-Consumer":    c["consumer_key"],
                "X-Ovh-Timestamp":   ts,
                "X-Ovh-Signature":   sig,
                "Content-Type":      "application/json",
            })
        ok = r.status_code < 300
        return NotifResult(
            ok, to,
            error=None if ok else f"HTTP {r.status_code}: {r.text[:200]}",
            backend_info={"provider":"ovh", "status": r.status_code},
        )

    async def _send_twilio(self, text: str, to: str) -> NotifResult:
        c = self.config
        url = f"https://api.twilio.com/2010-04-01/Accounts/{c['account_sid']}/Messages.json"
        async with httpx.AsyncClient(timeout=15.0,
                                     auth=(c["account_sid"], c["auth_token"])) as client:
            r = await client.post(url, data={
                "From": c["sender"],
                "To":   to,
                "Body": text,
            })
        ok = r.status_code < 300
        return NotifResult(
            ok, to,
            error=None if ok else f"HTTP {r.status_code}: {r.text[:200]}",
            backend_info={"provider":"twilio", "status": r.status_code},
        )

    async def _send_free(self, text: str, to: str) -> NotifResult:
        """Free Mobile — ignore `to`, envoie au compte configuré."""
        c = self.config
        url = "https://smsapi.free-mobile.fr/sendmsg"
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params={
                "user":  c["user"],
                "pass":  c["api_key"],
                "msg":   text,
            })
        ok = r.status_code == 200
        return NotifResult(
            ok, c["user"],
            error=None if ok else f"HTTP {r.status_code}",
            backend_info={"provider":"free", "status": r.status_code},
        )
