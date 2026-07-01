"""
plugins/exercice/models.py — Modèles SQLAlchemy pour le plugin Exercice
Base séparée de app.database.Base pour isolation totale.
Préfixe tables : plugin_exo_*
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class ExoScenario(Base):
    """Scénario de crise stocké localement (JSON + métadonnées)."""
    __tablename__ = "plugin_exo_scenarios"

    id           = Column(Integer, primary_key=True, index=True)
    scenario_id  = Column(String(100), unique=True, index=True)  # ex: "exo_gyneco_2026"
    titre        = Column(String(200), nullable=False)
    description  = Column(Text, nullable=True)
    duree_min    = Column(Integer, default=60)       # durée exercice en minutes
    duree_reel_min = Column(Integer, default=240)    # durée incident réel simulé
    ratio_compression = Column(Float, default=4.0)   # reel/exercice
    nb_sites     = Column(Integer, default=1)
    complexite   = Column(String(20), default="MOYEN")  # FACILE|MOYEN|DIFFICILE|EXPERT
    type_crise   = Column(String(30), default="SANITAIRE")
    sujet        = Column(Text, nullable=True)        # description libre du sujet
    contenu_json = Column(Text, nullable=False)       # JSON complet du scénario
    genere_par_ia = Column(Boolean, default=False)
    prompt_ia    = Column(Text, nullable=True)        # prompt utilisé si IA
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by   = Column(String(100), nullable=True)
    archive      = Column(Boolean, default=False)


class ExoSession(Base):
    """Session d'exercice en cours ou terminée."""
    __tablename__ = "plugin_exo_sessions"

    id              = Column(Integer, primary_key=True, index=True)
    session_uid     = Column(String(50), unique=True, index=True)  # UUID court
    scenario_id     = Column(String(100), nullable=False)
    scenario_titre  = Column(String(200), nullable=False)
    status          = Column(String(20), default="PRET")  # PRET|EN_COURS|PAUSE|TERMINE|ARCHIVE
    started_at      = Column(DateTime, nullable=True)
    paused_at       = Column(DateTime, nullable=True)
    stopped_at      = Column(DateTime, nullable=True)
    t_elapsed_s     = Column(Integer, default=0)   # secondes écoulées dans le scénario
    ratio_compression = Column(Float, default=4.0)
<<<<<<< HEAD
    sites_actifs    = Column(Text, nullable=True)  # JSON: ["CHV","GHT1",...]
=======
    sites_actifs    = Column(Text, nullable=True)  # JSON: ["CHAG","GHTLMB",...]
>>>>>>> 42014cc0f1f987ee0564de52890336b067151060
    animateur       = Column(String(100), nullable=True)
    notes_animateur = Column(Text, nullable=True)
    bilan_ia        = Column(Text, nullable=True)  # JSON bilan post-exercice
    bilan_at        = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    archive         = Column(Boolean, default=False)
    archive_at      = Column(DateTime, nullable=True)
    archive_zip     = Column(String(200), nullable=True)  # chemin du ZIP d'archive


class ExoInjection(Base):
    """Log de chaque stimulus injecté pendant l'exercice."""
    __tablename__ = "plugin_exo_injections"

    id             = Column(Integer, primary_key=True, index=True)
    session_uid    = Column(String(50), index=True)
    stimulus_id    = Column(String(20), nullable=False)   # ex: "S01"
    stimulus_type  = Column(String(30), nullable=False)   # incident|message|transfert|capacite|chat
    cible_sigle    = Column(String(30), nullable=False)   # instance cible
    cible_port     = Column(Integer, nullable=False)
    t_min_prevu    = Column(Float, nullable=False)        # timing prévu dans le scénario
    injected_at    = Column(DateTime, nullable=True)      # horodatage réel injection
    success        = Column(Boolean, default=True)
    response_code  = Column(Integer, nullable=True)
    response_body  = Column(Text, nullable=True)
    manuel         = Column(Boolean, default=False)       # injection manuelle par animateur


class ExoJoueur(Base):
    """Joueur participant à l'exercice (compte utilisateur SCRIBE + rôle exercice)."""
    __tablename__ = "plugin_exo_joueurs"

    id           = Column(Integer, primary_key=True, index=True)
    session_uid  = Column(String(50), index=True)
    username     = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
<<<<<<< HEAD
    role_exercice = Column(String(100), nullable=False)   # ex: "Directeur de crise CHV"
=======
    role_exercice = Column(String(100), nullable=False)   # ex: "Directeur de crise CHAG"
>>>>>>> 42014cc0f1f987ee0564de52890336b067151060
    sigle_site   = Column(String(30), nullable=False)     # instance assignée
    port_site    = Column(Integer, nullable=False)
    password_tmp = Column(String(100), nullable=True)     # mot de passe temporaire exercice
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ExoActionLog(Base):
    """Log de toutes les actions des joueurs pendant l'exercice (pour bilan IA)."""
    __tablename__ = "plugin_exo_action_logs"

    id            = Column(Integer, primary_key=True, index=True)
    session_uid   = Column(String(50), index=True)
    t_exercice_s  = Column(Integer, nullable=False)  # secondes depuis début exercice
    sigle_site    = Column(String(30), nullable=False)
    username      = Column(String(100), nullable=True)
    action_type   = Column(String(50), nullable=False)   # INCIDENT_CREE|INCIDENT_RESOLU|DECISION|TRANSFERT|MESSAGE|JALON
    action_detail = Column(Text, nullable=True)          # description lisible
    ref_id        = Column(Integer, nullable=True)       # ID de l'entité liée
    logged_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    stimulus_id   = Column(String(20), nullable=True)    # stimulus associé si réponse à une injection
