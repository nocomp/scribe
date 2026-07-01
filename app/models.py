"""
models.py — Tous les modèles SQLAlchemy — SCRIBE v5
Ajouts v5 : User, Notification, Task, RexEntry
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Hospital(Base):
    __tablename__ = "hospitals"
    id              = Column(Integer, primary_key=True, index=True)
    nom             = Column(String, unique=True, index=True)
    code_finess     = Column(String, unique=True, nullable=True)
    latitude        = Column(Float)
    longitude       = Column(Float)
    adresse         = Column(String, nullable=True)
    telephone_garde = Column(String, nullable=True)
    units = relationship("UniteFonctionnelle", back_populates="hospital", cascade="all, delete-orphan")

class UserOnlineStatus(Base):
    """Statut en ligne des utilisateurs — mis à jour par heartbeat toutes les 30s."""
    __tablename__ = "user_online_status"
    user_id    = Column(Integer, primary_key=True)
    username   = Column(String, nullable=False)
    last_seen  = Column(DateTime(timezone=True), nullable=False)
    # vert = vu < 2min, rouge = vu < 10min, gris = jamais/> 10min


class MainCouranteLog(Base):
    """Log exhaustif de tous les événements pour la main courante."""
    __tablename__ = "main_courante_logs"
    id         = Column(Integer, primary_key=True, index=True)
    timestamp  = Column(DateTime(timezone=True), server_default=func.now())
    auteur     = Column(String, nullable=False, default="Système")
    auteur_role= Column(String, nullable=True)
    categorie  = Column(String, nullable=False)  # INCIDENT, MESSAGE, TRANSFERT, KANBAN, NOTIFICATION, RELEVE, DECISION, CONNEXION
    action     = Column(String, nullable=False)   # verbe court: CRÉÉ, MODIFIÉ, RÉSOLU, ENVOYÉ, etc.
    detail     = Column(Text, nullable=True)      # description lisible
    ref_id     = Column(Integer, nullable=True)   # ID de l'entité liée (incident, message, etc.)
    ref_type   = Column(String, nullable=True)    # type de l'entité liée
    site       = Column(String, nullable=True)    # site concerné
    niveau     = Column(String, default="INFO")   # INFO, WARN, CRITIQUE


class UniteFonctionnelle(Base):
    __tablename__ = "unites_fonctionnelles"
    id          = Column(Integer, primary_key=True, index=True)
    code_uf     = Column(String, index=True)
    libelle     = Column(String)
    pole        = Column(String, nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    actif       = Column(Boolean, default=True)  # v2.4.7 : désactivation soft
    hospital    = relationship("Hospital", back_populates="units")

class SitrepEntry(Base):
    __tablename__ = "sitrep_entries"
    id        = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    declarant_nom       = Column(String, nullable=False)
    directeur_crise     = Column(String, nullable=True)
    site_id             = Column(String, nullable=False)
    unite_fonctionnelle = Column(String, nullable=True)
    type_crise          = Column(String, default="CYBER")
    urgency             = Column(Integer, default=1)
    fait                = Column(Text, nullable=False)
    analyse             = Column(Text, nullable=True)
    moyens_engages      = Column(Text, nullable=True)
    actions_remediation = Column(Text, nullable=True)
    intervenant_nom     = Column(String, nullable=True)
    intervenant_contact = Column(String, nullable=True)
    status              = Column(String, default="SIGNALÉ")
    completion_percent  = Column(Integer, default=0)
    estimated_resolution = Column(DateTime, nullable=True)
    resolved_at         = Column(DateTime, nullable=True)
    jalons              = Column(Text, nullable=True)
    albert_avis         = Column(Text, nullable=True)
    archived            = Column(Boolean, default=False)   # incident archivé (masqué vue principale)
    archived_at         = Column(DateTime, nullable=True)
    # v2182 : distingue les incidents à impact opérationnel (panne respirateur,
    # DPI down, locaux inaccessibles…) des événements cliniques (hémorragie,
    # urgence vitale…). Les premiers font basculer le panneau SOINS en mode
    # dégradé, les seconds restent visibles mais n'altèrent pas l'état du pôle.
    impact_fonctionnel  = Column(Boolean, default=False)
    # v3.4 (h34) — Visibilité côté personnel soignant.
    # Cochée par la cellule de crise lors de la création/modification de
    # l'incident pour les cas qui impactent l'activité soignante : panne DPI,
    # ascenseur HS, panne d'équipement médical, indisponibilité d'un service.
    # Permet au rôle `soignant` de voir ces incidents (par défaut il ne voit
    # que ceux qui sont liés à ses missions/tâches assignées).
    visible_soignant    = Column(Boolean, default=False, nullable=False)
    impact_global       = Column(Boolean, default=False, nullable=False)  # h96 — impact transversal (tous services de soins)
    attachments = relationship("Attachment", back_populates="entry", cascade="all, delete-orphan")
    tasks       = relationship("Task", back_populates="incident", cascade="all, delete-orphan")

class Decision(Base):
    __tablename__ = "decisions"
    id                 = Column(Integer, primary_key=True, index=True)
    timestamp          = Column(DateTime(timezone=True), server_default=func.now())
    contenu            = Column(Text, nullable=False)
    responsable        = Column(String, nullable=True)
    base_reglementaire = Column(String, default="Plan Blanc")
    statut_validation  = Column(String, default="VALIDÉ")

class Presence(Base):
    __tablename__ = "presences"
    id        = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    nom       = Column(String, nullable=False)
    role      = Column(String, nullable=True)
    action    = Column(String, nullable=False)

class Consigne(Base):
    __tablename__ = "consignes"
    id        = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    pour      = Column(String, nullable=False)
    texte     = Column(Text, nullable=False)
    accuse    = Column(Boolean, default=False)
    accuse_at = Column(DateTime, nullable=True)
    accuse_par = Column(String, nullable=True)  # prénom de la personne qui a accusé réception

class Attachment(Base):
    __tablename__ = "attachments"
    id        = Column(Integer, primary_key=True, index=True)
    filename  = Column(String)
    file_path = Column(String)
    entry_id  = Column(Integer, ForeignKey("sitrep_entries.id"))
    entry     = relationship("SitrepEntry", back_populates="attachments")

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String, unique=True, index=True, nullable=False)
    display_name  = Column(String, nullable=False)
    # v3.4 (h34) — Système de rôles RGPD-compliant.
    # Valeurs autorisées :
    #   admin         : accès intégral + gestion des comptes/rôles
    #   cellule_crise : directeur de crise, RSSI, qualité — voit tout sauf
    #                   le flux nominatif soignant (brancardage/transferts internes)
    #   soignant      : agent de brancardage, IDE coordo transferts —
    #                   ne voit que brancardage/transferts patient + incidents
    #                   marqués visible_soignant ou liés à ses missions
    # Anciens rôles préservés en lecture (migration auto au démarrage) :
    #   directeur, observateur → migrés en cellule_crise
    role          = Column(String, default="cellule_crise")
    hashed_password = Column(String, nullable=False)
    perimetre             = Column(String, nullable=True)
    # v3000h41 — Coordonnées de contact pour les notifications sortantes.
    # email     : utilisé par le backend mail (SMTP) du plugin notifications
    # telephone : numéro E.164 (+33...) utilisé par le backend SMS
    # Ces champs sont OPTIONNELS. Quand ils sont renseignés depuis l'admin,
    # une souscription notifications (mail/sms) est créée/mise à jour
    # automatiquement pour l'utilisateur (voir auth._sync_contact_subscriptions).
    # RGPD : données de contact professionnel, jamais nominatif patient.
    email                 = Column(String, nullable=True)
    telephone             = Column(String, nullable=True)
    must_change_password  = Column(Boolean, default=False)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    active                = Column(Boolean, default=True)
    # v2315 — MFA TOTP (activable depuis l'admin ou par l'utilisateur lui-même).
    # mfa_enabled : MFA actif sur ce compte → login exigera un code TOTP
    # mfa_secret  : clé partagée base32 (32 chars), générée à l'activation
    # mfa_backup_codes : JSON array de codes à usage unique (si token perdu)
    mfa_enabled       = Column(Boolean, default=False)
    mfa_secret        = Column(String,  nullable=True)
    mfa_backup_codes  = Column(Text,    nullable=True)  # JSON list
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class Notification(Base):
    __tablename__ = "notifications"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp   = Column(DateTime(timezone=True), server_default=func.now())
    titre       = Column(String, nullable=False)
    message     = Column(Text, nullable=False)
    type_notif  = Column(String, default="INCIDENT")  # INCIDENT | TACHE | SYSTEME
    incident_id = Column(Integer, ForeignKey("sitrep_entries.id"), nullable=True)
    task_id     = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    lu          = Column(Boolean, default=False)
    user        = relationship("User", back_populates="notifications")

class Task(Base):
    __tablename__ = "tasks"
    id          = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("sitrep_entries.id"), nullable=True)
    titre       = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    assignee    = Column(String, nullable=True)
    priorite    = Column(Integer, default=2)  # 1=basse 2=normale 3=haute 4=critique
    colonne     = Column(String, default="BACKLOG")  # BACKLOG | EN_COURS | EN_ATTENTE | TERMINÉ
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    due_at      = Column(DateTime, nullable=True)
    incident    = relationship("SitrepEntry", back_populates="tasks")

class ServiceStatus(Base):
    """Statut manuel des services transverses (sécurité physique, logistique…)."""
    __tablename__ = "service_status"
    id         = Column(Integer, primary_key=True, index=True)
    service_id = Column(String, unique=True, index=True, nullable=False)  # ex: "securite_physique"
    libelle    = Column(String, nullable=False)                            # ex: "Sécurité physique"
    statut     = Column(String, default="OK")                             # OK | DEGRADE | CRITIQUE
    commentaire= Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RexEntry(Base):
    __tablename__ = "rex_entries"
    id              = Column(Integer, primary_key=True, index=True)
    incident_id     = Column(Integer, ForeignKey("sitrep_entries.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    titre           = Column(String, nullable=False)
    type_crise      = Column(String, nullable=True)
    duree_minutes   = Column(Integer, nullable=True)
    nb_poles        = Column(Integer, default=0)
    nb_decisions    = Column(Integer, default=0)
    nb_jalons_total = Column(Integer, default=0)
    nb_jalons_done  = Column(Integer, default=0)
    mttd_minutes    = Column(Integer, nullable=True)
    mttr_minutes    = Column(Integer, nullable=True)
    points_positifs = Column(Text, nullable=True)
    points_amelio   = Column(Text, nullable=True)
    actions_futures = Column(Text, nullable=True)
    lecons          = Column(Text, nullable=True)
    redacteur       = Column(String, nullable=True)


# ══════════════════════════════════════════════════════════════
#  SCRIBE v1.3.0 — Gestion capacitaire des lits
# ══════════════════════════════════════════════════════════════

class CapaciteReferentiel(Base):
    """Capacité nominale d'une unité — données fixes, saisies par la direction des soins."""
    __tablename__ = "capacite_referentiel"
    id              = Column(Integer, primary_key=True, index=True)
    service_nom     = Column(String, nullable=False, index=True)
    uf_code         = Column(String, nullable=True)
    pole            = Column(String, nullable=True)
    site            = Column(String, nullable=True)       # Valmont / Saint-Julien / Plainville / USLD
    capacite_totale = Column(Integer, default=0)          # capacité nominale totale
    tension_1       = Column(Integer, default=0)          # lits ouverts en tension niveau 1
    tension_2       = Column(Integer, default=0)          # lits ouverts en tension niveau 2
    accept_homme    = Column(Boolean, default=True)       # accepte patients H
    accept_femme    = Column(Boolean, default=True)       # accepte patients F
    accept_indiffer = Column(Boolean, default=True)       # chambre indifférente
    telephone_cadre = Column(String, nullable=True)
    ordre_affichage = Column(Integer, default=99)
    actif           = Column(Boolean, default=True)
    declarations    = relationship("CapaciteDeclaration", back_populates="referentiel",
                                   cascade="all, delete-orphan")


class CapaciteDeclaration(Base):
    """Déclaration capacitaire d'un cadre — conservée pour historique et REX."""
    __tablename__ = "capacite_declarations"
    id              = Column(Integer, primary_key=True, index=True)
    referentiel_id  = Column(Integer, ForeignKey("capacite_referentiel.id"), nullable=False)
    referentiel     = relationship("CapaciteReferentiel", back_populates="declarations")
    horodatage      = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    redacteur       = Column(String, nullable=False)       # prénom+nom du cadre déclarant
    point           = Column(String, default="matin")      # matin | aprem | soir
    # Disponibilité lits par genre
    lits_vides_h    = Column(Integer, default=0)           # lits disponibles hommes
    lits_vides_f    = Column(Integer, default=0)           # lits disponibles femmes
    lits_vides_i    = Column(Integer, default=0)           # lits disponibles indifférent
    # Tensions
    tension_activee = Column(Integer, default=0)           # 0=non / 1=tension1 / 2=tension2
    lits_sup        = Column(Integer, default=0)           # lits supplémentaires
    # Statuts globaux (menus déroulants)
    statut_lits     = Column(String, default="normal")     # normal|tension|critique|ferme
    statut_rh       = Column(String, default="complet")    # complet|tension|critique|insuffisant
    statut_materiel = Column(String, default="ok")         # ok|degrade|critique|hs
    # Alertes déclarées par le cadre
    alerte_lits     = Column(Boolean, default=False)
    alerte_rh       = Column(Boolean, default=False)
    alerte_materiel = Column(Boolean, default=False)
    # Textes libres
    commentaire_lits     = Column(Text, nullable=True)
    commentaire_rh       = Column(Text, nullable=True)
    commentaire_materiel = Column(Text, nullable=True)
    commentaire_general  = Column(Text, nullable=True)
    # Mode dégradé et RH souplesse (v1.5.0)
    mode_degrade    = Column(Boolean, default=False)       # procédures dégradées activées
    besoin_renfort  = Column(Integer, default=0)           # nb personnes manquantes
    peut_preter     = Column(Integer, default=0)           # nb personnes disponibles à prêter
    # Lien incident créé automatiquement si alerte
    incident_id     = Column(Integer, ForeignKey("sitrep_entries.id"), nullable=True)


# ══════════════════════════════════════════════════════════════
#  SCRIBE v1.4.0 — Nouvelles tables
# ══════════════════════════════════════════════════════════════

class CapaciteMedicotech(Base):
    """Capacité médico-technique : blocs, dialyse, pharmacie."""
    __tablename__ = "capacite_medicotech"
    id                         = Column(Integer, primary_key=True, index=True)
    site_id                    = Column(String, nullable=False, index=True)
    blocs_total                = Column(Integer, default=0)
    blocs_operationnels        = Column(Integer, default=0)
    blocs_commentaire          = Column(Text, nullable=True)
    dialyse_postes_total       = Column(Integer, default=0)
    dialyse_postes_actifs      = Column(Integer, default=0)
    dialyse_sessions_24h       = Column(Integer, default=0)
    dialyse_commentaire        = Column(Text, nullable=True)
    pharmacie_statut           = Column(String, default="normal")  # normal|degrade|arret
    pharmacie_urgences_vitales = Column(Boolean, default=True)
    pharmacie_commentaire      = Column(Text, nullable=True)
    updated_by                 = Column(String, nullable=True)
    updated_at                 = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IASession(Base):
    """Session de chat IA contextuel sur une analyse."""
    __tablename__ = "ia_sessions"
    id              = Column(Integer, primary_key=True, index=True)
    incident_id     = Column(Integer, ForeignKey("sitrep_entries.id"), nullable=True)
    statut_genere   = Column(Text, nullable=True)
    historique_chat = Column(Text, default="[]")  # JSON array de messages
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TransfertPatient(Base):
    """Transfert de patient inter-services / inter-établissements."""
    __tablename__ = "transferts_patients"
    id                    = Column(Integer, primary_key=True, index=True)
    # Données patient (HDS — ne remontent JAMAIS dans le collecteur)
    nom                   = Column(String, nullable=True)       # chiffré côté client idéalement
    prenom                = Column(String, nullable=True)
    nom_jeune_fille       = Column(String, nullable=True)
    ipp                   = Column(String, nullable=True)
    date_naissance        = Column(String, nullable=True)       # stocké en string YYYY-MM-DD
    # Flux
    unite_origine         = Column(String, nullable=False)
    etablissement_origine = Column(String, nullable=False)
    unite_destination     = Column(String, nullable=False)
    etablissement_destination = Column(String, nullable=False)
    site_destination        = Column(String, nullable=True)  # Nom du site exact (pour carte)
    # Statut
    statut                = Column(String, default="EN_PREPARATION")  # EN_PREPARATION|EN_COURS|ARRIVE|ANNULE
    horodatage_creation   = Column(DateTime(timezone=True), server_default=func.now())
    horodatage_depart     = Column(DateTime, nullable=True)
    horodatage_arrivee    = Column(DateTime, nullable=True)
    eta                   = Column(String, nullable=True)   # heure d'arrivée estimée (ISO string)
    # Métadonnées
    redacteur             = Column(String, nullable=False)
    commentaire           = Column(Text, nullable=True)
    # v2.4.6 : historique des changements de statut (liste JSON-encoded de
    # {"ts": "ISO-UTC", "from": "EN_PREPARATION", "to": "EN_COURS", "user": "..."})
    historique_json       = Column(Text, nullable=True, default="[]")


class MessageInterne(Base):
    """Messagerie interne entre comptes SCRIBE."""
    __tablename__ = "messages_internes"
    id               = Column(Integer, primary_key=True, index=True)
    expediteur_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    # v2307-hotfix — Champs ajoutés pour supporter les messages externes
    # (broadcast-externe depuis ARS/CERT/SAMU/collecteur exercice).
    # Avant : le code plugins/messagerie/api.py instanciait MessageInterne
    # avec ces kwargs mais ils étaient ignorés silencieusement (SQLAlchemy
    # erreur silencieuse → messages perdus). Avec les colonnes explicites,
    # les messages sont correctement stockés et affichés dans l'inbox.
    expediteur_nom   = Column(String, nullable=True)     # nom affiché (ex: "ARS", "CERT Santé")
    destinataire_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    destinataire_nom = Column(String, nullable=True)
    sujet            = Column(String, nullable=True)
    contenu          = Column(Text, nullable=False)
    lu               = Column(Boolean, default=False)
    lu_at            = Column(DateTime, nullable=True)
    reply_to         = Column(Integer, nullable=True)   # id du message parent (thread)
    ght_source       = Column(String, nullable=True)    # sigle GHT émetteur (inter-GHT)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class DeclarationSituation(Base):
    """Déclaration de situation visible par le collecteur inter-GHT."""
    __tablename__ = "declarations_situation"
    id              = Column(Integer, primary_key=True, index=True)
    site_id         = Column(String, nullable=False)
    unite_fonct     = Column(String, nullable=True)
    type_crise      = Column(String, nullable=False)   # sanitaire|cyber|tension_capacitaire|plan_blanc
    niveau_tension  = Column(Integer, default=1)        # 1=vigilance 2=tension 3=crise
    description     = Column(Text, nullable=True)
    actif           = Column(Boolean, default=True)
    created_by      = Column(String, nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DemandeInterGHT(Base):
    """Demande de transfert ou de capacité vers un autre GHT, routée via le collecteur."""
    __tablename__ = "demandes_interght"
    id                 = Column(Integer, primary_key=True, index=True)
    type_situation     = Column(String, nullable=False)   # sanitaire|cyber|transfert|ressources
    unite_concernee    = Column(String, nullable=True)
    description        = Column(Text, nullable=False)
    ght_emetteur       = Column(String, nullable=False)
    ght_destinataire   = Column(String, nullable=True)
    statut             = Column(String, default="en_attente")  # en_attente|transmis|recu|traite
    reponse            = Column(Text, nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    updated_at         = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# ── Plugin system (v2.0.4) ───────────────────────────────────────────────────
from core.plugin_state_model import PluginState  # noqa — crée la table plugin_states


class IncidentMailSub(Base):
    """h76 — Abonnement d'un utilisateur aux notifications mail d'un incident
    (changements d'état / évolution). L'email est résolu depuis User.email à
    l'envoi, donc on ne stocke pas l'adresse ici."""
    __tablename__ = "incident_mail_subs"
    id          = Column(Integer, primary_key=True)
    incident_id = Column(Integer, nullable=False, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("incident_id", "user_id", name="uq_inc_mail_sub"),)


# ── h79 — Chaîne d'alerte / annuaire de mobilisation (Phase A) ───────────────
# Données personnelles → strictement locales à l'instance (HDS/RGPD),
# jamais remontées au collecteur.

class ContactMobilisation(Base):
    """Personne mobilisable (importée depuis l'Excel établissement)."""
    __tablename__ = "contacts_mobilisation"
    id         = Column(Integer, primary_key=True)
    cle        = Column(String, index=True)
    nom        = Column(String)
    prenom     = Column(String)
    tel1       = Column(String)
    tel2       = Column(String)
    email      = Column(String)
    fonction   = Column(String)
    service    = Column(String)
    uf         = Column(String, index=True)
    grade      = Column(String)
    pole       = Column(String, index=True)
    site       = Column(String, index=True)
    perimetre_abonnement = Column(String, default="uf")    # uf|pole|site|etablissement|aucun
    priorite             = Column(Integer, default=3)       # 1 = alerté en premier … 4
    actif      = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AlerteMobilisation(Base):
    """Un déclenchement de chaîne d'alerte (campagne de mobilisation)."""
    __tablename__ = "alertes_mobilisation"
    id          = Column(Integer, primary_key=True)
    titre       = Column(String)
    message     = Column(Text)
    criteres    = Column(Text, default="{}")   # JSON: {uf:[],pole:[],site:[],fonction:[]}
    incident_id = Column(Integer, nullable=True)
    cree_par    = Column(String)
    archived    = Column(Integer, default=0)   # h82 — campagne archivée (terminée)
    vague_courante = Column(Integer, default=0)  # h93 — 0 = à plat ; sinon priorité de la vague en cours
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AlerteCible(Base):
    """Destinataire d'une alerte + sa réponse ETA (via formulaire tokenisé)."""
    __tablename__ = "alerte_cibles"
    id           = Column(Integer, primary_key=True)
    alerte_id    = Column(Integer, ForeignKey("alertes_mobilisation.id"), index=True)
    contact_id   = Column(Integer, nullable=True)
    nom          = Column(String)
    fonction     = Column(String)
    site         = Column(String)
    tel          = Column(String)
    email        = Column(String)
    token        = Column(String, unique=True, index=True)
    canaux       = Column(String)                 # "sms,mail"
    statut       = Column(String, default="envoye")     # envoye / repondu
    eta_choice   = Column(String, nullable=True)        # 15 / 30 / 60 / indispo
    commentaire  = Column(Text, nullable=True)          # h82 — note libre du répondant
    responded_at = Column(DateTime, nullable=True)
    vague        = Column(Integer, default=0)            # h93 — = priorité du contact (groupe de vague)
    livraison    = Column(String, default="")            # h94 — "" / ok / echec (remise SMS+mail)


class MobPreset(Base):
    """h95 — Pré-réglage de ciblage réutilisable (ex. « Plan blanc », « Rappel bloc »)."""
    __tablename__ = "mob_presets"
    id         = Column(Integer, primary_key=True)
    nom        = Column(String, index=True)
    criteres   = Column(Text, default="{}")   # JSON: {uf:[],pole:[],site:[],fonction:[],contact_ids:[]}
    canaux     = Column(String, default="sms,mail")
    escalade   = Column(Integer, default=0)
    cree_par   = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
