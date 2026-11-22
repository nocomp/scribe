"""
plugins/lignes/models.py — Modèles du plugin `lignes`.

IMPORTANT : Base vient de app.database (jamais de declarative_base() local,
sinon NoReferencedTableError silencieux sur les FK).
"""
from datetime import datetime, timezone

from sqlalchemy import (Column, Integer, String, Text, Boolean, DateTime,
                        ForeignKey)
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class LigneInfo(Base):
    """Une ligne d'information de crise (ex : Médias, Familles, Patients).

    En production il y en a plusieurs ; elles sont normalement DORMANTES
    (actif=False) et activées en deux clics le jour J.
    """
    __tablename__ = "plugin_lignes_ligne"

    id            = Column(Integer, primary_key=True)
    label         = Column(String(120), nullable=False)
    numero        = Column(String(40), default="")        # numéro Twilio affiché au public
    description   = Column(String(300), default="")
    actif         = Column(Boolean, default=False)        # dormante tant que non activée
    ordre         = Column(Integer, default=0)
    langue_defaut = Column(String(8), default="fr")
    created_at    = Column(DateTime, default=_utcnow)
    updated_at    = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    messages = relationship("LigneMessage", back_populates="ligne",
                            cascade="all, delete-orphan")


class LigneMessage(Base):
    """Annonce d'une ligne pour UNE langue. Multilingue = plusieurs lignes."""
    __tablename__ = "plugin_lignes_message"

    id         = Column(Integer, primary_key=True)
    ligne_id   = Column(Integer, ForeignKey("plugin_lignes_ligne.id"), nullable=False)
    langue     = Column(String(8), default="fr")
    texte      = Column(Text, default="")
    source     = Column(String(20), default="manuel")     # manuel|fichiers|assistant|communique
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(String(120), default="")

    ligne = relationship("LigneInfo", back_populates="messages")
