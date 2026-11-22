"""
collecteur/messagerie_mount.py — v3000h48
=========================================
Embarque le **vrai** plugin messagerie (plugins/messagerie) DANS le service
collecteur, sur une base dédiée, avec une identité « supervision ». Objectif :
la messagerie de la supervision est *exactement le même module* que celui des
instances (mêmes modèles, mêmes routes /api/v1/messagerie/*).

Principe :
  - On fixe DATABASE_URL vers une base propre au collecteur AVANT d'importer
    app.database (sinon la base par défaut scribe.db serait utilisée).
  - On ajoute la racine du dépôt au sys.path pour pouvoir importer `app.*` et
    `plugins.messagerie.*` tels quels (zéro fork du plugin).
  - On crée les tables (users + messagerie) et un compte « supervision ».
  - On surcharge la dépendance get_current_user : le collecteur EST la
    supervision (identité unique), authentifiée par ailleurs via l'admin du
    collecteur — donc toutes les routes messagerie agissent en tant que
    « supervision ».
"""
import os
import sys
import logging

logger = logging.getLogger("scribe.collecteur.messagerie")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collecteur_messagerie.db")

# 1) Base dédiée AVANT tout import de app.database
os.environ.setdefault("DATABASE_URL", "sqlite:///" + _DB_PATH)
# 2) Racine du dépôt importable
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

SUPERVISION_USERNAME = "supervision"
_supervision_user = None
_ready = False


def _bootstrap_db():
    """Crée les tables (users + messagerie) et le compte supervision."""
    global _supervision_user
    from app.database import engine, SessionLocal, Base
    from app import models as app_models          # enregistre la table users
    from plugins.messagerie import models as msg_models  # enregistre messagerie_*

    Base.metadata.create_all(bind=engine, checkfirst=True)

    db = SessionLocal()
    try:
        User = app_models.User
        u = db.query(User).filter(User.username == SUPERVISION_USERNAME).first()
        if not u:
            u = User(
                username=SUPERVISION_USERNAME,
                display_name="Supervision",
                role="cellule_crise",
                active=True,
            )
            # mot de passe non utilisé (auth surchargée) mais champ non-null
            if hasattr(u, "hashed_password"):
                try:
                    from app.api.auth import hash_password
                    u.hashed_password = hash_password("supervision-local-only")
                except Exception:
                    u.hashed_password = "x"
            db.add(u)
            db.commit()
            db.refresh(u)
            logger.info("[messagerie-collecteur] compte 'supervision' créé (id=%s)", u.id)
        _supervision_user = {"id": u.id, "username": u.username,
                             "display_name": u.display_name, "role": u.role}
    finally:
        db.close()


def mount(app, token_validator=None):
    """Monte le router messagerie sur l'app FastAPI du collecteur.

    token_validator(token:str)->bool : si fourni, l'identité « supervision » n'est
    rendue que si le token (header Authorization Bearer OU ?token= pour les liens
    de PJ) est validé. Sinon 401. C'est ce qui ferme l'IDOR : sans le token du
    collecteur, aucun accès aux messages / pièces jointes.
    """
    global _ready
    try:
        _bootstrap_db()
        from app.database import SessionLocal
        from app.models import User
        from app.api.auth import get_current_user
        from plugins.messagerie.routes import router as messagerie_router
        from fastapi import Request, HTTPException

        # get_current_user → vérifie l'auth du collecteur, puis renvoie « supervision ».
        def _supervision_current_user(request: Request):
            if token_validator is not None:
                tok = ""
                auth = request.headers.get("authorization") or ""
                if auth.lower().startswith("bearer "):
                    tok = auth[7:].strip()
                if not tok:
                    tok = request.query_params.get("token", "") or ""
                if not token_validator(tok):
                    raise HTTPException(status_code=401, detail="Authentification supervision requise")
            db = SessionLocal()
            try:
                return db.query(User).filter(User.username == SUPERVISION_USERNAME).first()
            finally:
                db.close()

        app.dependency_overrides[get_current_user] = _supervision_current_user
        app.include_router(messagerie_router, prefix="/api/v1/messagerie", tags=["MESSAGERIE"])
        _ready = True
        logger.info("[messagerie-collecteur] plugin messagerie monté sur /api/v1/messagerie (base=%s)", _DB_PATH)
    except Exception as e:
        logger.error("[messagerie-collecteur] échec du montage : %s", e, exc_info=True)
        _ready = False
    return _ready


def supervision_user():
    return _supervision_user
