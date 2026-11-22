"""
app/api/ai_router.py — Routeur IA universel pour SCRIBE

Fournisseurs supportés :
  albert    → Albert AI (DINUM / gouvernement français) — recommandé santé publique
  openai    → ChatGPT (GPT-4o, GPT-4-turbo, GPT-3.5-turbo...)
  anthropic → Claude (claude-opus-4, claude-sonnet-4, claude-haiku...)
  gemini    → Google Gemini (gemini-2.0-flash, gemini-1.5-pro...)
  mistral   → Mistral AI (mistral-large, mistral-small, open-mistral-7b...)
  ollama    → Modèle local Ollama (llama3, mistral, phi3... — zéro donnée externe)
  openai_compat → Tout serveur compatible OpenAI (LM Studio, vLLM, Jan, etc.)

Configuration dans config.xml :
  <ia>
    <fournisseur>albert</fournisseur>
    <cle_api>sk-...</cle_api>
    <modele>mistralai/Ministral-3-8B-Instruct-2512</modele>
    <url_base></url_base>   ← optionnel, pour openai_compat/ollama
  </ia>

Variables d'environnement (surpassent config.xml) :
  SCRIBE_IA_PROVIDER   ex: openai
  SCRIBE_IA_KEY        ex: sk-proj-...
  SCRIBE_IA_MODEL      ex: gpt-4o
  SCRIBE_IA_URL        ex: http://localhost:11434/v1  (ollama)
"""

import os, json, httpx
from typing import Optional, Tuple
from fastapi import HTTPException


# ── Defaults constructeur ───────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "albert": {
        "url":   "https://albert.api.etalab.gouv.fr/v1/chat/completions",
        "model": "mistralai/Ministral-3-8B-Instruct-2512",
    },
    "openai": {
        "url":   "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
    "anthropic": {
        "url":   "https://api.anthropic.com/v1/messages",
        "model": "claude-haiku-4-5-20251001",
    },
    "gemini": {
        "url":   "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "model": "gemini-2.0-flash",
    },
    "mistral": {
        "url":   "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
    },
    "ollama": {
        "url":   "http://localhost:11434/v1/chat/completions",
        "model": "llama3",
    },
    "openai_compat": {
        "url":   "http://localhost:1234/v1/chat/completions",
        "model": "local-model",
    },
}


# ── Chargement de la configuration ─────────────────────────────────────────

class AIConfig:
    """Configuration du fournisseur IA, chargée une fois au démarrage."""

    def __init__(self):
        # v2321 — Priorité de lecture :
        #   1. config.IA (qui a déjà appliqué instance/ia_config.json + env vars)
        #   2. fallback config.js IA section (legacy)
        # Ainsi l'admin qui sauvegarde via UI voit son changement pris en compte
        # immédiatement après reload_ai_config().
        try:
            from config import IA
            self.provider = (IA.get("provider") or "albert").lower()
            self.api_key  = IA.get("api_key", "") or ""
            self.model    = IA.get("model", "") or ""
            self.base_url = IA.get("base_url", "") or ""
        except Exception:
            # Fallback strict env si import config échoue (cas exotique)
            self.provider = os.getenv("SCRIBE_IA_PROVIDER", "albert").lower()
            self.api_key  = os.getenv("SCRIBE_IA_KEY", "")
            self.model    = os.getenv("SCRIBE_IA_MODEL", "")
            self.base_url = os.getenv("SCRIBE_IA_URL", "")

        self._load_from_config_js()

        # Couche centrale (supervision) — comble UNIQUEMENT les champs non définis
        # localement. Précédence : local explicite > central > env.
        try:
            from app.central_config import get_domain as _cc_get
            cc = _cc_get("ia")
            if cc and cc.get("enabled"):
                if not (self.api_key or "").strip() and cc.get("api_key"):
                    self.api_key = cc["api_key"]
                    if cc.get("provider"):
                        self.provider = (cc["provider"] or self.provider).lower()
                if not (self.model or "").strip() and cc.get("model"):
                    self.model = cc["model"]
                if not (self.base_url or "").strip() and cc.get("base_url"):
                    self.base_url = cc["base_url"]
        except Exception:
            pass

        defaults = PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["albert"])
        if not self.model:
            self.model = defaults["model"]
        if not self.base_url:
            self.base_url = defaults["url"]

    def _load_from_config_js(self):
        """Lit SCRIBE_CONFIG.ia depuis le config.js (SCRIBE_CONFIG_JS ou app/static/config.js)."""
        config_js_path = os.environ.get("SCRIBE_CONFIG_JS") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "static", "config.js"
        )
        if not os.path.exists(config_js_path):
            return
        try:
            raw = open(config_js_path, encoding="utf-8").read()
            start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
            end   = raw.rfind(";")
            cfg   = json.loads(raw[start:end])
            ia    = cfg.get("ia", {})
            if ia.get("fournisseur") and not os.getenv("SCRIBE_IA_PROVIDER"):
                self.provider = ia["fournisseur"].lower()
            if ia.get("cle_api") and not os.getenv("SCRIBE_IA_KEY"):
                self.api_key = ia["cle_api"]
            if ia.get("modele") and not os.getenv("SCRIBE_IA_MODEL"):
                self.model = ia["modele"]
            if ia.get("url_base") and not os.getenv("SCRIBE_IA_URL"):
                self.base_url = ia["url_base"]
        except Exception:
            pass

    @property
    def display_name(self) -> str:
        names = {
            "albert":        "Albert AI (DINUM)",
            "openai":        f"OpenAI / ChatGPT ({self.model})",
            "anthropic":     f"Anthropic / Claude ({self.model})",
            "gemini":        f"Google Gemini ({self.model})",
            "mistral":       f"Mistral AI ({self.model})",
            "ollama":        f"Ollama local ({self.model})",
            "openai_compat": f"IA locale compatible OpenAI ({self.model})",
        }
        return names.get(self.provider, f"{self.provider} ({self.model})")

    @property
    def is_local(self) -> bool:
        return self.provider in ("ollama", "openai_compat")


_ai_config: Optional[AIConfig] = None


def get_ai_config() -> AIConfig:
    global _ai_config
    # Toujours recharger depuis config.js (critique pour multi-instance)
    # La config.js change après setup.py donc on ne cache pas
    _ai_config = AIConfig()
    return _ai_config


def reload_ai_config():
    """Force le rechargement de la config (après setup.py)."""
    global _ai_config
    _ai_config = AIConfig()
    return _ai_config


# ── Adaptateurs par fournisseur ─────────────────────────────────────────────

async def _call_openai_compat(cfg: AIConfig, system: str, prompt: str, max_tokens: int) -> str:
    """Format OpenAI Chat Completions."""
    payload = {
        "model":       cfg.model,
        "messages":    [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": 0.3,
        "stream":      False,
    }
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(cfg.base_url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"IA ({cfg.provider}) HTTP {resp.status_code} : {resp.text[:400]}"
        )
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise HTTPException(status_code=502, detail=f"IA : reponse vide — {data}")
    return choices[0]["message"]["content"]


async def _call_anthropic(cfg: AIConfig, system: str, prompt: str, max_tokens: int) -> str:
    """Format Anthropic Messages API (Claude)."""
    payload = {
        "model":      cfg.model,
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt}],
    }
    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         cfg.api_key,
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(cfg.base_url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Claude API HTTP {resp.status_code} : {resp.text[:400]}"
        )
    data = resp.json()
    content = data.get("content", [])
    if not content:
        raise HTTPException(status_code=502, detail="Claude : reponse vide")
    return content[0]["text"]


async def _call_gemini(cfg: AIConfig, system: str, prompt: str, max_tokens: int) -> str:
    """Format Google Gemini generateContent."""
    url = cfg.base_url.replace("{model}", cfg.model)
    if cfg.api_key:
        url += f"?key={cfg.api_key}"

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
        },
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload,
                                  headers={"Content-Type": "application/json"})
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API HTTP {resp.status_code} : {resp.text[:400]}"
        )
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail=f"Gemini : reponse inattendue — {data}")


# ── Point d'entrée universel ────────────────────────────────────────────────

async def call_ai(system: str, prompt: str, max_tokens: int = 700) -> Tuple[str, str]:
    """
    Appelle le fournisseur IA configuré.
    Retourne (texte_reponse, nom_source).
    """
    cfg = get_ai_config()

    try:
        if cfg.provider == "anthropic":
            text = await _call_anthropic(cfg, system, prompt, max_tokens)
        elif cfg.provider == "gemini":
            text = await _call_gemini(cfg, system, prompt, max_tokens)
        else:
            text = await _call_openai_compat(cfg, system, prompt, max_tokens)

        return text, cfg.display_name

    except HTTPException:
        raise
    except httpx.ConnectError:
        provider_label = "serveur local" if cfg.is_local else cfg.provider
        extra = "Vérifiez votre connexion et la clé API."
        if cfg.provider == "ollama":
            extra = "Vérifiez qu'Ollama est démarré."
        raise HTTPException(
            status_code=503,
            detail=f"Impossible de joindre {provider_label} ({cfg.base_url}). {extra}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"Delai depasse ({cfg.provider}) — le modele met trop de temps a repondre."
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"IA indisponible ({cfg.provider}) : {str(e)}")


# ── Helper "IA configurée ?" — fix UX transversal v2.1.0 ────────────────────

# Providers cloud : clé API obligatoire.
_CLOUD_PROVIDERS = {"albert", "openai", "anthropic", "gemini", "mistral"}
# Providers locaux : clé API optionnelle, mais base_url indispensable.
_LOCAL_PROVIDERS = {"ollama", "openai_compat"}


def require_ia_configured() -> Optional[dict]:
    """
    Retourne None si une IA est utilisable, sinon un dict d'erreur structurée
    à passer en `detail` d'une HTTPException(400).

    Le frontend (apiFetch dans scribe.js) reconnaît le marqueur
    `error: "ia_not_configured"` et affiche un pop-up DSFR uniforme,
    quel que soit l'endpoint qui a déclenché l'erreur.

    Pattern d'usage dans une route IA :
        @router.post("/analyser")
        async def analyser(...):
            err = require_ia_configured()
            if err:
                raise HTTPException(status_code=400, detail=err)
            # ... appel à call_ai() ...
    """
    cfg = get_ai_config()
    missing = None

    if not cfg.provider:
        missing = "fournisseur IA"
    elif cfg.provider in _CLOUD_PROVIDERS and not cfg.api_key:
        missing = "clé API"
    elif cfg.provider in _LOCAL_PROVIDERS and not cfg.base_url:
        missing = "URL du serveur local"
    # Si provider inconnu mais clé fournie : on laisse passer (compat openai_compat custom)

    if missing is None:
        return None

    return {
        "error":     "ia_not_configured",
        "message":   f"L'IA n'est pas configurée pour utiliser cette fonction "
                     f"(manquant : {missing}).",
        "action":    "Demandez à votre administrateur de configurer un fournisseur IA "
                     "dans l'espace administration (Configuration → APIs & IA).",
        "admin_url": "/#admin-ia",
        "provider":  cfg.provider or None,
    }
