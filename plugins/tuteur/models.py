"""
plugins/tuteur/models.py — Modèles SQLAlchemy du plugin Tuteur

Base isolée (declarative_base local) pour ne pas perturber la Base
principale de l'app. Préfixe tables : plugin_tuteur_*

Pas de ForeignKey vers users.id : la table users vit sur app.database.Base
(autre déclarative). On stocke user_id (Integer indexé) + username (String)
pour résilience aux purges utilisateurs et facilité d'export.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


class TuteurSession(Base):
    """Une session = un exercice joué OU une période de mode prod observée."""
    __tablename__ = "plugin_tuteur_sessions"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, nullable=True, index=True)
    username         = Column(String(100), nullable=True, index=True)
    instance_sigle   = Column(String(30), nullable=False)
    mode             = Column(String(20), nullable=False)   # "exercice" | "prod"
    scenario_id      = Column(String(100), nullable=True)
    intention_pedago = Column(Text, nullable=True)
    started_at       = Column(DateTime, default=_utcnow)
    ended_at         = Column(DateTime, nullable=True)


class TuteurObservation(Base):
    """Toutes les actions et non-actions observées pendant une session."""
    __tablename__ = "plugin_tuteur_observations"

    id               = Column(Integer, primary_key=True, index=True)
    session_id       = Column(Integer, ForeignKey("plugin_tuteur_sessions.id"), index=True)
    timestamp        = Column(DateTime, default=_utcnow)
    type_observation = Column(String(40), nullable=False)
    # Valeurs : ACTION | INACTION | DECISION | RAPPEL_AFFICHE
    #           MESSAGE_ENVOYE | INCIDENT_CREE | INCIDENT_RESOLU | TRANSFERT | JALON
    target_type      = Column(String(40), nullable=True)
    target_id        = Column(Integer, nullable=True)
    detail           = Column(JSON, nullable=True)
    latence_s        = Column(Integer, nullable=True)


class TuteurRappel(Base):
    """Pop-ups de rappel envoyés à l'utilisateur (Hook 2A/2B)."""
    __tablename__ = "plugin_tuteur_rappels"

    id           = Column(Integer, primary_key=True, index=True)
    session_id   = Column(Integer, ForeignKey("plugin_tuteur_sessions.id"), index=True)
    timestamp    = Column(DateTime, default=_utcnow)
    contexte     = Column(JSON, nullable=True)
    contenu      = Column(Text, nullable=True)
    ack          = Column(Boolean, default=False)
    ack_at       = Column(DateTime, nullable=True)
    action_apres = Column(String(50), nullable=True)
    # Valeurs : COMPRIS | PAS_PERTINENT | DESACTIVE | PAS_MAINTENANT


class TuteurDebriefing(Base):
    """Debriefings post-exercice — un par session (Hook 3)."""
    __tablename__ = "plugin_tuteur_debriefings"

    id                = Column(Integer, primary_key=True, index=True)
    session_id        = Column(Integer, ForeignKey("plugin_tuteur_sessions.id"),
                               unique=True, index=True)
    generated_at      = Column(DateTime, default=_utcnow)
    synthese          = Column(Text, nullable=True)
    points_forts      = Column(JSON, nullable=True)
    axes_amelioration = Column(JSON, nullable=True)
    recommandations   = Column(JSON, nullable=True)
    score_global      = Column(Integer, nullable=True)
    ia_provider       = Column(String(50), nullable=True)


class TuteurEquipe(Base):
    """Agrégation des observations à l'échelle équipe (Hook 4 — bonus jour 6)."""
    __tablename__ = "plugin_tuteur_equipes"

    id                = Column(Integer, primary_key=True, index=True)
    exercice_id       = Column(String(100), nullable=False, index=True)
    sessions_ids      = Column(JSON, nullable=True)
    timestamp_debut   = Column(DateTime, nullable=True)
    timestamp_fin     = Column(DateTime, nullable=True)
    bilan_equipe      = Column(JSON, nullable=True)
    coordination_kpis = Column(JSON, nullable=True)
