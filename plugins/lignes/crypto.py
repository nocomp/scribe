"""
plugins/lignes/crypto.py — Chiffrement au repos des secrets Twilio.
Même approche que plugins/bluefiles/crypto.py : Fernet dérivé de SCRIBE_SECRET,
repli propre en clair si la lib `cryptography` est absente. dec() rend la valeur
telle quelle si elle n'a pas le préfixe (compat ascendante).
"""
import os
import base64
import hashlib
import logging

logger = logging.getLogger("scribe.plugins.lignes.crypto")
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
    if not value:
        return ""
    f = _fernet()
    if not f:
        logger.warning("cryptography indisponible — secret Twilio stocke en clair")
        return value
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode()
    except Exception:
        return value


def dec(value: str) -> str:
    if not value or not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value or ""
    f = _fernet()
    if not f:
        return value
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return ""
