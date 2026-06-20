"""SCRIBE — Magasin de configuration centrale (côté collecteur / supervision).

La supervision détient un jeu de réglages partagés (IA, Bluefiles, SMTP, SMS)
que les instances TIRENT (pull) via leur token de nœud. Les instances appliquent
ces valeurs en « comble-trou » : local explicite > central > env.

- Stockage : fichier JSON à côté de collecteur.py.
- Secrets chiffrés au repos (Fernet, clé dérivée de SCRIBE_SECRET) si la lib
  `cryptography` est dispo ; sinon stockés en clair + fichier en 0600 + warning.
- Jamais renvoyés masqués à une instance (elle en a besoin) ; toujours masqués
  vers l'UI admin.
"""
import os, json, base64, hashlib, logging
from pathlib import Path

logger = logging.getLogger("scribe.collecteur.central")

_STORE_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / "collecteur_central_config.json"

# Domaines + champs secrets (chiffrés au repos, masqués en UI)
DOMAINS = ("ia", "bluefiles", "smtp", "sms")

_DEFAULT = {
    "ia":        {"provider": "albert", "api_key": "", "base_url": "", "model": "", "enabled": False},
    "bluefiles": {"api_key": "", "api_url": "", "account": "", "mode": "LIVE", "enabled": False},
    "smtp":      {"smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "",
                  "from_addr": "", "use_tls": True, "use_ssl": False, "enabled": False},
    "sms":       {"provider": "ovh", "sender": "SCRIBE", "api_key": "", "api_secret": "",
                  "base_url": "", "enabled": False},
    "_meta":     {"updated_at": "", "updated_by": ""},
}

_ENC_PREFIX = "enc:"

# Champs secrets (chiffrés au repos, masqués en UI)
SECRET_FIELDS = {
    "ia":        ["api_key"],
    "bluefiles": ["api_key"],
    "smtp":      ["smtp_pass"],
    "sms":       ["api_key", "api_secret"],
}


# ── Chiffrement (Fernet si dispo) ────────────────────────────────────────────
def _fernet():
    try:
        from cryptography.fernet import Fernet
        secret = os.getenv("SCRIBE_SECRET") or os.getenv("ADMIN_TOKEN") or "scribe-default-key"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)
    except Exception:
        return None


def _enc(value: str) -> str:
    if not value:
        return ""
    f = _fernet()
    if not f:
        return value  # pas de chiffrement dispo → clair (fichier 0600)
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode()
    except Exception:
        return value


def _dec(value: str) -> str:
    if not value or not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value or ""
    f = _fernet()
    if not f:
        return value
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return ""


# ── Lecture / écriture ───────────────────────────────────────────────────────
def _read_file() -> dict:
    if not _STORE_PATH.exists():
        return json.loads(json.dumps(_DEFAULT))
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(_DEFAULT))
    # compléter les domaines manquants
    base = json.loads(json.dumps(_DEFAULT))
    for d in DOMAINS:
        if isinstance(data.get(d), dict):
            base[d].update(data[d])
    if isinstance(data.get("_meta"), dict):
        base["_meta"].update(data["_meta"])
    return base


def load_clear() -> dict:
    """Config complète, secrets DÉCHIFFRÉS en clair (usage interne / instance)."""
    data = _read_file()
    for d in DOMAINS:
        for fld in SECRET_FIELDS.get(d, []):
            data[d][fld] = _dec(data[d].get(fld, ""))
    return data


def save(domain: str, fields: dict, updated_by: str = "supervision") -> dict:
    """Met à jour un domaine. Pour un champ secret reçu VIDE → on conserve l'ancien
    (l'UI envoie vide quand l'opérateur ne change pas la clé)."""
    if domain not in DOMAINS:
        raise ValueError("domaine inconnu")
    from datetime import datetime, timezone
    data = _read_file()  # secrets encore chiffrés
    cur = data[domain]
    secret_flds = SECRET_FIELDS.get(domain, [])
    for k, v in (fields or {}).items():
        if k in secret_flds:
            if v:  # nouvelle valeur → chiffrer ; vide → conserver l'existant
                cur[k] = _enc(v)
        else:
            cur[k] = v
    data["_meta"] = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": updated_by}
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(_STORE_PATH, 0o600)
    except Exception:
        pass
    return masked()


def masked() -> dict:
    """Vue UI admin : secrets jamais révélés (booléen has_xxx, valeur vidée)."""
    data = load_clear()
    out = json.loads(json.dumps(_DEFAULT))
    for d in DOMAINS:
        out[d].update(data[d])
        for fld in SECRET_FIELDS.get(d, []):
            has = bool((out[d].get(fld) or "").strip())
            out[d][fld] = ""           # jamais renvoyé en clair à l'UI
            out[d]["has_" + fld] = has  # l'UI affiche « configuré »
    out["_meta"] = data.get("_meta", {})
    return out


def for_instance() -> dict:
    """Vue servie à une instance authentifiée : secrets EN CLAIR, domaines activés
    uniquement (les autres renvoyés désactivés, sans secret)."""
    data = load_clear()
    out = {}
    for d in DOMAINS:
        dom = dict(data[d])
        if not dom.get("enabled"):
            for fld in SECRET_FIELDS.get(d, []):
                dom[fld] = ""
        out[d] = dom
    return out
