"""SCRIBE — Réglages admin par plugin (messagerie, fichiers).

Stocke, par plugin, une politique d'upload LOCALE éditable depuis l'admin du
plugin (carte ⚙) : poids max par fichier + types de fichiers autorisés, classés
par CATÉGORIE MIME (images, PDF, bureautique, tableurs, texte, archives, audio,
vidéo). Persisté dans un JSON sous SCRIBE_DATA_DIR (stable entre builds si défini),
sinon à la racine du build.

Précédence à l'application : config LOCALE du plugin (si une restriction est
définie) > politique CENTRALE 'uploads' (supervision) > défaut du module appelant.
"""
import os
import json
import pathlib
import threading

_lock = threading.Lock()
_cache = None

# ── Catégories de types de fichiers (classées par MIME) ──────────────────────
# Chaque catégorie : libellé FR + extensions associées. L'admin coche des
# catégories ; les extensions autorisées en découlent.
MIME_CATEGORIES = {
    "image":       {"label": "Images",                 "exts": ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "tif", "tiff", "heic"]},
    "pdf":         {"label": "PDF",                     "exts": ["pdf"]},
    "bureautique": {"label": "Documents bureautiques",  "exts": ["doc", "docx", "odt", "rtf", "ppt", "pptx", "odp"]},
    "tableur":     {"label": "Tableurs / CSV",          "exts": ["xls", "xlsx", "ods", "csv", "tsv"]},
    "texte":       {"label": "Texte brut",              "exts": ["txt", "md", "log"]},
    "archive":     {"label": "Archives",                "exts": ["zip", "7z", "rar", "tar", "gz", "bz2"]},
    "audio":       {"label": "Audio",                   "exts": ["mp3", "wav", "ogg", "m4a", "aac"]},
    "video":       {"label": "Vidéo",                   "exts": ["mp4", "webm", "mov", "avi", "mkv"]},
}

_PLUGINS = ("messagerie", "fichiers")

_DEFAULT = {
    "messagerie": {"max_size_mb": 0, "categories": [], "max_attachments": 0},
    "fichiers":   {"max_size_mb": 0, "categories": []},
}


def _config_path() -> pathlib.Path:
    base = os.environ.get("SCRIBE_DATA_DIR")
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = pathlib.Path(base)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p / "plugin_admin_config.json"


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    data = {}
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    _cache = data
    return _cache


def categories_meta() -> list:
    """Liste ordonnée des catégories pour l'UI : [{key, label, exts}]."""
    return [{"key": k, "label": v["label"], "exts": v["exts"]} for k, v in MIME_CATEGORIES.items()]


def get_plugin_config(plugin: str) -> dict:
    base = dict(_DEFAULT.get(plugin, {"max_size_mb": 0, "categories": []}))
    stored = _load().get(plugin)
    if isinstance(stored, dict):
        base.update(stored)
    # normaliser categories
    cats = base.get("categories") or []
    base["categories"] = [c for c in cats if c in MIME_CATEGORIES]
    return base


def set_plugin_config(plugin: str, cfg: dict) -> dict:
    if plugin not in _PLUGINS:
        raise ValueError("plugin inconnu")
    clean = {}
    try:
        clean["max_size_mb"] = max(0, int(float(cfg.get("max_size_mb") or 0)))
    except Exception:
        clean["max_size_mb"] = 0
    cats = cfg.get("categories") or []
    if isinstance(cats, str):
        cats = [c for c in cats.replace(",", " ").split() if c]
    clean["categories"] = [c for c in cats if c in MIME_CATEGORIES]
    if plugin == "messagerie":
        try:
            clean["max_attachments"] = max(0, int(float(cfg.get("max_attachments") or 0)))
        except Exception:
            clean["max_attachments"] = 0
    with _lock:
        data = _load()
        data[plugin] = clean
        try:
            _config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        globals()["_cache"] = data
    return clean


def _allowed_exts(cfg: dict) -> list:
    """Extensions autorisées dérivées des catégories cochées. [] = toutes."""
    cats = cfg.get("categories") or []
    if not cats:
        return []
    exts = []
    for c in cats:
        for e in MIME_CATEGORIES.get(c, {}).get("exts", []):
            exts.append("." + e)
    return exts


def enforce(plugin: str, filename: str, default_max_bytes: int) -> int:
    """Applique la politique LOCALE du plugin si définie, sinon la politique
    CENTRALE 'uploads', sinon le défaut. Lève HTTPException 415 si l'extension
    n'est pas autorisée. Renvoie la taille max effective (octets)."""
    try:
        cfg = get_plugin_config(plugin)
    except Exception:
        cfg = {}
    local_exts = _allowed_exts(cfg)
    local_max = int(cfg.get("max_size_mb") or 0) * 1024 * 1024
    if local_exts or local_max:
        if local_exts:
            name = (filename or "").lower()
            ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
            if ext not in local_exts:
                from fastapi import HTTPException
                raise HTTPException(415, f"Type de fichier non autorisé : {filename}")
        return local_max or default_max_bytes
    # Pas de restriction locale → politique centrale (supervision)
    try:
        from app.central_config import enforce_upload_policy
        return enforce_upload_policy(filename, default_max_bytes)
    except Exception:
        return default_max_bytes
