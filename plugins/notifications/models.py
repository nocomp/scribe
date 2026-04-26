"""
plugins/notifications/models.py — Modèles SQLAlchemy pour le plugin Notifications.

Tables :
  - notif_channel         : Configuration globale des canaux (mail SMTP,
                            Web Push VAPID, SMS provider) + activation ON/OFF
  - notif_subscription    : Abonnement d'un utilisateur à un canal
                            (endpoint push, adresse mail override, tel)
  - notif_silence         : État sourdine par utilisateur (1h / jusqu'à levée)
  - notif_log             : Journal exhaustif des notifications émises
                            (audit trail pour "est-ce que le Dr X a été prévenu ?")
  - notif_settings        : Clé/valeur globale (règles de routage, quiet hours,
                            sons par urgence, etc.)
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database import Base


class NotifChannel(Base):
    """Canal de notification configuré globalement (mail, push, sms, webhook)."""
    __tablename__ = "notif_channel"

    id          = Column(Integer, primary_key=True)
    kind        = Column(String(20), nullable=False, index=True)
        # "mail" | "webpush" | "sms" | "webhook"
    label       = Column(String(80), nullable=False, default="")
        # "Mail SMTP interne", "OVH SMS prod", etc.
    enabled     = Column(Boolean, default=False)
    config_json = Column(Text, default="{}")
        # Config spécifique au canal :
        # mail     : {"smtp_host":"...","smtp_port":587,"smtp_user":"...","from_addr":"..."}
        # webpush  : {"vapid_public_key":"...","vapid_private_key":"...","subject":"mailto:..."}
        # sms      : {"provider":"ovh|twilio","api_key":"...","sender":"SCRIBE"}
        # webhook  : {"url":"https://outlook.office.com/webhook/...","format":"teams|slack"}
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class NotifSubscription(Base):
    """Abonnement d'un utilisateur à un canal.

    Un user peut avoir plusieurs souscriptions (mail perso + push tablette
    de garde + SMS astreinte). Le champ `min_urgency` filtre côté backend
    pour ne pas spammer les niveaux d'info à tout le monde.
    """
    __tablename__ = "notif_subscription"

    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_kind   = Column(String(20), nullable=False, index=True)
        # "mail" | "webpush" | "sms"
    target         = Column(Text, nullable=False)
        # mail     : adresse mail
        # webpush  : JSON {"endpoint":"...","keys":{"p256dh":"...","auth":"..."}}
        # sms      : numéro E.164 (+33612345678)
    label          = Column(String(80), default="")
        # "Mail pro", "iPhone de garde", "SMS astreinte"
    min_urgency    = Column(Integer, default=2)
        # 1=info, 2=vigilance, 3=alerte, 4=critique. Notif envoyée si
        # incident.urgency >= min_urgency.
    active         = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at   = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_notif_sub_user_kind", "user_id", "channel_kind"),
    )


class NotifSilence(Base):
    """Mode sourdine actif pour un utilisateur.

    Règle métier v2.3.87 : sourdine = silencieux SAUF urgency=4.
    Les critiques passent toujours (contrat de sécurité).
    """
    __tablename__ = "notif_silence"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    active       = Column(Boolean, default=True)
    until        = Column(DateTime, nullable=True)
        # NULL = jusqu'à levée manuelle
    reason       = Column(String(200), default="")
        # "Crise en cours", "Réunion", etc. Affiché dans le digest de fin.
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    lifted_at    = Column(DateTime, nullable=True)


class NotifLog(Base):
    """Journal exhaustif des notifications émises.

    Critique pour répondre à "est-ce que le Dr X a bien été prévenu ?"
    après un incident. Chaque tentative (réussie ou non) est tracée avec
    horodatage, canal, statut, et raison d'échec le cas échéant.
    """
    __tablename__ = "notif_log"

    id            = Column(Integer, primary_key=True)
    ts            = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    event_type    = Column(String(40), index=True)
        # "incident_created" | "incident_escalated" | "transfert_created"
        # "decision_taken" | "chat_mention" | "test" | "digest_silence"
    event_ref_id  = Column(Integer, nullable=True)
        # ID de l'entité source (incident.id, transfert.id, ...)
    urgency       = Column(Integer, nullable=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    channel_kind  = Column(String(20), index=True)
    target        = Column(String(200))
        # Adresse mail / numéro tel / endpoint push (tronqué)
    title         = Column(String(200))
    body          = Column(Text)
    status        = Column(String(20), index=True)
        # "sent" | "failed" | "silenced" | "rate_limited" | "deduped"
    error         = Column(Text, nullable=True)
    silenced      = Column(Boolean, default=False)
        # True si la notif a été filtrée par le mode sourdine

    __table_args__ = (
        Index("idx_notif_log_event", "event_type", "event_ref_id"),
    )


class NotifSettings(Base):
    """Paramètres globaux clé/valeur (JSON) du plugin.

    Ex: règles de routage urgency → canaux, quiet hours, sons par urgence,
    rate limit, dedup window.
    """
    __tablename__ = "notif_settings"

    key         = Column(String(80), primary_key=True)
    value_json  = Column(Text, default="{}")
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
