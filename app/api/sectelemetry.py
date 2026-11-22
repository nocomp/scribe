"""Télémétrie sécurité — version de test (OBSERVE ONLY, ne bloque rien).

Capte chaque requête, classe les suspectes (scanners/bots), agrège des
indicateurs en mémoire (borné) pour un tableau de bord visuel. Aucune donnée
patient. Aucun blocage à ce stade — pure observation.
"""
import re
import time
import threading
from collections import deque, defaultdict

_LOCK = threading.Lock()
_MAX_EVENTS = 800          # anneau d'événements récents
_MAX_IPS = 2000            # borne du dico par IP (anti-croissance)
_started_at = time.time()

_events = deque(maxlen=_MAX_EVENTS)
_by_ip = {}                # ip → {"total","suspect","last","reasons":set}
_by_path = defaultdict(int)     # chemin suspect → count
_by_reason = defaultdict(int)   # raison → count
_by_status = defaultdict(int)   # code HTTP → count
_hourly = {}               # "YYYY-MM-DDTHH" → {"total","suspect"}
_totals = {"total": 0, "suspect": 0}

# ── Résolution IP derrière proxy ─────────────────────────────────────────────
import os
_TRUSTED = set(
    p.strip() for p in os.getenv("SCRIBE_TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if p.strip()
)

def client_ip(request) -> str:
    """IP client réelle. X-Forwarded-For n'est cru QUE si le pair direct est un
    proxy de confiance ; on retire les proxies de confiance par la droite."""
    peer = getattr(getattr(request, "client", None), "host", "") or "?"
    if peer in _TRUSTED:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            while hops and hops[-1] in _TRUSTED:
                hops.pop()
            if hops:
                return hops[-1]
    return peer

# ── Classification ───────────────────────────────────────────────────────────
# Chemins typiques de scan/exploitation (SCRIBE n'a ni PHP, ni wp, ni .env exposé)
_SUSPECT_PATH = re.compile(
    r"(?i)(wp-admin|wp-login|xmlrpc\.php|/wp-content|/wordpress|phpmyadmin|/pma/|"
    r"\.env\b|/\.git|/\.aws|/\.ssh|/\.svn|\.php\b|/vendor/|/cgi-bin|/boaform|"
    r"/actuator|/solr|/manager/html|/remote/|/owa/|/autodiscover|/telescope|"
    r"/_ignition|/console|/shell|/eval|/config\.json|/backup|/dump|/adminer|"
    r"/hudson|/jenkins|/struts|/\.well-known/security|/HNAP1|/setup\.cgi)"
)
# Agents connus de scan (on évite curl/python génériques = fédération légitime httpx)
_SUSPECT_UA = re.compile(
    r"(?i)(sqlmap|nikto|nmap|masscan|zgrab|nuclei|dirbuster|gobuster|wpscan|"
    r"acunetix|nessus|openvas|censys|zmeu|hydra|fuzz|semrush|ahrefsbot|mj12bot|"
    r"petalbot|dotbot|bytespider)"
)
_BAD_METHOD = {"TRACE", "TRACK", "CONNECT", "DEBUG"}


def classify(method: str, path: str, status: int, ua: str):
    """Retourne (suspect: bool, raison: str|None)."""
    if method and method.upper() in _BAD_METHOD:
        return True, "methode_anormale"
    if _SUSPECT_PATH.search(path or ""):
        return True, "chemin_scan"
    if _SUSPECT_UA.search(ua or ""):
        return True, "agent_scan"
    # 404 en rafale sur des chemins inconnus = balayage probable
    if status == 404 and (path or "").count("/") <= 3:
        return True, "sondage_404"
    return False, None


def _prune_ips():
    if len(_by_ip) <= _MAX_IPS:
        return
    # garde les IP les plus actives (suspect puis total)
    top = sorted(_by_ip.items(), key=lambda kv: (kv[1]["suspect"], kv[1]["total"]), reverse=True)[:_MAX_IPS]
    keep = dict(top)
    _by_ip.clear()
    _by_ip.update(keep)


def record(ip: str, method: str, path: str, status: int, ua: str):
    """Enregistre une requête. Ne lève jamais (appelé depuis le middleware)."""
    try:
        suspect, reason = classify(method, path, status, ua)
        now = time.time()
        with _LOCK:
            _totals["total"] += 1
            if suspect:
                _totals["suspect"] += 1
                _by_reason[reason] += 1
                if path:
                    _by_path[path[:120]] += 1
            _by_status[str(status)] += 1
            e = _by_ip.get(ip)
            if not e:
                e = {"total": 0, "suspect": 0, "last": 0, "reasons": set()}
                _by_ip[ip] = e
            e["total"] += 1
            e["last"] = now
            if suspect:
                e["suspect"] += 1
                if reason:
                    e["reasons"].add(reason)
            hk = time.strftime("%Y-%m-%dT%H", time.gmtime(now))
            hb = _hourly.get(hk)
            if not hb:
                hb = {"total": 0, "suspect": 0}
                _hourly[hk] = hb
                # borne : garde 48 dernières heures
                if len(_hourly) > 48:
                    for k in sorted(_hourly.keys())[:-48]:
                        _hourly.pop(k, None)
            hb["total"] += 1
            if suspect:
                hb["suspect"] += 1
            if suspect:
                _events.appendleft({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    "ip": ip, "method": method, "path": path[:160], "status": status,
                    "reason": reason, "ua": (ua or "")[:120],
                })
            _prune_ips()
    except Exception:
        pass


def snapshot(limit_events: int = 100, top: int = 15) -> dict:
    """Agrégats pour le tableau de bord."""
    with _LOCK:
        top_ips = sorted(
            ({"ip": k, "total": v["total"], "suspect": v["suspect"],
              "reasons": sorted(v["reasons"]),
              "last": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(v["last"]))}
             for k, v in _by_ip.items() if v["suspect"] > 0),
            key=lambda x: x["suspect"], reverse=True)[:top]
        top_paths = sorted(({"path": k, "count": v} for k, v in _by_path.items()),
                           key=lambda x: x["count"], reverse=True)[:top]
        reasons = sorted(({"reason": k, "count": v} for k, v in _by_reason.items()),
                         key=lambda x: x["count"], reverse=True)
        status = sorted(({"status": k, "count": v} for k, v in _by_status.items()),
                        key=lambda x: x["count"], reverse=True)
        hourly = [{"h": k, "total": v["total"], "suspect": v["suspect"]}
                  for k, v in sorted(_hourly.items())][-24:]
        return {
            "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_started_at)),
            "uptime_s": int(time.time() - _started_at),
            "total": _totals["total"],
            "suspect": _totals["suspect"],
            "ip_uniques": len(_by_ip),
            "ip_suspectes": sum(1 for v in _by_ip.values() if v["suspect"] > 0),
            "top_ips": top_ips,
            "top_paths": top_paths,
            "reasons": reasons,
            "status": status,
            "hourly": hourly,
            "events": list(_events)[:limit_events],
        }


def reset():
    with _LOCK:
        _events.clear(); _by_ip.clear(); _by_path.clear()
        _by_reason.clear(); _by_status.clear(); _hourly.clear()
        _totals["total"] = 0; _totals["suspect"] = 0
