"""
core/plugin_state_model.py — SCRIBE v2.0.4
Modèle SQLAlchemy pour la persistance de l'état des plugins.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from app.database import Base


class PluginState(Base):
    """Persistance de l'état activé/désactivé de chaque plugin."""
    __tablename__ = "plugin_states"

    plugin_id  = Column(String, primary_key=True)
    enabled    = Column(Boolean, default=True, nullable=False)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    changed_by = Column(String, nullable=True)   # username de l'admin qui a modifié
