"""
master/exercice_manager.py — Pilotage des instances SCRIBE en MODE EXERCICE
==========================================================================
Miroir de instances_manager.py mais pour le mode exercice :
  - Plage de ports 8660-8669 (au lieu de 8000-8009)
  - Pousse au collecteur exercice :8565 (au lieu de :9000)
  - DBs isolées dans data/instances_exercice/<sigle>/
  - State séparé dans master/master_instances_exercice.json
  - Variable d'env SCRIBE_EXERCICE_MODE=1 injectée → bandeau "🎯 MODE EXERCICE"
    s'affiche automatiquement sur l'instance fille (existant dans index.html)

Le master gère AUSSI le collecteur exercice :8565 lui-même comme un subprocess
spécial (start_collecteur / stop_collecteur), pour que l'animateur n'ait qu'un
point d'entrée : le master :9000.

Lecteur du code : tout ce qui ne change pas par rapport à instances_manager
est implémenté à l'identique. Les divergences sont annotées par # [EXO].
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import secrets
import signal
import string
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Réutiliser les helpers existants pour ne pas dupliquer
from master.instances_manager import (
    PROJECT_ROOT,
    PROFIL_BASE_XLSX,
    generate_password,
    generate_token,
    now_iso,
    _safe_path_segment,
    _pid_alive,
)

logger = logging.getLogger("scribe.master.exercice")

# [EXO] Chemins isolés du mode prod
DATA_DIR_EXO = PROJECT_ROOT / "data" / "instances_exercice"
STATE_FILE_EXO = PROJECT_ROOT / "master" / "master_instances_exercice.json"

# [EXO] Plage de ports exercice
EXO_PORT_RANGE = range(8660, 8670)
# [EXO] Port du collecteur exercice (animateur)
EXO_COLLECTEUR_PORT = 8565
# [EXO] Chemin vers collecteur_exercice.py
EXO_COLLECTEUR_SCRIPT = PROJECT_ROOT / "collecteur_exercice" / "collecteur_exercice.py"


# ─────────────────────────────────────────────────────────────────────────────
# Modèles de données — réutilisent InstanceConfig/State de instances_manager
# en passant par dataclass dédiée (peut diverger si besoin futur)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExerciceInstanceConfig:
    """Configuration d'une instance SCRIBE en mode EXERCICE.

    Symétrique d'InstanceConfig (mode prod) — les champs sont identiques.
    On garde une dataclass séparée pour pouvoir diverger plus tard sans
    impacter le mode prod.
    """
    port: int
    sigle: str = ""
    nom: str = ""
    admin_login: str = "dircrise"
    admin_password: str = ""
    adresse: str = ""
    latitude: float | None = None
    longitude: float | None = None
    # Pas de mode "solo" en exercice : toute instance exo pousse au :8565.
    # Champ conservé pour compat ascendante avec InstanceConfig si besoin
    # de réutiliser des helpers communs.
    synchroniser: bool = True

    def __post_init__(self):
        if not self.sigle:
            self.sigle = f"Exo_{self.port}"
        if not self.nom:
            self.nom = self.sigle
        if not self.admin_password:
            # [EXO] Mot de passe par défaut différent de prod
            # (visible dans l'UI animateur, pas un secret)
            self.admin_password = generate_password()


@dataclass
class ExerciceInstanceState:
    """État runtime d'une instance exercice."""
    config: ExerciceInstanceConfig
    statut: str = "arrete"  # arrete | actif | erreur
    pid: int | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    db_path: str | None = None
    log_path: str | None = None
    fed_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["config"] = asdict(self.config)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExerciceInstanceState":
        cfg = ExerciceInstanceConfig(**d.pop("config"))
        return cls(config=cfg, **d)


# ─────────────────────────────────────────────────────────────────────────────
# Manager principal
# ─────────────────────────────────────────────────────────────────────────────

class ExerciceManager:
    """Orchestrateur des instances exercice + du collecteur exercice :8565."""

    def __init__(self):
        self.instances: dict[int, ExerciceInstanceState] = {}
        # [EXO] Subprocess du collecteur exercice (None si pas démarré)
        self.collecteur_proc: subprocess.Popen | None = None
        self.collecteur_started_at: str | None = None
        self._load_state()
        self._ensure_defaults()

    # ── Persistance ──────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        if not STATE_FILE_EXO.exists():
            return
        try:
            with open(STATE_FILE_EXO, encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("instances", []):
                state = ExerciceInstanceState.from_dict(d)
                if state.pid and not _pid_alive(state.pid):
                    state.statut = "arrete"
                    state.pid = None
                self.instances[state.config.port] = state
            # [EXO] Recharger aussi le PID du collecteur exercice si présent
            coll = data.get("collecteur", {})
            coll_pid = coll.get("pid")
            if coll_pid and _pid_alive(coll_pid):
                # On crée un proxy Popen "fantôme" — on ne peut pas reconstituer
                # un vrai Popen mais on retient le PID pour stop/health.
                # On stocke comme un dict simple, ensure_collecteur_running
                # vérifie via _pid_alive et /health avant de relancer.
                self.collecteur_proc = _AdoptedProcess(coll_pid)
                self.collecteur_started_at = coll.get("started_at")
            logger.info(f"État exercice rechargé : {len(self.instances)} instances")
        except Exception as e:
            logger.warning(f"Impossible de charger l'état exercice : {e}")

    def _save_state(self) -> None:
        STATE_FILE_EXO.parent.mkdir(parents=True, exist_ok=True)
        try:
            data: dict[str, Any] = {
                "instances": [s.to_dict() for s in self.instances.values()],
                "saved_at": now_iso(),
            }
            if self.collecteur_proc is not None:
                pid = self.collecteur_proc.pid
                if pid and _pid_alive(pid):
                    data["collecteur"] = {
                        "pid": pid,
                        "started_at": self.collecteur_started_at,
                    }
            with open(STATE_FILE_EXO, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Impossible de sauvegarder l'état exercice : {e}")

    def _ensure_defaults(self) -> None:
        """Crée les 10 slots par défaut (ports 8660-8669) si absents."""
        for port in EXO_PORT_RANGE:
            if port not in self.instances:
                cfg = ExerciceInstanceConfig(port=port)
                self.instances[port] = ExerciceInstanceState(config=cfg)
        self._save_state()

    # ── API publique ─────────────────────────────────────────────────────────

    def list_instances(self) -> list[dict[str, Any]]:
        out = []
        for state in sorted(self.instances.values(), key=lambda s: s.config.port):
            d = state.to_dict()
            # Ne pas exposer le mot de passe en clair — masqué pour l'UI
            if d["config"].get("admin_password"):
                d["config"]["admin_password_masked"] = True
            d["alive"] = bool(state.pid and _pid_alive(state.pid))
            out.append(d)
        return out

    def update_config(self, port: int, **kwargs) -> ExerciceInstanceState:
        if port not in self.instances:
            raise ValueError(f"Port {port} inconnu")
        state = self.instances[port]
        if state.statut == "actif":
            raise ValueError(
                f"Instance exercice {state.config.sigle} active sur :{port}. "
                "Arrêtez-la avant de modifier sa configuration."
            )
        for key, val in kwargs.items():
            if hasattr(state.config, key) and key != "port":
                setattr(state.config, key, val)
        self._save_state()
        return state

    def get_status(self) -> dict[str, Any]:
        """Retourne l'état global du mode exercice : collecteur + instances."""
        coll_alive = False
        coll_pid = None
        if self.collecteur_proc is not None:
            coll_pid = self.collecteur_proc.pid
            if coll_pid and _pid_alive(coll_pid):
                coll_alive = True
        actives = sum(
            1 for s in self.instances.values()
            if s.pid and _pid_alive(s.pid)
        )
        return {
            "collecteur_actif":     coll_alive,
            "collecteur_pid":       coll_pid if coll_alive else None,
            "collecteur_url":       f"http://localhost:{EXO_COLLECTEUR_PORT}",
            "collecteur_started_at": self.collecteur_started_at if coll_alive else None,
            "instances_actives":    actives,
            "instances_total":      len(self.instances),
        }

    # ── Collecteur exercice (port 8565) ──────────────────────────────────────

    def start_collecteur(self) -> dict[str, Any]:
        """Démarre le subprocess du collecteur exercice :8565.

        Si déjà actif et joignable, ne fait rien (idempotent).
        """
        # Idempotent : déjà actif ?
        if self.collecteur_proc is not None:
            pid = self.collecteur_proc.pid
            if pid and _pid_alive(pid):
                logger.info("Collecteur exercice déjà actif (PID %s)", pid)
                return self.get_status()
            # Process mort — on nettoie et on relance
            self.collecteur_proc = None
            self.collecteur_started_at = None

        if not EXO_COLLECTEUR_SCRIPT.exists():
            raise FileNotFoundError(
                f"collecteur_exercice.py introuvable : {EXO_COLLECTEUR_SCRIPT}"
            )

        # Vérifier que le port n'est pas déjà occupé par un autre process
        if _port_in_use(EXO_COLLECTEUR_PORT):
            raise ValueError(
                f"Port {EXO_COLLECTEUR_PORT} déjà occupé. Vérifiez qu'un autre "
                f"collecteur exercice n'est pas déjà lancé."
            )

        # Préparer répertoires
        coll_dir = EXO_COLLECTEUR_SCRIPT.parent
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "collecteur_exercice.log"

        # Variables d'env (cohérentes avec lancer_exercice.sh)
        env = os.environ.copy()
        env.update({
            "SCRIBE_EXERCICE_MODE": "1",
            "COLLECTEUR_PORT": str(EXO_COLLECTEUR_PORT),
            "COLLECTEUR_DATA":   str(coll_dir / "collecteur_exo_data.json"),
            "COLLECTEUR_TOKENS": str(coll_dir / "collecteur_exo_tokens.json"),
            "COLLECTEUR_ADMIN":  str(coll_dir / "collecteur_exo_admin.json"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        })

        log_file = open(log_path, "ab", buffering=0)
        popen_kwargs = {
            "cwd": str(coll_dir),
            "env": env,
            "stdout": log_file,
            "stderr": log_file,
            "stdin":  subprocess.DEVNULL,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        else:
            CREATE_NO_WINDOW = 0x08000000
            popen_kwargs["creationflags"] = CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(
                [sys.executable, str(EXO_COLLECTEUR_SCRIPT)],
                **popen_kwargs,
            )
        except Exception as e:
            try: log_file.close()
            except Exception: pass
            logger.error(f"Lancement collecteur exercice échoué : {e}")
            raise ValueError(f"Lancement collecteur exercice échoué : {e}") from e

        self.collecteur_proc = proc
        self.collecteur_started_at = now_iso()

        # Vérifier que le subprocess vit après 2s
        import time
        time.sleep(2.0)
        rc = proc.poll()
        if rc is not None:
            self.collecteur_proc = None
            self.collecteur_started_at = None
            log_tail = ""
            try:
                with open(log_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="replace")
                lines = content.splitlines()[-30:]
                log_tail = "\n".join(lines)
            except Exception:
                pass
            raise ValueError(
                f"Le collecteur exercice a planté immédiatement (returncode={rc}). "
                f"Voir logs/collecteur_exercice.log\n"
                f"Dernières lignes :\n{log_tail[-800:]}"
            )

        # Attendre que /health réponde (max 15s)
        for _ in range(15):
            if _port_in_use(EXO_COLLECTEUR_PORT):
                break
            time.sleep(1)

        self._save_state()
        logger.info(f"Collecteur exercice lancé (PID {proc.pid}, port {EXO_COLLECTEUR_PORT})")
        return self.get_status()

    def stop_collecteur(self) -> dict[str, Any]:
        """Arrête le collecteur exercice :8565 (et toutes les instances exercice)."""
        # Stopper d'abord toutes les instances exercice (push impossible sinon)
        for port, state in list(self.instances.items()):
            if state.pid and _pid_alive(state.pid):
                try:
                    self.stop(port)
                except Exception as e:
                    logger.warning(f"Erreur stop instance exo :{port} : {e}")

        # Puis stopper le collecteur lui-même
        if self.collecteur_proc is None:
            return self.get_status()

        pid = self.collecteur_proc.pid
        if not pid or not _pid_alive(pid):
            self.collecteur_proc = None
            self.collecteur_started_at = None
            self._save_state()
            return self.get_status()

        try:
            if isinstance(self.collecteur_proc, _AdoptedProcess):
                # PID adopté depuis state — on ne peut que kill
                _kill_pid(pid)
            else:
                self.collecteur_proc.terminate()
                try:
                    self.collecteur_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.collecteur_proc.kill()
            logger.info(f"Collecteur exercice arrêté (PID {pid})")
        except Exception as e:
            logger.warning(f"Erreur arrêt collecteur exercice : {e}")

        self.collecteur_proc = None
        self.collecteur_started_at = None
        self._save_state()
        return self.get_status()

    # ── Instances exercice ───────────────────────────────────────────────────

    def start(self, port: int) -> ExerciceInstanceState:
        """Démarre une instance exercice.

        Vérifie d'abord que le collecteur exercice :8565 est actif.
        Si non, le démarre automatiquement (commodité utilisateur).
        """
        if port not in self.instances:
            raise ValueError(f"Port {port} inconnu (plage exercice : 8660-8669)")

        state = self.instances[port]
        cfg = state.config

        if state.statut == "actif" and state.pid and _pid_alive(state.pid):
            return state  # idempotent

        # [EXO] Le collecteur exercice doit être actif pour que la fédération
        # marche. On le démarre si nécessaire (commodité).
        coll_status = self.get_status()
        if not coll_status["collecteur_actif"]:
            logger.info("Démarrage automatique du collecteur exercice :8565")
            self.start_collecteur()

        # Cleanup DB existante (DB exercice = volatile, repartir propre)
        # [EXO] Différence importante avec mode prod : la DB est TOUJOURS reset
        # au lancement pour partir d'une DB propre — on simule un exercice
        # depuis l'état initial.
        path_segment = _safe_path_segment(cfg.sigle, fallback=f"exo_{cfg.port}")
        inst_dir = DATA_DIR_EXO / path_segment

        try:
            if inst_dir.exists():
                import shutil
                shutil.rmtree(inst_dir, ignore_errors=True)
            inst_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Cleanup répertoire {inst_dir} échoué : {e}")

        state.db_path = str(inst_dir / "scribe.db")
        state.log_path = str(inst_dir / "scribe.log")

        if not state.fed_token:
            state.fed_token = generate_token()

        # Bootstrap DB (UF + capacité + admin) — on réutilise la logique
        # d'instances_manager via une import lazy
        from master.instances_manager import InstanceManager
        try:
            # Astuce : on triche un peu en réutilisant _bootstrap_db
            # de InstanceManager mais avec notre state. Les méthodes
            # _bootstrap_db / _create_admin / _import_xlsx_inprocess
            # ne dépendent que de state.db_path et de cfg, pas du manager.
            tmp_mgr = InstanceManager.__new__(InstanceManager)
            tmp_mgr._bootstrap_db(state)
        except Exception as e:
            logger.error(f"Bootstrap exercice échoué pour {cfg.sigle} : {e}")
            state.statut = "erreur"
            self._save_state()
            raise ValueError(f"Bootstrap DB exercice échoué : {e}") from e

        # Générer config.js + config.xml exercice
        config_js_path = inst_dir / "config.js"
        config_xml_path = inst_dir / "config.xml"
        try:
            self._generate_exo_config(state, config_js_path, config_xml_path)
            logger.info(f"  config.js + config.xml exercice générés pour {cfg.sigle}")
        except Exception as e:
            logger.warning(f"  Génération config exo échouée : {e}")

        # Auto-enrôlement AVANT Popen (cf. fix v2.3.35)
        try:
            self._auto_enrol_exo(state)
        except Exception as e:
            logger.warning(f"Auto-enrôlement exercice échoué pour {cfg.sigle} : {e}")

        # [EXO] Variables d'env spécifiques mode exercice
        env = os.environ.copy()
        env.update({
            "SCRIBE_PORT":          str(cfg.port),
            "SCRIBE_SIGLE":         cfg.sigle,
            "SCRIBE_NOM":           cfg.nom,
            "DATABASE_URL":         f"sqlite:///{state.db_path}",
            "SCRIBE_CONFIG_JS":     str(config_js_path),
            "SCRIBE_CONFIG_FILE":   str(config_xml_path),
            "SCRIBE_ADMIN_LOGIN":   cfg.admin_login,
            "SCRIBE_ADMIN_PWD":     cfg.admin_password,
            "SCRIBE_LATITUDE":      str(cfg.latitude or ""),
            "SCRIBE_LONGITUDE":     str(cfg.longitude or ""),
            "SCRIBE_ADRESSE":       cfg.adresse or "",
            # [EXO] Marqueurs mode exercice (déclenchent le bandeau dans index.html)
            "SCRIBE_EXERCICE_MODE": "1",
            "SCRIBE_EXO_SIGLE":     cfg.sigle,
            "SCRIBE_EXO_COLLECTEUR": f"http://localhost:{EXO_COLLECTEUR_PORT}",
            "PYTHONIOENCODING":     "utf-8",
            "PYTHONUTF8":           "1",
        })

        log_file = None
        try:
            log_file = open(state.log_path, "ab", buffering=0)
            popen_kwargs = {
                "cwd": str(PROJECT_ROOT),
                "env": env,
                "stdout": log_file,
                "stderr": log_file,
                "stdin":  subprocess.DEVNULL,
            }
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            else:
                CREATE_NO_WINDOW = 0x08000000
                popen_kwargs["creationflags"] = CREATE_NO_WINDOW
            proc = subprocess.Popen(
                [sys.executable, "main.py"],
                **popen_kwargs,
            )
        except Exception as e:
            if log_file:
                try: log_file.close()
                except Exception: pass
            logger.error(f"Popen exo échoué pour {cfg.sigle} : {e}")
            state.statut = "erreur"
            self._save_state()
            raise ValueError(f"Lancement subprocess exo échoué : {e}") from e

        state.pid = proc.pid
        state.started_at = now_iso()
        state.stopped_at = None
        state.statut = "actif"

        # Vérification post-launch
        import time
        time.sleep(2.0)
        rc = proc.poll()
        if rc is not None:
            state.statut = "erreur"
            state.pid = None
            self._save_state()
            log_tail = ""
            try:
                with open(state.log_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="replace")
                lines = content.splitlines()[-30:]
                log_tail = "\n".join(lines)
            except Exception:
                pass
            raise ValueError(
                f"L'instance exercice a planté immédiatement (returncode={rc}). "
                f"Voir data/instances_exercice/{path_segment}/scribe.log\n"
                f"Dernières lignes :\n{log_tail[-800:]}"
            )

        self._save_state()
        logger.info(f"Instance exercice {cfg.sigle} lancée (PID {proc.pid}, port {port})")
        return state

    def stop(self, port: int) -> ExerciceInstanceState:
        if port not in self.instances:
            raise ValueError(f"Port {port} inconnu")
        state = self.instances[port]
        if state.pid and _pid_alive(state.pid):
            try:
                _kill_pid(state.pid)
                logger.info(f"SIGTERM exo envoyé à {state.config.sigle} (PID {state.pid})")
            except Exception as e:
                logger.warning(f"Erreur stop exo {state.config.sigle} : {e}")
        state.statut = "arrete"
        state.pid = None
        state.stopped_at = now_iso()
        self._save_state()
        return state

    def stop_all(self) -> int:
        """Arrête toutes les instances exercice + le collecteur exercice.
        Retourne le nombre d'instances arrêtées."""
        n = 0
        for port, state in list(self.instances.items()):
            if state.pid and _pid_alive(state.pid):
                try:
                    self.stop(port)
                    n += 1
                except Exception:
                    pass
        # Puis le collecteur
        if self.collecteur_proc is not None:
            self.stop_collecteur()
        return n

    # ── Reset DBs exercice ───────────────────────────────────────────────────

    def reset_all_dbs(self) -> dict[str, Any]:
        """Supprime toutes les DBs exercice + l'état du collecteur exercice.

        Équivalent de `lancer_exercice.sh --reset` mais piloté depuis le master.
        Toutes les instances doivent être arrêtées avant.
        """
        # Vérifier qu'aucune instance n'est active
        actives = [
            s.config.sigle for s in self.instances.values()
            if s.pid and _pid_alive(s.pid)
        ]
        if actives:
            raise ValueError(
                f"Arrêtez d'abord les instances actives : {', '.join(actives)}"
            )
        if self.collecteur_proc is not None:
            pid = self.collecteur_proc.pid
            if pid and _pid_alive(pid):
                raise ValueError(
                    "Arrêtez d'abord le collecteur exercice :8565"
                )

        deleted = {"instances_dbs": 0, "collecteur_state_files": 0}

        # Purger les répertoires d'instances exercice
        if DATA_DIR_EXO.exists():
            import shutil
            for child in DATA_DIR_EXO.iterdir():
                if child.is_dir():
                    try:
                        shutil.rmtree(child, ignore_errors=True)
                        deleted["instances_dbs"] += 1
                    except Exception as e:
                        logger.warning(f"Reset {child} : {e}")

        # Purger les state files du collecteur exercice
        coll_dir = EXO_COLLECTEUR_SCRIPT.parent
        for fname in [
            "collecteur_exo_data.json",
            "collecteur_exo_tokens.json",
            "collecteur_exo_admin.json",
            "collecteur_exo_sessions.json",
            "collecteur_exo_transferts.json",
            "collecteur_exo_incidents.json",
            "collecteur_exo_decisions.json",
            "collecteur_exo_prets.json",
        ]:
            f = coll_dir / fname
            if f.exists():
                try:
                    f.unlink()
                    deleted["collecteur_state_files"] += 1
                except Exception as e:
                    logger.warning(f"Reset {f} : {e}")

        # Purger les scénarios générés (garde les démos example_*.json)
        scenarios_dir = PROJECT_ROOT / "scenarios"
        if scenarios_dir.exists():
            for f in scenarios_dir.iterdir():
                if f.is_file() and f.suffix == ".json" and not f.name.startswith("example_"):
                    try:
                        f.unlink()
                    except Exception:
                        pass

        # Reset des states d'instances dans master_instances_exercice.json
        # (PIDs déjà nuls, fed_tokens régénérés au prochain start)
        for state in self.instances.values():
            state.fed_token = None
            state.db_path = None
            state.log_path = None
            state.started_at = None
            state.stopped_at = None
        self._save_state()

        logger.info(f"Reset exercice : {deleted}")
        return deleted

    # ── Génération config.js + config.xml exercice ───────────────────────────

    def _generate_exo_config(
        self,
        state: ExerciceInstanceState,
        config_js_path: pathlib.Path,
        config_xml_path: pathlib.Path,
    ) -> None:
        """Génère config.js et config.xml pour une instance exercice.

        Symétrique de _generate_instance_config (mode prod) mais :
          - federation.collecteur_url → :8565 (au lieu de :9000)
          - exercice.mode = true (déclenche le bandeau dans index.html)
        """
        cfg = state.config
        push_url = f"http://localhost:{EXO_COLLECTEUR_PORT}/api/push"

        cfg_js = {
            "etablissement": {
                "nom":   cfg.nom,
                "sigle": cfg.sigle,
                "logo": "/static/logo-scribe.png",
            },
            "site": {
                "nom":       cfg.nom,
                "adresse":   cfg.adresse,
                "latitude":  cfg.latitude,
                "longitude": cfg.longitude,
            },
            "federation": {
                "enabled":             "true",
                "collecteur_url":      push_url,
                "token":               state.fed_token,
                "intervalle_secondes": 30,
                "share_details":       "true",
                "share_min_urgency":   1,
                "sync_crise":          "true",
                "sync_sanitaire":      "true",
                "share_capacite_details": "true",
            },
            # [EXO] Bloc spécifique mode exercice (lu par main.py + index.html)
            "exercice": {
                "mode":       True,
                "sigle":      cfg.sigle,
                "collecteur": f"http://localhost:{EXO_COLLECTEUR_PORT}",
            },
        }
        config_js_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_js_path, "w", encoding="utf-8") as f:
            f.write("const SCRIBE_CONFIG = ")
            f.write(json.dumps(cfg_js, ensure_ascii=False, indent=2))
            f.write(";\n")

        # Config XML minimal (federation lue par FederationConfig._load)
        xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<scribe>
  <etablissement>
    <nom>{_xml_escape(cfg.nom)} — Mode Exercice</nom>
    <sigle>{_xml_escape(cfg.sigle)}</sigle>
  </etablissement>
  <federation>
    <enabled>true</enabled>
    <collecteur_url>{push_url}</collecteur_url>
    <token>{state.fed_token}</token>
    <intervalle_secondes>30</intervalle_secondes>
  </federation>
</scribe>
"""
        config_xml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_xml_path, "w", encoding="utf-8") as f:
            f.write(xml_body)

    # ── Auto-enrôlement vers le collecteur exercice :8565 ────────────────────

    def _auto_enrol_exo(self, state: ExerciceInstanceState) -> None:
        """Pré-enregistre le token de l'instance auprès du collecteur exo :8565."""
        try:
            import urllib.request

            # Lire le token admin du collecteur exercice
            admin_file = EXO_COLLECTEUR_SCRIPT.parent / "collecteur_exo_admin.json"
            if not admin_file.exists():
                logger.warning(
                    "collecteur_exo_admin.json introuvable, pas d'auto-enrôlement. "
                    "Le collecteur exercice doit être démarré au moins une fois."
                )
                return
            with open(admin_file, encoding="utf-8") as f:
                admin_data = json.load(f)
            admin_token = admin_data.get("admin_token") or admin_data.get("token")
            if not admin_token:
                logger.warning("admin_token absent dans collecteur_exo_admin.json")
                return

            payload = json.dumps({
                "sigle": state.config.sigle,
                "token": state.fed_token,
                "nom":   state.config.nom,
                "latitude":  state.config.latitude,
                "longitude": state.config.longitude,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://localhost:{EXO_COLLECTEUR_PORT}/api/admin/tokens",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {admin_token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status >= 300:
                    logger.warning(f"Auto-enrôlement exo HTTP {resp.status}")
                else:
                    logger.info(f"Auto-enrôlement exo OK pour {state.config.sigle}")
        except Exception as e:
            logger.warning(f"Auto-enrôlement exo échoué : {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _xml_escape(s: str) -> str:
    return (
        str(s).replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace('"', "&quot;")
              .replace("'", "&apos;")
    )


def _kill_pid(pid: int) -> None:
    """Tue un processus de manière cross-platform."""
    if not pid:
        return
    try:
        if os.name == "posix":
            os.kill(pid, signal.SIGTERM)
        else:
            # Windows : taskkill /PID
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception:
        pass


def _port_in_use(port: int) -> bool:
    """Vérifie qu'un port TCP est déjà ouvert (cross-platform)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


class _AdoptedProcess:
    """Proxy minimal pour un PID adopté depuis le master_instances_exercice.json
    après un redémarrage du master, où on n'a plus le vrai Popen."""
    def __init__(self, pid: int):
        self.pid = pid
    def poll(self):
        return None if _pid_alive(self.pid) else 0
    def terminate(self):
        _kill_pid(self.pid)
    def wait(self, timeout=None):
        import time
        t0 = time.monotonic()
        while _pid_alive(self.pid):
            if timeout and (time.monotonic() - t0) > timeout:
                raise subprocess.TimeoutExpired(cmd="adopted", timeout=timeout)
            time.sleep(0.2)
    def kill(self):
        _kill_pid(self.pid)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_manager: ExerciceManager | None = None

def get_exercice_manager() -> ExerciceManager:
    global _manager
    if _manager is None:
        _manager = ExerciceManager()
    return _manager
