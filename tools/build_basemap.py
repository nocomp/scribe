#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/build_basemap.py — Fabrique le fond de carte local de SCRIBE.

Pourquoi cet outil existe
-------------------------
SCRIBE promet de fonctionner quand le reste du systeme d information est a
terre. Tant que la carte appelle un CDN exterieur, cette promesse est fausse :
un etablissement qui coupe sa sortie Internet pour contenir une attaque perd sa
cartographie des transferts au moment ou il en a le plus besoin.

Un fichier MBTiles depose dans data/ devient prioritaire automatiquement (voir
core/basemap.py). Aucune configuration, aucun redemarrage particulier : la
carte cesse simplement de sortir du reseau.

Le second interet est la resistance aux changements de conditions des
fournisseurs. En aout 2026, CARTO a filigrane ses tuiles raster sans preavis,
en repondant HTTP 200 : une degradation invisible pour tout mecanisme de
supervision. Des tuiles possedees ne connaissent pas ce probleme.

Usage
-----
    # Emprise autour d un territoire, zooms 8 a 14
    python3 tools/build_basemap.py --bbox 45.4,5.5,46.4,7.0 --min-zoom 8 --max-zoom 14

    # Filet de securite mondial, tres leger (quelques Mo)
    python3 tools/build_basemap.py --monde

Le fichier produit va dans data/ :
    data/basemap.mbtiles         fond regional, prioritaire
    data/basemap_world.mbtiles   filet mondial, utilise a defaut

Attention
---------
Le telechargement massif de tuiles est encadre par la politique d usage des
fournisseurs. La source par defaut est le Plan IGN, dont les conditions
autorisent la reutilisation. Restez sur des emprises et des zooms
raisonnables : une emprise departementale jusqu au zoom 14 represente deja
plusieurs dizaines de milliers de tuiles.
"""

import argparse
import math
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCES = {
    "ign": {
        "url": (
            "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile"
            "&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
            "&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM"
            "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
        ),
        "format": "png",
        "attribution": "Plan IGN v2 - (c) IGN / Geoplateforme",
    },
    "osm": {
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "format": "png",
        "attribution": "(c) OpenStreetMap contributors",
    },
}

UA = "SCRIBE/3.6 (gestion de crise hospitaliere; +https://github.com/nocomp/scribe)"


def deg2num(lat, lon, z):
    lat_r = math.radians(lat)
    n = 2.0 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return max(0, min(int(n) - 1, x)), max(0, min(int(n) - 1, y))


def creer_base(chemin, meta):
    if os.path.exists(chemin):
        os.remove(chemin)
    cx = sqlite3.connect(chemin)
    cx.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    cx.execute(
        "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, "
        "tile_row INTEGER, tile_data BLOB)"
    )
    cx.execute(
        "CREATE UNIQUE INDEX idx_tiles ON tiles "
        "(zoom_level, tile_column, tile_row)"
    )
    cx.executemany("INSERT INTO metadata VALUES (?,?)", list(meta.items()))
    cx.commit()
    return cx


def telecharger(url, essais=3):
    for n in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as rep:
                return rep.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 204):
                return None
            time.sleep(1.5 * (n + 1))
        except Exception:
            time.sleep(1.5 * (n + 1))
    return None


def construire(bbox, zmin, zmax, source, sortie, pause):
    src = SOURCES[source]
    lat_min, lon_min, lat_max, lon_max = bbox

    plan = []
    for z in range(zmin, zmax + 1):
        x0, y0 = deg2num(lat_max, lon_min, z)
        x1, y1 = deg2num(lat_min, lon_max, z)
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                plan.append((z, x, y))

    total = len(plan)
    print("Emprise      : %.3f,%.3f -> %.3f,%.3f" % (lat_min, lon_min, lat_max, lon_max))
    print("Zooms        : %d a %d" % (zmin, zmax))
    print("Source       : %s" % source)
    print("Tuiles       : %d" % total)
    print("Sortie       : %s" % sortie)
    if total > 200000:
        print("\nATTENTION : plus de 200 000 tuiles. Reduisez l emprise ou le zoom maximal.")
        if input("Continuer malgre tout ? [o/N] ").strip().lower() != "o":
            return 1
    print()

    cx = creer_base(sortie, {
        "name": "SCRIBE %s z%d-%d" % (source.upper(), zmin, zmax),
        "type": "baselayer",
        "version": "1",
        "description": "Fond de carte local SCRIBE - " + src["attribution"],
        "format": src["format"],
        "minzoom": str(zmin),
        "maxzoom": str(zmax),
        "bounds": "%f,%f,%f,%f" % (lon_min, lat_min, lon_max, lat_max),
        "attribution": src["attribution"],
    })

    ok = vide = ko = 0
    debut = time.time()
    for i, (z, x, y) in enumerate(plan, 1):
        data = telecharger(src["url"].format(z=z, x=x, y=y))
        if data:
            # MBTiles stocke en TMS : inversion de la ligne.
            ty = (2 ** z - 1) - y
            cx.execute(
                "INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)",
                (z, x, ty, sqlite3.Binary(data)),
            )
            ok += 1
        elif data == b"":
            vide += 1
        else:
            ko += 1
        if i % 200 == 0:
            cx.commit()
            reste = (time.time() - debut) / i * (total - i)
            sys.stdout.write(
                "\r  %d/%d  ok=%d  echecs=%d  reste ~%dmin"
                % (i, total, ok, ko, reste / 60)
            )
            sys.stdout.flush()
        if pause:
            time.sleep(pause)

    cx.commit()
    cx.close()
    taille = os.path.getsize(sortie) / (1024 * 1024)
    print("\n\nTermine : %d tuiles, %.1f Mo" % (ok, taille))
    if ko:
        print("%d tuiles non recuperees (relancer la commande les completera)" % ko)
    print("\nLe fichier est pris en compte automatiquement au prochain demarrage.")
    print("Verification : Administration -> APIs & IA -> Fond de carte")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Fond de carte local SCRIBE")
    ap.add_argument("--bbox", help="lat_min,lon_min,lat_max,lon_max")
    ap.add_argument("--min-zoom", type=int, default=8)
    ap.add_argument("--max-zoom", type=int, default=14)
    ap.add_argument("--source", choices=list(SOURCES), default="ign")
    ap.add_argument("--sortie", default=None)
    ap.add_argument("--pause", type=float, default=0.05,
                    help="secondes entre deux tuiles, par respect du fournisseur")
    ap.add_argument("--monde", action="store_true",
                    help="filet de securite mondial z0-5, quelques Mo")
    a = ap.parse_args()

    os.makedirs(os.path.join(RACINE, "data"), exist_ok=True)

    if a.monde:
        sortie = a.sortie or os.path.join(RACINE, "data", "basemap_world.mbtiles")
        return construire((-85.0, -180.0, 85.0, 180.0), 0, 5, "osm", sortie, a.pause)

    if not a.bbox:
        ap.error("--bbox est requis (ou utilisez --monde)")
    try:
        bbox = tuple(float(v) for v in a.bbox.split(","))
        assert len(bbox) == 4
    except Exception:
        ap.error("--bbox attend lat_min,lon_min,lat_max,lon_max")

    sortie = a.sortie or os.path.join(RACINE, "data", "basemap.mbtiles")
    return construire(bbox, a.min_zoom, a.max_zoom, a.source, sortie, a.pause)


if __name__ == "__main__":
    sys.exit(main())
