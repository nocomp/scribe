"""
plugins/notifications/backends/base.py — Classe abstraite pour les backends.

Chaque backend concret (mail, webpush, sms) hérite de NotificationBackend
et implémente `send()`. Le dispatcher appelle ces backends en parallèle
avec asyncio.gather.

Contrat du backend :
- receive une NotifPayload (dataclass avec title, body, urgency, context)
- renvoie un NotifResult (success bool + error optionnel + target loggé)
- NE DOIT JAMAIS lever — toutes les erreurs sont capturées et loggées.
  Un backend qui crash ne doit pas bloquer les autres.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class NotifPayload:
    """Contenu à notifier."""
    event_type: str                 # "incident_created", "transfert_created", etc.
    title:      str                 # court, 120 chars max
    body:       str                 # corps, markdown toléré
    urgency:    int = 2             # 1-4
    context:    Dict[str, Any] = field(default_factory=dict)
        # {"incident_id": 42, "uf": "URGENCES", "url": "..."}

    def severity_emoji(self) -> str:
        return {1:"ℹ️", 2:"⚠️", 3:"🚨", 4:"🔴"}.get(self.urgency, "ℹ️")


@dataclass
class NotifResult:
    """Résultat de l'envoi par un backend."""
    success:   bool
    target:    str           # loggé en audit ("jean.dupont@ch.fr", "+3361...", endpoint push tronqué)
    error:     Optional[str] = None
    backend_info: Dict[str, Any] = field(default_factory=dict)
        # Infos utiles pour debug : message_id SMTP, status SMS, etc.


class NotificationBackend:
    """Classe abstraite. Hériter et implémenter send()."""
    kind: str = "abstract"

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}

    def is_configured(self) -> bool:
        """True si le backend a les credentials nécessaires pour envoyer."""
        return False

    async def send(self, payload: NotifPayload, target: str) -> NotifResult:
        """Envoie la notification à `target`.

        `target` est spécifique au backend :
          - mail : adresse mail
          - webpush : JSON subscription
          - sms : numéro E.164

        NE DOIT PAS LEVER D'EXCEPTION. Toujours retourner un NotifResult,
        même en cas d'erreur (success=False + error="...").
        """
        raise NotImplementedError
