"""
plugins/fichiers/models.py — SCRIBE
====================================
Modèles SQLAlchemy du plugin `fichiers` (drive interne).

RÈGLE ABSOLUE : Base partagée — ``from app.database import Base`` (jamais
``declarative_base()`` local, sinon ``NoReferencedTableError`` sur la FK
``users.id``).

Tables préfixées ``plugin_fichiers_*``. La DB ne contient que des
MÉTADONNÉES — jamais le contenu binaire (cf. storage.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
)

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FichierBlob(Base):
    """Contenu adressé par empreinte (dédupliqué). Le binaire vit sur disque."""
    __tablename__ = "plugin_fichiers_blobs"

    id             = Column(Integer, primary_key=True, index=True)
    checksum       = Column(String(64), unique=True, index=True, nullable=False)
    taille         = Column(Integer, default=0)
    mime           = Column(String(160), default="application/octet-stream")
    chemin_stockage = Column(String(300), default="")
    chiffre        = Column(Boolean, default=False)
    created_at     = Column(DateTime, default=_now)


class Dossier(Base):
    __tablename__ = "plugin_fichiers_dossiers"

    id            = Column(Integer, primary_key=True, index=True)
    nom           = Column(String(255), nullable=False)
    parent_id     = Column(Integer, ForeignKey("plugin_fichiers_dossiers.id"), nullable=True)
    proprietaire_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    # perso | corbeille (l'institutionnel viendra en v2)
    type          = Column(String(20), default="perso")
    etablissement = Column(String(60), nullable=True)
    created_at    = Column(DateTime, default=_now)


class Fichier(Base):
    __tablename__ = "plugin_fichiers_fichiers"

    id            = Column(Integer, primary_key=True, index=True)
    nom           = Column(String(255), nullable=False)
    dossier_id    = Column(Integer, ForeignKey("plugin_fichiers_dossiers.id"), nullable=True)
    proprietaire_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    blob_id       = Column(Integer, ForeignKey("plugin_fichiers_blobs.id"), nullable=False)
    tags          = Column(String(400), default="")
    favori        = Column(Boolean, default=False)
    # Choix à l'upload : un fichier ÉPHÉMÈRE s'auto-détruit après son premier
    # téléchargement via un lien de partage. Un fichier PERMANENT (défaut) reste
    # dans le drive ; partager un lien éphémère ne le supprime pas.
    ephemere      = Column(Boolean, default=False)
    # Sécurité (case à cocher à l'upload, cochée par défaut) : si True, le
    # fichier ne peut être téléchargé QUE par un destinataire authentifié figurant
    # dans le partage (lien /d/ avec contrôle d'accès). Empêche un lien recopié de
    # « se promener » (navigation privée / tiers → refus).
    download_restreint = Column(Boolean, default=True)
    # Garde-fou HDS/RGPD : un fichier marqué patient est exclu de tout
    # partage inter-établissement / push supervision (contrôle serveur).
    contient_donnees_patient = Column(Boolean, default=False)
    supprime      = Column(Boolean, default=False)   # corbeille (suppression douce)
    supprime_at   = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=_now)
    updated_at    = Column(DateTime, default=_now, onupdate=_now)


class Partage(Base):
    """Partage interne à jeton. ``ephemere=True`` → le fichier est consommé et
    effacé après le PREMIER téléchargement réussi."""
    __tablename__ = "plugin_fichiers_partages"

    id            = Column(Integer, primary_key=True, index=True)
    fichier_id    = Column(Integer, ForeignKey("plugin_fichiers_fichiers.id"), nullable=True)
    dossier_id    = Column(Integer, ForeignKey("plugin_fichiers_dossiers.id"), nullable=True)
    jeton         = Column(String(64), unique=True, index=True, nullable=False)
    # user | role | lien (lien éphémère à jeton)
    cible_type    = Column(String(20), default="lien")
    cible_valeur  = Column(String(120), default="")
    droit         = Column(String(20), default="lecture")   # lecture | ecriture
    ephemere      = Column(Boolean, default=False)
    # Sécurité : si restreint, le téléchargement (/d/{jeton}) exige une session
    # authentifiée ET que l'utilisateur connecté figure dans destinataires_uids.
    restreint     = Column(Boolean, default=False)
    destinataires_uids = Column(String(600), default="")  # CSV d'ids users locaux
    # Envoi externe sécurisé : le pli est protégé par un mot de passe à usage
    # unique, envoyé au destinataire par SMS (canal séparé du lien). Le serveur
    # ne stocke QUE le hash bcrypt du mot de passe — jamais le mot de passe clair.
    protege       = Column(Boolean, default=False)
    mdp_hash      = Column(String(120), default="")
    tentatives    = Column(Integer, default=0)             # anti-brute-force
    contact_externe = Column(String(60), default="")       # tél. masqué (affichage/audit)
    telecharge    = Column(Boolean, default=False)
    telecharge_at = Column(DateTime, nullable=True)
    expire_at     = Column(DateTime, nullable=True)
    created_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime, default=_now)


class JournalFichier(Base):
    """Piste d'audit immuable — jamais le contenu, seulement des métadonnées."""
    __tablename__ = "plugin_fichiers_journal"

    id            = Column(Integer, primary_key=True, index=True)
    action        = Column(String(40))   # upload|download|partage|suppression|purge|ephemere
    fichier_id    = Column(Integer, nullable=True)
    acteur        = Column(String(120))
    acteur_role   = Column(String(40))
    etablissement = Column(String(60), nullable=True)
    horodatage    = Column(DateTime, default=_now)
    details       = Column(Text, default="")


class PartageRangement(Base):
    """Rangement d'un partage REÇU dans un dossier d'organisation du destinataire.

    « Partagé avec moi » : chaque destinataire peut classer les partages qu'il a
    reçus dans ses propres dossiers (Dossier type='partage_recu'), indépendamment
    des autres destinataires. Un rangement absent = le partage est à la racine de
    « Partagé avec moi ». Supprimer le dossier supprime les rangements (les
    partages reviennent à la racine), jamais les fichiers.
    """
    __tablename__ = "plugin_fichiers_partage_rangement"

    id         = Column(Integer, primary_key=True, index=True)
    partage_id = Column(Integer, ForeignKey("plugin_fichiers_partages.id"), index=True, nullable=False)
    uid        = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)  # destinataire
    dossier_id = Column(Integer, ForeignKey("plugin_fichiers_dossiers.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=_now)
