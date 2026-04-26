#!/usr/bin/env python3
"""
setup_collecteur_auth.py — Configure le login/mot de passe de la supervision SCRIBE.

Usage :
  python setup_collecteur_auth.py              → configure login/mdp interactif
  python setup_collecteur_auth.py -u USER -p PASS → configure sans interaction
  python setup_collecteur_auth.py --remove      → supprime la protection

Le fichier collecteur_ui_auth.json est créé dans le dossier du script.
Sans ce fichier, l'interface est accessible sans authentification.
"""
import sys, json, hashlib, getpass
from pathlib import Path

# Toujours créer le fichier dans le même dossier que ce script
AUTH_FILE = Path(__file__).parent / "collecteur_ui_auth.json"

if "--remove" in sys.argv:
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
        print("✓ Protection supprimée.")
    else:
        print("~ Aucune protection configurée.")
    sys.exit(0)

# Mode non-interactif : -u USER -p PASS
if "-u" in sys.argv and "-p" in sys.argv:
    idx_u = sys.argv.index("-u")
    idx_p = sys.argv.index("-p")
    login    = sys.argv[idx_u + 1]
    password = sys.argv[idx_p + 1]
else:
    print("\n  Configuration du login collecteur")
    print("  ─────────────────────────────────\n")
    login = input("  Identifiant : ").strip()
    if not login:
        print("✗ Identifiant vide.")
        sys.exit(1)
    password = getpass.getpass("  Mot de passe : ")
    if len(password) < 6:
        print("✗ Mot de passe trop court (6 caractères minimum).")
        sys.exit(1)
    confirm = getpass.getpass("  Confirmer : ")
    if password != confirm:
        print("✗ Mots de passe différents.")
        sys.exit(1)

h = hashlib.sha256(password.encode()).hexdigest()
AUTH_FILE.write_text(json.dumps({"login": login, "password_hash": h}, indent=2))
print(f"\n  ✓ Protection configurée.")
print(f"  Login  : {login}")
print(f"  Fichier: {AUTH_FILE}")
print(f"\n  Relancez le collecteur : python collecteur.py")
