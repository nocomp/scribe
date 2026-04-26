"""
plugins/inter_ght/api.py — SCRIBE v2.0.6
Demandes et declarations inter-GHT.
Migration depuis app/api/v140.py (fonctions interght + declarations + supervision).
"""
from fastapi import APIRouter
# Import depuis v140 le temps de la migration complete
# Les routes sont re-enregistrees sous /api/v1/interght par plugin.py
from app.api.v140 import router as _v140_router

# On cree un router propre qui delegue vers v140 le temps de la migration
router = APIRouter()

# Note : les endpoints /interght/* et /declarations/* et /supervision/*
# restent dans v140.router pour l instant.
# Prochaine etape : extraire chaque groupe dans ce fichier.
