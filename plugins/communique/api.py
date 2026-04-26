"""
plugins/communique/api.py — SCRIBE v2.1.1
Délègue vers app.api.status_page pour éviter le doublon de modèles SQLAlchemy.
"""
from app.api.status_page import router  # noqa — re-export direct
