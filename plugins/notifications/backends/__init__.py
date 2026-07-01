# h148 — Canal Telegram définitivement retiré de SCRIBE.
# Non conforme au cadre réglementaire des OSE de santé français
# (serveurs hors UE, incompatible HDS/NIS2/CERT Santé).
# Canaux supportés : Mail · SMS · Web Push.

from plugins.notifications.backends.base import (
    NotificationBackend, NotifPayload, NotifResult
)
from plugins.notifications.backends.mail import MailBackend
from plugins.notifications.backends.webpush import WebPushBackend
from plugins.notifications.backends.sms import SmsBackend

BACKENDS = {
    "mail":    MailBackend,
    "webpush": WebPushBackend,
    "sms":     SmsBackend,
}

__all__ = [
    "NotificationBackend", "NotifPayload", "NotifResult",
    "MailBackend", "WebPushBackend", "SmsBackend",
    "BACKENDS",
]
