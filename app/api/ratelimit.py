"""Limiteur de débit léger, en mémoire, sans dépendance externe.

Protège les endpoints coûteux (IA) et à effet réel (SMS, appels) contre l'abus
par un compte valide. Clé = jeton d'auth (par utilisateur) sinon IP. Fenêtre
glissante. Volontairement généreux pour ne pas gêner l'usage normal en crise.
"""
import time
import hashlib
from collections import defaultdict

from fastapi import Request, HTTPException

_BUCKETS: dict = defaultdict(list)   # clé → [timestamps]


def _key(request: Request, name: str) -> str:
    auth = request.headers.get("Authorization", "") or ""
    if auth:
        who = hashlib.sha256(auth.encode()).hexdigest()[:16]
    else:
        who = getattr(request.client, "host", "?")
    return f"{name}:{who}"


def rate_limit(name: str, max_calls: int = 30, window: int = 60):
    """Dépendance FastAPI : limite à `max_calls` appels par `window` secondes."""
    def _dep(request: Request):
        now = time.time()
        k = _key(request, name)
        hits = [t for t in _BUCKETS[k] if now - t < window]
        if len(hits) >= max_calls:
            wait = max(int(window - (now - hits[0])), 1)
            raise HTTPException(
                status_code=429,
                detail=f"Trop de requêtes. Réessayez dans {wait}s.",
                headers={"Retry-After": str(wait)},
            )
        hits.append(now)
        _BUCKETS[k] = hits
    return _dep
