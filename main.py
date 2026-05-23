"""
main.py — SCRIBE v2.4.8.3
"""
import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import engine, Base
import app.models  # noqa
import app.api.status_page  # noqa — enregistre les tables StatusPage
from app.api import status_page  # v2.4.8.3 — explicitement pour include_router

from app.api import sitrep, cartographie, attachments, i18n
from app.api import auth, tasks
from app.api import v140
from app.api import scenario_export  # v2.4.8.3 — Générateur scénario depuis crise
from app.api import lang_admin  # v2.4.8.3 — Admin sélection langue
from app.api import mfa as mfa_module  # v2315 — MFA TOTP
from app.api import admin_uf  # v2.4.8.3 — Admin UF (activer/désactiver/éditer)
from core import admin_plugins
from core.plugin_loader import load_all_plugins, get_loaded_plugins

# v2.4.8.3 — Importer les modèles des plugins avant create_all pour que
# SQLAlchemy découvre toutes les tables (sinon les tables du plugin
# notifications ne seraient créées qu'au premier appel API).
try:
    from plugins.notifications import models as _notif_models  # noqa: F401
except Exception:
    pass  # plugin optionnel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scribe")

Base.metadata.create_all(bind=engine)

# ── Middleware sécurité HTTP headers ─────────────────────────────────────────

def _build_csp() -> str:
    """Construit la CSP dynamiquement en incluant l'origine du collecteur
    configurée dans config.js, ainsi que toutes les origines CORS autorisées.
    Appelé une seule fois au démarrage."""
    import json as _json, pathlib as _pl

    # Origines autorisées pour connect-src :
    # 1. self (même origine)
    # 2. OSRM routing
    # 3. Collecteur depuis config.js (URL du /api/push → extraire l'origine)
    # 4. Toutes les origines CORS configurées (pour inter-instances)
    connect_origins = {"'self'", "router.project-osrm.org", "unpkg.com", "cdnjs.cloudflare.com", "cdn.jsdelivr.net"}

    # Lire le collecteur depuis config.js
    try:
        config_js = os.environ.get(
            "SCRIBE_CONFIG_JS",
            str(_pl.Path(__file__).parent / "app" / "static" / "config.js")
        )
        if _pl.Path(config_js).exists():
            raw = _pl.Path(config_js).read_text(encoding="utf-8")
            start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
            end = raw.rfind(";")
            cfg = _json.loads(raw[start:end])
            coll_url = cfg.get("federation", {}).get("collecteur_url", "")
            if coll_url:
                # Extraire l'origine (scheme://host:port)
                from urllib.parse import urlparse
                parsed = urlparse(coll_url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                connect_origins.add(origin)
    except Exception as e:
        logger.warning(f"CSP: impossible de lire config.js pour collecteur_url: {e}")

    # Ajouter les origines CORS configurées (inter-instances)
    # Lire directement depuis l'env (évite la dépendance à _allowed_origins)
    _cors_env = os.getenv(
        "SCRIBE_ALLOWED_ORIGINS",
        ",".join([f"http://localhost:{p}" for p in list(range(8000, 8010)) + list(range(6560, 6568)) + [9000, 7474, 7373]])
    )
    for orig in _cors_env.split(","):
        orig = orig.strip()
        if orig:
            connect_origins.add(orig)

    connect_src = " ".join(sorted(connect_origins))

    # TODO ANSSI: retirer 'unsafe-inline' de script-src et style-src en migrant
    # vers des nonces CSP. Chantier non trivial (refactor des onclick inline).
    # En attendant, mitigation via Permissions-Policy stricte + Referrer-Policy.
    # frame-ancestors : autoriser self + origines configurées (pour iframe master)
    frame_ancestors_extra = os.getenv("SCRIBE_FRAME_ANCESTORS", "http://localhost:8565")

    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' unpkg.com cdnjs.cloudflare.com cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com unpkg.com cdnjs.cloudflare.com; "
        "font-src 'self' fonts.gstatic.com data:; "
        "img-src 'self' data: blob: *.basemaps.cartocdn.com *.tile.openstreetmap.org "
        "server.arcgisonline.com unpkg.com cdnjs.cloudflare.com; "
        f"connect-src {connect_src}; "
        "worker-src 'self'; "
        f"frame-ancestors 'self' {frame_ancestors_extra}"
    )

# Calculer la CSP une fois au démarrage (après _allowed_origins)
_CSP = _build_csp()
logger.info(f"CSP connect-src configurée")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # X-Frame-Options géré par frame-ancestors dans CSP
        response.headers["X-XSS-Protection"] = "0"  # v2.5.0: header déprécié, protection via CSP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = _CSP
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app = FastAPI(title="SCRIBE v2.5.0 Crisis OS", version="2.5.0")

# CORS — restreint aux origines configurées (jamais wildcard en prod)
_VPS = "http://localhost"
_ALL_PORTS = list(range(8000, 8010)) + list(range(6560, 6568)) + [9000, 7474, 7373]
_allowed_origins = os.getenv(
    "SCRIBE_ALLOWED_ORIGINS",
    ",".join([
        *[f"http://localhost:{p}" for p in _ALL_PORTS],
        *[f"http://127.0.0.1:{p}" for p in _ALL_PORTS],
        *[f"{_VPS}:{p}" for p in _ALL_PORTS],
    ])
).split(",")

# Les requêtes same-origin (même hôte:port) ne passent pas par CORS —
# allow_origins couvre uniquement les vraies requêtes cross-origin.
# En production, définir SCRIBE_ALLOWED_ORIGINS avec l'URL publique.
app.add_middleware(CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    allow_credentials=False,
    max_age=600
)
app.add_middleware(SecurityHeadersMiddleware)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "app", "static")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static",  StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ── Core (toujours actif) ──────────────────────────────────────────────────
app.include_router(sitrep.router,       prefix="/api/v1/sitrep",       tags=["Incidents"])
app.include_router(cartographie.router, prefix="/api/v1/cartographie", tags=["Cartographie"])
app.include_router(attachments.router,  prefix="/api/v1/attachments",  tags=["PJ"])
app.include_router(auth.router,         prefix="/api/v1/auth",         tags=["Auth"])
app.include_router(tasks.router,        prefix="/api/v1/tasks",        tags=["Kanban"])
app.include_router(i18n.router,         prefix="",                     tags=["i18n"])
# ── Admin plugins ──────────────────────────────────────────────────────────
app.include_router(admin_plugins.router, prefix="/api/v1/admin",       tags=["Admin Plugins"])
# v2.4.8.3 — Export scénario depuis une crise passée (crise → rejouable)
app.include_router(scenario_export.router)
# v2.4.8.3 — Changement de langue depuis l'admin (style WordPress)
app.include_router(lang_admin.router)
# v2315 — MFA TOTP (activation par l'utilisateur, vérification login phase 2)
app.include_router(mfa_module.router)
# v2.4.8.3 — Statut public / page de situation. Le routeur existait mais
# n'était pas inclus dans l'app → les endpoints /api/v1/status/* étaient
# invisibles. Maintenant exposés, utilisés par le collecteur animateur
# pour afficher la vue pédagogique des statuts publics de chaque site.
app.include_router(status_page.router, prefix="/api/v1/status",        tags=["Status Page"])
# v2.4.8.3 — Admin UF : activer / désactiver / éditer le référentiel
app.include_router(admin_uf.router, tags=["Admin UF"])
# ── Compatibilité v140 (endpoints non encore migrés en plugins) ────────────
app.include_router(v140.router,         prefix="/api/v1",              tags=["v1.4.0 legacy"])


@app.get("/api/v1/plugins/active")
def get_active_plugins():
    """
    Retourne les plugins actifs selon l'état DB.
    Inclut les plugins auto-découverts (uploadés).
    Retourne le MANIFEST complet pour permettre la création dynamique d'onglets.
    """
    import pathlib, importlib
    from config import PLUGINS, PLUGIN_META, get_plugin_enabled
    from core.plugin_loader import _load_db_state, _loaded_plugins
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db_state = _load_db_state(db)
    finally:
        db.close()

    # Fusionner PLUGINS + plugins physiquement présents
    all_pids = set(PLUGINS.keys())
    plugins_dir = pathlib.Path(__file__).parent / "plugins"
    if plugins_dir.exists():
        for d in plugins_dir.iterdir():
            if d.is_dir() and (d / "plugin.py").exists():
                all_pids.add(d.name)

    result = []
    for pid in all_pids:
        if not get_plugin_enabled(pid, db_state, default=False):
            continue
        # v2186a — ne pas lister l'onglet exercice dans une instance de prod.
        # Même condition que dans core/plugin_loader.py : seul le mode exercice
        # (lancer_exercice.sh) doit afficher cet onglet côté joueur.
        if pid == "exercice":
            import os as _os
            if _os.getenv("SCRIBE_EXERCICE_MODE", "0") != "1":
                continue
        # Priorité : MANIFEST chargé en mémoire > fichier plugin.py > PLUGIN_META
        manifest = dict(_loaded_plugins.get(pid, {}))
        if not manifest:
            try:
                mod = importlib.import_module(f"plugins.{pid}.plugin")
                manifest = dict(getattr(mod, "MANIFEST", {}))
            except Exception:
                pass
        meta = PLUGIN_META.get(pid, {})
        result.append({
            "id":      pid,
            "label":   manifest.get("label") or meta.get("label",  pid.upper()),
            "icon":    manifest.get("icon")  or meta.get("icon",   "📦"),
            "order":   manifest.get("order") or meta.get("order",  999),
            "tab_id":  manifest.get("tab_id",  None),
            "has_tab": manifest.get("has_tab", bool(manifest.get("tab_id"))),
            "api_prefix": manifest.get("api_prefix", ""),
            "description": manifest.get("description", ""),
        })
    return sorted(result, key=lambda p: p["order"])


@app.get("/api/v1/plugins/all")
def get_all_plugins_public():
    """Liste tous les plugins connus avec leur état. Auth admin dans /admin/plugins."""
    from config import PLUGINS, PLUGIN_META
    return [
        {
            "id":    pid,
            "label": PLUGIN_META.get(pid, {}).get("label", pid.upper()),
            "icon":  PLUGIN_META.get(pid, {}).get("icon", ""),
            "order": PLUGIN_META.get(pid, {}).get("order", 999),
            "default_enabled": default,
        }
        for pid, default in PLUGINS.items()
    ]


@app.on_event("startup")
async def startup():
    _run_migrations()
    _init_status_page()
    # Charger les plugins activés (config.py + surcharge DB)
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        loaded = load_all_plugins(app, db)
        # Démarrer les tâches de fond des plugins qui en ont besoin
        for manifest in loaded:
            pid = manifest.get("id")
            try:
                import importlib
                mod = importlib.import_module(f"plugins.{pid}.plugin")
                if hasattr(mod, "start_background"):
                    mod.start_background(app)
            except Exception:
                pass
    finally:
        db.close()
    # federation_loop est maintenant dans plugins/federation/plugin.py
    # Mais si le plugin n'est pas chargé, lancer le loop legacy
    from core.plugin_loader import is_plugin_loaded
    if not is_plugin_loaded("federation"):
        from app.api import federation as fed_legacy
        asyncio.create_task(fed_legacy.federation_loop())


def _init_status_page():
    """Crée la ligne status_page globale avec published=True si elle n'existe pas."""
    try:
        from app.database import SessionLocal
        from app.api.status_page import _get_or_create
        db = SessionLocal()
        row = _get_or_create(db, site_id=0, site_nom="")
        if not row.published:
            row.published = True
            db.commit()
        db.close()
    except Exception as e:
        print(f"[init_status_page] {e}")


def _run_migrations():
    """Migrations SQLite légères — ALTER TABLE si colonne absente."""
    import sqlite3
    db_path = str(engine.url).replace("sqlite:///", "")
    if not db_path or db_path == ":memory:": return
    try:
        cx = sqlite3.connect(db_path)
        cols = [r[1] for r in cx.execute("PRAGMA table_info(messages_internes)")]
        if "reply_to"   not in cols: cx.execute("ALTER TABLE messages_internes ADD COLUMN reply_to INTEGER")
        if "ght_source" not in cols: cx.execute("ALTER TABLE messages_internes ADD COLUMN ght_source TEXT")
        # Migration must_change_password sur users
        user_cols = [r[1] for r in cx.execute("PRAGMA table_info(users)")]
        if "must_change_password" not in user_cols:
            cx.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
        # Migration expediteur_nom / destinataire_nom sur messages_internes
        if "expediteur_nom" not in cols: cx.execute("ALTER TABLE messages_internes ADD COLUMN expediteur_nom TEXT")
        if "destinataire_nom" not in cols: cx.execute("ALTER TABLE messages_internes ADD COLUMN destinataire_nom TEXT")
        # Migration rôles : directeur → collaborateur, observateur → soignant
        cx.execute("UPDATE users SET role='collaborateur' WHERE role='directeur'")
        cx.execute("UPDATE users SET role='soignant' WHERE role='observateur'")
        # v2315 — Colonnes MFA TOTP sur users
        if "mfa_enabled"      not in user_cols: cx.execute("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER DEFAULT 0")
        if "mfa_secret"       not in user_cols: cx.execute("ALTER TABLE users ADD COLUMN mfa_secret TEXT")
        if "mfa_backup_codes" not in user_cols: cx.execute("ALTER TABLE users ADD COLUMN mfa_backup_codes TEXT")
        # v2182 : ajout impact_fonctionnel sur sitrep_entries
        sitrep_cols = [r[1] for r in cx.execute("PRAGMA table_info(sitrep_entries)")]
        if "impact_fonctionnel" not in sitrep_cols:
            cx.execute("ALTER TABLE sitrep_entries ADD COLUMN impact_fonctionnel INTEGER DEFAULT 0")
        cx.commit(); cx.close()
    except Exception as e:
        logger.warning(f"Migration: {e}")

def _run_migrations_legacy():
    """Ajoute les colonnes manquantes sans casser les données existantes."""
    import sqlite3
    db_url = os.environ.get("DATABASE_URL", "sqlite:///scribe.db")
    db_path = db_url.replace("sqlite:///", "", 1)
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(transferts_patients)")
        cols = {row[1] for row in cur.fetchall()}
        if "eta" not in cols:
            cur.execute("ALTER TABLE transferts_patients ADD COLUMN eta TEXT")
            conn.commit()
            print("[migration] Colonne 'eta' ajoutée à transferts_patients")
        if "site_destination" not in cols:
            cur.execute("ALTER TABLE transferts_patients ADD COLUMN site_destination TEXT")
            conn.commit()
            print("[migration] Colonne 'site_destination' ajoutée à transferts_patients")
        conn.close()
    except Exception as e:
        print(f"[migration] {e}")


@app.get("/api/config.js")
async def serve_config_js():
    """Sert le config.js spécifique à cette instance (SCRIBE_CONFIG_JS)."""
    from fastapi.responses import FileResponse, PlainTextResponse
    custom = os.environ.get("SCRIBE_CONFIG_JS", "")
    default = os.path.join(STATIC_DIR, "config.js")
    path = custom if custom and os.path.exists(custom) else default
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript",
                           headers={"Cache-Control": "no-cache"})
    # Fallback : config minimale pour que le JS démarre sans erreur
    return PlainTextResponse(
        'const SCRIBE_CONFIG = {"etablissement":{"nom":"SCRIBE","sigle":"SCRIBE"},'
        '"directeurs":[],"annuaire_normal":[],"annuaire_secours":[],'
        '"federation":{"enabled":"false"},"langue":"fr"};',
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"}
    )


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    from starlette.responses import Response
    resp = FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )
    return resp


# v2315 — Vue mobile autonome `/m`. Dédiée aux utilisations terrain (RSSI
# en déplacement entre établissements, directeur de crise mobile, cadre
# de garde qui doit garder le fil en se déplaçant). Philosophie :
# - Lecture rapide avant tout : cartes empilables, font lisible
# - Actions rapides essentielles : pointer un incident, répondre à un
#   message, déclarer tension capacité
# - Un seul fichier HTML autonome (pas de dépendance au scribe.js monolithique)
# - Mêmes APIs que le desktop, authentification identique (JWT localStorage)
# - Offline-aware : cache du dernier dashboard pour affichage même sans réseau
@app.get("/m")
async def mobile_root():
    from fastapi.responses import FileResponse
    return FileResponse(
        os.path.join(STATIC_DIR, "mobile.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@app.get("/status", response_class=HTMLResponse)
async def public_status():
    """Page de statut publique — accessible sans authentification."""
    return HTMLResponse(open(os.path.join(STATIC_DIR, "status.html"), encoding="utf-8").read())


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.5.0", "build": "v2500"}


@app.get("/api/push-test")
async def push_test():
    """Test push fédération — GET simple pour diagnostic."""
    fed_cfg = federation.FederationConfig()
    if not fed_cfg.is_ready:
        return {"ok": False, "reason": "federation not ready",
                "config_js": os.environ.get("SCRIBE_CONFIG_JS","?"),
                "config_js_ok": os.path.exists(os.environ.get("SCRIBE_CONFIG_JS",""))}
    try:
        from app.database import SessionLocal
        from app.api.federation import build_payload, push_to_collecteur
        db = SessionLocal()
        payload = build_payload(db, fed_cfg)
        db.close()
        ok = await push_to_collecteur(fed_cfg, payload)
        return {"ok": ok, "sigle": fed_cfg.etablissement_sigle,
                "collecteur": fed_cfg.collecteur_url,
                "token": fed_cfg.token[:8]+"..."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/debug")
def debug_info():
    """Diagnostic rapide — config, DB, fédération."""
    fed_cfg = federation.FederationConfig()
    config_js = os.environ.get("SCRIBE_CONFIG_JS", os.path.join(STATIC_DIR, "config.js"))
    db_url = os.environ.get("DATABASE_URL", "")
    try:
        import sqlite3
        db_path = db_url.replace("sqlite:///", "").lstrip("/") if db_url.startswith("sqlite:////") else db_url.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        sites = conn.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        demo  = conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE '%demo%'").fetchone()[0]
        conn.close()
    except Exception as e:
        sites = users = demo = str(e)[:30]
    # Fix db_path pour chemin absolu
    db_path_clean = db_url.replace("sqlite:///", "", 1) if db_url.startswith("sqlite:///") else db_url

    return {
        "version":      "1.4.0",
        "port":         os.environ.get("SCRIBE_PORT", "8000"),
        "config_js":    config_js,
        "config_js_ok": os.path.exists(config_js),
        "config_file":  os.environ.get("SCRIBE_CONFIG_FILE", "?"),
        "db_path":      db_path_clean,
        "db_exists":    os.path.exists(db_path_clean),
        "federation": {
            "enabled":      fed_cfg.enabled,
            "ready":        fed_cfg.is_ready,
            "sigle":        fed_cfg.etablissement_sigle,
            "collecteur":   fed_cfg.collecteur_url,
            "token_prefix": fed_cfg.token[:8] + "..." if fed_cfg.token else "",
        },
        "db": {"sites": sites, "users": users, "demo_accounts": demo},
    }


if __name__ == "__main__":
    port = int(os.environ.get("SCRIBE_PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
