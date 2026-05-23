"""
config.py — SCRIBE v2.0.6 : Configuration centrale
====================================================
Source de vérité unique pour :
  - L URL de base (localhost ou nom de domaine)
  - Les plugins actives/desactives
  - Les fournisseurs IA et leurs endpoints
  - Les moteurs de routing trafic (ambulances)
  - La federation multi-instances G7

Priorite de surcharge :
  1. Variables d environnement (toujours prioritaires)
  2. Persistance DB via /admin/ (plugins)
  3. Valeurs de ce fichier (defauts)
"""
import os

# ── RESEAU ────────────────────────────────────────────────────────────────────
NETWORK: dict = {
    "base_url": os.getenv("SCRIBE_BASE_URL", "http://localhost:8000"),
    "port":     int(os.getenv("SCRIBE_PORT", "8000")),
    "host":     os.getenv("SCRIBE_HOST", "0.0.0.0"),
    "allowed_origins": os.getenv("SCRIBE_ALLOWED_ORIGINS", ""),
}

# ── ROUTING TRAFIC ────────────────────────────────────────────────────────────
ROUTING: dict = {
    # "osrm_public" | "osrm_local" | "openrouteservice" | "graphhopper" | "valhalla"
    "engine": os.getenv("SCRIBE_ROUTING_ENGINE", "osrm_public"),

    "osrm_public": {
        "url":     "https://router.project-osrm.org/route/v1/driving",
        "timeout": 5,
    },
    "osrm_local": {
        "url":     os.getenv("SCRIBE_OSRM_URL", "http://localhost:5000/route/v1/driving"),
        "timeout": 3,
    },
    "openrouteservice": {
        "url":     "https://api.openrouteservice.org/v2/directions/driving-car",
        "api_key": os.getenv("SCRIBE_ORS_KEY", ""),
        "timeout": 5,
    },
    "graphhopper": {
        "url":     os.getenv("SCRIBE_GH_URL", "https://graphhopper.com/api/1/route"),
        "api_key": os.getenv("SCRIBE_GH_KEY", ""),
        "timeout": 5,
    },
    "valhalla": {
        "url":     os.getenv("SCRIBE_VALHALLA_URL", "http://localhost:8002/route"),
        "timeout": 3,
    },
}

# ── INTELLIGENCE ARTIFICIELLE ─────────────────────────────────────────────────
IA: dict = {
    # "albert" | "openai" | "anthropic" | "gemini" | "mistral" | "ollama" | "openai_compat" | "none"
    "provider": os.getenv("SCRIBE_IA_PROVIDER", "albert"),
    "api_key":  os.getenv("SCRIBE_IA_KEY",      ""),
    "model":    os.getenv("SCRIBE_IA_MODEL",     ""),
    "base_url": os.getenv("SCRIBE_IA_URL",       ""),

    "providers": {
        "albert": {
            "label": "Albert (DINUM)", "hds": True, "local": False,
            "url":   "https://albert.api.etalab.gouv.fr/v1/chat/completions",
            "model": "mistralai/Ministral-3-8B-Instruct-2512",
            "doc":   "https://albert.api.etalab.gouv.fr",
        },
        "openai": {
            "label": "OpenAI (GPT-4o...)", "hds": False, "local": False,
            "url":   "https://api.openai.com/v1/chat/completions",
            "model": "gpt-4o-mini",
            "doc":   "https://platform.openai.com",
        },
        "anthropic": {
            "label": "Anthropic (Claude...)", "hds": False, "local": False,
            "url":   "https://api.anthropic.com/v1/messages",
            "model": "claude-haiku-4-5-20251001",
            "doc":   "https://docs.anthropic.com",
        },
        "gemini": {
            "label": "Google Gemini", "hds": False, "local": False,
            "url":   "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "model": "gemini-2.0-flash",
            "doc":   "https://ai.google.dev",
        },
        "mistral": {
            "label": "Mistral AI", "hds": False, "local": False,
            "url":   "https://api.mistral.ai/v1/chat/completions",
            "model": "mistral-small-latest",
            "doc":   "https://docs.mistral.ai",
        },
        "ollama": {
            "label": "Ollama (local)", "hds": True, "local": True,
            "url":   "http://localhost:11434/v1/chat/completions",
            "model": "llama3",
            "doc":   "https://ollama.com",
        },
        "openai_compat": {
            "label": "Compatible OpenAI (LM Studio, vLLM...)", "hds": True, "local": True,
            "url":   "http://localhost:1234/v1/chat/completions",
            "model": "local-model",
            "doc":   "https://lmstudio.ai",
        },
        "none": {
            "label": "Desactive", "hds": True, "local": True,
            "url": "", "model": "", "doc": "",
        },
    },
}

# ── INTERFACE / LOGIN ────────────────────────────────────────────────────────
UI: dict = {
    # Texte affiché sous le logo sur la mire de login.
    # Si vide : utilise automatiquement le nom de l'etablissement depuis config.xml.
    # Exemple : "CHU Grenoble Alpes — Crisis OS"
    "login_tagline": os.getenv("SCRIBE_LOGIN_TAGLINE", ""),

    # Texte pied de mire (en dessous du bouton connexion)
    "login_footer":  os.getenv("SCRIBE_LOGIN_FOOTER", "Réseau parallèle — Accès restreint"),
}

# ── PLUGINS ───────────────────────────────────────────────────────────────────
# v2320 — BUILD PRIVÉ : tous les plugins activés par défaut.
# Pour le build public GitHub, repasser inter_ght et tuteur à False.
PLUGINS: dict[str, bool] = {
    "cellule":    True,
    "releve":     True,
    "rex":        True,
    "annuaire":   True,
    "capacite":   True,
    "communique": True,
    "rapport":    True,
    "transferts": True,
    "messagerie": True,
    # v2307 → v2320 : Plugin inter_ght normalement désactivé en public car
    # le chat temps réel couvre les besoins d'échanges inter-établissements.
    # Activé ici pour build privé où l'onglet est attendu.
    "inter_ght":  True,
    "federation": True,
    "albert":     True,
    "brancardage":   True,
    "chat":          True,
    "exercice":      True,   # Plugin exercice de crise (ports 8660-8666)
    "notifications": True,
    # v2320 — Plugin tuteur v0.5 (compagnon d'apprentissage). Sur build public
    # GitHub : repasser à False (opt-in admin via /admin/plugins) pour
    # rétrocompatibilité.
    "tuteur":        True,
    # "chaine_alerte": False,
}

PLUGIN_META: dict[str, dict] = {
    "cellule":    {"label": "CELLULE",    "icon": "🏛️", "order": 30,  "tab": True},
    "releve":     {"label": "RELEVE",     "icon": "📋", "order": 40,  "tab": True},
    "rex":        {"label": "REX",        "icon": "🔍", "order": 80,  "tab": True},
    "annuaire":   {"label": "ANNUAIRE",   "icon": "📞", "order": 70,  "tab": True},
    "capacite":   {"label": "CAPACITE",   "icon": "🛏", "order": 20,  "tab": True},
    "communique": {"label": "COMMUNIQUE", "icon": "📣", "order": 60,  "tab": True},
    "rapport":    {"label": "RAPPORT",    "icon": "📦", "order": 65,  "tab": False},
    "transferts": {"label": "TRANSFERTS", "icon": "🚑", "order": 50,  "tab": True},
    "messagerie": {"label": "MESSAGERIE", "icon": "✉️", "order": 90,  "tab": True},
    "inter_ght":  {"label": "INTER-GHT",  "icon": "🔗", "order": 100, "tab": True},
    "federation": {"label": "SUPERVISION","icon": "🗺", "order": 110, "tab": False},
    "albert":     {"label": "ASSISTANT IA", "icon": "🤖", "order": 120, "tab": False},
    "exercice":   {"label": "EXERCICE",    "icon": "🎯", "order": 88,  "tab": True},
    "notifications": {"label": "NOTIFICATIONS", "icon": "🔔", "order": 95, "tab": False},
    "tuteur":     {"label": "MON COACH",   "icon": "🎓", "order": 115, "tab": True},
}

# ── FEDERATION ────────────────────────────────────────────────────────────────
FEDERATION: dict = {
    "collector_port":      int(os.getenv("SCRIBE_COLLECTOR_PORT", "9000")),
    "demo_port":           int(os.getenv("SCRIBE_DEMO_PORT",      "7474")),
    "demo_collector_port": int(os.getenv("SCRIBE_DEMO_COLL_PORT", "7373")),
    "instances": [
        {"sigle": "DEMO",      "port": 8000},
        {"sigle": "DEMO2",    "port": 8001},
        {"sigle": "DEMO3", "port": 8002},
        {"sigle": "DEMO4",   "port": 8003},
        {"sigle": "DEMO5",      "port": 8004},
        {"sigle": "DEMO6",       "port": 8005},
        {"sigle": "DEMO7",      "port": 8006},
    ],
}

# ── LOGIN / MIRE D'ACCUEIL ───────────────────────────────────────────────────
# Textes affichés sur l'écran de connexion. Modifiables sans redémarrage
# (lus dynamiquement depuis config.js par le frontend, ou ici comme défauts).
LOGIN: dict = {
    # Ligne de sous-titre sous le logo (nom de l'établissement + contexte)
    # Exemples : "DEMO — Crisis OS" | "CHU Grenoble — Cellule de Crise"
    "subtitle":    os.getenv("SCRIBE_LOGIN_SUBTITLE",   "Votre Établissement — Crisis OS"),

    # Texte en bas de la login box (contexte réseau, mention légale, etc.)
    "footer_text": os.getenv("SCRIBE_LOGIN_FOOTER",     "Réseau parallèle — Accès restreint"),

    # Crédit de conception (affiché sous le footer_text)
    "credit":      "Designed by Hervé PELLARIN",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_plugin_enabled(plugin_id: str, db_state: dict | None = None, default: bool = False) -> bool:
    if db_state and plugin_id in db_state:
        return db_state[plugin_id]
    return PLUGINS.get(plugin_id, default)

def get_routing_url() -> str:
    engine = ROUTING["engine"]
    return ROUTING.get(engine, ROUTING["osrm_public"]).get("url", "")

def get_routing_config() -> dict:
    engine = ROUTING["engine"]
    cfg = ROUTING.get(engine, ROUTING["osrm_public"]).copy()
    cfg["engine"] = engine
    return cfg

def get_ia_provider_config() -> dict:
    provider = IA["provider"]
    base = IA["providers"].get(provider, IA["providers"]["albert"]).copy()
    if IA["api_key"]:  base["api_key"]  = IA["api_key"]
    if IA["model"]:    base["model"]    = IA["model"]
    if IA["base_url"]: base["url"]      = IA["base_url"]
    base["provider"] = provider
    return base


# ── v2321 — Persistance config IA via fichier JSON ────────────────────────────
# Permet à l'admin de sauvegarder provider/api_key/model/base_url depuis l'UI
# sans redémarrer le process. Le fichier prime sur les variables d'env au boot,
# et reload_ia_config() le relit à chaud après écriture.

import json as _json

_IA_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "instance", "ia_config.json")


def _load_persisted_ia() -> None:
    """
    Lit instance/ia_config.json si présent et applique provider/api_key/model/
    base_url sur le dict IA. Silencieux si le fichier est absent ou corrompu —
    on retombe sur les variables d'env / valeurs par défaut.
    """
    try:
        if not os.path.exists(_IA_CONFIG_PATH):
            return
        with open(_IA_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if not isinstance(data, dict):
            return
        for key in ("provider", "api_key", "model", "base_url"):
            v = data.get(key)
            if v is not None and isinstance(v, str):
                IA[key] = v
    except Exception:
        # Échec silencieux — on n'empêche pas le boot si le JSON est cassé
        pass


def save_persisted_ia(provider: str, api_key: str = "",
                      model: str = "", base_url: str = "") -> str:
    """
    Écrit instance/ia_config.json avec provider/api_key/model/base_url.
    Met aussi à jour le dict IA en mémoire (pour ne pas avoir à reload).
    Permissions 0600 sur le fichier (clé API = sensible).

    Retourne le chemin du fichier écrit.
    """
    os.makedirs(os.path.dirname(_IA_CONFIG_PATH), exist_ok=True)
    data = {
        "provider": (provider or "").strip(),
        "api_key":  (api_key  or "").strip(),
        "model":    (model    or "").strip(),
        "base_url": (base_url or "").strip(),
    }
    with open(_IA_CONFIG_PATH, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(_IA_CONFIG_PATH, 0o600)
    except Exception:
        pass  # Windows ou FS sans support de chmod

    # Met à jour le dict IA en mémoire immédiatement
    for k, v in data.items():
        IA[k] = v
    return _IA_CONFIG_PATH


# Appliquer la persistance au boot (une seule fois)
_load_persisted_ia()
