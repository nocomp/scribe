"""
plugins/repondeur/models.py — SCRIBE
=====================================
Plugin RÉPONDEUR : lignes d'information de crise (audiotext / SVI).

Chaque LIGNE est un numéro de téléphone (fourni par Twilio) configuré en
répondeur : quand un appelant compose le numéro, Twilio interroge le webhook
SCRIBE qui répond en TwiML <Say> le message courant, dans la langue choisie
(SVI multilingue « 1 pour le français, 2 for English »).

Conventions SCRIBE :
  - Base SQLAlchemy partagée (app.database.Base) — JAMAIS de declarative_base()
    local (sinon NoReferencedTableError sur les FK vers `users`).
  - Tables préfixées `plugin_repondeur_*`.
  - Secrets (auth_token Twilio) chiffrés au repos (préfixe `enc:`).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class RepondeurConfig(Base):
    """Configuration Twilio (singleton id=1).

    Précédence à la lecture : cette table (config LOCALE) > config CENTRALE
    'twilio' (supervision) > variables d'environnement SCRIBE_TWILIO_*.
    """
    __tablename__ = "plugin_repondeur_config"

    id           = Column(Integer, primary_key=True)         # toujours 1
    # Fournisseur actif : "twilio" (webhook TwiML live) ou "ovh" (SVI assisté).
    provider     = Column(String(10), default="twilio", nullable=False)
    account_sid  = Column(String(80),  nullable=True)        # ACxxxx…
    auth_token   = Column(String(300), nullable=True)        # chiffré (enc:)
    # URL publique de CETTE instance, utilisée pour construire le webhook voix
    # déclaré côté Twilio (ex: https://mon-serveur.example.net:8000).
    public_url   = Column(String(300), nullable=True)
    # Voix Twilio par défaut ("Polly.Lea" FR, "alice", "man", "woman"…).
    default_voice = Column(String(80), nullable=True)
    # ── OVH Télécom (API : auth app_key/app_secret/consumer_key, comme le SMS) ──
    ovh_endpoint        = Column(String(20),  nullable=True)  # "ovh-eu" / "ovh-ca"
    ovh_app_key         = Column(String(120), nullable=True)
    ovh_app_secret      = Column(String(300), nullable=True)  # chiffré (enc:)
    ovh_consumer_key    = Column(String(300), nullable=True)  # chiffré (enc:)
    ovh_billing_account = Column(String(60),  nullable=True)  # ovhtel-xxxxx-1
    ovh_service         = Column(String(60),  nullable=True)  # numéro / serviceName OVH
    updated_at   = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    updated_by   = Column(String(120), nullable=True)


class RepondeurLigne(Base):
    """Une ligne d'information (Médias, Familles, Patients…)."""
    __tablename__ = "plugin_repondeur_lignes"

    id        = Column(Integer, primary_key=True, index=True)
    libelle   = Column(String(120), nullable=False)          # "Familles de patients"
    numero    = Column(String(40),  nullable=True)           # numéro Twilio (affichage public)
    # Langue principale (code SCRIBE 2 lettres : fr, en, de…).
    langue_principale = Column(String(8), default="fr", nullable=False)
    # Langues actives pour le SVI multilingue (CSV : "fr,en,de"). Vide => langue_principale seule.
    langues   = Column(String(200), default="", nullable=False)
    actif     = Column(Boolean, default=False, nullable=False)
    ordre     = Column(Integer, default=0, nullable=False)
    voice     = Column(String(80), nullable=True)            # surcharge voix par ligne
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(String(120), nullable=True)

    messages = relationship(
        "RepondeurMessage", back_populates="ligne",
        cascade="all, delete-orphan", lazy="selectin",
    )

    def langues_list(self):
        base = [l.strip() for l in (self.langues or "").split(",") if l.strip()]
        if self.langue_principale and self.langue_principale not in base:
            base.insert(0, self.langue_principale)
        return base or [self.langue_principale or "fr"]


class RepondeurMessage(Base):
    """Texte du message d'une ligne, PAR langue (une entrée par langue)."""
    __tablename__ = "plugin_repondeur_messages"

    id        = Column(Integer, primary_key=True, index=True)
    ligne_id  = Column(Integer, ForeignKey("plugin_repondeur_lignes.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    langue    = Column(String(8), default="fr", nullable=False)
    texte     = Column(Text, default="", nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(String(120), nullable=True)

    ligne = relationship("RepondeurLigne", back_populates="messages")


Index("ix_repondeur_msg_ligne_langue",
      RepondeurMessage.ligne_id, RepondeurMessage.langue, unique=True)
