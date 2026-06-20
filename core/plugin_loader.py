"""
core/plugin_loader.py — SCRIBE v2.0.4
======================================
Charge les plugins activés et enregistre leurs routes FastAPI.
Fournit l'API d'état des plugins pour /admin/plugins.
"""
import importlib
import logging
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.orm import Session

logger = logging.getLogger("scribe.plugins")


# ── Registre en mémoire des plugins chargés ───────────────────────────────────
_loaded_plugins: dict[str, dict] = {}
# v3.6.0-alpha3 — Registre des erreurs de chargement (pour diagnostic admin)
_plugin_errors: dict[str, str] = {}


def load_all_plugins(app: FastAPI, db_session: Session) -> list[dict]:
    """
    Charge tous les plugins activés (config.py + surcharge DB + auto-découverte dossiers).
    Appelé une seule fois au démarrage dans main.py.
    Retourne la liste des manifests des plugins chargés.
    """
    import pathlib
    from config import PLUGINS, PLUGIN_META, get_plugin_enabled

    # Lire l'état persisté en DB
    db_state = _load_db_state(db_session)

    # Auto-découverte : ajouter les plugins présents physiquement mais absents de PLUGINS
    plugins_dir = pathlib.Path(__file__).parent.parent / "plugins"
    discovered = set(PLUGINS.keys())
    if plugins_dir.exists():
        for d in plugins_dir.iterdir():
            if d.is_dir() and (d / "plugin.py").exists() and d.name not in discovered:
                logger.info(f"Plugin auto-découvert : '{d.name}'")
                discovered.add(d.name)

    loaded = []
    for plugin_id in discovered:
        # Les plugins auto-découverts sont activés seulement si DB dit True
        default_enabled = PLUGINS.get(plugin_id, False)
        enabled = get_plugin_enabled(plugin_id, db_state, default=default_enabled)
        if not enabled:
            logger.info(f"Plugin '{plugin_id}' désactivé — ignoré")
            continue
        # v2186a — le plugin exercice n'est chargé que si l'instance a été
        # lancée en mode exercice (SCRIBE_EXERCICE_MODE=1, typiquement via
        # lancer_exercice.sh). Sécurité : éviter toute confusion entre un mode
        # entraînement et une instance de crise réelle.
        if plugin_id == "exercice":
            import os
            if os.getenv("SCRIBE_EXERCICE_MODE", "0") != "1":
                logger.info("Plugin 'exercice' ignoré (instance de production, "
                            "SCRIBE_EXERCICE_MODE != 1)")
                continue
        manifest = _load_plugin(app, plugin_id)
        if manifest:
            loaded.append(manifest)

    logger.info(f"{len(loaded)} plugin(s) chargé(s) : {[p['id'] for p in loaded]}")
    return loaded


def _load_plugin(app: FastAPI, plugin_id: str) -> Optional[dict]:
    """Importe et enregistre un plugin individuel."""
    from config import PLUGIN_META
    try:
        module = importlib.import_module(f"plugins.{plugin_id}.plugin")

        # Le plugin expose une fonction register(app) et un dict MANIFEST
        if hasattr(module, "register"):
            module.register(app)

        manifest = getattr(module, "MANIFEST", {})
        manifest.setdefault("id", plugin_id)
        manifest.setdefault("label", PLUGIN_META.get(plugin_id, {}).get("label", plugin_id.upper()))
        manifest.setdefault("icon",  PLUGIN_META.get(plugin_id, {}).get("icon",  ""))
        manifest.setdefault("order", PLUGIN_META.get(plugin_id, {}).get("order", 999))

        _loaded_plugins[plugin_id] = manifest
        logger.info(f"Plugin '{plugin_id}' chargé ✓")
        return manifest

    except ModuleNotFoundError:
        # Plugin pas encore migré — wrapper de compatibilité
        logger.debug(f"Plugin '{plugin_id}' non migré, utilisation du module legacy app.api.*")
        manifest = _compat_manifest(plugin_id)
        _loaded_plugins[plugin_id] = manifest
        return manifest

    except Exception as e:
        # v3.6.0-alpha3 — Stocker l'erreur pour diagnostic via endpoint debug
        import traceback as _tb
        _plugin_errors[plugin_id] = f"{type(e).__name__}: {e}\n{_tb.format_exc()}"
        logger.error(f"Plugin '{plugin_id}' en échec : {e}", exc_info=True)
        return None


def get_plugin_errors() -> dict[str, str]:
    """Retourne les erreurs de chargement des plugins (vide si tout OK)."""
    return dict(_plugin_errors)


def _compat_manifest(plugin_id: str) -> dict:
    """Manifest de compatibilité pour les modules non encore migrés."""
    from config import PLUGIN_META
    meta = PLUGIN_META.get(plugin_id, {})
    return {
        "id":      plugin_id,
        "label":   meta.get("label",  plugin_id.upper()),
        "icon":    meta.get("icon",   ""),
        "order":   meta.get("order",  999),
        "legacy":  True,  # signale que ce plugin utilise encore app/api/
    }


def get_loaded_plugins() -> list[dict]:
    """Retourne les manifests des plugins actuellement chargés."""
    return sorted(_loaded_plugins.values(), key=lambda p: p.get("order", 999))


def is_plugin_loaded(plugin_id: str) -> bool:
    return plugin_id in _loaded_plugins


# ── Persistance DB ────────────────────────────────────────────────────────────

def _load_db_state(db: Session) -> dict:
    """Lit l'état des plugins depuis la table plugin_states."""
    try:
        from core.plugin_state_model import PluginState
        rows = db.query(PluginState).all()
        return {r.plugin_id: r.enabled for r in rows}
    except Exception:
        return {}


def save_plugin_state(db: Session, plugin_id: str, enabled: bool) -> None:
    """Persiste l'état d'un plugin en DB."""
    try:
        from core.plugin_state_model import PluginState
        row = db.query(PluginState).filter_by(plugin_id=plugin_id).first()
        if row:
            row.enabled = enabled
        else:
            db.add(PluginState(plugin_id=plugin_id, enabled=enabled))
        db.commit()
    except Exception as e:
        logger.error(f"Impossible de persister l'état du plugin '{plugin_id}' : {e}")


def get_all_plugin_states(db: Session) -> list[dict]:
    """Retourne l'état complet de tous les plugins pour /admin/plugins.
    Inclut les plugins auto-découverts dans le dossier plugins/.
    """
    import pathlib
    from config import PLUGINS, PLUGIN_META, get_plugin_enabled
    db_state = _load_db_state(db)

    # Fusionner PLUGINS dict + plugins physiquement présents dans plugins/
    all_ids = set(PLUGINS.keys())
    plugins_dir = pathlib.Path(__file__).parent.parent / "plugins"
    if plugins_dir.exists():
        for d in plugins_dir.iterdir():
            if d.is_dir() and (d / "plugin.py").exists():
                all_ids.add(d.name)

    result = []
    for plugin_id in all_ids:
        # Lire le MANIFEST du plugin si disponible
        manifest = _loaded_plugins.get(plugin_id, {})
        # Tenter de lire le MANIFEST depuis le fichier plugin.py si pas chargé
        if not manifest:
            try:
                import importlib
                mod = importlib.import_module(f"plugins.{plugin_id}.plugin")
                manifest = getattr(mod, "MANIFEST", {})
            except Exception:
                pass
        meta = PLUGIN_META.get(plugin_id, {})
        result.append({
            "id":      plugin_id,
            "label":   manifest.get("label") or meta.get("label",  plugin_id.upper()),
            "icon":    manifest.get("icon")  or meta.get("icon",   "📦"),
            "order":   manifest.get("order") or meta.get("order",  999),
            "enabled": get_plugin_enabled(plugin_id, db_state),
            "loaded":  is_plugin_loaded(plugin_id),
            "legacy":  _loaded_plugins.get(plugin_id, {}).get("legacy", False),
            "discovered": plugin_id not in PLUGINS,  # True = plugin uploadé
        })
    return sorted(result, key=lambda p: p["order"])
