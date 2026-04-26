import os as _os

from plugins.notifications.backends.base import (
    NotificationBackend, NotifPayload, NotifResult
)
from plugins.notifications.backends.mail import MailBackend
from plugins.notifications.backends.webpush import WebPushBackend
from plugins.notifications.backends.sms import SmsBackend
from plugins.notifications.backends.telegram import TelegramBackend

# v2307 — Telegram retiré des backends activés par défaut suite aux
# recommandations du CERT Santé : serveurs hors UE, incompatible avec
# les obligations OSE / NIS2 / HDS pour les hôpitaux publics français.
# Canaux officiels SCRIBE : Mail + SMS + Web Push + webhook générique.
#
# Le code Telegram reste présent pour les établissements qui veulent
# l'activer explicitement sous leur propre responsabilité (ex: hôpital
# privé hors OSE, exercice pédagogique, GHT hors France). Pour activer :
# export SCRIBE_ENABLE_TELEGRAM=1 avant le démarrage.
_TELEGRAM_ENABLED = _os.environ.get("SCRIBE_ENABLE_TELEGRAM", "0").lower() in (
    "1", "true", "yes", "on",
)

BACKENDS = {
    "mail":     MailBackend,
    "webpush":  WebPushBackend,
    "sms":      SmsBackend,
}
if _TELEGRAM_ENABLED:
    BACKENDS["telegram"] = TelegramBackend

__all__ = [
    "NotificationBackend", "NotifPayload", "NotifResult",
    "MailBackend", "WebPushBackend", "SmsBackend", "TelegramBackend",
    "BACKENDS",
]
