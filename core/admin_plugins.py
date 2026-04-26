"""
core/admin_plugins.py — SCRIBE v2.0.4
API de gestion des plugins depuis /admin/plugins.
Accessible uniquement aux comptes admin.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.api.auth import get_current_user, require_admin
from app.models import User
from core.plugin_loader import get_all_plugin_states, save_plugin_state
from app.api.v140 import _log_mc

router = APIRouter()


class PluginToggle(BaseModel):
    enabled: bool


@router.get("/plugins")
def list_plugins(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Liste tous les plugins avec leur état actuel. Admin requis."""
    return get_all_plugin_states(db)


@router.post("/plugins/{plugin_id}/toggle")
def toggle_plugin(
    plugin_id: str,
    body: PluginToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Active ou désactive un plugin.
    Persisté en DB immédiatement.
    Prend effet au prochain redémarrage de l'instance.
    Loggé en main courante.
    """
    import pathlib
    from config import PLUGINS
    # Accepter aussi les plugins découverts physiquement (uploadés)
    plugins_dir = pathlib.Path(__file__).parent.parent / "plugins"
    is_discovered = (plugins_dir / plugin_id / "plugin.py").exists()
    if plugin_id not in PLUGINS and not is_discovered:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' inconnu")

    # Mise à jour DB
    from core.plugin_state_model import PluginState
    row = db.query(PluginState).filter_by(plugin_id=plugin_id).first()
    if row:
        row.enabled    = body.enabled
        row.changed_at = datetime.now(timezone.utc)
        row.changed_by = current_user.username
    else:
        db.add(PluginState(
            plugin_id  = plugin_id,
            enabled    = body.enabled,
            changed_by = current_user.username,
        ))
    db.commit()

    action = "ACTIVÉ" if body.enabled else "DÉSACTIVÉ"
    _log_mc(
        db, current_user,
        "ADMIN", f"PLUGIN {action}",
        f"Plugin '{plugin_id}' {action.lower()} par {current_user.username}",
        niveau="INFO"
    )

    return {
        "ok":        True,
        "plugin_id": plugin_id,
        "enabled":   body.enabled,
        "message":   f"Plugin '{plugin_id}' {action.lower()}. Redémarrage requis pour prendre effet.",
        "restart_required": True,
    }


@router.get("/plugins/{plugin_id}")
def get_plugin(
    plugin_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Détail d'un plugin spécifique."""
    states = get_all_plugin_states(db)
    plugin = next((p for p in states if p["id"] == plugin_id), None)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' inconnu")
    return plugin


# ── Config IA et Routing (lecture seule — modifiable via env vars) ────────────

@router.get("/config/ia")
def get_ia_config(current_user: User = Depends(require_admin)):
    """Config IA active (fournisseur, modele, HDS). Admin requis."""
    from config import IA
    provider = IA["provider"]
    meta = IA["providers"].get(provider, {})
    return {
        "provider":    provider,
        "label":       meta.get("label",  provider),
        "model":       IA["model"] or meta.get("model", ""),
        "hds":         meta.get("hds", False),
        "local":       meta.get("local", False),
        "doc":         meta.get("doc", ""),
        "has_key":     bool(IA["api_key"]),
        "all_providers": [
            {"id": pid, "label": p["label"], "hds": p["hds"], "local": p["local"]}
            for pid, p in IA["providers"].items()
        ],
    }


@router.get("/config/routing")
def get_routing_config(current_user: User = Depends(require_admin)):
    """Config routing trafic active. Admin requis."""
    from config import ROUTING, get_routing_url
    engine = ROUTING["engine"]
    cfg = ROUTING.get(engine, {})
    return {
        "engine":   engine,
        "url":      get_routing_url(),
        "timeout":  cfg.get("timeout", 5),
        "has_key":  bool(cfg.get("api_key", "")),
        "all_engines": [
            {"id": k, "url": v.get("url", "")}
            for k, v in ROUTING.items()
            if isinstance(v, dict) and "url" in v
        ],
    }


@router.get("/config/network")
def get_network_config(current_user: User = Depends(require_admin)):
    """Config reseau de l instance. Admin requis."""
    from config import NETWORK, FEDERATION
    return {
        "base_url": NETWORK["base_url"],
        "port":     NETWORK["port"],
        "instances": FEDERATION["instances"],
        "collector_port": FEDERATION["collector_port"],
    }



@router.post("/config/federation")
def save_federation_config(body: dict, current_user: User = Depends(require_admin)):
    """Sauvegarde la config fédération dans config.xml."""
    import xml.etree.ElementTree as ET, os
    url   = (body.get("collecteur_url") or "").strip()
    token = (body.get("token") or "").strip()
    inter = int(body.get("intervalle_secondes") or 30)
    if not url:
        raise HTTPException(400, "URL collecteur requise")
    # Trouver config.xml
    config_file = os.environ.get("SCRIBE_CONFIG_FILE", "config.xml")
    if not os.path.exists(config_file):
        raise HTTPException(404, f"config.xml introuvable ({config_file})")
    try:
        tree = ET.parse(config_file)
        root = tree.getroot()
        fed = root.find("federation")
        if fed is None:
            fed = ET.SubElement(root, "federation")
        def _set(parent, tag, val):
            el = parent.find(tag)
            if el is None: el = ET.SubElement(parent, tag)
            el.text = val
        _set(fed, "enabled", "true")
        _set(fed, "collecteur_url", url)
        if token:
            _set(fed, "token", token)
        _set(fed, "intervalle_secondes", str(inter))
        tree.write(config_file, encoding="unicode", xml_declaration=False)
        # Recharger la config en mémoire immédiatement (sans redémarrage)
        try:
            from app.api.federation import reload_fed_config
            reload_fed_config()
        except Exception:
            pass
        return {"ok": True, "message": "Configuration sauvegardée et rechargée."}
    except Exception as e:
        raise HTTPException(500, f"Erreur config.xml: {type(e).__name__}: {e}")


@router.post("/config/ia/test")
def test_ia_key(body: dict, current_user: User = Depends(require_admin)):
    """Teste une clé API pour un fournisseur IA donné."""
    import httpx
    from config import IA
    provider = body.get("provider", "").strip()
    api_key  = body.get("api_key", "").strip()
    if not provider or not api_key:
        raise HTTPException(400, "provider et api_key requis")
    providers = IA.get("providers", {})
    prov_cfg  = providers.get(provider)
    if not prov_cfg:
        raise HTTPException(404, f"Fournisseur inconnu: {provider}")
    test_url = prov_cfg.get("url", "").replace("/chat/completions", "/models")
    if not test_url:
        return {"ok": True, "message": "Fournisseur local — pas de test distant possible"}
    try:
        resp = httpx.get(
            test_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8.0
        )
        if resp.status_code in (200, 401, 403):
            ok = resp.status_code == 200
            return {"ok": ok, "message": f"HTTP {resp.status_code}" + (" — Clé valide" if ok else " — Clé invalide ou non autorisée")}
        return {"ok": False, "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "message": f"Erreur réseau: {e}"}

# ── Upload d'un nouveau plugin (ZIP) ──────────────────────────────────────────

@router.post("/plugins/upload")
async def upload_plugin(
    current_user: User = Depends(require_admin),
    file: UploadFile = File(...),
):
    """Upload un plugin sous forme de ZIP. Extrait dans plugins/. Redémarrage requis."""
    import zipfile, io, pathlib, shutil, re as _re

    if file is None:
        raise HTTPException(400, "Fichier ZIP requis")
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Format ZIP requis")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "ZIP trop volumineux (max 20 Mo)")

    plugins_dir = pathlib.Path(__file__).parent.parent / "plugins"
    plugins_dir.mkdir(exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Vérifier qu'il y a un plugin.py à la racine ou dans un sous-dossier
            names = zf.namelist()
            plugin_id = None
            for name in names:
                if name.endswith("/plugin.py") or name == "plugin.py":
                    parts = name.split("/")
                    if len(parts) >= 2:
                        plugin_id = parts[0]
                    break
            if not plugin_id:
                raise HTTPException(400, "ZIP invalide : plugin.py introuvable")

            # Sanitiser le nom
            plugin_id = _re.sub(r"[^a-z0-9_]", "_", plugin_id.lower())
            dest = plugins_dir / plugin_id
            if dest.exists():
                shutil.rmtree(dest)
            zf.extractall(plugins_dir)

    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier ZIP corrompu")

    # Enregistrer le plugin en DB comme DÉSACTIVÉ (l'admin l'active manuellement)
    try:
        from app.database import SessionLocal
        from core.plugin_state_model import PluginState
        _db = SessionLocal()
        try:
            existing = _db.query(PluginState).filter_by(plugin_id=plugin_id).first()
            if not existing:
                _db.add(PluginState(plugin_id=plugin_id, enabled=False))
                _db.commit()
        finally:
            _db.close()
    except Exception:
        pass

    return {
        "ok": True,
        "plugin_id": plugin_id,
        "hot_loaded": False,
        "message": f"Plugin \'{plugin_id}\' installé — visible dans la liste des plugins. Activez-le puis rechargez."
    }


# ── v2.3.90 — Reset exercice (appelé par le collecteur depuis /api/exercice/reset-all)
@router.delete("/reset-exercice")
def reset_exercice(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Efface toutes les données opérationnelles d'exercice d'une instance SCRIBE.

    Sécurité :
    - Réservé aux admins (require_admin)
    - N'efface QUE les données opérationnelles, PAS les utilisateurs, PAS
      les configurations plugins, PAS les permissions
    - Réservé au mode exercice en théorie, mais permis partout (le RSSI
      peut vouloir un "reset grand ménage" sur son instance production
      après une simulation réelle).

    Purge les tables :
    - SitrepEntry (incidents)
    - MessageInterne + Notification (messagerie & inbox)
    - Transfert (transferts locaux)
    - MainCouranteLog (main courante)
    - CelluleDecision (décisions de crise)
    - RexEntry (retours d'expérience liés à l'exercice)
    """
    import os
    from sqlalchemy import text

    # Import lazy des modèles pour éviter import circulaire
    try:
        from app.models import (
            SitrepEntry, MessageInterne, Notification, Transfert,
            MainCouranteLog, User as UserModel
        )
    except ImportError:
        pass

    counts = {}
    tables_to_purge = [
        ("sitrep_entries", "incidents"),
        ("message_interne", "messages"),
        ("notifications", "notifications"),
        ("transferts", "transferts"),
        ("main_courante_logs", "main_courante"),
        ("cellule_decisions", "decisions"),
        ("rex_entries", "rex"),
        ("tasks", "tasks"),
    ]

    try:
        for tbl, label in tables_to_purge:
            try:
                # Compter avant, puis delete (évite de s'appuyer sur reflection)
                r = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
                db.execute(text(f"DELETE FROM {tbl}"))
                counts[label] = r
            except Exception as e:
                # Table peut-être absente sur une instance qui n'a pas ce plugin
                counts[label] = f"skip ({type(e).__name__})"

        # Log de l'action dans une nouvelle main courante (après purge)
        try:
            db.execute(text(
                "INSERT INTO main_courante_logs (timestamp, auteur, type_action, niveau, message) "
                "VALUES (datetime('now'), :a, 'SYSTEME', 'WARN', :m)"
            ), {"a": current_user.username, "m": "RESET exercice — toutes données opérationnelles effacées"})
        except Exception:
            pass
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Erreur reset: {e}")

    return {
        "ok": True,
        "message": "Données opérationnelles effacées",
        "purged": counts,
        "mode_exercice": os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1",
    }
