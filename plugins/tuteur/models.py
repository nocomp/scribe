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


# v3.0.0 — Coach proactif : messages générés par les règles côté serveur,
# présentés dans le widget flottant côté joueur. Anti-spam : une règle qui
# touche la même cible (incident_id, decision_id, etc.) n'émet pas plus d'1
# message par fenêtre de re-déclenchement (~10 min). Les messages "ack"
# (acknowledgés) ne sont plus re-affichés.
class TuteurCoachMessage(Base):
    """Messages du coach proactif (widget flottant)."""
    __tablename__ = "plugin_tuteur_coach_messages"

    id                = Column(Integer, primary_key=True, index=True)
    session_id        = Column(Integer, ForeignKey("plugin_tuteur_sessions.id"),
                               index=True, nullable=True)
    # Code de la règle déclenchante (ex: "incident_sans_action", "stagnation")
    rule_id           = Column(String(50), nullable=False, index=True)
    # Priorité : 1 (faible) à 3 (critique). Affichage trié par priorité décroissante.
    priorite          = Column(Integer, default=2, nullable=False)
    # Type d'affichage : info | warning | critique
    type_msg          = Column(String(20), default="info")
    # v3.1.0 — Niveau d'intrusion : silent | marker | alert
    # silent : visible seulement en historique, pas de badge
    # marker : badge sur la bulle, pas de son
    # alert  : pulse rouge + bip court (cas exceptionnels)
    niveau            = Column(String(10), default="marker", nullable=False)
    # Message court affiché dans le widget
    message           = Column(Text, nullable=False)
    # Actions suggérées (boutons) — liste de {label, action_type, payload}
    # action_type ∈ {generate_tasks, open_tab, ask_ai, dismiss}
    actions_json      = Column(JSON, nullable=True)
    # Cible (ex: incident.id, decision.id) — pour anti-spam et navigation
    target_type       = Column(String(50), nullable=True)
    target_id         = Column(Integer, nullable=True)
    created_at        = Column(DateTime, default=_utcnow, index=True)
    # Acknowledgé par le joueur (dismiss) → reste visible dans l'historique
    # mais grisé. Permet de retrouver un message déjà traité.
    ack_at            = Column(DateTime, nullable=True)
    # Snooze : ne pas réafficher avant cette date (ex: "Pas maintenant" = +10 min)
    snooze_until      = Column(DateTime, nullable=True)


class TuteurSynthese(Base):
    """v3.1.0 — Synthèses stratégiques générées par l'IA (boucle lente).

    Chaque appel /coach/situation (manuel ou auto) produit une ligne ici.
    Permet le replay en debriefing avec toutes les synthèses du parcours.
    """
    __tablename__ = "plugin_tuteur_syntheses"

    id           = Column(Integer, primary_key=True, index=True)
    session_id   = Column(Integer, ForeignKey("plugin_tuteur_sessions.id"),
                          index=True, nullable=True)
    created_at   = Column(DateTime, default=_utcnow, index=True)
    # Source : "ia" (Albert, OpenAI…) ou "local" (fallback heuristique)
    source       = Column(String(20), default="local")
    ai_provider  = Column(String(40), nullable=True)
    # Mode de déclenchement : "manual" (clic bouton) ou "auto" (boucle 5min)
    trigger      = Column(String(20), default="manual")
    # Contenu structuré (situation, court_terme, moyen_terme, long_terme, priorites)
    payload      = Column(JSON, nullable=False)
    # Compteurs au moment de la synthèse (pour comparer dans le temps)
    nb_incidents_actifs = Column(Integer, default=0)
    nb_decisions        = Column(Integer, default=0)
    duree_min           = Column(Integer, default=0)
