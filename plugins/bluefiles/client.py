"""
plugins/bluefiles/client.py — v3.5.0-alpha1
============================================
Wrapper de l'API Bluefiles, avec **mode DEV simulé** quand aucune clé n'est
configurée. Le code applicatif appelle la même interface dans les deux cas ;
seul le résultat change (vrai uuid + vrai lien vs uuid+lien factices).

⚠ La doc API exacte de Bluefiles n'est pas publique côté développeur SCRIBE
   (récup via portail client Forecomm). Le code LIVE ci-dessous est une
   ébauche raisonnable basée sur les patterns REST classiques. Il faudra
   ajuster les chemins / payloads à la doc réelle quand on aura un compte.
"""
import os
import secrets
import string
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import BinaryIO

logger = logging.getLogger("scribe.plugins.bluefiles")


# ── Configuration ────────────────────────────────────────────────────────────
# Deux sources, par ordre de priorité :
#   1. Base de données (table plugin_bluefiles_config) — éditable depuis l'admin
#   2. Variables d'environnement SCRIBE_BLUEFILES_* — fallback / valeurs par défaut
#
# Les valeurs env servent de défaut ET de repli si la table n'existe pas encore
# (premier démarrage, plugin notifications/DB non migrée, etc.).
_ENV_DEFAULTS = {
    "api_url":        os.getenv("SCRIBE_BLUEFILES_API_URL", "https://api.bluefiles.com/v1"),
    "api_key":        os.getenv("SCRIBE_BLUEFILES_API_KEY", ""),
    "account":        os.getenv("SCRIBE_BLUEFILES_ACCOUNT", ""),
    "webhook_secret": os.getenv("SCRIBE_BLUEFILES_WEBHOOK_SECRET", ""),
}


def get_config() -> dict:
    """Retourne la config effective {api_url, api_key, account, webhook_secret}.

    Lit la ligne singleton en DB ; pour chaque champ vide/None, retombe sur la
    variable d'environnement correspondante. N'échoue jamais : en cas de
    problème DB, retourne intégralement les valeurs env.
    """
    cfg = dict(_ENV_DEFAULTS)
    # Couche centrale (supervision) — comble si le domaine est activé. Le DB local
    # ci-dessous reste prioritaire → local > central > env.
    try:
        from app.central_config import get_domain as _cc_get
        cc = _cc_get("bluefiles")
        if cc and cc.get("enabled"):
            if (cc.get("api_key") or "").strip():  cfg["api_key"] = cc["api_key"].strip()
            if (cc.get("api_url") or "").strip():  cfg["api_url"] = cc["api_url"].strip()
            if (cc.get("account") or "").strip():  cfg["account"] = cc["account"].strip()
    except Exception:
        pass
    try:
        from app.database import SessionLocal
        from plugins.bluefiles.models import BluefilesConfig
        db = SessionLocal()
        try:
            row = db.query(BluefilesConfig).filter_by(id=1).first()
            if row:
                if (row.api_url or "").strip():        cfg["api_url"]        = row.api_url.strip()
                if (row.api_key or "").strip():        cfg["api_key"]        = row.api_key.strip()
                if (row.account or "").strip():        cfg["account"]        = row.account.strip()
                if (row.webhook_secret or "").strip(): cfg["webhook_secret"] = row.webhook_secret.strip()
        finally:
            db.close()
    except Exception:
        pass  # table absente / DB indisponible → on garde les valeurs env
    return cfg


def is_live_mode() -> bool:
    """True si une clé API réelle est configurée (DB ou env)."""
    c = get_config()
    return bool(c["api_key"] and c["api_url"] and c["account"])


def current_mode() -> str:
    return "live" if is_live_mode() else "dev"


# ── Génération de mot de passe destinataire ─────────────────────────────────
# Exclus : caractères ambigus à l'œil (0/O, l/1/I), à l'oral (8/B…).
_PWD_ALPHABET = ''.join(c for c in (string.ascii_letters + string.digits)
                       if c not in "0OoIl1B8")


def generate_recipient_password(length: int = 12) -> str:
    """Génère un MdP destinataire avec séparateurs lisibles : 'aB3X-7yK2-mP4n'."""
    raw = ''.join(secrets.choice(_PWD_ALPHABET) for _ in range(length))
    # Groupes de 4 séparés par tiret pour lisibilité
    return '-'.join(raw[i:i+4] for i in range(0, length, 4))


# ── Hashing utilitaire ──────────────────────────────────────────────────────
def hash_file_stream(stream: BinaryIO, chunk_size: int = 65536) -> tuple[str, int]:
    """Calcule SHA-256 + taille en lisant le stream sans le charger en mémoire.
    Le stream est consommé ; appelant doit faire seek(0) avant ré-utilisation.
    """
    h = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)
        total += len(chunk)
    return h.hexdigest(), total


# ── Client Bluefiles ────────────────────────────────────────────────────────
class BluefilesClient:
    """Client minimal pour l'API Bluefiles.

    Méthodes principales :
      - create_envoi(...)  : déclare un envoi côté Bluefiles, renvoie uuid+upload_url
      - upload_file(...)   : streame un fichier vers Bluefiles
      - finalize_envoi(...): déclare l'envoi complet et déclenche notification destinataires
      - get_status(uuid)   : récupère l'état d'un envoi
      - verify_webhook(...): vérifie la signature HMAC d'un callback

    En mode DEV : tout est simulé localement, aucun appel réseau.
    """

    def __init__(self):
        # Capture la config effective (DB → env) à l'instanciation. Chaque
        # nouvelle instance reflète donc la dernière config admin enregistrée,
        # sans redémarrage de l'instance SCRIBE.
        self.cfg  = get_config()
        self.live = bool(self.cfg["api_key"] and self.cfg["api_url"] and self.cfg["account"])
        if not self.live:
            logger.info("Bluefiles client en mode DEV (pas de clé API configurée)")

    # ── API publique côté plugin SCRIBE ─────────────────────────────────────

    def create_envoi(
        self,
        destinataires: list[dict],
        fichiers_meta: list[dict],
        expiration_days: int = 15,
        password_required: bool = True,
        ar_enabled: bool = True,
        commentaire: str = "",
    ) -> dict:
        """Crée un envoi côté Bluefiles. Retourne :
            {
              "uuid": "...",
              "short_link": "https://bluefiles.com/r/abc123",
              "expires_at": "2026-06-22T14:32:00Z",
              "destinataires": [
                {"email": "...", "password": "9k7-X2-mNp4", "mode_auth": "password"},
                ...
              ],
              "upload_url": "..."   # éventuellement utilisé par upload_file
            }
        """
        if self.live:
            return self._live_create_envoi(
                destinataires, fichiers_meta,
                expiration_days, password_required, ar_enabled, commentaire,
            )
        return self._dev_create_envoi(
            destinataires, fichiers_meta,
            expiration_days, password_required, ar_enabled, commentaire,
        )

    def upload_file(self, upload_url: str, file_stream: BinaryIO, filename: str) -> bool:
        """Upload un fichier (streaming). True si OK."""
        if self.live:
            return self._live_upload_file(upload_url, file_stream, filename)
        return self._dev_upload_file(upload_url, file_stream, filename)

    def finalize_envoi(self, uuid: str) -> bool:
        """Marque l'envoi comme complet, déclenche notifications destinataires."""
        if self.live:
            return self._live_finalize_envoi(uuid)
        return self._dev_finalize_envoi(uuid)

    def get_status(self, uuid: str) -> dict | None:
        if self.live:
            return self._live_get_status(uuid)
        return self._dev_get_status(uuid)

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Vérifie la signature HMAC-SHA256 d'un callback Bluefiles."""
        secret = (self.cfg.get("webhook_secret") or "")
        if not secret:
            # Pas de secret configuré → on accepte (mode permissif dev)
            return True
        import hmac
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    # ── Implémentation LIVE ─────────────────────────────────────────────────
    # ⚠ ÉBAUCHE : chemins et payloads à ajuster avec la doc officielle Bluefiles.

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "X-Account":     self.cfg["account"],
            "Accept":        "application/json",
        }

    def _live_create_envoi(self, destinataires, fichiers_meta,
                           expiration_days, password_required, ar_enabled,
                           commentaire):
        import httpx
        payload = {
            "recipients": [
                {"email": r["email"], "name": r.get("nom", "")}
                for r in destinataires
            ],
            "files": [
                {"name": f["nom"], "size": f["taille"], "mime": f.get("mime", "")}
                for f in fichiers_meta
            ],
            "expiration_days":  expiration_days,
            "require_password": password_required,
            "read_receipt":     ar_enabled,
            "comment":          commentaire,
        }
        try:
            with httpx.Client(timeout=30.0) as cli:
                r = cli.post(f"{self.cfg['api_url']}/envois",
                             json=payload, headers=self._headers())
                r.raise_for_status()
                data = r.json()
            # Le retour Bluefiles devrait fournir : uuid, short_link, expires_at,
            # destinataires (avec MdP si password_required).
            return data
        except httpx.HTTPError as e:
            logger.error(f"Bluefiles create_envoi failed: {e}")
            raise

    def _live_upload_file(self, upload_url, file_stream, filename):
        import httpx
        try:
            with httpx.Client(timeout=None) as cli:
                # Streaming upload : on ne charge pas le fichier en RAM
                r = cli.put(
                    upload_url,
                    content=_iter_chunks(file_stream),
                    headers={**self._headers(),
                             "Content-Disposition": f'attachment; filename="{filename}"'},
                )
                r.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Bluefiles upload_file failed: {e}")
            return False

    def _live_finalize_envoi(self, uuid):
        import httpx
        try:
            with httpx.Client(timeout=30.0) as cli:
                r = cli.post(f"{self.cfg['api_url']}/envois/{uuid}/finalize",
                             headers=self._headers())
                r.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Bluefiles finalize_envoi failed: {e}")
            return False

    def _live_get_status(self, uuid):
        import httpx
        try:
            with httpx.Client(timeout=15.0) as cli:
                r = cli.get(f"{self.cfg['api_url']}/envois/{uuid}",
                            headers=self._headers())
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as e:
            logger.error(f"Bluefiles get_status failed: {e}")
            return None

    # ── Implémentation DEV (simulation locale) ──────────────────────────────
    # Aucun appel réseau. Génère des UUIDs/liens factices et marque les envois
    # "delivered" instantanément.

    def _dev_create_envoi(self, destinataires, fichiers_meta,
                          expiration_days, password_required, ar_enabled,
                          commentaire):
        uuid = "dev-" + secrets.token_urlsafe(12)
        now = datetime.now(timezone.utc)
        return {
            "uuid":       uuid,
            "short_link": f"https://example.com/bluefiles-dev/{uuid}",
            "expires_at": (now + timedelta(days=expiration_days)).isoformat(),
            "destinataires": [
                {
                    "email":     r["email"],
                    "nom":       r.get("nom", ""),
                    "mode_auth": "password" if password_required else "open",
                    "password":  generate_recipient_password() if password_required else None,
                }
                for r in destinataires
            ],
            "upload_url": f"https://example.com/bluefiles-dev/{uuid}/upload",
            "mode": "dev",
        }

    def _dev_upload_file(self, upload_url, file_stream, filename):
        # Consomme le stream sans rien stocker (juste pour respecter l'interface)
        total = 0
        while True:
            chunk = file_stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
        logger.info(f"[DEV] upload simulé {filename} ({total} octets)")
        return True

    def _dev_finalize_envoi(self, uuid):
        logger.info(f"[DEV] envoi {uuid} finalisé (simulé)")
        return True

    def _dev_get_status(self, uuid):
        # En DEV, on retourne toujours "delivered" comme si tout marchait
        return {"uuid": uuid, "status": "delivered", "mode": "dev"}


def _iter_chunks(stream: BinaryIO, size: int = 65536):
    while True:
        chunk = stream.read(size)
        if not chunk:
            break
        yield chunk
