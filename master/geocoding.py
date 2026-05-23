"""
core/geocoding.py — Géocodage Nominatim (OpenStreetMap)
=========================================================
Service gratuit, sans clé. Limite officielle : 1 requête/seconde, User-Agent
identifiable obligatoire (sinon ban).

Usage type :
    from core.geocoding import geocode
    result = geocode("Troyes")
    if result:
        lat, lon, display = result["lat"], result["lon"], result["display_name"]

Cache en mémoire pour éviter les requêtes répétées (LRU bounded).
Réservé aux requêtes ponctuelles (création d'incident). Pour des batchs,
utiliser un import structuré.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TypedDict

import httpx


log = logging.getLogger("scribe.geocoding")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT    = "SCRIBE-CrisisManagement/2.1 (https://github.com/nocomp/scribe)"

_cache: dict[str, dict | None] = {}
_cache_lock = threading.Lock()
_last_request_at = 0.0
_request_lock = threading.Lock()
_MIN_INTERVAL  = 1.1  # secondes (Nominatim limite à 1 req/s, on prend une marge)
_MAX_CACHE     = 500


class GeocodeResult(TypedDict):
    lat:          float
    lon:          float
    display_name: str
    source:       str


def geocode(query: str, *, country: str = "", timeout: float = 8.0) -> GeocodeResult | None:
    """Tente de géocoder une chaîne libre (ville, adresse) via Nominatim.

    Retourne un dict {lat, lon, display_name, source} ou None si rien trouvé
    ou si Nominatim est indisponible.

    Par défaut PAS de filtrage pays — on accepte les adresses mondiales
    (utile pour les hôpitaux frontaliers : Suisse, Belgique, Allemagne,
    Luxembourg, Monaco, Andorre). Passer `country="fr"` pour forcer France.

    NOTE : on filtre AVANT non-fr, ce qui causait des résultats absurdes
    pour des adresses suisses ("12 rue de la paix 1202 geneve" → Bordeaux
    parce que Nominatim cherchait dans la France et trouvait n'importe quoi).
    """
    if not query or not query.strip():
        return None
    key = f"{country}::{query.strip().lower()}"

    with _cache_lock:
        if key in _cache:
            return _cache[key]

    # Throttle 1 req/s
    global _last_request_at
    with _request_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_at = time.monotonic()

    params = {
        "q":      query,
        "format": "json",
        "limit":  3,    # demander 3 résultats pour pouvoir choisir le meilleur
    }
    if country:
        params["countrycodes"] = country
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr,en"}

    try:
        r = httpx.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
        if r.status_code != 200:
            log.warning(f"Nominatim HTTP {r.status_code} pour '{query}'")
            _put_cache(key, None)
            return None
        data = r.json()
        if not data:
            _put_cache(key, None)
            return None

        # Heuristique : choisir le meilleur résultat. Nominatim trie déjà
        # par pertinence, mais on peut rejeter les résultats clairement
        # absurdes en cas de query non-correspondante.
        # On prend le 1er résultat sauf cas particulier.
        first = data[0]
        result: GeocodeResult = {
            "lat":          float(first["lat"]),
            "lon":          float(first["lon"]),
            "display_name": first.get("display_name", query),
            "source":       "nominatim",
        }
        _put_cache(key, result)
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.info(f"Nominatim injoignable : {e}")
        return None
    except Exception as e:
        log.warning(f"Erreur géocodage : {e}")
        return None


def _put_cache(key: str, value: dict | None) -> None:
    with _cache_lock:
        if len(_cache) >= _MAX_CACHE:
            # Eviction grossière du plus ancien (FIFO simplifiée)
            for k in list(_cache.keys())[:_MAX_CACHE // 5]:
                _cache.pop(k, None)
        _cache[key] = value
