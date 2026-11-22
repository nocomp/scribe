"""
plugins/bluefiles/crypto.py — SCRIBE
=====================================
Chiffrement au repos des secrets BlueFiles (mot de passe API), avec la même
approche que collecteur/central_config_store : Fernet, clé dérivée de
SCRIBE_SECRET. Repli propre si la lib `cryptography` est absente (valeur en
clair + protection au niveau fichier/DB OS) — jamais d'échec bloquant.

Compatibilité ascendante : dec() rend la valeur telle quelle si elle n'a pas le
préfixe de chiffrement (anciennes lignes stockées en clair avant h136).
"""
import os
import base64
import hashlib
import logging

logger = logging.getLogger("scribe.plugins.bluefiles.crypto")
_ENC_PREFIX = "enc::"


def _fernet():
    try:
        from cryptography.fernet import Fernet
        secret = (os.getenv("SCRIBE_SECRET") or os.getenv("SECRET_KEY")
                  or os.getenv("ADMIN_TOKEN") or "scribe-default-key")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)
    except Exception:
        return None


def enc(value: str) -> str:
    """Chiffre une valeur (préfixée). Repli sur le clair si pas de lib crypto."""
    if not value:
        return ""
    f = _fernet()
    if not f:
        logger.warning("cryptography indisponible — secret BlueFiles stocké en clair")
        return value
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode()
    except Exception:
        return value


def dec(value: str) -> str:
    """Déchiffre si préfixé ; sinon rend la valeur telle quelle (clair legacy)."""
    if not value or not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value or ""
    f = _fernet()
    if not f:
        return ""
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return ""


def is_encrypted(value: str) -> bool:
    return bool(value) and isinstance(value, str) and value.startswith(_ENC_PREFIX)
