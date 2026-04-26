"""
plugins/brancardage/models.py — v2.2.6
Nouveaux champs : ref_type, agent_tel, transport_externe, etab_destination, arrivee_confirmee
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class BrcMission(Base):
    __tablename__ = "plugin_brc_missions"

    id               = Column(Integer, primary_key=True, index=True)

    # Référence patient anonyme
    ref_type         = Column(String(10),  default="AUTRE")   # IPP | NOM | AUTRE
    ref_patient      = Column(String(100), nullable=False)

    # Localisation
    uf_origine       = Column(String(200), nullable=False)
    chambre_depart   = Column(String(50),  nullable=True)
    uf_destination   = Column(String(200), nullable=False)
    etab_destination = Column(String(100), nullable=True)  # sigle GHT externe
    chambre_arrivee  = Column(String(50),  nullable=True)

    # Transport
    type_transport    = Column(String(20),  default="BRANCARD")
    transport_externe = Column(Integer,     default=0)   # 1 = ambulance inter-étab
    priorite          = Column(String(10),  default="P2")
    motif             = Column(String(200), nullable=True)
    commentaire       = Column(Text,        nullable=True)

    # Programmation
    programmee   = Column(Integer, default=0)
    heure_prevue = Column(String(10), nullable=True)
    avec_retour  = Column(Integer, default=0)
    heure_retour = Column(String(10), nullable=True)

    # État
    statut           = Column(String(20), default="EN_ATTENTE")
    arrivee_confirmee= Column(Integer,    default=0)

    # Personnel brancardier
    agent_id  = Column(String(100), nullable=True)
    agent_nom = Column(String(200), nullable=True)
    agent_tel = Column(String(50),  nullable=True)

    # Demandeur
    demandeur_id  = Column(String(100), nullable=True)
    demandeur_nom = Column(String(200), nullable=True)

    # Horodatages
    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                  onupdate=lambda: datetime.now(timezone.utc))
    prise_en_charge_at  = Column(DateTime, nullable=True)
    termine_at          = Column(DateTime, nullable=True)


class BrcHistorique(Base):
    __tablename__ = "plugin_brc_historique"

    id          = Column(Integer, primary_key=True, index=True)
    mission_id  = Column(Integer, ForeignKey("plugin_brc_missions.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    ancien_stat = Column(String(20), nullable=True)
    nouveau_stat= Column(String(20), nullable=False)
    par_user    = Column(String(100), nullable=True)
    commentaire = Column(String(500), nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
