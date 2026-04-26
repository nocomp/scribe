#!/usr/bin/env python3
"""
tests/bench/bench.py — SCRIBE benchmark de validation bout-en-bout.

Lance en local 1 collecteur d'exercice + 2 instances SCRIBE (CHAG/GHTLMB),
exécute 5 scénarios critiques, produit un rapport console et un exit code
cohérent avec l'état des tests.

Usage :
    python3 tests/bench/bench.py
    python3 tests/bench/bench.py --verbose
    python3 tests/bench/bench.py --keep-running   # ne tue pas les instances à la fin

Prérequis :
    - Python 3.8+ avec fastapi, uvicorn, sqlalchemy, httpx (déjà requis par SCRIBE)
    - Ports 17900, 17901, 17902 libres
    - Être lancé depuis la racine de scribe (ou via tests/bench/run_bench.sh)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

# ── Configuration ──────────────────────────────────────────────────────
# Les ports 17900/17901/17902 sont délibérément au-dessus de la plage
# SCRIBE habituelle (8000, 8660-8666, 8565) pour éviter tout conflit
# avec une instance déjà en cours.
COLLECTEUR_PORT = 17900
CHAG_PORT       = 17901
GHTLMB_PORT     = 17902

COLLECTEUR_URL = f"http://127.0.0.1:{COLLECTEUR_PORT}"
CHAG_URL       = f"http://127.0.0.1:{CHAG_PORT}"
GHTLMB_URL     = f"http://127.0.0.1:{GHTLMB_PORT}"

BENCH_DIR   = Path(tempfile.mkdtemp(prefix="scribe_bench_"))
SCRIBE_ROOT = Path(__file__).resolve().parent.parent.parent  # racine scribe/

# ── Couleurs terminal ──────────────────────────────────────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

GREEN  = lambda s: _c("92", s)
RED    = lambda s: _c("91", s)
YELLOW = lambda s: _c("93", s)
CYAN   = lambda s: _c("96", s)
DIM    = lambda s: _c("2",  s)
BOLD   = lambda s: _c("1",  s)


# ── Utilitaires ────────────────────────────────────────────────────────
def log(msg: str, level: str = "info") -> None:
    prefix = {
        "info":  DIM("  ·"),
        "ok":    GREEN("  ✓"),
        "ko":    RED("  ✗"),
        "warn":  YELLOW("  !"),
        "step":  CYAN("  ▸"),
    }.get(level, "  ")
    print(f"{prefix} {msg}")


def port_free(port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_for_port(port: int, timeout_s: float = 15.0) -> bool:
    """Attend qu'un port accepte des connexions (instance prête)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.25)
    return False


def http(method: str, url: str, token: Optional[str] = None,
         json_body: Optional[dict] = None, timeout: float = 8.0) -> tuple[int, Any]:
    """Requête HTTP via httpx (déjà dépendance SCRIBE)."""
    import httpx
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.request(method, url, headers=headers, json=json_body)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except Exception as e:
        return 0, f"EXCEPTION: {e}"


# ── Config XML minimale générée pour le bench ──────────────────────────
CONFIG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<scribe>
  <etablissement>
    <nom>{nom}</nom>
    <sigle>{sigle}</sigle>
    <finess>{finess}</finess>
  </etablissement>
  <admin>
    <login>benchadmin</login>
    <password>BenchPass2026!</password>
    <nom_affiche>Benchmark Admin</nom_affiche>
  </admin>
  <sites>
    <site>
      <nom>{nom} — Site principal</nom>
      <adresse>Bench, 00000 Local</adresse>
      <latitude>45.9</latitude>
      <longitude>6.1</longitude>
      <telephone_garde>BENCH</telephone_garde>
    </site>
  </sites>
  <langue>fr</langue>
  <federation>
    <enabled>true</enabled>
    <collecteur_url>{collecteur_url}/api/push</collecteur_url>
    <token>{token}</token>
    <intervalle_secondes>10</intervalle_secondes>
    <share_details>true</share_details>
    <sync_sanitaire>true</sync_sanitaire>
  </federation>
</scribe>
"""


def write_config(sigle: str, finess: str, port: int, token: str) -> Path:
    path = BENCH_DIR / f"config_{sigle.lower()}.xml"
    path.write_text(CONFIG_TEMPLATE.format(
        nom=f"{sigle} Bench",
        sigle=sigle,
        finess=finess,
        collecteur_url=COLLECTEUR_URL,
        token=token,
    ))
    return path


# ── Gestion des process ────────────────────────────────────────────────
_processes: list[subprocess.Popen] = []


def start_collecteur() -> subprocess.Popen:
    """Démarre le collecteur exercice sur COLLECTEUR_PORT."""
    env = os.environ.copy()
    env["COLLECTEUR_PORT"] = str(COLLECTEUR_PORT)
    env["COLLECTEUR_DATA_DIR"] = str(BENCH_DIR / "collecteur_data")
    (BENCH_DIR / "collecteur_data").mkdir(exist_ok=True)
    log_file = open(BENCH_DIR / "collecteur.log", "w")
    p = subprocess.Popen(
        [sys.executable, "collecteur_exercice.py"],
        cwd=str(SCRIBE_ROOT / "collecteur_exercice"),
        env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )
    _processes.append(p)
    return p


def _bench_init_db(db_path: Path, admin_login: str, admin_password: str,
                   admin_display: str = "Benchmark Admin") -> None:
    """Initialise une DB SCRIBE vierge avec un utilisateur admin.

    Ne passe pas par setup.py (qui est interactif et lance main.py).
    Utilise directement SQLAlchemy + bcrypt pour créer la table users
    et y insérer l'admin. Suffit pour le bench : main.py créera les
    autres tables au démarrage via Base.metadata.create_all().
    """
    import bcrypt
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Import dynamique depuis la racine SCRIBE
    sys.path.insert(0, str(SCRIBE_ROOT))
    try:
        from app.models import Base, User
    finally:
        sys.path.pop(0)

    # Créer l'engine sur la DB vide (supprime si existe pour test propre)
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(bind=engine)

    # Créer l'utilisateur admin
    Session = sessionmaker(bind=engine)
    with Session() as s:
        hashed = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
        admin = User(
            username=admin_login,
            display_name=admin_display,
            role="admin",
            hashed_password=hashed,
            must_change_password=False,
            active=True,
        )
        s.add(admin)
        s.commit()

    engine.dispose()


def start_instance(sigle: str, port: int, config_path: Path) -> subprocess.Popen:
    """Démarre une instance SCRIBE sans passer par setup.py."""
    db_path = BENCH_DIR / f"{sigle.lower()}.db"
    config_js = BENCH_DIR / f"config_{sigle.lower()}.js"

    # Étape 1 : initialiser la DB directement (bypass setup.py interactif)
    _bench_init_db(db_path, "benchadmin", "BenchPass2026!", f"{sigle} Bench Admin")

    # Étape 2 : créer le config.js minimal attendu par main.py CSP
    config_js.write_text(f"""window.SCRIBE_CONFIG = {{
  etablissement: {{ sigle: "{sigle}", nom: "{sigle} Bench" }},
  collecteur_url: "{COLLECTEUR_URL}/api/push",
  federation_enabled: true,
  exercice_mode: false,
}};
""")

    # Étape 3 : lancer main.py
    run_env = os.environ.copy()
    run_env["DATABASE_URL"]       = f"sqlite:///{db_path}"
    run_env["SCRIBE_CONFIG_JS"]   = str(config_js)
    run_env["SCRIBE_CONFIG_FILE"] = str(config_path)
    run_env["SCRIBE_PORT"]        = str(port)
    # Important : aligner SCRIBE_ADMIN_USER avec l'admin qu'on a créé en base,
    # pour qu'ensure_admin() trouve l'user déjà présent et n'essaie pas de créer
    # un autre admin (qui crasherait sur le bug passlib/bcrypt 4+ connu).
    run_env["SCRIBE_ADMIN_USER"] = "benchadmin"
    run_env["SCRIBE_ADMIN_PASS"] = "BenchPass2026!"
    # Désactiver le plugin exercice pour ces instances (on reste en prod)
    run_env.pop("SCRIBE_EXERCICE_MODE", None)

    log_file = open(BENCH_DIR / f"{sigle.lower()}.log", "w")
    p = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(SCRIBE_ROOT), env=run_env,
        stdout=log_file, stderr=subprocess.STDOUT,
    )
    _processes.append(p)
    return p


def kill_all() -> None:
    for p in _processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(0.8)
    for p in _processes:
        try:
            if p.poll() is None:
                p.kill()
        except Exception:
            pass


# ── Scénarios ──────────────────────────────────────────────────────────
class Scenario:
    """Un scénario = une séquence d'étapes avec un résultat global."""
    def __init__(self, name: str, desc: str):
        self.name = name
        self.desc = desc
        self.steps: list[tuple[str, bool, str]] = []  # (nom, OK, détail)
        self.duration_s: float = 0.0

    def add(self, step_name: str, success: bool, detail: str = "") -> bool:
        self.steps.append((step_name, success, detail))
        return success

    @property
    def passed(self) -> bool:
        return all(s[1] for s in self.steps) and len(self.steps) > 0

    def print_summary(self, verbose: bool = False) -> None:
        icon = GREEN("✓") if self.passed else RED("✗")
        total = len(self.steps)
        ok_count = sum(1 for s in self.steps if s[1])
        timing = DIM(f"{self.duration_s:.2f}s")
        print(f"  {icon} {self.name:<28} ({ok_count}/{total} steps, {timing})")
        if verbose or not self.passed:
            for step_name, ok, detail in self.steps:
                sub_icon = GREEN("✓") if ok else RED("✗")
                print(f"      {sub_icon} {step_name}")
                if detail and (verbose or not ok):
                    for line in detail.split("\n"):
                        print(f"          {DIM(line)}")


def sc_01_health() -> Scenario:
    """Les 3 services répondent sur /health."""
    s = Scenario("01_health", "Les 3 services répondent sur /health")
    for label, url in [("collecteur", COLLECTEUR_URL), ("chag", CHAG_URL), ("ghtlmb", GHTLMB_URL)]:
        code, body = http("GET", f"{url}/health")
        s.add(f"GET {label}/health",
              code == 200,
              f"HTTP {code} — {str(body)[:200]}")
    return s


def sc_02_auth() -> Scenario:
    """Login fonctionne sur chaque instance."""
    s = Scenario("02_auth", "Login admin sur CHAG et GHTLMB")
    for label, url in [("chag", CHAG_URL), ("ghtlmb", GHTLMB_URL)]:
        code, body = http("POST", f"{url}/api/v1/auth/login",
                         json_body={"username": "benchadmin", "password": "BenchPass2026!"})
        tok = body.get("token") if isinstance(body, dict) else None
        s.add(f"POST {label}/auth/login",
              code == 200 and bool(tok),
              f"HTTP {code}, token présent: {bool(tok)} — {str(body)[:200] if not tok else 'OK'}")
    return s


def sc_03_incident_local() -> Scenario:
    """Créer un incident via API, vérifier qu'il est listé."""
    s = Scenario("03_incident_local", "Incident CHAG : create + relecture")
    # Login
    code, body = http("POST", f"{CHAG_URL}/api/v1/auth/login",
                     json_body={"username": "benchadmin", "password": "BenchPass2026!"})
    tok = body.get("token") if isinstance(body, dict) else None
    if not s.add("login chag", bool(tok),
                 f"HTTP {code} — {str(body)[:200] if not tok else 'OK'}"):
        return s

    # Créer un incident
    incident_payload = {
        "fait":       "Benchmark — incident auto",
        "analyse":    "Incident créé par le benchmark pour validation",
        "type_crise": "TECHNIQUE",
        "urgency":    2,
        "status":     "SIGNALÉ",
        "declarant_nom":   "Bench",
        "declarant_fonction": "Auto",
        "site_id":    "CHAG",  # string libre, pas de FK
    }
    code, body = http("POST", f"{CHAG_URL}/api/v1/sitrep/post",
                     token=tok, json_body=incident_payload)
    new_id = body.get("id") if isinstance(body, dict) else None
    if not s.add("POST /api/v1/sitrep/post", code < 300 and bool(new_id),
                 f"HTTP {code}, id={new_id} — {str(body)[:200] if not new_id else 'OK'}"):
        return s

    # Le relire
    code, body = http("GET", f"{CHAG_URL}/api/v1/sitrep/history", token=tok)
    found = isinstance(body, list) and any(
        i.get("id") == new_id and i.get("fait") == incident_payload["fait"]
        for i in body
    )
    s.add("GET /api/v1/sitrep/history contient notre incident",
          code == 200 and found,
          f"HTTP {code}, {len(body) if isinstance(body,list) else '?'} incidents, trouvé={found}")
    return s


def sc_04_transfert_federe() -> Scenario:
    """Transfert CHAG → GHTLMB via fédération collecteur.
    C'est le flow qui a bugué en 2182 et 2184, donc test-clef."""
    s = Scenario("04_transfert_federe", "Transfert CHAG → GHTLMB via collecteur")

    code, body = http("POST", f"{CHAG_URL}/api/v1/auth/login",
                     json_body={"username": "benchadmin", "password": "BenchPass2026!"})
    tok_chag = body.get("token") if isinstance(body, dict) else None
    if not s.add("login CHAG", bool(tok_chag), f"HTTP {code}"):
        return s

    # Créer un transfert côté CHAG
    transfert = {
        "unite_origine":            "Maternité Bench",
        "etablissement_origine":    "CHAG",
        "unite_destination":        "Réanimation Bench",
        "etablissement_destination":"GHTLMB",
        "site_destination":         "GHTLMB",
        "redacteur":                "Benchmark auto",
        "statut":                   "EN_COURS",
        "nom":                      "BenchPatient",
        "ipp":                      "BENCH-TRANSF-001",
        "motif":                    "Validation automatique fédération transferts",
        "mode_transport":           "SMUR",
        "urgence":                  "IMMEDIAT",
    }
    code, body = http("POST", f"{CHAG_URL}/api/v1/transferts",
                     token=tok_chag, json_body=transfert)
    tid = body.get("id") if isinstance(body, dict) else None
    if not s.add("POST transfert côté CHAG", code < 300 and bool(tid),
                 f"HTTP {code}, id={tid} — {str(body)[:400] if not tid else 'OK'}"):
        return s

    # Vérifier côté CHAG
    code, body = http("GET", f"{CHAG_URL}/api/v1/transferts", token=tok_chag)
    found_local = isinstance(body, list) and any(
        t.get("id") == tid for t in body
    )
    s.add("CHAG liste le transfert local",
          code == 200 and found_local,
          f"HTTP {code}, {len(body) if isinstance(body,list) else '?'} transferts")

    # Attendre un peu que le polling collecteur fasse son œuvre
    # (intervalle 10s dans la config ; on force une push direct pour accélérer)
    push_payload = dict(transfert)
    push_payload["id_local"] = tid
    push_payload["ght_emetteur_nom"] = "CHAG"
    push_payload["ght_destinataire"] = "GHTLMB"
    code, body = http("POST", f"{COLLECTEUR_URL}/api/push-transfert",
                     token="token_exo_demo1", json_body=push_payload)
    s.add("Push manuel du transfert vers le collecteur",
          code < 300 and isinstance(body, dict) and body.get("ok"),
          f"HTTP {code} — {str(body)[:200]}")

    # Vérifier côté GHTLMB
    code, body = http("GET",
                     f"{COLLECTEUR_URL}/api/transferts-en-cours?destinataire=GHTLMB",
                     token="token_exo_demo2")
    found_dest = isinstance(body, list) and any(
        t.get("id_local") == tid for t in body
    )
    s.add("GHTLMB voit le transfert entrant (via collecteur)",
          code == 200 and found_dest,
          f"HTTP {code}, {len(body) if isinstance(body,list) else '?'} entrants, "
          f"trouvé={found_dest}")
    return s


def sc_05_rapport_html() -> Scenario:
    """Le collecteur génère un rapport HTML téléchargeable."""
    s = Scenario("05_rapport_html", "Collecteur génère un rapport HTML valide")

    # Login UI animateur
    code, body = http("POST", f"{COLLECTEUR_URL}/api/ui/login",
                     json_body={"login": "animateur", "password": "Animateur2026!"})
    tok = body.get("token") if isinstance(body, dict) else None
    if not tok:
        # Fallback dircrise
        code, body = http("POST", f"{COLLECTEUR_URL}/api/ui/login",
                         json_body={"login": "dircrise", "password": "Exercice2026!"})
        tok = body.get("token") if isinstance(body, dict) else None
    if not s.add("login UI animateur collecteur", bool(tok),
                 f"HTTP {code} — {str(body)[:200] if not tok else 'OK'}"):
        return s

    # bilan-data
    code, body = http("GET", f"{COLLECTEUR_URL}/api/exercice/bilan-data", token=tok)
    has_keys = isinstance(body, dict) and all(
        k in body for k in ("meta", "stimuli", "sites", "generated_at")
    )
    s.add("GET /api/exercice/bilan-data",
          code == 200 and has_keys,
          f"HTTP {code}, keys présents={has_keys}")

    # rapport.html
    import httpx
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(f"{COLLECTEUR_URL}/api/exercice/rapport.html",
                     headers={"Authorization": f"Bearer {tok}"})
        content_type_ok = "text/html" in r.headers.get("content-type", "").lower()
        has_sections = all(
            marker in r.text for marker in
            ["Caractéristiques", "Radar", "Timeline", "chart.js", "radarChart"]
        )
        s.add("GET /api/exercice/rapport.html avec content-type text/html",
              r.status_code == 200 and content_type_ok,
              f"HTTP {r.status_code}, CT={r.headers.get('content-type')}")
        s.add("Rapport HTML contient les 5 sections clés",
              has_sections,
              f"Caractéristiques/Radar/Timeline/chart.js/radarChart")
    except Exception as e:
        s.add("GET rapport.html", False, f"EXCEPTION: {e}")
    return s


# ── Exécution ─────────────────────────────────────────────────────────
def run_all(verbose: bool = False) -> int:
    print()
    print(BOLD("╔" + "═"*62 + "╗"))
    print(BOLD("║  SCRIBE benchmark — validation bout-en-bout") + " "*18 + BOLD("║"))
    print(BOLD("╠" + "═"*62 + "╣"))
    print(BOLD("║  ") + f"Workspace : {BENCH_DIR}" + " "*(60-14-len(str(BENCH_DIR))) + BOLD("║"))
    print(BOLD("╚" + "═"*62 + "╝"))

    # ── Vérifier ports libres ──
    print()
    log("Vérification des ports", "step")
    all_free = True
    for port in (COLLECTEUR_PORT, CHAG_PORT, GHTLMB_PORT):
        if port_free(port):
            log(f"port {port} libre", "ok")
        else:
            log(f"port {port} DÉJÀ OCCUPÉ — arrêtez le process qui l'utilise", "ko")
            all_free = False
    if not all_free:
        return 2

    # ── Écrire les configs ──
    print()
    log("Génération des configs", "step")
    write_config("CHAG",   "740000001", CHAG_PORT,   "token_chag_bench")
    write_config("GHTLMB", "740000002", GHTLMB_PORT, "token_ghtlmb_bench")
    log(f"2 configs XML dans {BENCH_DIR}", "ok")

    # ── Démarrer le collecteur ──
    print()
    log("Démarrage du collecteur (port 17900)", "step")
    try:
        start_collecteur()
        if not wait_for_port(COLLECTEUR_PORT, timeout_s=10):
            log("Collecteur n'a pas démarré dans les 10s", "ko")
            log(f"Voir log : {BENCH_DIR}/collecteur.log", "warn")
            return 3
        log("collecteur prêt", "ok")
    except Exception as e:
        log(f"Échec démarrage collecteur : {e}", "ko")
        return 3

    # ── Démarrer les instances ──
    for sigle, port in [("CHAG", CHAG_PORT), ("GHTLMB", GHTLMB_PORT)]:
        print()
        log(f"Démarrage instance {sigle} (port {port})", "step")
        try:
            start_instance(sigle, port, BENCH_DIR / f"config_{sigle.lower()}.xml")
            if not wait_for_port(port, timeout_s=20):
                log(f"{sigle} n'a pas démarré dans les 20s", "ko")
                log(f"Voir log : {BENCH_DIR}/{sigle.lower()}.log", "warn")
                return 3
            log(f"{sigle} prêt", "ok")
        except Exception as e:
            log(f"Échec démarrage {sigle} : {e}", "ko")
            traceback.print_exc()
            return 3

    # Stabilisation (1s) pour laisser le polling collecteur s'initialiser
    time.sleep(1.0)

    # ── Exécuter les scénarios ──
    print()
    print(BOLD("  Exécution des scénarios"))
    print("  " + "─"*50)

    scenarios_fn = [
        sc_01_health,
        sc_02_auth,
        sc_03_incident_local,
        sc_04_transfert_federe,
        sc_05_rapport_html,
    ]
    scenarios: list[Scenario] = []
    for fn in scenarios_fn:
        t0 = time.time()
        try:
            s = fn()
        except Exception as e:
            s = Scenario(fn.__name__, "exception")
            s.add("exception non gérée", False, f"{type(e).__name__}: {e}")
            if verbose:
                traceback.print_exc()
        s.duration_s = time.time() - t0
        scenarios.append(s)
        s.print_summary(verbose=verbose)

    # ── Récapitulatif ──
    ok_count = sum(1 for s in scenarios if s.passed)
    total = len(scenarios)
    total_steps = sum(len(s.steps) for s in scenarios)
    ok_steps = sum(sum(1 for st in s.steps if st[1]) for s in scenarios)
    total_dur = sum(s.duration_s for s in scenarios)

    print()
    print(BOLD("╔" + "═"*62 + "╗"))
    if ok_count == total:
        print(BOLD("║  ") + GREEN(f"TOUS LES SCÉNARIOS OK  ({ok_count}/{total})")
              + " "*(40-len(f"TOUS LES SCÉNARIOS OK  ({ok_count}/{total})")) + BOLD("║"))
    else:
        print(BOLD("║  ") + RED(f"RÉGRESSIONS DÉTECTÉES  ({total-ok_count} échec(s) / {total})")
              + " "*(38-len(f"RÉGRESSIONS DÉTECTÉES  ({total-ok_count} échec(s) / {total})")) + BOLD("║"))
    print(BOLD("║  ") + f"Steps : {ok_steps}/{total_steps}   Durée : {total_dur:.2f}s"
          + " "*(58-len(f"Steps : {ok_steps}/{total_steps}   Durée : {total_dur:.2f}s")) + BOLD("║"))
    print(BOLD("║  ") + f"Logs détaillés : {BENCH_DIR}"
          + " "*(58-len(f"Logs détaillés : {BENCH_DIR}")) + BOLD("║"))
    print(BOLD("╚" + "═"*62 + "╝"))
    print()

    return 0 if ok_count == total else 1


def main():
    ap = argparse.ArgumentParser(description="SCRIBE benchmark")
    ap.add_argument("--verbose", action="store_true",
                    help="affiche le détail de chaque step")
    ap.add_argument("--keep-running", action="store_true",
                    help="ne pas tuer les instances à la fin (debug)")
    args = ap.parse_args()

    exit_code = 4
    try:
        exit_code = run_all(verbose=args.verbose)
    except KeyboardInterrupt:
        print()
        log("Interrompu par l'utilisateur", "warn")
        exit_code = 130
    finally:
        if args.keep_running:
            print()
            log(f"--keep-running : instances toujours actives", "warn")
            log(f"  Collecteur : {COLLECTEUR_URL}", "info")
            log(f"  CHAG       : {CHAG_URL}", "info")
            log(f"  GHTLMB     : {GHTLMB_URL}", "info")
            log(f"  Workspace  : {BENCH_DIR}", "info")
            log("Kill manuel : pkill -f 'main.py|collecteur_exercice'", "info")
        else:
            kill_all()
            # Nettoyer le workspace sauf si on a eu des échecs (pour debug)
            if exit_code == 0:
                shutil.rmtree(BENCH_DIR, ignore_errors=True)
            else:
                print(f"  {YELLOW('!')} Workspace conservé pour debug : {BENCH_DIR}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
