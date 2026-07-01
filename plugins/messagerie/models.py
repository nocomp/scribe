"""
plugins/messagerie/models.py — v3.6.0-alpha1 (Phase 1)
========================================================
Refonte complète de la messagerie SCRIBE :
  - Table `messages` unifiée pour les 3 canaux (interne | mail | sms)
  - Table `messagerie_folders` pour les dossiers personnels
  - Table `messagerie_attachments` pour les PJ (locales + Bluefiles)

Phase 1 : seul le canal "interne" est activé fonctionnellement.
L'architecture est prête pour les canaux mail et sms (Phase 3).

Migration automatique au boot :
  Si la table `messages` est vide et que `messages_internes` (legacy)
  contient des données, recopie automatique avec canal="interne".
  Idempotent : ne migre qu'une seule fois.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, Boolean, JSON, Index
)
from datetime import datetime, timezone

# v3.6.0-alpha4 — IMPORTANT : utiliser la Base partagée de app.database
# pour que les FK vers `users` puissent se résoudre (cross-Base FK
# = NoReferencedTableError). C'est la même Base que app/models.py.
from app.database import Base


# ── Table principale : Message ──────────────────────────────────────────────
class Message(Base):
    """Message unifié (interne / mail / sms).

    Pour la Phase 1, seul `canal="interne"` est créé.
    Les colonnes mail/sms (Cc, Cci, backend_meta) restent vides mais existent
    pour ne pas devoir migrer le schéma en Phase 3.
    """
    __tablename__ = "messagerie_messages"

    id              = Column(Integer, primary_key=True, index=True)

    # Canal : "interne" (v1) | "mail" (v3) | "sms" (v3)
    canal           = Column(String(10), nullable=False, default="interne", index=True)
    # Direction : "in" (reçu par moi) | "out" (envoyé par moi)
    direction       = Column(String(3),  nullable=False, default="in", index=True)

    # ── Expéditeur ───────────────────────────────────────────────────────────
    expediteur_id   = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Snapshot d'affichage si user supprimé OU expéditeur externe ("ARS", "CERT...")
    expediteur_nom  = Column(String(200), nullable=True)
    # Pour mail/sms : adresse complète ("j@chu.fr" ou "+33612...")
    expediteur_addr = Column(String(200), nullable=True)

    # ── Destinataires (JSON, multi-destinataires possibles) ─────────────────
    # Format : [
    #   {"type": "user",  "value": 42,           "display": "Dr Dupont (cellule)"},
    #   {"type": "email", "value": "j@chu.fr",   "display": "j@chu.fr"},
    #   {"type": "phone", "value": "+33612...",  "display": "+33 6 12 ..."}
    # ]
    destinataires    = Column(JSON, nullable=False, default=list)
    destinataires_cc = Column(JSON, nullable=False, default=list)   # mail Cc (Phase 3)
    destinataires_bcc = Column(JSON, nullable=False, default=list)  # mail Cci (Phase 3)

    # ── Contenu ──────────────────────────────────────────────────────────────
    sujet           = Column(String(500), nullable=True)
    contenu         = Column(Text,        nullable=False, default="")
    # Format : "plain" (v1) | "html" (v3+)
    contenu_format  = Column(String(8), default="plain")
    # Si l'user a caviardé son propre msg : contenu = "[REDACTED]" + flag
    contenu_redacted = Column(Boolean, default=False)

    # ── Threading ────────────────────────────────────────────────────────────
    reply_to_id     = Column(Integer, nullable=True, index=True)  # message parent direct
    thread_id       = Column(String(40), nullable=False, default="", index=True)
    # Threading mail externe (RFC 5322) — pour préserver les threads chez les
    # destinataires Outlook/Gmail lorsqu'on enverra en mode mail (Phase 3).
    rfc_message_id  = Column(String(200), nullable=True)
    rfc_in_reply_to = Column(String(200), nullable=True)

    # ── Organisation ─────────────────────────────────────────────────────────
    # Dossier personnel où l'user a classé le message. NULL = pas classé
    # (visible dans les dossiers virtuels Inbox/Envoyés selon direction).
    folder_id       = Column(Integer, ForeignKey("messagerie_folders.id"), nullable=True, index=True)
    # Flags utilisateur
    flag_important  = Column(Boolean, default=False, index=True)

    # ── Statut d'envoi ───────────────────────────────────────────────────────
    # "draft" (brouillon) | "sent" (envoyé OK) | "failed" (échec) | "received" (reçu)
    statut          = Column(String(10), default="received", nullable=False, index=True)
    # Erreur en cas de "failed"
    error_msg       = Column(Text, nullable=True)

    # ── Lecture ──────────────────────────────────────────────────────────────
    lu              = Column(Boolean, default=False, index=True)
    lu_at           = Column(DateTime, nullable=True)

    # ── Pièces jointes (compteur dénormalisé pour affichage rapide) ─────────
    attachments_count = Column(Integer, default=0)

    # ── Méta backend (Phase 3 : id Twilio, AR mail, etc.) ────────────────────
    backend_meta    = Column(JSON, default=dict)

    # ── Horodatages ──────────────────────────────────────────────────────────
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at         = Column(DateTime, nullable=True)
    # Soft delete (corbeille). Le message reste en DB mais n'apparaît plus
    # qu'en consultant la corbeille.
    deleted_at      = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_msg_canal_direction",    "canal", "direction"),
        Index("ix_msg_expediteur_canal",   "expediteur_id", "canal"),
        Index("ix_msg_thread",             "thread_id"),
        Index("ix_msg_folder_lu",          "folder_id", "lu"),
    )

    def to_dict(self, with_attachments: bool = False) -> dict:
        d = {
            "id":              self.id,
            "canal":           self.canal,
            "direction":       self.direction,
            "expediteur_id":   self.expediteur_id,
            "expediteur_nom":  self.expediteur_nom,
            "expediteur_addr": self.expediteur_addr,
            "expediteur_sigle": self.expediteur_addr or "",  # sigle de l'étab expéditeur (inter-GHT)
            "destinataires":   self.destinataires or [],
            "destinataires_cc":  self.destinataires_cc or [],
            "destinataires_bcc": self.destinataires_bcc or [],
            "sujet":           self.sujet or "",
            "contenu":         self.contenu if not self.contenu_redacted else "[CONTENU SUPPRIMÉ]",
            "contenu_format":  self.contenu_format,
            "contenu_redacted": bool(self.contenu_redacted),
            "reply_to_id":     self.reply_to_id,
            "thread_id":       self.thread_id,
            "folder_id":       self.folder_id,
            "flag_important":  bool(self.flag_important),
            "statut":          self.statut,
            "lu":              bool(self.lu),
            "lu_at":           self.lu_at.isoformat() if self.lu_at else None,
            "attachments_count": self.attachments_count or 0,
            "backend_meta":    self.backend_meta or {},
            "created_at":      self.created_at.isoformat() if self.created_at else None,
            "sent_at":         self.sent_at.isoformat() if self.sent_at else None,
            "deleted_at":      self.deleted_at.isoformat() if self.deleted_at else None,
            "error_msg":       self.error_msg,
        }
        return d


# ── Dossiers personnels ─────────────────────────────────────────────────────
class Folder(Base):
    """Dossier personnel créé par un utilisateur.

    Les dossiers standards (Inbox, Envoyés, Brouillons, Corbeille, Important)
    sont VIRTUELS et calculés depuis le champ `direction`/`statut`/`flag_important`/
    `deleted_at`. Seuls les dossiers utilisateurs sont stockés ici.
    """
    __tablename__ = "messagerie_folders"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Canal où vit le dossier ("interne" | "mail" | "sms" | "all")
    canal       = Column(String(10), nullable=False, default="interne")
    nom         = Column(String(100), nullable=False)
    parent_id   = Column(Integer, ForeignKey("messagerie_folders.id"), nullable=True)
    ordre       = Column(Integer, default=0)
    color_hex   = Column(String(7), nullable=True)        # ex: "#003189"
    icon        = Column(String(8), nullable=True)        # ex: "📁" ou "🏥"
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_folder_user_canal", "user_id", "canal"),
    )

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "user_id":    self.user_id,
            "canal":      self.canal,
            "nom":        self.nom,
            "parent_id":  self.parent_id,
            "ordre":      self.ordre or 0,
            "color_hex":  self.color_hex,
            "icon":       self.icon or "📁",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Pièces jointes ──────────────────────────────────────────────────────────
class MessageAttachment(Base):
    """Pièce jointe d'un message.

    Deux modes :
      - "local"     : fichier stocké dans ./uploads/messages/<msg_id>/<filename>
      - "bluefiles" : référence vers un envoi du plugin Bluefiles (audit + lien)
    """
    __tablename__ = "messagerie_attachments"

    id          = Column(Integer, primary_key=True, index=True)
    message_id  = Column(Integer, ForeignKey("messagerie_messages.id", ondelete="CASCADE"),
                         nullable=False, index=True)

    kind        = Column(String(10), nullable=False, default="local")   # "local" | "bluefiles"
    nom         = Column(String(255), nullable=False)
    taille      = Column(Integer, default=0)
    mime        = Column(String(100), nullable=True)
    sha256      = Column(String(64), nullable=True)

    # Si kind="local"
    storage_path = Column(String(500), nullable=True)

    # Si kind="bluefiles"
    bluefiles_envoi_id    = Column(Integer, nullable=True)  # FK applicative vers BluefilesEnvoi
    bluefiles_short_link  = Column(String(300), nullable=True)
    bluefiles_uuid        = Column(String(64),  nullable=True)

    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "message_id":  self.message_id,
            "kind":        self.kind,
            "nom":         self.nom,
            "taille":      self.taille or 0,
            "mime":        self.mime,
            "sha256":      self.sha256,
            # Le storage_path n'est PAS exposé (info interne serveur)
            "has_storage": bool(self.storage_path),
            "bluefiles_short_link": self.bluefiles_short_link,
            "bluefiles_uuid":       self.bluefiles_uuid,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }


# ── Migration depuis l'ancien MessageInterne ────────────────────────────────
def migrate_from_legacy(db_session) -> int:
    """Migre les MessageInterne existants vers la nouvelle table messages.

    Idempotent : ne migre que si la nouvelle table est vide.
    Retourne le nombre de messages migrés (0 si déjà migré).
    """
    import logging
    log = logging.getLogger("scribe.plugins.messagerie.migrate")

    # 1. La nouvelle table contient-elle déjà des données ?
    existing = db_session.query(Message).count()
    if existing > 0:
        return 0

    # 2. Récup de tous les anciens messages
    try:
        from app.models import MessageInterne, User
    except ImportError:
        log.warning("Modèle MessageInterne introuvable — migration skip")
        return 0

    legacy_rows = db_session.query(MessageInterne).all()
    if not legacy_rows:
        log.info("Aucun MessageInterne à migrer")
        return 0

    # 3. Copie
    import uuid
    migrated = 0
    for legacy in legacy_rows:
        # Récupérer le display name destinataire pour le snapshot
        dest_display = legacy.destinataire_nom or ""
        if legacy.destinataire_id and not dest_display:
            try:
                u = db_session.query(User).filter(User.id == legacy.destinataire_id).first()
                if u:
                    dest_display = u.display_name or u.username
            except Exception:
                pass

        dest_list = []
        if legacy.destinataire_id:
            dest_list.append({
                "type":    "user",
                "value":   legacy.destinataire_id,
                "display": dest_display,
            })
        elif legacy.destinataire_nom:
            dest_list.append({
                "type":    "external",
                "value":   legacy.destinataire_nom,
                "display": legacy.destinataire_nom,
            })

        # Direction = "in" si je suis destinataire, "out" si je suis expéditeur.
        # En réalité l'ancien modèle ne distinguait pas explicitement — un
        # message est soit reçu soit envoyé selon le user qui le lit. Pour la
        # migration : si expediteur_id != null → direction="out" pour l'auteur,
        # mais le destinataire le verra en "in".
        # Stratégie de migration : on crée UNE ligne par message, direction
        # déterminée par convention (direction du point de vue de l'expéditeur).
        # Le rendu des listes utilisera : "tous les msg où je suis dans destinataires.value"
        # pour Inbox, "tous les msg où expediteur_id = moi" pour Envoyés.
        direction = "out"  # convention : on stocke du point de vue de l'expéditeur
        statut    = "received" if not legacy.expediteur_id else "sent"

        # thread_id : si reply_to existe, hériter du thread parent ; sinon nouveau
        thread_id = ""
        if legacy.reply_to:
            try:
                parent = db_session.query(Message).filter(Message.id == legacy.reply_to).first()
                if parent and parent.thread_id:
                    thread_id = parent.thread_id
            except Exception:
                pass
        if not thread_id:
            thread_id = uuid.uuid4().hex

        new_msg = Message(
            canal           = "interne",
            direction       = direction,
            expediteur_id   = legacy.expediteur_id,
            expediteur_nom  = legacy.expediteur_nom,
            destinataires   = dest_list,
            sujet           = legacy.sujet,
            contenu         = legacy.contenu or "",
            contenu_format  = "plain",
            reply_to_id     = legacy.reply_to,
            thread_id       = thread_id,
            statut          = statut,
            lu              = bool(legacy.lu),
            lu_at           = legacy.lu_at,
            created_at      = legacy.created_at or datetime.now(timezone.utc),
            sent_at         = legacy.created_at,
        )
        db_session.add(new_msg)
        migrated += 1

    db_session.commit()
    log.info(f"Migration messagerie OK : {migrated} messages copiés vers messagerie_messages")
    return migrated
