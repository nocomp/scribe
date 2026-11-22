"""
app/api/i18n.py — Internationalisation SCRIBE
Sert les fichiers de traduction depuis app/lang/
"""
import json
import os
from functools import lru_cache
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/i18n", tags=["i18n"])

LANG_DIR = os.path.join(os.path.dirname(__file__), "..", "lang")
DEFAULT_LANG = "fr"


@lru_cache(maxsize=16)
def load_lang(code: str) -> dict:
    """Charge un fichier de langue avec fallback vers le français."""
    # Nettoyer le code (sécurité : éviter path traversal)
    code = code.lower().replace("..", "").replace("/", "").replace("\\", "")[:5]
    
    path = os.path.join(LANG_DIR, f"{code}.json")
    if not os.path.exists(path):
        path = os.path.join(LANG_DIR, f"{DEFAULT_LANG}.json")
    
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_available_languages() -> list:
    """Retourne la liste des langues disponibles."""
    langs = []
    if not os.path.exists(LANG_DIR):
        return [{"code": "fr", "name": "Français", "flag": "🇫🇷"}]
    
    for fname in sorted(os.listdir(LANG_DIR)):
        if fname.endswith(".json") and not fname.startswith("_"):
            try:
                with open(os.path.join(LANG_DIR, fname), encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("_meta", {})
                langs.append({
                    "code": meta.get("code", fname[:-5]),
                    "name": meta.get("name", fname[:-5]),
                    "flag": meta.get("flag", ""),
                    "direction": meta.get("direction", "ltr"),
                })
            except Exception:
                pass
    return langs


@router.get("/languages")
def list_languages():
    """Liste toutes les langues disponibles."""
    return get_available_languages()


# v2307 — Persistence de la langue courante de l'instance
# Fichier simple plutôt qu'entrée DB pour portabilité multi-bases.
# Écrit uniquement via l'API admin.
_CURRENT_LANG_FILE = os.path.join(LANG_DIR, "_current.json")


def get_current_lang() -> str | None:
    """Retourne le code de la langue active pour cette instance.
    
    v3.4 (h38n) — Retourne None si pas de fichier _current.json (= pas d'override
    admin). Cela permet à scribe.js de tomber sur SCRIBE_CONFIG.langue (langue
    posée au wizard) plutôt que de toujours renvoyer 'fr' par défaut.
    """
    try:
        with open(_CURRENT_LANG_FILE, encoding="utf-8") as f:
            return json.load(f).get("code")
    except Exception:
        return None


def set_current_lang(code: str) -> None:
    """Change la langue active (écrit atomiquement)."""
    # Validation : doit être dans les langues disponibles
    available = {l["code"] for l in get_available_languages()}
    if code not in available:
        raise ValueError(f"Langue non disponible : {code}")
    tmp = _CURRENT_LANG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"code": code}, f)
    os.replace(tmp, _CURRENT_LANG_FILE)


@router.get("/current")
def get_current():
    """Retourne la langue active pour cette instance.
    
    Si pas de configuration admin (_current.json absent), retourne {code: null}
    pour que le frontend fallback sur SCRIBE_CONFIG.langue (wizard).
    """
    code = get_current_lang()
    return {"code": code}  # null si pas configuré


@router.get("/{lang_code}")
def get_translations(lang_code: str):
    """Retourne toutes les traductions pour une langue donnée."""
    return load_lang(lang_code)


@router.get("/{lang_code}/{section}")
def get_section(lang_code: str, section: str):
    """Retourne une section spécifique des traductions."""
    data = load_lang(lang_code)
    if section not in data:
        # Fallback sur le français
        data = load_lang(DEFAULT_LANG)
    return data.get(section, {})
