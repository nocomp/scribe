# SCRIBE 3.6.2-beta — Fond de carte sans configuration

## Ce qui a motivé ce changement

Fin août 2026, CARTO a filigrané ses tuiles raster sans préavis et annoncé le
retrait progressif du service. Toutes les cartes de SCRIBE se sont retrouvées
barrées d'un « API KEY REQUIRED ».

Le mode de défaillance mérite d'être noté, parce qu'il conditionne la solution
retenue : le serveur répondait **HTTP 200 avec une image valide**. Aucune
erreur réseau, aucun code d'échec, rien qu'un mécanisme de supervision aurait
pu détecter. Une chaîne de repli automatique n'aurait rien vu.

La conclusion est simple : dépendre de la bienveillance d'un fournisseur
commercial revient à accepter ce risque à chaque renouvellement de ses
conditions. Et cela contredisait directement ce que SCRIBE promet — fonctionner
quand plus rien d'autre ne fonctionne.

## Ce qui change

### Résolution automatique, aucune configuration

Le fond de carte est désormais choisi par le serveur au démarrage, selon une
chaîne de priorité. Aucune clé d'API n'est requise à aucun niveau.

| Rang | Source | Couverture | Condition |
|------|--------|-----------|-----------|
| 1 | `data/basemap.mbtiles` | selon le fichier | présent → prioritaire |
| 2 | Plan IGN (Géoplateforme) | France + DOM-TOM | sites dans l'emprise |
| 3 | OpenStreetMap | mondiale | défaut |

Une installation neuve, n'importe où dans le monde, affiche une carte
utilisable au premier démarrage. Un établissement français obtient
automatiquement le Plan IGN, sans avoir rien à paramétrer.

### Une seule déclaration de couche pour tout le projet

Avant cette version, la déclaration Leaflet du fond de carte existait en
**quatre exemplaires** : `scribe.js` (carte principale et carte Soins),
`collecteur/collecteur.py`, `collecteur_demo/collecteur.py`. Corriger le
filigrane CARTO a demandé quatre modifications identiques — et il aurait suffi
d'en oublier une pour livrer une supervision propre et une console d'exercice
filigranée.

Il n'existe plus aucun appel à `L.tileLayer` en dehors de
`app/static/js/basemap.js`. Le collecteur sert ce même fichier depuis
`/static/js/basemap.js` : instance et supervision partagent physiquement le
même code.

### Mode hors-ligne

Un fichier MBTiles déposé dans `data/` est détecté et devient prioritaire. La
cartographie ne sort alors plus du réseau du tout, ce qui répond au scénario où
l'établissement coupe sa sortie Internet pour contenir une attaque.

    python3 tools/build_basemap.py --bbox 45.4,5.5,46.4,7.0 --min-zoom 8 --max-zoom 14
    python3 tools/build_basemap.py --monde     # filet mondial z0-5, quelques Mo

### Mode vectoriel optionnel

`SCRIBE_BASEMAP=openfreemap` bascule sur OpenFreeMap, qui ne demande ni
inscription, ni clé, ni quota. MapLibre GL n'est téléchargé que si ce mode est
réellement activé : en configuration par défaut, aucune dépendance
supplémentaire n'est chargée.

### Écran d'administration

Administration → APIs & IA → **Fond de carte** affiche la source active, le
motif du choix automatique et le catalogue disponible. En lecture seule, comme
les sections Fournisseur IA et Routing ambulances.

## Fichiers

**Nouveaux**

- `core/basemap.py` — résolution de la chaîne, lecture MBTiles. Bibliothèque
  standard uniquement, pour être importable par le collecteur qui tourne dans
  un processus séparé.
- `app/api/basemap.py` — `/api/v1/config/basemap`, service des tuiles locales,
  catalogue réservé aux administrateurs.
- `app/static/js/basemap.js` — construction de la couche, partagée par
  l'instance et les deux collecteurs.
- `tools/build_basemap.py` — fabrication du MBTiles hors-ligne.

**Modifiés**

- `main.py` — enregistrement du router ; CSP construite depuis
  `core.basemap.csp_hosts()`.
- `app/static/js/scribe.js` — les deux cartes passent par `scribeBasemap.init()`.
- `collecteur/collecteur.py`, `collecteur_demo/collecteur.py` — même bascule,
  plus les routes servant `basemap.js` et la configuration résolue.
- `app/static/index.html` — chargement de `basemap.js`, section d'administration.

## Point de vigilance sur la CSP

`img-src` et `connect-src` autorisent **tous** les fournisseurs de la chaîne,
pas seulement celui qui est actif. C'est délibéré : la chaîne peut basculer
d'une source à l'autre entre deux démarrages, et une CSP calculée sur le seul
fournisseur actif produirait une carte grise avec un blocage silencieux en
console.

`worker-src` accepte désormais `blob:`, requis par MapLibre qui instancie ses
workers depuis un blob. Sans cela, le mode vectoriel afficherait un fond vide.

## Variables d'environnement

| Variable | Valeurs | Effet |
|----------|---------|-------|
| `SCRIBE_BASEMAP` | `auto` `local` `ign` `osm` `openfreemap` `custom` | force un fournisseur |
| `SCRIBE_BASEMAP_URL` | gabarit XYZ ou WMTS | mode `custom` |
| `SCRIBE_BASEMAP_ATTR` | texte | attribution du mode `custom` |
| `SCRIBE_BASEMAP_MBTILES` | chemin | MBTiles hors de `data/` |
| `SCRIBE_BASEMAP_MAXZOOM` | entier | plafond de zoom |
| `SCRIBE_BASEMAP_CSP_EXTRA` | hôtes séparés par des virgules | ajouts à la CSP |

Sans aucune de ces variables, la chaîne automatique s'applique.

## Vérification après déploiement

    curl -s http://localhost:8000/api/v1/config/basemap | python3 -m json.tool
    curl -sI http://localhost:8000/health | grep -i content-security-policy

Puis Ctrl+Shift+R sur l'interface et sur la supervision. Le paramètre
`?v=362beta` du cache-busting a été aligné sur les trois surfaces : sans cela,
le navigateur servirait l'ancien `scribe.js` et la carte resterait filigranée
alors que le serveur envoie le bon fichier.

## Limite assumée

La bascule automatique du navigateur ne se déclenche que sur des erreurs
franches — délai dépassé, 403, 404. Une dégradation silencieuse du type
filigrane reste indétectable côté client. Seul un fond local protège
réellement contre ce cas, et c'est la raison pour laquelle il occupe le premier
rang de la chaîne.
