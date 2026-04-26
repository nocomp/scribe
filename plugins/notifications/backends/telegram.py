"""
plugins/notifications/backends/telegram.py — Backend Telegram Bot API.

Totalement gratuit, officiel, sans quota raisonnable. Chaque établissement
crée son propre bot via @BotFather (2 minutes) et obtient un token.

Config attendue :
  {
    "bot_token": "1234567890:AAA...",    # token du bot obtenu via @BotFather
    "parse_mode": "HTML",                # ou "Markdown" ou "" pour texte brut
    "disable_notification_below": 3,     # urgency < 3 = notif silencieuse
  }

Target (NotifSubscription.target) = `chat_id` Telegram de l'utilisateur
(entier stocké comme string : "123456789").

Pour récupérer son chat_id :
  1. L'utilisateur envoie /start au bot
  2. Le bot répond avec son chat_id (via la commande /monid implémentée
     soit côté serveur webhook, soit simplement via la page d'inscription
     SCRIBE qui demande d'envoyer /start et de coller la réponse)
  3. L'utilisateur colle son chat_id dans la page "Notifications" SCRIBE

Ergonomie pour l'utilisateur :
  - Ouvre l'appli Telegram (déjà installée par 500M d'Européens)
  - Cherche le bot @NomDeVotreHopitalBot
  - Clique "Démarrer"
  - Reçoit son chat_id dans le chat
  - Colle dans SCRIBE

C'est plus simple qu'une app native et ça marche sur tous les téléphones.
"""
from __future__ import annotations
import logging
from typing import Dict, Any
import httpx

from plugins.notifications.backends.base import NotificationBackend, NotifPayload, NotifResult

logger = logging.getLogger("scribe.notifications.telegram")


class TelegramBackend(NotificationBackend):
    kind = "telegram"

    def is_configured(self) -> bool:
        return bool(self.config.get("bot_token"))

    def _format_message(self, payload: NotifPayload) -> str:
        """Construit le message avec éventuellement du HTML/Markdown."""
        parse_mode = self.config.get("parse_mode", "HTML")
        emoji = payload.severity_emoji()
        urgency_label = {1:"Info", 2:"Vigilance", 3:"Alerte", 4:"CRITIQUE"}.get(payload.urgency, "")

        if parse_mode == "HTML":
            # Échappement HTML Telegram (seuls < > & doivent être échappés)
            esc = lambda s: (str(s or "")
                             .replace("&", "&amp;")
                             .replace("<", "&lt;")
                             .replace(">", "&gt;"))
            msg = f"{emoji} <b>SCRIBE — {urgency_label}</b>\n\n"
            msg += f"<b>{esc(payload.title)}</b>\n"
            if payload.body:
                msg += f"\n{esc(payload.body[:500])}\n"
            url = payload.context.get("url")
            if url:
                # Rendre le lien absolu si besoin
                base = self.config.get("scribe_base_url", "")
                full_url = url if url.startswith("http") else (base.rstrip("/") + url if base else url)
                if full_url.startswith("http"):
                    msg += f"\n<a href=\"{esc(full_url)}\">🔗 Consulter dans SCRIBE</a>"
            return msg[:4000]  # Telegram limite à 4096 chars

        elif parse_mode == "Markdown":
            esc = lambda s: str(s or "").replace("*","\\*").replace("_","\\_").replace("[","\\[")
            msg = f"{emoji} *SCRIBE — {urgency_label}*\n\n*{esc(payload.title)}*\n"
            if payload.body:
                msg += f"\n{esc(payload.body[:500])}\n"
            url = payload.context.get("url")
            if url:
                base = self.config.get("scribe_base_url", "")
                full_url = url if url.startswith("http") else (base.rstrip("/") + url if base else url)
                if full_url.startswith("http"):
                    msg += f"\n[🔗 Consulter]({full_url})"
            return msg[:4000]

        else:
            # Plain text
            msg = f"{emoji} SCRIBE — {urgency_label}\n\n{payload.title}\n"
            if payload.body:
                msg += f"\n{payload.body[:500]}\n"
            url = payload.context.get("url")
            if url:
                base = self.config.get("scribe_base_url", "")
                full_url = url if url.startswith("http") else (base.rstrip("/") + url if base else url)
                msg += f"\n🔗 {full_url}"
            return msg[:4000]

    async def send(self, payload: NotifPayload, target: str) -> NotifResult:
        if not self.is_configured():
            return NotifResult(False, target, "Backend telegram non configuré (bot_token manquant)")

        # target = chat_id (entier en string)
        chat_id = str(target).strip()
        if not chat_id or not (chat_id.lstrip("-").isdigit()):
            return NotifResult(False, target, f"chat_id Telegram invalide : {target[:40]}")

        bot_token = self.config["bot_token"]
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        message_text = self._format_message(payload)
        parse_mode = self.config.get("parse_mode", "HTML")

        # Notification silencieuse si urgency faible
        silent_below = int(self.config.get("disable_notification_below", 3))
        disable_notif = payload.urgency < silent_below

        data = {
            "chat_id": chat_id,
            "text": message_text,
            "disable_notification": disable_notif,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            data["parse_mode"] = parse_mode

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, json=data)
            if r.status_code == 200:
                resp = r.json()
                if resp.get("ok"):
                    return NotifResult(
                        True, f"tg:{chat_id}",
                        backend_info={"message_id": resp.get("result", {}).get("message_id")},
                    )
                return NotifResult(False, f"tg:{chat_id}",
                                   f"Telegram rejet: {resp.get('description', '?')}")
            # 400 = chat_id invalide ou bot bloqué par l'user
            # 401 = bot_token invalide
            # 429 = rate limit (rare)
            elif r.status_code == 403:
                # Typiquement "Forbidden: bot was blocked by the user"
                return NotifResult(False, f"tg:{chat_id}",
                                   "Bot bloqué par l'utilisateur — subscription à désactiver")
            return NotifResult(False, f"tg:{chat_id}",
                               f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"Telegram → {chat_id}: {e}")
            return NotifResult(False, f"tg:{chat_id}", str(e))


async def telegram_get_chat_id_from_update(bot_token: str) -> dict:
    """Helper pour récupérer les chat_id depuis les updates récentes du bot.

    Utile pour un premier setup : l'user envoie /start au bot, puis
    l'admin SCRIBE appelle cette fonction pour lister les chat_id
    disponibles.
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    data = r.json()
    if not data.get("ok"):
        return {"error": data.get("description", "?")}
    chats = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid:
            chats[cid] = {
                "chat_id": cid,
                "first_name": chat.get("first_name", ""),
                "last_name": chat.get("last_name", ""),
                "username": chat.get("username", ""),
                "type": chat.get("type", ""),
            }
    return {"chats": list(chats.values())}
