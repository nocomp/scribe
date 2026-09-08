"""
app/api/basemap.py — Configuration du fond de carte et service des tuiles
locales.

Trois routes :
  GET /api/v1/config/basemap                     config resolue (rendu carte)
  GET /api/v1/config/basemap/tiles/{z}/{x}/{y}.png   tuiles MBTiles locales
  GET /api/v1/config/basemap/providers           catalogue (ecran admin)

La config resolue ne contient qu un gabarit d URL et une attribution : aucune
donnee sensible, aucune coordonnee de site. Elle reste donc accessible sans
authentification, comme les fichiers statiques dont elle pilote le rendu. Le
catalogue complet, lui, exige un compte administrateur.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.auth import require_admin
from app.models import User
from core import basemap as _bm

logger = logging.getLogger("scribe")
router = APIRouter()

_CACHE_TUILES = "public, max-age=604800, immutable"


def _coords_sites():
    """Coordonnees des sites de l instance, pour decider si le Plan IGN est
    pertinent. Toute erreur est absorbee : la carte doit s afficher meme si la
    base n est pas encore initialisee."""
    try:
        from app.database import SessionLocal
        from app.models import Hospital
        db = SessionLocal()
        try:
            return [
                (h.latitude, h.longitude)
                for h in db.query(Hospital).all()
                if h.latitude is not None and h.longitude is not None
            ]
        finally:
            db.close()
    except Exception:
        return []


@router.get("/basemap")
def get_basemap_config():
    """Fond de carte resolu. Consomme par app/static/js/basemap.js."""
    cfg = _bm.resolve(_coords_sites())
    return {
        "id":          cfg["id"],
        "label":       cfg["label"],
        "mode":        cfg["mode"],
        "url":         cfg["url"],
        "attribution": cfg["attribution"],
        "maxZoom":     cfg["maxZoom"],
        "reason":      cfg["reason"],
        "offline":     cfg.get("offline", False),
        # Repli mondial propose au navigateur si la source principale echoue.
        "fallback": {
            "url":         _bm.PROVIDERS["osm"]["url"],
            "attribution": _bm.PROVIDERS["osm"]["attribution"],
            "maxZoom":     _bm.PROVIDERS["osm"]["maxZoom"],
        },
        "satellite": {
            "url":         _bm.PROVIDERS["satellite"]["url"],
            "attribution": _bm.PROVIDERS["satellite"]["attribution"],
            "maxZoom":     _bm.PROVIDERS["satellite"]["maxZoom"],
        },
    }


@router.get("/basemap/tiles/{z}/{x}/{y}.png")
def get_local_tile(z: int, x: int, y: int):
    """Sert une tuile depuis le MBTiles local. Aucune sortie reseau."""
    if not (0 <= z <= 22):
        raise HTTPException(status_code=400, detail="zoom hors limites")
    data = _bm.read_tile(z, x, y)
    if data is None:
        # 204 plutot que 404 : Leaflet n emet alors pas d erreur bruyante pour
        # les zones non couvertes par le fond local.
        return Response(status_code=204)
    fmt = _bm.mbtiles_metadata().get("format", "png").lower()
    media = "image/jpeg" if fmt in ("jpg", "jpeg") else "image/png"
    return Response(content=data, media_type=media,
                    headers={"Cache-Control": _CACHE_TUILES})


@router.get("/basemap/providers")
def get_basemap_providers(current_user: User = Depends(require_admin)):
    """Catalogue des fonds disponibles. Reserve a l administration."""
    return _bm.providers(_coords_sites())
