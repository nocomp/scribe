"""
database.py — Connexion SQLite auto-suffisante, sans dépendance externe.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os as _os_sec

def _secure_db_file(path):
    """v2.5.0 patch sécu M7: chmod 600 sur les fichiers DB SQLite."""
    try:
        if path and _os_sec.path.exists(path):
            _os_sec.chmod(path, 0o600)
    except Exception:
        pass

# DATABASE_URL : variable d'environnement prioritaire (Docker),
# sinon chemin local par défaut (déploiement direct)
DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "sqlite:///" + os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scribe.db"
    )
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)
# v2.5.0 patch sécu M7: sécuriser la DB après création
if engine.url.drivername == "sqlite" and engine.url.database:
    _secure_db_file(engine.url.database)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency FastAPI : fournit une session DB et la ferme proprement."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
