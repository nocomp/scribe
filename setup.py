#!/usr/bin/env python3
"""
setup.py — SCRIBE v1.5.0 — Script de démarrage interactif
Équivalent Linux/macOS du SETUP.bat Windows

Usage :
    python setup.py                  ← menu interactif
    python setup.py config.xml       ← initialiser depuis un XML directement
    python setup.py --demo1          ← démo CHV Valmont sans menu
    python setup.py --demo2          ← démo CSBM Montrelay sans menu
"""

import sys
import os
import subprocess
import shutil
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ── Couleurs terminal ──────────────────────────────────────────────────
def _c(code, text): return f"\033[{code}m{text}\033[0m"
def cyan(t):   return _c("96", t)
def green(t):  return _c("92", t)
def yellow(t): return _c("93", t)
def red(t):    return _c("91", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)
def ok(msg):   print(f"  {green('✓')}  {msg}")
def warn(msg): print(f"  {yellow('⚠')}  {msg}")
def err(msg):  print(f"  {red('✗')}  {msg}")
def banner(msg): print(f"\n  {cyan(msg)}")

def run(cmd, exit_on_error=True):
    result = subprocess.run(cmd, shell=True, cwd=BASE_DIR)
    if result.returncode != 0 and exit_on_error:
        err(f"Commande échouée : {cmd}")
        input("\n  Appuyez sur Entrée pour continuer...")
    return result.returncode

def python_cmd():
    for cmd in ("python3", "python"):
        if shutil.which(cmd):
            return cmd
    return None

def check_python():
    py = python_cmd()
    if not py:
        err("Python introuvable. Installez Python 3.8+ : https://www.python.org")
        sys.exit(1)
    return py

def check_docker():
    if shutil.which("docker"):
        result = subprocess.run("docker --version", shell=True, capture_output=True)
        return result.returncode == 0
    return False

def delete_file(rel_path):
    full = os.path.join(BASE_DIR, rel_path)
    if os.path.exists(full):
        os.remove(full)

def delete_db():
    delete_file("scribe.db")

def delete_config_js():
    delete_file(os.path.join("app", "static", "config.js"))

def print_header():
    print()
    print(cyan("  ====================================================="))
    print(cyan("   SCRIBE v1.5.0 beta — Configuration initiale"))
    print(cyan("   github.com/nocomp/scribe  (branche : beta)"))
    print(cyan("  ====================================================="))
    print()

def menu():
    print_header()
    while True:
        print("  Choisissez un mode :\n")
        print(f"   {bold('1')}  {green('Démo ransomware LockBit 48h')} (CHV Valmont — recommandé pour découvrir SCRIBE)")
        print(f"   {bold('2')}  {green('Démo clinique Montrelay')}")
        print(f"   {bold('3')}  {yellow('Supervision multi-établissements')} (démo 4 GHTs + collecteur Example Network)")
        print(f"   {bold('4')}  {cyan('Mon établissement')} (depuis config.xml)")
        print(f"   {bold('5')}  {cyan('Mon établissement')} (depuis fichier Excel SCRIBE_config_etablissement.xlsx)")
        print(f"   {bold('6')}  Docker")
        print(f"   {bold('7')}  Quitter")
        print()
        choix = input("  Votre choix (1-7) : ").strip()
        print()
        if choix == "1":    demo1()
        elif choix == "2":  demo2()
        elif choix == "3":  supervision()
        elif choix == "4":  from_xml()
        elif choix == "5":  from_excel()
        elif choix == "6":  docker_menu()
        elif choix == "7":  print(dim("  Au revoir.\n")); sys.exit(0)
        else:               warn("Choix invalide.")
        print()

def demo1():
    banner("[DÉMO 1] Centre Hospitalier de Valmont — Scénario ransomware LockBit")
    py = check_python()
    delete_db(); delete_config_js()
    if run(f"{py} setup_demo1.py") != 0: return
    run(f"{py} setup_capacite_demo.py", exit_on_error=False)
    if run(f"{py} seed_demo_crise.py") != 0: return
    demarrer()

def demo2():
    banner("[DÉMO 2] Clinique Saint-Benoît de Montrelay")
    py = check_python()
    delete_db(); delete_config_js()
    if run(f"{py} setup_demo2.py") != 0: return
    demarrer()

def supervision():
    banner("[SUPERVISION] Démo 4 GHTs + collecteur territorial (Example Network)")
    print()
    print("  Ce mode démarre 5 services :")
    print(f"  {dim('→')} Collecteur      : http://localhost:9000")
    print(f"  {dim('→')} Site 1 (8000)   : http://localhost:8000")
    print(f"  {dim('→')} Site 2 (8001)   : http://localhost:8001")
    print(f"  {dim('→')} Site 3 (8002)   : http://localhost:8002")
    print(f"  {dim('→')} Site 4 (8003)   : http://localhost:8003")
    print()
    script = os.path.join(BASE_DIR, "lancer_arc_alpin.sh")
    if not os.path.exists(script):
        err("lancer_arc_alpin.sh introuvable.")
        warn("Ce script est fourni dans la version de déploiement multi-GHT.")
        input("\n  Appuyez sur Entrée pour revenir au menu...")
        return
    reset = input("  Réinitialiser les bases de données ? (o/N) : ").strip().lower()
    print()
    flag = "--reset" if reset in ("o", "oui", "y", "yes") else ""
    run(f"bash lancer_arc_alpin.sh {flag}")

def from_xml(xml_file=None):
    banner("[MON ÉTABLISSEMENT] Initialisation depuis config.xml")
    py = check_python()
    if not xml_file:
        defaut = os.path.join(BASE_DIR, "config.xml")
        saisie = input(f"  Fichier XML [{defaut}] : ").strip()
        xml_file = saisie if saisie else defaut
    if not os.path.exists(xml_file):
        err(f"Fichier introuvable : {xml_file}")
        warn("Copiez config.xml et personnalisez-le, puis relancez.")
        input("\n  Appuyez sur Entrée pour continuer...")
        return
    try:
        root = ET.parse(xml_file).getroot()
        sigle = (root.findtext("etablissement/sigle") or "scribe").lower().replace(" ", "_")
        login = root.findtext("admin/login") or "dircrise"
        db_name = f"scribe_{sigle}.db"
    except Exception:
        sigle, login, db_name = "scribe", "dircrise", "scribe.db"

    db_path = os.path.join(BASE_DIR, db_name)
    print(f"\n  {dim('→')} Base : {db_name} | Config : {xml_file}")

    if os.path.exists(db_path):
        confirm = input(f"\n  {yellow('⚠')}  La base {db_name} existe. Réinitialiser ? (o/N) : ").strip().lower()
        if confirm in ("o", "oui", "y", "yes"):
            os.remove(db_path); ok(f"Base supprimée : {db_name}")
            delete_config_js()
        else:
            ok("Base conservée")
    else:
        delete_config_js()

    # Appeler l'initialisation
    env = os.environ.copy()
    env["SCRIBE_CONFIG_FILE"] = os.path.abspath(xml_file)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    # (pas de relance récursive setup.py — from_xml() gère déjà l'init)

    _print_demarrer("8000", login, sigle.upper())
    env["SCRIBE_PORT"] = "8000"
    env["SCRIBE_CONFIG_JS"] = os.path.join(BASE_DIR, "app", "static", "config.js")
    subprocess.run(f"{py} main.py", shell=True, cwd=BASE_DIR, env=env)
    input("\n  Appuyez sur Entrée pour continuer...")

def from_excel():
    banner("[MON ÉTABLISSEMENT] Import depuis fichier Excel")
    py = check_python()
    xlsx = os.path.join(BASE_DIR, "SCRIBE_config_etablissement.xlsx")
    if not os.path.exists(xlsx):
        err("SCRIBE_config_etablissement.xlsx introuvable.")
        warn("Placez le fichier Excel dans ce dossier et relancez.")
        input("\n  Appuyez sur Entrée pour continuer...")
        return
    delete_db(); delete_config_js()
    if run(f"{py} import_config_xlsx.py SCRIBE_config_etablissement.xlsx") != 0:
        return
    demarrer()

def docker_menu():
    banner("[DOCKER]")
    if not check_docker():
        err("Docker introuvable.")
        warn("Installez Docker : https://docs.docker.com/engine/install/")
        input("\n  Appuyez sur Entrée pour continuer...")
        return
    ok("Docker détecté")
    print()
    print(f"   {bold('1')}  Démo (mode par défaut — aucun fichier requis)")
    print(f"   {bold('2')}  Mon établissement (monte config.xml en volume)")
    print(f"   {bold('3')}  Retour")
    print()
    dsub = input("  Votre choix (1-3) : ").strip()
    print()
    if dsub == "1":
        if run("docker compose up -d") != 0: return
        ok("SCRIBE → http://localhost:8000  |  login: dircrise / Scribe2026!")
        print(f"  {dim('Logs : docker compose logs -f')}")
        input("\n  Appuyez sur Entrée...")
    elif dsub == "2":
        if not os.path.exists(os.path.join(BASE_DIR, "config.xml")):
            err("config.xml introuvable."); input("\n  Entrée..."); return
        run("docker compose up -d")
        run("docker cp config.xml scribe:/data/config.xml")
        run("docker restart scribe")
        ok("SCRIBE → http://localhost:8000")
        input("\n  Appuyez sur Entrée...")

def demarrer():
    py = check_python()
    _print_demarrer("8000", "dircrise", "SCRIBE")
    run(f"{py} main.py", exit_on_error=False)
    input("\n  Appuyez sur Entrée pour continuer...")

def _print_demarrer(port, login, sigle):
    print()
    print(cyan("  ====================================================="))
    print(cyan(f"   SCRIBE [{sigle}] → http://localhost:{port}"))
    print(cyan(f"   Login    : {login}"))
    print(cyan("   Password : Scribe2026! (ou celui défini dans config.xml)"))
    print(cyan("  ====================================================="))
    print()
    print(f"  {dim('Ctrl+C pour arrêter')}\n")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--demo1":
        print_header(); demo1()
    elif args and args[0] == "--demo2":
        print_header(); demo2()
    elif args and args[0].endswith(".xml"):
        print_header(); from_xml(xml_file=args[0])
    else:
        try:
            menu()
        except KeyboardInterrupt:
            print(f"\n\n  {dim('Interruption. Au revoir.')}\n")
            sys.exit(0)
