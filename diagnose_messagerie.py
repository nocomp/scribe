#!/usr/bin/env python3
"""
diagnose_messagerie.py — Diagnostic pas-à-pas du plugin messagerie
==================================================================
Usage :
    cd /chemin/vers/scribe_v3000h40c-messagerie
    python3 diagnose_messagerie.py

Détecte précisément quelle étape du chargement plante.
"""
import sys
import traceback
from pathlib import Path

# S'assurer qu'on est dans le bon répertoire
HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

print("=" * 70)
print("DIAGNOSTIC PLUGIN MESSAGERIE — v3.6.0-alpha6")
print("=" * 70)
print(f"Répertoire courant : {HERE}")
print(f"Python : {sys.version}")
print()

# ── Étape 1 : python-multipart ──────────────────────────────────────────────
print("[1/7] Test python-multipart …")
try:
    import multipart
    print(f"   ✓ import multipart OK, version = {getattr(multipart, '__version__', '?')}")
except ImportError as e:
    print(f"   ✗ import multipart ÉCHEC : {e}")
    print()
    print("   → SOLUTION : pip install --break-system-packages python-multipart")
    print()
    sys.exit(1)

try:
    import python_multipart  # alias récent
    print(f"   ✓ import python_multipart OK")
except ImportError:
    print(f"   ℹ python_multipart non importable (OK sur anciennes versions)")

# ── Étape 2 : FastAPI ───────────────────────────────────────────────────────
print()
print("[2/7] Test FastAPI …")
try:
    import fastapi
    print(f"   ✓ fastapi version = {fastapi.__version__}")
    from fastapi import UploadFile, File, Form
    print(f"   ✓ UploadFile, File, Form importables")
except Exception as e:
    print(f"   ✗ FastAPI : {e}")
    sys.exit(1)

# ── Étape 3 : Modèles SQLAlchemy du plugin ──────────────────────────────────
print()
print("[3/7] Test plugins/messagerie/models.py …")
try:
    # IMPORTANT : importer d'abord app.models pour que `users` soit enregistrée
    # dans la Base partagée avant que nos FK ne s'y réfèrent.
    from app import models as _appmodels  # noqa: F401
    print(f"   ✓ app.models importé (users table = {_appmodels.User.__tablename__})")
    from plugins.messagerie.models import (
        Base, Message, Folder, MessageAttachment, migrate_from_legacy
    )
    print(f"   ✓ Models importés : Message, Folder, MessageAttachment")
    tables = [t.name for t in Base.metadata.sorted_tables]
    msg_tables = [t for t in tables if t.startswith('messagerie_')]
    print(f"   ✓ Tables messagerie déclarées : {msg_tables}")
except Exception as e:
    print(f"   ✗ ÉCHEC import models : {e}")
    traceback.print_exc()
    print()
    print("   → Le bug est dans models.py — voir traceback ci-dessus")
    sys.exit(1)

# ── Étape 4 : Routes du plugin (import sans côté serveur) ───────────────────
print()
print("[4/7] Test plugins/messagerie/routes.py …")
try:
    from plugins.messagerie.routes import router
    n_routes = len(router.routes)
    print(f"   ✓ Router importé, {n_routes} routes définies")
    if n_routes < 10:
        print(f"   ⚠ Nombre de routes faible — peut-être qu'une route a planté ?")
    for r in router.routes[:5]:
        try:
            methods = list(r.methods)[0] if r.methods else '?'
            print(f"     - {methods:6s} {r.path}")
        except AttributeError:
            pass
    if n_routes > 5:
        print(f"     ... et {n_routes - 5} autres")
except Exception as e:
    print(f"   ✗ ÉCHEC import routes.py : {e}")
    traceback.print_exc()
    print()
    print("   → Le bug est dans routes.py — voir traceback ci-dessus")
    sys.exit(1)

# ── Étape 5 : Base de données SCRIBE ────────────────────────────────────────
print()
print("[5/7] Test connexion base SCRIBE …")
try:
    from app.database import engine, SessionLocal
    print(f"   ✓ engine importé : {engine.url}")
    with engine.connect() as conn:
        print(f"   ✓ connexion DB OK")
except Exception as e:
    print(f"   ✗ ÉCHEC DB : {e}")
    traceback.print_exc()
    sys.exit(1)

# ── Étape 6 : Création des tables ───────────────────────────────────────────
print()
print("[6/7] Test création tables messagerie_* …")
try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print(f"   ✓ Tables créées/vérifiées")
    # Vérifier qu'elles existent vraiment
    from sqlalchemy import inspect
    insp = inspect(engine)
    existing = insp.get_table_names()
    for needed in ("messagerie_messages", "messagerie_folders", "messagerie_attachments"):
        if needed in existing:
            print(f"     ✓ {needed} existe dans la DB")
        else:
            print(f"     ✗ {needed} ABSENTE de la DB !")
except Exception as e:
    print(f"   ✗ ÉCHEC création tables : {e}")
    traceback.print_exc()
    sys.exit(1)

# ── Étape 7 : Migration depuis MessageInterne ───────────────────────────────
print()
print("[7/7] Test migration depuis MessageInterne (lecture seule) …")
try:
    from app.models import MessageInterne
    db = SessionLocal()
    try:
        n_legacy = db.query(MessageInterne).count()
        print(f"   ✓ MessageInterne (legacy) : {n_legacy} messages")
        n_new = db.query(Message).count()
        print(f"   ✓ Message (nouveau) : {n_new} messages")
        if n_legacy > 0 and n_new == 0:
            print(f"   ℹ Migration pas encore lancée — sera faite au boot SCRIBE")
        elif n_legacy > 0 and n_new > 0:
            print(f"   ✓ Migration déjà effectuée")
    finally:
        db.close()
except Exception as e:
    print(f"   ⚠ Erreur lecture migration : {e}")
    print(f"     (non-bloquant — le plugin peut quand même fonctionner)")

# ── Test final : import du module plugin lui-même ───────────────────────────
print()
print("=" * 70)
print("Test FINAL : import du module plugins.messagerie.plugin …")
try:
    from plugins.messagerie import plugin as msg_plugin
    print(f"   ✓ Module plugin importé")
    print(f"   ✓ MANIFEST = {msg_plugin.MANIFEST}")
    print(f"   ✓ register() existe : {callable(msg_plugin.register)}")
except Exception as e:
    print(f"   ✗ ÉCHEC import plugin.py : {e}")
    traceback.print_exc()
    sys.exit(1)

# ── Conclusion ──────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("✓✓✓ TOUS LES TESTS PASSENT — Le plugin DEVRAIT se charger au démarrage SCRIBE.")
print("=" * 70)
print()
print("Si malgré ce diagnostic OK le serveur SCRIBE n'enregistre toujours pas")
print("les routes /api/v1/messagerie/*, c'est probablement :")
print("  1. Le serveur SCRIBE tourne avec un AUTRE Python que celui qui a réussi")
print("     ce diagnostic. Vérifier :")
print("       which python3        # Doit être identique à celui utilisé par main.py")
print("       ps aux | grep main.py")
print("  2. Le serveur n'a pas été redémarré APRÈS l'install de python-multipart.")
print("     Solution : pkill -f main.py && bash lancer_scribe.sh")
print("  3. config.py n'a pas PLUGINS['messagerie']=True OU il y a une surcharge")
print("     en DB qui désactive le plugin. Vérifier :")
print("       grep messagerie config.py")
print("       sqlite3 scribe.db 'SELECT * FROM plugin_states WHERE plugin_id=\"messagerie\";'")
print()
