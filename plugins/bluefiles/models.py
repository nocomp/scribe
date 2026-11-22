"""
plugins/bluefiles/models.py — v3.5.0-alpha1
============================================
Modèle d'audit local Bluefiles : QUI a envoyé QUOI à QUI, QUAND.

Principe RGPD/HDS strict :
  - JAMAIS de contenu de fichier en DB SCRIBE
  - JAMAIS de mot de passe destinataire (généré, affiché 1×, jeté)
  - Métadonnées légères uniquement : noms, tailles, MIME, hash SHA-256
  - Le hash permet de prouver "j'ai bien envoyé CE fichier-là" sans
    pouvoir le reconstituer.

Le contenu chiffré vit exclusivement chez Bluefiles (HDS, expiration 15j max).
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Index
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class BluefilesConfig(Base):
    """Configuration runtime du connecteur Bluefiles — éditable depuis l'admin.

    Singleton (une seule ligne, id=1). Remplace la configuration par variables
    d'environnement : si une ligne existe et que ses champs sont renseignés,
    elle a PRIORITÉ sur les env vars SCRIBE_BLUEFILES_*. Sinon, fallback env.

    Sécurité : la clé API et le secret webhook sont stockés en clair en DB
    locale (même base SQLite que le reste de SCRIBE, protégée au niveau OS).
    Ils ne sont JAMAIS renvoyés en clair par l'API admin (masqués), seulement
    un aperçu (4 derniers caractères) et un booléen "configuré".
    """
    __tablename__ = "plugin_bluefiles_config"

    id              = Column(Integer, primary_key=True)  # toujours 1
    api_url         = Column(String(300), nullable=True)
    api_key         = Column(String(300), nullable=True)
    account         = Column(String(200), nullable=True)
    webhook_secret  = Column(String(300), nullable=True)
    # v3000h135 — Champs de l'utilitaire CLI BlueFiles (BlueFilesTransfer).
    # C'est la voie réelle d'envoi. login/password obligatoires ; server par
    # défaut api.bluefiles.com ; impersonate facultatif (email émetteur rattaché).
    cli_login       = Column(String(200), nullable=True)
    cli_password    = Column(String(300), nullable=True)
    cli_server      = Column(String(200), nullable=True)
    cli_impersonate = Column(String(200), nullable=True)
    # Métadonnées d'audit
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    updated_by      = Column(String(120), nullable=True)


class BluefilesEnvoi(Base):
    """Trace d'un envoi sécurisé Bluefiles depuis SCRIBE."""
    __tablename__ = "plugin_bluefiles_envois"

    id              = Column(Integer, primary_key=True, index=True)

    # Identifiant côté Bluefiles (UUID retourné par l'API) — null en mode DEV
    bf_uuid         = Column(String(64), nullable=True, index=True)

    # Mode : "live" (vrai envoi Bluefiles) | "dev" (simulé, pas d'appel réseau)
    mode            = Column(String(8), default="dev", nullable=False)

    # ── Rattachement métier ──────────────────────────────────────────────────
    # On stocke un couple (module, ref_id) pour permettre l'affichage des
    # envois liés dans la fiche métier sans table de jointure dédiée.
    module_origine  = Column(String(20), nullable=False)   # "transfert" | "communique" | "cellule" | "rex"
    ref_id          = Column(Integer,    nullable=True, index=True)
    # Snapshot de l'objet métier (numéro de transfert, sujet du communiqué…)
    # pour rester lisible même si l'objet métier est supprimé plus tard.
    ref_label       = Column(String(200), nullable=True)

    # ── Auteur SCRIBE ────────────────────────────────────────────────────────
    auteur_id       = Column(Integer, nullable=True, index=True)
    auteur_nom      = Column(String(200), nullable=True)
    auteur_role     = Column(String(50),  nullable=True)

    # ── Destinataires ────────────────────────────────────────────────────────
    # Format : [{"email": "...", "nom": "?", "mode_auth": "password|account",
    #            "statut": "pending|delivered|read|expired|error",
    #            "delivered_at": "...", "read_at": "..."}]
    destinataires   = Column(JSON, nullable=False, default=list)

    # ── Fichiers (méta seulement) ────────────────────────────────────────────
    # Format : [{"nom": "dossier.pdf", "taille": 1234567,
    #            "mime": "application/pdf", "sha256": "abc...def"}]
    fichiers_meta   = Column(JSON, nullable=False, default=list)
    fichiers_total_size = Column(Integer, default=0)

    # ── Politique ────────────────────────────────────────────────────────────
    expiration_days = Column(Integer, default=15)
    password_required = Column(Integer, default=1)        # 0/1 (SQLite-friendly)
    ar_enabled      = Column(Integer, default=1)
    commentaire     = Column(Text, nullable=True)

    # ── Statut global de l'envoi ─────────────────────────────────────────────
    # pending → uploaded → delivered → read → expired
    # ou        → error
    statut          = Column(String(20), default="pending", nullable=False, index=True)
    short_link      = Column(String(200), nullable=True)   # lien court Bluefiles

    # ── Horodatages (UTC) ────────────────────────────────────────────────────
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    uploaded_at     = Column(DateTime, nullable=True)
    delivered_at    = Column(DateTime, nullable=True)
    expires_at      = Column(DateTime, nullable=True)
    error_msg       = Column(Text, nullable=True)

    # ── Log brut des webhooks reçus ──────────────────────────────────────────
    # Append-only ; sert d'audit chronologique des événements Bluefiles.
    webhook_events  = Column(JSON, default=list)

    __table_args__ = (
        Index("ix_bf_module_ref", "module_origine", "ref_id"),
        Index("ix_bf_auteur_created", "auteur_id", "created_at"),
    )

    def to_dict(self, include_meta: bool = True) -> dict:
        """Sérialisation pour les routes API."""
        d = {
            "id":             self.id,
            "bf_uuid":        self.bf_uuid,
            "mode":           self.mode,
            "module_origine": self.module_origine,
            "ref_id":         self.ref_id,
            "ref_label":      self.ref_label,
            "auteur_id":      self.auteur_id,
            "auteur_nom":     self.auteur_nom,
            "destinataires":  self.destinataires or [],
            "statut":         self.statut,
            "short_link":     self.short_link,
            "expiration_days": self.expiration_days,
            "password_required": bool(self.password_required),
            "ar_enabled":     bool(self.ar_enabled),
            "commentaire":    self.commentaire,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "uploaded_at":    self.uploaded_at.isoformat() if self.uploaded_at else None,
            "delivered_at":   self.delivered_at.isoformat() if self.delivered_at else None,
            "expires_at":     self.expires_at.isoformat() if self.expires_at else None,
            "error_msg":      self.error_msg,
        }
        if include_meta:
            d["fichiers_meta"] = self.fichiers_meta or []
            d["fichiers_total_size"] = self.fichiers_total_size or 0
        return d
