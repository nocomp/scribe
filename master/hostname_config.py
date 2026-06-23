"""
master/hostname_config.py — v3.2.0 / h17

Source de vérité unique pour le hostname externe de SCRIBE.

Problème résolu :
  Quand SCRIBE est installé sur un VPS (vps-389073b7.vps.ovh.net) ou un
  serveur LAN (192.168.x.x), les liens entre composants ne doivent PAS
  utiliser 'localhost' car les utilisateurs distants reçoivent des URLs
  inaccessibles.

Stratégie :
  - Une seule source : fichier `hostname.conf` à la racine du projet
  - Auto-détection au premier lancement (IP locale, NIC active)
  - Wizard de validation accessible via /api/master/setup-hostname
  - Fallback intelligent : si pas de fichier, on lit le header Host: de la
    requête HTTP en cours (donc ça marche sans config pour les accès
    navigateur, seul le M2M nécessite la config)

API :
  get_configured_hostname() -> str | None
  set_configured_hostname(host: str)
  detect_local_ip() -> str
  get_external_host(request=None, fallback="localhost") -> str
"""
from __future__ import annotations
import os
import pathlib
import socket
import logging

logger = logging.getLogger("scribe.hostname")

# Fichier de config — racine du projet (un cran au-dessus de master/)
_CONFIG_FILE = pathlib.Path(__file__).resolve().parent.parent / "hostname.conf"


def get_configured_hostname() -> str | None:
    """Lit le hostname configuré, ou None si pas de fichier."""
    # Priorité 1 : variable d'environnement (utile pour Docker)
    env = os.getenv("SCRIBE_EXTERNAL_HOST")
    if env:
        return env.strip()
    # Priorité 2 : fichier
    try:
        if _CONFIG_FILE.exists():
            content = _CONFIG_FILE.read_text(encoding="utf-8").strip()
            # Tolérer un fichier multi-lignes (commentaires) : on prend la
            # première ligne non vide non commentée
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except Exception as e:
        logger.warning(f"Lecture hostname.conf impossible : {e}")
    return None


def set_configured_hostname(host: str) -> None:
    """Écrit le hostname dans hostname.conf."""
    host = (host or "").strip()
    # Sécurité minimale : pas d'espaces, pas de schéma http(s)://
    if not host:
        raise ValueError("Hostname vide")
    if "://" in host:
        host = host.split("://", 1)[1]
    if "/" in host:
        host = host.split("/", 1)[0]
    if " " in host or "\n" in host:
        raise ValueError("Hostname invalide")
    content = (
        "# SCRIBE — hostname externe utilisé pour les liens publics et la\n"
        "# communication inter-instances (collecteur, fédération).\n"
        "# Modifié par /api/master/setup-hostname ou directement à la main.\n"
        "# Variable d'environnement prioritaire : SCRIBE_EXTERNAL_HOST.\n"
        f"{host}\n"
    )
    _CONFIG_FILE.write_text(content, encoding="utf-8")
    logger.info(f"hostname configuré : {host}")


def detect_local_ip() -> str:
    """Détecte l'IP de l'interface réseau active.

    Méthode : connecter un socket UDP vers une adresse externe (sans envoyer
    réellement de paquet), récupérer l'IP locale utilisée par le routage.
    Fonctionne sans accès Internet effectif.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def suggest_hostnames() -> list[dict]:
    """Propose plusieurs hostnames possibles pour le wizard.

    Retourne une liste de {value, label, source}.
    """
    out = []
    # IP locale détectée
    try:
        ip = detect_local_ip()
        if ip and ip != "127.0.0.1":
            out.append({
                "value":  ip,
                "label":  f"{ip} (IP locale détectée)",
                "source": "auto_ip",
            })
    except Exception:
        pass
    # Hostname système (utile sur VPS configurés)
    try:
        hn = socket.gethostname()
        # FQDN si disponible
        try:
            fqdn = socket.getfqdn()
            if fqdn and fqdn != hn and "." in fqdn:
                out.append({
                    "value":  fqdn,
                    "label":  f"{fqdn} (nom système complet)",
                    "source": "fqdn",
                })
        except Exception:
            pass
        if hn and hn != "localhost":
            out.append({
                "value":  hn,
                "label":  f"{hn} (nom machine)",
                "source": "hostname",
            })
    except Exception:
        pass
    # Toujours proposer localhost en dernier
    out.append({
        "value":  "localhost",
        "label":  "localhost (usage local uniquement, déconseillé en réseau)",
        "source": "default",
    })
    return out


def get_external_host(request=None, fallback: str = "localhost") -> str:
    """Retourne le hostname à utiliser pour les URLs externes.

    Ordre de priorité :
      1. Hostname configuré (fichier ou env)
      2. Header Host: de la requête courante (si fournie)
      3. Fallback fourni en paramètre (par défaut "localhost")

    Retourne juste le hostname (sans port, sans schéma).
    """
    # 1. Configuré explicitement
    cfg = get_configured_hostname()
    if cfg:
        # Si le user a mis "host:port", on garde uniquement la partie host
        if ":" in cfg and not cfg.startswith("["):  # pas IPv6
            return cfg.split(":", 1)[0]
        return cfg
    # 2. Header Host de la requête
    if request is not None:
        try:
            host_header = request.headers.get("host") or request.headers.get("Host")
            if host_header:
                # Retirer le port
                if ":" in host_header and not host_header.startswith("["):
                    host_header = host_header.split(":", 1)[0]
                if host_header and host_header not in ("localhost", "127.0.0.1"):
                    return host_header
        except Exception:
            pass
    # 3. Fallback
    return fallback


def build_external_url(host: str, port: int, scheme: str = "http", path: str = "") -> str:
    """Construit une URL externe complète et propre.

    Si host est une IPv6, l'encadre de crochets.
    Si scheme est https et port standard 443, omet le port.
    """
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port_part = ""
    if not (scheme == "http" and port == 80) and not (scheme == "https" and port == 443):
        port_part = f":{port}"
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{host}{port_part}{path}"


# Au chargement du module, log l'état
_initial = get_configured_hostname()
if _initial:
    logger.info(f"Hostname externe configuré : {_initial}")
else:
    logger.info("Hostname externe non configuré (fallback dynamique via Host header)")
