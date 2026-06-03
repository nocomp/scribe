#!/usr/bin/env python3
"""
seed_exercice_comptes.py — Comptes supplémentaires pour les exercices de crise.
Appelé après seed_demo_comptes.py pour ajouter les rôles spécifiques exercice.
Mot de passe : Exercice2026!
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, Base
from app.models import User
from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
PWD = "Exercice2026!"

COMPTES = [
    ("maternite",   "Sage-femme Coordinatrice",   "directeur"),
    ("reanimation", "Médecin Réanimateur",          "directeur"),
    ("samu",        "Coordination SAMU 15",         "utilisateur"),
    ("observateur", "Observateur Exercice",         "utilisateur"),
    ("cadrebloc",   "Cadre de Bloc Opératoire",    "directeur"),
    ("pharmacien",  "Pharmacien de Garde",          "utilisateur"),
]

db = SessionLocal()
created = 0
for username, display, role in COMPTES:
    if not db.query(User).filter_by(username=username).first():
        db.add(User(
            username=username,
            display_name=display,
            role=role,
            hashed_password=_ctx.hash(PWD),
            active=True,
            must_change_password=False,
        ))
        created += 1

# Forcer le mot de passe de dircrise en mode exercice
# (au cas où la DB existerait déjà avec Scribe2026!)
existing_admin = db.query(User).filter_by(username="dircrise").first()
if existing_admin:
    existing_admin.hashed_password = _ctx.hash(PWD)
    existing_admin.active = True
    created_str = "mis à jour"
else:
    created_str = str(created)

db.commit()
db.close()
print(f"  ✓ {created_str} comptes exercice — dircrise forcé à {PWD}")
