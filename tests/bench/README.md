# SCRIBE benchmark de validation

Valide en **3 secondes** que SCRIBE fonctionne de bout en bout : ce que tu vérifierais manuellement en 30 minutes.

## Lancer

```bash
./tests/bench/run_bench.sh
```

Ou avec détail des étapes :

```bash
python3 tests/bench/bench.py --verbose
```

## Ce que le bench vérifie

Cinq scénarios critiques sont exécutés contre **1 collecteur + 2 instances SCRIBE** démarrés automatiquement sur les ports 17900/17901/17902 (en local uniquement) :

| #   | Scénario                  | Ce qui est testé                                               |
|-----|---------------------------|----------------------------------------------------------------|
| 01  | `health`                  | Les 3 services répondent sur `/health`                         |
| 02  | `auth`                    | Login admin fonctionne sur chaque instance SCRIBE              |
| 03  | `incident_local`          | Créer un incident puis le relire via l'API                     |
| 04  | `transfert_federe`        | Transfert CHAG → GHTLMB via collecteur (flow qui a bugué en 2182/2184) |
| 05  | `rapport_html`            | Le collecteur génère un rapport HTML valide avec Chart.js      |

**Objectif** : à chaque nouveau build SCRIBE, lancer ce bench avant déploiement pour détecter les régressions.

## Sortie attendue

```
╔══════════════════════════════════════════════════════════════╗
║  TOUS LES SCÉNARIOS OK  (5/5)                                ║
║  Steps : 17/17   Durée : 3.04s                               ║
╚══════════════════════════════════════════════════════════════╝
```

Exit code `0` si tout passe, `1` en cas de régression, `2` si un port est déjà occupé, `3` si une instance a refusé de démarrer.

## Modes

- `--verbose` : affiche le détail de chaque étape (HTTP status, body, timings)
- `--keep-running` : ne tue pas les instances à la fin, permet de les inspecter manuellement sur localhost:17900/17901/17902

## Prérequis

Python 3.8+ avec les dépendances SCRIBE habituelles (`fastapi`, `httpx`, `sqlalchemy`, `uvicorn`, `bcrypt`, `passlib`).

### ⚠ Incompatibilité bcrypt 5.x + passlib 1.7.4

**Bug connu** : sur Python 3.12 avec `bcrypt >= 5.0.0` et `passlib == 1.7.4`, le login crashe avec `ValueError: password cannot be longer than 72 bytes`.

**Contournement** : installer `bcrypt < 5` :

```bash
pip install 'bcrypt<5'
```

Si ton VPS de prod fonctionne, c'est probablement qu'il a déjà `bcrypt 4.x` installé. Vérifier avec :

```bash
python3 -c "import bcrypt; print(bcrypt.__version__)"
```

Ce problème concerne SCRIBE lui-même (pas le bench) et devrait être fixé dans un build ultérieur soit par pin de `bcrypt<5` dans `requirements.txt`, soit par migration de `passlib` vers `bcrypt` natif.

## Ajouter un nouveau scénario

Dans `bench.py`, ajouter une fonction `sc_06_xxx()` qui retourne un `Scenario` puis l'ajouter dans `scenarios_fn` dans `run_all()` :

```python
def sc_06_mon_test() -> Scenario:
    s = Scenario("06_mon_test", "Description courte")
    # Login + actions + vérifications
    code, body = http("POST", f"{CHAG_URL}/api/v1/auth/login", ...)
    s.add("nom de l'étape", success_bool, "détail pour debug")
    return s
```

## Debug en cas d'échec

Quand un scénario échoue, le workspace temporaire est **conservé** et son chemin affiché. Il contient :

- `collecteur.log` — logs complets du collecteur
- `chag.log`, `ghtlmb.log` — logs complets des instances
- `*.db` — bases SQLite pour inspection
- `config_*.xml`, `config_*.js` — configurations générées

Si tout passe, le workspace est nettoyé automatiquement.

## Limites

- Le bench teste le **comportement API** pas l'UI web (pas de Selenium/Playwright)
- Les 5 scénarios couvrent les flows les plus critiques mais pas toutes les fonctionnalités (cellule, brancardage, chat inter-GHT, rex, etc.) — à enrichir au besoin
- Ports 17900-17902 en dur (éviter conflit avec instances de prod sur 8000 / 8660-8666 / 8565)
- Tourne en local uniquement (pas de mode `--target=vps` pour l'instant)
