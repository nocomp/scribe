"""
master/port_cleanup.py — v3.0.0
================================
Nettoyage prudent des ports occupés par d'anciens process SCRIBE orphelins.

Stratégie : on tue UNIQUEMENT les process clairement identifiables comme SCRIBE
(ligne de commande contient un de nos scripts connus). Tout autre process est
laissé intact et signalé à l'utilisateur — il décide.

Fonctionne sous Linux (lsof + /proc/<pid>/cmdline) et Windows (netstat + wmic
puis taskkill). Tente d'abord SIGTERM (terminaison propre), puis SIGKILL après
3 secondes si le process ne s'est pas arrêté.

Aucun privilège élevé n'est requis pour les process de l'utilisateur courant.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger("scribe.port_cleanup")

# ── Périmètre SCRIBE ────────────────────────────────────────────────────────
# Ports protégés par défaut. Modifiable au besoin par les appelants.
DEFAULT_SCRIBE_PORTS: list[int] = (
    [9000]                          # master
    + list(range(8000, 8010))       # instances master classiques
    + [8565]                        # collecteur exercice
    + list(range(8660, 8670))       # instances exercice
    + [7474, 7373]                  # démo permanente + collecteur démo
)

# Signatures d'identification dans la ligne de commande d'un process : si l'un
# de ces fragments apparaît, on considère le process comme étant SCRIBE.
# Volontairement spécifique pour éviter les faux positifs (on ne tape pas juste
# "python", trop large).
SCRIBE_CMDLINE_HINTS: tuple[str, ...] = (
    "scribe",                       # n'importe quel chemin contenant "scribe"
    "main.py",                      # entrée principale SCRIBE
    "collecteur_exercice.py",       # collecteur exercice
    "collecteur.py",                # collecteurs (principal + démo)
    "uvicorn",                      # serveur ASGI lancé par SCRIBE
)


@dataclass
class PortHolder:
    """Information sur un process qui occupe un port."""
    port: int
    pid: int
    cmdline: str        # ligne de commande complète, ou nom du process
    is_scribe: bool     # True si la ligne contient un hint SCRIBE


# ─────────────────────────────────────────────────────────────────────────────
# Détection d'occupation
# ─────────────────────────────────────────────────────────────────────────────

def is_port_in_use(port: int) -> bool:
    """Vérifie si un port TCP est occupé sur localhost."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        s.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


# ─────────────────────────────────────────────────────────────────────────────
# Identification du process qui occupe un port
# ─────────────────────────────────────────────────────────────────────────────

def _identify_holder_linux(port: int) -> PortHolder | None:
    """Sous Linux/macOS, utilise lsof si disponible, sinon ss."""
    # 1) lsof (présent par défaut sur la plupart des distros)
    if shutil.which("lsof"):
        try:
            out = subprocess.run(
                ["lsof", "-iTCP:" + str(port), "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=3,
            )
            pids = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
            if pids:
                pid = pids[0]
                return _build_holder_linux(port, pid)
        except Exception as e:
            logger.debug(f"lsof a échoué pour port {port}: {e}")
    # 2) ss en repli (paquet iproute2)
    if shutil.which("ss"):
        try:
            out = subprocess.run(
                ["ss", "-tlnpH", f"( sport = :{port} )"],
                capture_output=True, text=True, timeout=3,
            )
            # Format : ... users:(("python3",pid=12345,fd=10))
            import re
            m = re.search(r"pid=(\d+)", out.stdout)
            if m:
                return _build_holder_linux(port, int(m.group(1)))
        except Exception as e:
            logger.debug(f"ss a échoué pour port {port}: {e}")
    return None


def _build_holder_linux(port: int, pid: int) -> PortHolder | None:
    """Construit un PortHolder en lisant /proc/<pid>/cmdline."""
    try:
        cmd_path = f"/proc/{pid}/cmdline"
        if not os.path.exists(cmd_path):
            return None
        with open(cmd_path, "rb") as f:
            raw = f.read()
        # cmdline est null-séparé ; remplacer par espaces
        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        return PortHolder(
            port=port, pid=pid, cmdline=cmdline,
            is_scribe=_looks_like_scribe(cmdline, port=port),
        )
    except Exception as e:
        logger.debug(f"lecture /proc/{pid}/cmdline a échoué: {e}")
        return None


def _identify_holder_windows(port: int) -> PortHolder | None:
    """Sous Windows : PowerShell Get-NetTCPConnection (recommandé, locale-insensitive)
    puis netstat en fallback. wmic est utilisé pour la cmdline si dispo, sinon
    PowerShell aussi."""
    pid = None
    # 1) PowerShell Get-NetTCPConnection — méthode propre et fiable Win10/11
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-NetTCPConnection -State Listen -LocalPort {port} "
             "-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"],
            capture_output=True, text=True, timeout=5,
        )
        v = out.stdout.strip()
        if v.isdigit():
            pid = int(v)
    except Exception as e:
        logger.debug(f"Get-NetTCPConnection KO pour port {port}: {e}")

    # 2) Fallback netstat -ano (en cas de PowerShell bloqué)
    if pid is None:
        try:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=4,
            )
            needle = f":{port} "
            # "LISTENING" en anglais, "ÉCOUTE" en français Win — on accepte les deux
            listen_markers = ("LISTENING", "LISTEN", "ÉCOUTE", "ECOUTE")
            for line in out.stdout.splitlines():
                if needle in line and any(m in line.upper() for m in listen_markers):
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pid = int(parts[-1])
                        break
        except Exception as e:
            logger.debug(f"netstat KO pour port {port}: {e}")

    if pid is None:
        return None

    # 3) Ligne de commande du process
    cmdline = _windows_cmdline_for_pid(pid)
    return PortHolder(
        port=port, pid=pid, cmdline=cmdline,
        is_scribe=_looks_like_scribe(cmdline, port=port),
    )


def _windows_cmdline_for_pid(pid: int) -> str:
    """Récupère la ligne de commande d'un PID sous Windows.

    Ordre v3.0.0-fix : PowerShell d'abord (toujours présent sur Win10/11),
    puis wmic (deprecated, peut être absent), puis tasklist (juste le nom).
    """
    # 1) PowerShell — méthode la plus fiable et présente partout
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine"],
            capture_output=True, text=True, timeout=5,
        )
        line = out.stdout.strip()
        if line:
            return line
    except Exception:
        pass
    # 2) wmic — fallback (deprecated dans Win 10 22H2+ et absent par défaut sur W11 21H2+)
    try:
        out = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/format:list"],
            capture_output=True, text=True, timeout=4,
        )
        for line in out.stdout.splitlines():
            if line.startswith("CommandLine="):
                val = line[len("CommandLine="):].strip()
                if val:
                    return val
    except Exception:
        pass
    # 3) Dernier repli : juste le nom via tasklist (suffit pour Python sur port SCRIBE
    #    grâce à l'heuristique de _looks_like_scribe)
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=4,
        )
        return out.stdout.strip()
    except Exception:
        return f"PID {pid} (cmdline introuvable)"


def identify_port_holder(port: int) -> PortHolder | None:
    """Cross-platform : qui occupe ce port ? Retourne None si port libre ou
    non identifiable."""
    if not is_port_in_use(port):
        return None
    if platform.system() == "Windows":
        return _identify_holder_windows(port)
    return _identify_holder_linux(port)


def _looks_like_scribe(cmdline: str, port: int | None = None) -> bool:
    """Détermine si une ligne de commande correspond à un process SCRIBE.

    On exige un hint MÉTIER (main.py, scribe, collecteur*) — un simple "uvicorn"
    seul ne suffit pas, car uvicorn peut servir d'autres applications. Le check
    "uvicorn ET scribe" est implicite : si la commande contient déjà "scribe" ou
    "main.py", on est bon.

    v3.0.0-fix Windows : sur Windows 10/11, wmic peut être absent (deprecated) et
    `tasklist` ne donne que le nom du process (ex: "python.exe"). Dans ce cas
    on a moins d'info pour décider. Heuristique sûre : si le port appartient à
    notre périmètre SCRIBE ET que le process est un python.exe/pythonw.exe SANS
    autre info, on considère que c'est très probablement SCRIBE (puisque ces
    ports n'ont normalement pas vocation à être occupés par du Python tiers).
    Les utilisateurs avec un autre python sur ces ports auront un message clair
    et pourront le confirmer.
    """
    if not cmdline:
        return False
    c = cmdline.lower()
    # 1) Hint métier explicite — cas idéal
    metier_hints = ("scribe", "main.py", "collecteur_exercice.py", "collecteur.py")
    if any(h in c for h in metier_hints):
        return True
    # 2) Windows fallback : si on n'a que le nom (python.exe / pythonw.exe) et
    #    qu'on est sur un port SCRIBE connu, considérer comme SCRIBE.
    if port is not None and port in DEFAULT_SCRIBE_PORTS:
        # Cmdline réduit au nom du process (cas tasklist sans CommandLine)
        c_trim = c.strip().strip('"')
        bare_names = {"python.exe", "pythonw.exe", "python", "pythonw"}
        # Récupérer le 1er mot ou le contenu CSV de tasklist
        first_token = c_trim.split(",")[0].strip().strip('"').split()[0] if c_trim else ""
        if first_token in bare_names:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Terminaison
# ─────────────────────────────────────────────────────────────────────────────

def _terminate_pid(pid: int) -> bool:
    """Termine proprement un PID (SIGTERM puis SIGKILL après 3s).

    Retourne True si le process est mort à la fin de l'opération."""
    if platform.system() == "Windows":
        # taskkill /PID 1234 → close gracefully (équivalent SIGTERM)
        try:
            subprocess.run(["taskkill", "/PID", str(pid)],
                           capture_output=True, timeout=3)
        except Exception:
            pass
        # Attendre 3s puis vérifier
        time.sleep(3)
        if not _pid_alive(pid):
            return True
        # SIGKILL équivalent
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=3)
        except Exception:
            pass
        time.sleep(0.5)
        return not _pid_alive(pid)
    else:
        # Linux/macOS : signaux POSIX
        import signal as _signal
        try:
            os.kill(pid, _signal.SIGTERM)
        except ProcessLookupError:
            return True
        except Exception:
            pass
        # Attendre 3s puis vérifier
        for _ in range(15):
            time.sleep(0.2)
            if not _pid_alive(pid):
                return True
        # SIGKILL
        try:
            os.kill(pid, _signal.SIGKILL)
        except Exception:
            pass
        time.sleep(0.3)
        return not _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    """Vérifie qu'un PID est encore vivant. Cross-platform."""
    if platform.system() == "Windows":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=3,
            )
            return str(pid) in out.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────

def free_port_if_scribe(port: int) -> dict:
    """Libère un port s'il est occupé par un process SCRIBE identifiable.

    Retourne un dict de résultat :
      {"port": int, "status": str, "detail": str, ...}
    où status ∈ {
        "free"           — port déjà libre
        "freed"          — process SCRIBE tué avec succès
        "failed_kill"    — process SCRIBE identifié mais terminaison KO
        "foreign"        — process non-SCRIBE, NON tué (signalé à l'utilisateur)
        "unidentified"   — port occupé mais impossible d'identifier qui
    }
    """
    if not is_port_in_use(port):
        return {"port": port, "status": "free"}
    holder = identify_port_holder(port)
    if holder is None:
        logger.warning(f"Port {port} occupé mais holder non identifiable.")
        return {"port": port, "status": "unidentified",
                "detail": "Port occupé mais impossible d'identifier le process. "
                          "Vérifiez manuellement (netstat/lsof)."}
    if not holder.is_scribe:
        logger.warning(
            f"Port {port} occupé par un process NON-SCRIBE (PID {holder.pid}). "
            f"Cmdline : {holder.cmdline[:200]}. NON tué."
        )
        return {"port": port, "status": "foreign", "pid": holder.pid,
                "cmdline": holder.cmdline[:200],
                "detail": f"Port {port} occupé par un process tiers (PID {holder.pid}). "
                          "SCRIBE ne touche pas aux process qu'il n'a pas lancés. "
                          "Arrêtez-le manuellement si nécessaire."}
    # Process SCRIBE → on termine
    logger.info(f"Port {port} occupé par SCRIBE (PID {holder.pid}) → terminaison")
    ok = _terminate_pid(holder.pid)
    # Petit délai pour que l'OS libère vraiment le port
    if ok:
        for _ in range(10):
            if not is_port_in_use(port):
                break
            time.sleep(0.2)
    return {
        "port": port, "pid": holder.pid,
        "status": "freed" if ok else "failed_kill",
        "cmdline": holder.cmdline[:200],
        "detail": "Process SCRIBE terminé." if ok else
                  "Process SCRIBE identifié mais terminaison a échoué.",
    }


def free_ports(ports: Iterable[int]) -> list[dict]:
    """Libère plusieurs ports SCRIBE. Retourne un rapport par port."""
    return [free_port_if_scribe(p) for p in ports]


def free_all_scribe_ports() -> list[dict]:
    """Libère tous les ports SCRIBE étendus (master + instances + exercice + démo)."""
    return free_ports(DEFAULT_SCRIBE_PORTS)


def summarize_results(results: list[dict]) -> str:
    """Format texte court pour les logs."""
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    parts = []
    if counts.get("free"):
        parts.append(f"{counts['free']} libres")
    if counts.get("freed"):
        parts.append(f"{counts['freed']} libérés")
    if counts.get("foreign"):
        parts.append(f"{counts['foreign']} occupés par tiers ⚠")
    if counts.get("failed_kill"):
        parts.append(f"{counts['failed_kill']} échecs terminaison ⚠")
    if counts.get("unidentified"):
        parts.append(f"{counts['unidentified']} non-identifiés")
    return ", ".join(parts) if parts else "rien à faire"
