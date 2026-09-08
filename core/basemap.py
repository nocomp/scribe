"""
core/basemap.py — Resolution du fond de carte, sans configuration.

SCRIBE doit afficher une carte utilisable des le premier demarrage, partout,
sans clef d API et sans intervention de l administrateur. Ce module resout la
source de tuiles a la demande, selon une chaine de priorite :

  1. Tuiles locales      data/basemap.mbtiles present -> servi par l instance
  2. Plan IGN            si les sites sont en France / DOM-TOM
  3. OpenStreetMap       defaut mondial
  4. Monde embarque      data/basemap_world.mbtiles (z0-5), filet de securite

Le mode vectoriel OpenFreeMap (sans clef, sans quota) est disponible via
SCRIBE_BASEMAP=openfreemap : il charge MapLibre a la demande cote navigateur.

Contexte : CARTO a filigrane ses tuiles raster fin aout 2026 et annonce le
retrait du service raster. La lecon retenue est qu une degradation peut etre
silencieuse (HTTP 200 + filigrane), donc indetectable par un simple test de
disponibilite. La seule protection durable est de ne dependre d aucun
fournisseur commercial : d ou la priorite donnee aux tuiles locales.

Variables d environnement :
  SCRIBE_BASEMAP           auto | local | ign | osm | openfreemap | custom
  SCRIBE_BASEMAP_URL       gabarit XYZ/WMTS (mode custom)
  SCRIBE_BASEMAP_ATTR      attribution (mode custom)
  SCRIBE_BASEMAP_MBTILES   chemin du .mbtiles local
  SCRIBE_BASEMAP_MAXZOOM   plafond de zoom

Aucune dependance hors bibliotheque standard : le collecteur, qui tourne dans
un processus separe, importe ce meme module.
"""

import os
import sqlite3
import threading
from pathlib import Path

__all__ = [
    "resolve", "providers", "csp_hosts", "mbtiles_path",
    "read_tile", "mbtiles_metadata", "PROVIDERS",
]

_ROOT = Path(__file__).resolve().parent.parent

# ── Emprises France (metropole + outre-mer) ──────────────────────────────────
# Utilisees pour decider si le Plan IGN est pertinent. Format : lat_min,
# lat_max, lon_min, lon_max.
_EMPRISES_IGN = [
    (41.0, 51.5, -5.5, 9.8),        # metropole + Corse
    (15.8, 16.6, -61.9, -60.8),     # Guadeloupe
    (14.3, 15.0, -61.3, -60.7),     # Martinique
    (2.0, 6.0, -55.0, -51.0),       # Guyane
    (-21.5, -20.8, 55.1, 55.9),     # La Reunion
    (-13.1, -12.6, 45.0, 45.4),     # Mayotte
    (-17.9, -7.8, -152.0, -134.0),  # Polynesie francaise
    (-22.8, -19.5, 163.5, 168.2),   # Nouvelle-Caledonie
    (46.7, 47.2, -56.5, -56.1),     # Saint-Pierre-et-Miquelon
]

# ── Catalogue des fournisseurs ───────────────────────────────────────────────
PROVIDERS = {
    "local": {
        "label":       "Tuiles locales",
        "mode":        "raster",
        "url":         "/api/v1/config/basemap/tiles/{z}/{x}/{y}.png",
        "attribution": "Fond de carte local",
        "maxZoom":     19,
        "scope":       "local",
        "offline":     True,
        "key":         False,
    },
    "ign": {
        "label": "Plan IGN",
        "mode":  "raster",
        # ATTENTION : WMTS, l ordre est TILEROW={y} puis TILECOL={x}.
        "url": (
            "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile"
            "&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
            "&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM"
            "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
        ),
        "attribution": "Plan IGN v2 \u2014 \u00a9 IGN / G\u00e9oplateforme",
        "maxZoom":     19,
        "scope":       "France + DOM-TOM",
        "offline":     False,
        "key":         False,
        "host":        "data.geopf.fr",
    },
    "osm": {
        "label":       "OpenStreetMap",
        "mode":        "raster",
        "url":         "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "\u00a9 OpenStreetMap contributors",
        "maxZoom":     19,
        "scope":       "Mondial",
        "offline":     False,
        "key":         False,
        "host":        "*.tile.openstreetmap.org",
    },
    "openfreemap": {
        "label":       "OpenFreeMap (vectoriel)",
        "mode":        "vector",
        "url":         "https://tiles.openfreemap.org/styles/positron",
        "attribution": "OpenFreeMap \u00a9 OpenMapTiles \u2014 donn\u00e9es OpenStreetMap",
        "maxZoom":     20,
        "scope":       "Mondial",
        "offline":     False,
        "key":         False,
        "host":        "tiles.openfreemap.org",
    },
    "satellite": {
        "label": "Satellite",
        "mode":  "raster",
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attribution": "\u00a9 Esri World Imagery",
        "maxZoom":     19,
        "scope":       "Mondial",
        "offline":     False,
        "key":         False,
        "host":        "server.arcgisonline.com",
    },
}

# Hotes a autoriser dans la CSP. Statique et exhaustif : la chaine peut basculer
# a chaud d un fournisseur a l autre, la CSP ne doit jamais avoir a etre
# recalculee. C est ce qui evite le piege de la carte grise apres bascule.
_CSP_HOSTS = [
    "data.geopf.fr", "*.geopf.fr",
    "*.tile.openstreetmap.org", "tile.openstreetmap.org",
    "tiles.openfreemap.org",
    "server.arcgisonline.com",
    "*.basemaps.cartocdn.com",
]


def csp_hosts():
    """Hotes a inserer dans img-src et connect-src."""
    extra = os.getenv("SCRIBE_BASEMAP_CSP_EXTRA", "").split(",")
    return _CSP_HOSTS + [h.strip() for h in extra if h.strip()]


# ── MBTiles ──────────────────────────────────────────────────────────────────

_mb_lock = threading.Lock()
_mb_conn = {}


def mbtiles_path():
    """Chemin du .mbtiles a utiliser, ou None. Le fond regional prime sur le
    fond mondial de secours."""
    explicit = os.getenv("SCRIBE_BASEMAP_MBTILES", "").strip()
    if explicit:
        return explicit if Path(explicit).is_file() else None
    for name in ("basemap.mbtiles", "basemap_world.mbtiles"):
        p = _ROOT / "data" / name
        if p.is_file():
            return str(p)
    return None


def _conn(path):
    with _mb_lock:
        c = _mb_conn.get(path)
        if c is None:
            c = sqlite3.connect(path, check_same_thread=False)
            _mb_conn[path] = c
        return c


def read_tile(z, x, y, path=None):
    """Lit une tuile dans le MBTiles. Retourne les octets ou None.

    MBTiles stocke les lignes en TMS (origine en bas), Leaflet demande du XYZ
    (origine en haut) : d ou l inversion de y.
    """
    path = path or mbtiles_path()
    if not path:
        return None
    try:
        ty = (2 ** int(z) - 1) - int(y)
        row = _conn(path).execute(
            "SELECT tile_data FROM tiles "
            "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (int(z), int(x), ty),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def mbtiles_metadata(path=None):
    """Metadonnees du MBTiles : name, format, bounds, minzoom, maxzoom."""
    path = path or mbtiles_path()
    if not path:
        return {}
    try:
        rows = _conn(path).execute("SELECT name, value FROM metadata").fetchall()
        return {k: v for k, v in rows}
    except Exception:
        return {}


# ── Detection de l emprise ───────────────────────────────────────────────────

def _in_ign(lat, lon):
    for lat_min, lat_max, lon_min, lon_max in _EMPRISES_IGN:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


def _sites_in_france(coords):
    """coords : iterable de (lat, lon). True si au moins un site est couvert
    par l IGN. Sans coordonnees, on ne presume rien -> False (defaut mondial)."""
    found = False
    for lat, lon in coords or []:
        try:
            if lat is None or lon is None:
                continue
            if _in_ign(float(lat), float(lon)):
                return True
            found = True
        except (TypeError, ValueError):
            continue
    return False if found else False


# ── Resolution ───────────────────────────────────────────────────────────────

def resolve(coords=None):
    """Resout le fond de carte a utiliser.

    coords : iterable de (lat, lon) des sites de l instance, pour decider si
             le Plan IGN est pertinent. Optionnel.

    Retourne un dict pret a etre serialise vers le navigateur.
    """
    forced = os.getenv("SCRIBE_BASEMAP", "auto").strip().lower()
    reason = ""

    if forced == "custom":
        url = os.getenv("SCRIBE_BASEMAP_URL", "").strip()
        if url:
            return _pack({
                "label":       "Personnalis\u00e9",
                "mode":        "vector" if url.endswith(("/style.json", "positron", "liberty", "bright")) else "raster",
                "url":         url,
                "attribution": os.getenv("SCRIBE_BASEMAP_ATTR", "Fond de carte personnalis\u00e9"),
                "maxZoom":     19,
                "offline":     False,
                "key":         False,
            }, "custom", "SCRIBE_BASEMAP_URL")

    if forced in PROVIDERS:
        if forced == "local" and not mbtiles_path():
            reason = "local demande mais aucun .mbtiles trouve, repli automatique"
        else:
            return _pack(PROVIDERS[forced], forced, "impose par SCRIBE_BASEMAP")

    # ── Chaine automatique ───────────────────────────────────────────────
    if mbtiles_path():
        meta = mbtiles_metadata()
        prov = dict(PROVIDERS["local"])
        if meta.get("name"):
            prov["label"] = "Tuiles locales \u2014 " + meta["name"]
        try:
            prov["maxZoom"] = int(meta.get("maxzoom", 19))
        except (TypeError, ValueError):
            pass
        return _pack(prov, "local", reason or "fichier .mbtiles present, aucune sortie reseau requise")

    if _sites_in_france(coords):
        return _pack(PROVIDERS["ign"], "ign", reason or "sites situes dans l emprise IGN")

    return _pack(PROVIDERS["osm"], "osm", reason or "defaut mondial, aucune clef requise")


def _pack(prov, pid, reason):
    out = dict(prov)
    out["id"] = pid
    out["reason"] = reason
    try:
        out["maxZoom"] = int(os.getenv("SCRIBE_BASEMAP_MAXZOOM", out.get("maxZoom", 19)))
    except (TypeError, ValueError):
        pass
    return out


def providers(coords=None):
    """Catalogue complet + fournisseur actif, pour l ecran d administration."""
    active = resolve(coords)
    has_local = bool(mbtiles_path())
    out = []
    for pid, p in PROVIDERS.items():
        if pid == "local" and not has_local:
            continue
        out.append({
            "id":      pid,
            "label":   p["label"],
            "mode":    p["mode"],
            "scope":   p.get("scope", ""),
            "offline": p.get("offline", False),
            "key":     p.get("key", False),
            "active":  pid == active["id"],
        })
    return {"active": active, "providers": out, "has_local": has_local}
