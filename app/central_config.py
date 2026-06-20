"""SCRIBE — Client de configuration centrale (côté instance).

L'instance TIRE périodiquement la config partagée depuis le collecteur
(supervision), via son token de nœud, et la met en cache local. Les résolveurs
(IA, Bluefiles, plus tard SMTP/SMS) consultent ce cache en couche « comble-trou » :
    local explicite > central (ce module) > env > vide

Résilience : si le collecteur est injoignable, on garde le dernier cache connu.
La config centrale n'est JAMAIS une dépendance dure (plateforme de crise).

N.B. : on lit collecteur_url + token DIRECTEMENT dans le XML (SCRIBE_CONFIG_FILE)
et on n'importe PAS app.api.federation (qui plante à l'import isolé).
"""
import os, json, time, threading, logging
import xml.etree.ElementTree as ET
import urllib.request

logger = logging.getLogger("scribe.central")

_CACHE_PATH = os.environ.get("SCRIBE_CENTRAL_CACHE", "central_config_cache.json")
_data = None
_lock = threading.Lock()
_started = False


def _read_federation():
    """(collecteur_url, token) depuis le XML d'instance, sinon ('','')."""
    path = os.environ.get("SCRIBE_CONFIG_FILE", "config.xml")
    try:
        root = ET.parse(path).getroot()
        fed = root.find("federation")
        if fed is None:
            return "", ""
        return (fed.findtext("collecteur_url") or "").strip(), (fed.findtext("token") or "").strip()
    except Exception:
        return "", ""


def _load_cache():
    global _data
    if _data is not None:
        return _data
    try:
        _data = json.loads(open(_CACHE_PATH, encoding="utf-8").read())
    except Exception:
        _data = {}
    return _data


def get_domain(domain: str) -> dict:
    """Config centrale (cache) pour un domaine : 'ia' | 'bluefiles' | 'smtp' | 'sms'."""
    _ensure_started()
    d = _load_cache()
    val = d.get(domain) if isinstance(d, dict) else None
    return val if isinstance(val, dict) else {}


def pull_now(timeout: float = 8.0) -> bool:
    url, tok = _read_federation()
    if not url or not tok:
        return False
    base = url.replace("/api/push", "").rstrip("/")
    endpoint = base + "/api/central-config"
    try:
        req = urllib.request.Request(endpoint, headers={"Authorization": "Bearer " + tok})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        cfg = body.get("config") or {}
        with _lock:
            tmp = _CACHE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(cfg, ensure_ascii=False))
            os.replace(tmp, _CACHE_PATH)
            globals()["_data"] = cfg
        logger.info("[central] config tirée depuis %s", endpoint)
        return True
    except Exception as e:
        logger.warning("[central] pull KO (%s) — cache local conservé : %s", endpoint, e)
        return False


def _ensure_started(interval: int = 600):
    """Démarre (une seule fois) le thread de pull périodique. Idempotent."""
    global _started
    if _started:
        return
    _started = True

    def _loop():
        time.sleep(5)  # laisser l'app finir de démarrer
        while True:
            try:
                pull_now()
            except Exception:
                pass
            time.sleep(interval)

    try:
        threading.Thread(target=_loop, daemon=True, name="central-config-pull").start()
    except Exception:
        pass
