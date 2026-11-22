"""
plugins/lignes/config_store.py — Configuration Twilio du plugin `lignes`.

Deux sources, avec PRÉCÉDENCE « comble-trou » identique au reste de SCRIBE :
    config LOCALE du plugin (éditable comme BlueFiles)  >  config CENTRALE
    (supervision, domaine "twilio", redescendue aux instances synchronisées)  >  vide

La config locale est persistée en JSON sous SCRIBE_DATA_DIR (stable entre builds
si défini), fichier 0600, secret (auth_token) chiffré au repos via crypto.enc.
"""
import os
import json
import pathlib
import threading

from plugins.lignes import crypto

_lock = threading.Lock()
_cache = None

# Champs de configuration (auth_token = secret chiffré au repos)
FIELDS = ("account_sid", "auth_token", "voice", "public_base_url", "enabled")
SECRET_FIELDS = ("auth_token",)

_DEFAULT = {
    "account_sid":     "",
    "auth_token":      "",      # chiffré au repos (enc::...)
    "voice":           "Polly.Lea",   # voix Twilio par défaut (FR)
    "public_base_url": "",      # URL publique atteignable par Twilio (TwiML)
    "enabled":         False,
}


def _path() -> pathlib.Path:
    base = os.environ.get("SCRIBE_DATA_DIR")
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = pathlib.Path(base)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p / "plugin_lignes_config.json"


def _read_local() -> dict:
    global _cache
    if _cache is not None:
        return dict(_cache)
    data = dict(_DEFAULT)
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update({k: raw.get(k, data[k]) for k in _DEFAULT})
    except Exception:
        pass
    _cache = data
    return dict(data)


def _central() -> dict:
    """Domaine 'twilio' de la config centrale (cache instance), ou {}."""
    try:
        from app.central_config import get_domain
        d = get_domain("twilio")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_local(fields: dict) -> dict:
    """Met à jour la config LOCALE. Secret vide reçu → on conserve l'ancien."""
    global _cache
    with _lock:
        cur = _read_local()
        for k in _DEFAULT:
            if k not in (fields or {}):
                continue
            v = fields[k]
            if k in SECRET_FIELDS:
                if v:                       # nouvelle valeur → chiffrer
                    cur[k] = crypto.enc(v)
            else:
                cur[k] = v
        p = _path()
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
        _cache = cur
    return masked()


def resolved() -> dict:
    """Config EFFECTIVE en clair (locale > centrale). Usage interne uniquement."""
    local = _read_local()
    central = _central()
    out = {}
    for k in _DEFAULT:
        lv = local.get(k, "")
        if k in SECRET_FIELDS:
            lv = crypto.dec(lv)
        if k == "enabled":
            out[k] = bool(lv or central.get(k))
            continue
        out[k] = lv if (lv not in ("", None)) else central.get(k, _DEFAULT[k])
    out["_source"] = "local" if any(_read_local().get(k) for k in ("account_sid", "auth_token")) else ("central" if central.get("account_sid") else "none")
    return out


def masked() -> dict:
    """Vue UI : secret jamais renvoyé, booléen has_auth_token + indication source."""
    local = _read_local()
    central = _central()
    out = {}
    for k in _DEFAULT:
        if k in SECRET_FIELDS:
            out[k] = ""
            out["has_" + k] = bool((crypto.dec(local.get(k, "")) or central.get(k) or "").strip())
        else:
            out[k] = local.get(k) if local.get(k) not in ("", None) else central.get(k, _DEFAULT[k])
    out["central_enabled"] = bool(central.get("enabled"))
    out["central_present"] = bool(central.get("account_sid"))
    return out


def is_configured() -> bool:
    r = resolved()
    return bool(r.get("account_sid") and r.get("auth_token"))
