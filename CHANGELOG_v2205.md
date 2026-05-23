# SCRIBE build v2205 — CHANGELOG

**Date** : 2026-04-22
**Version applicative** : v2.3.84
**Base** : v2204

---

## Résumé

**Hotfix critique** : le build v2204 contenait par erreur mes fichiers
de state collecteur persistants, ce qui polluait les déploiements neufs
avec des transferts et tokens admin résiduels de mes tests.

Ce build corrige ça + étend le `--reset` pour prévenir le problème.

Bench 5/5 vert.

## Bug critique identifié par test terrain

### Symptôme
Tu as déployé v2204 fraîchement, lancé avec `--reset`, et tu trouvais
toujours sur l'instance DEMO2 un transfert **"Maternité Bench →
Réanimation Bench"** qui n'existait pas dans ton exercice actuel.

Ce transfert était en plus visible **uniquement sur DEMO2, pas sur
CHANGE** — comportement incohérent qui ne collait pas à une simple
erreur de seed.

### Cause racine
Le zip v2204 contenait **3 fichiers de state runtime** qui n'auraient
jamais dû être dans l'archive :

```
collecteur_exercice/collecteur_exo_transferts.json  (478 bytes)
  → 1 transfert "Maternité Bench → Réanimation Bench" résiduel
collecteur_exercice/collecteur_exo_admin.json
  → Mon token admin local
collecteur/collecteur_admin.json
  → Autre token admin local
```

Ces fichiers sont créés automatiquement au runtime par les collecteurs
pour persister leur état (transferts pushés par les instances, token
admin éphémère). Ils étaient restés sur mon environnement de build
entre les tests et se sont retrouvés dans les zips v2201 à v2204.

Au redémarrage d'un collecteur exercice :
1. `load_transferts()` lit `collecteur_exo_transferts.json`
2. Trouve le transfert résiduel, le charge en mémoire
3. Le pousse aux instances via `/api/push` à leur première connexion
4. DEMO2 l'affiche → bug visible

Le `--reset` de `lancer_exercice.sh` ne supprimait **que les DBs des
instances**, pas les fichiers de state du collecteur exercice lui-même.
Donc même un reset "propre" laissait ce relicat.

**Impact sécurité** : en plus du bug UI, mon token admin était livré
à tous les utilisateurs du zip → si deux utilisateurs déployaient
v2204, ils partageaient le même admin token et pouvaient potentiellement
se piloter mutuellement.

## Fix 1 — Nettoyage du build

Les 3 fichiers problématiques retirés du workspace avant zip :

```bash
rm -f collecteur_exercice/collecteur_exo_transferts.json
rm -f collecteur_exercice/collecteur_exo_admin.json
rm -f collecteur/collecteur_admin.json
rm -f scribe_*.db scribe_*.db-journal  # DBs dev aussi
```

Vérification runtime : au démarrage du collecteur, `transferts_inter`
est bien une liste vide `[]`, confirmé par test.

## Fix 2 — `--reset` étendu

`lancer_exercice.sh` purge désormais tous les fichiers de state
runtime du collecteur exercice, pas seulement les DBs :

```bash
if [ $RESET -eq 1 ]; then
    # DBs instances
    rm -f scribe_exo_*.db
    rm -f scribe_exo_*.db-journal
    # v2205 — Purger aussi le state JSON du collecteur exercice
    rm -f collecteur_exercice/collecteur_exo_transferts.json
    rm -f collecteur_exercice/collecteur_exo_incidents.json
    rm -f collecteur_exercice/collecteur_exo_decisions.json
    rm -f collecteur_exercice/collecteur_exo_prets.json
    rm -f collecteur_exercice/collecteur_exo_admin.json
    rm -f collecteur_exercice/collecteur_exo_sessions.json
    # Configs JS regénérées
    for ES in ...; do rm -f instances/$ES/config.js; done
    echo "  DBs exercice + state collecteur supprimés"
fi
```

## Fix 3 — `.gitignore` étendu

Ajout des patterns pour **prévenir définitivement** que ces fichiers
reviennent dans les futurs builds ou un repo GitHub :

```
# State persistant des collecteurs (runtime, ne JAMAIS committer)
collecteur/collecteur_admin.json
collecteur/collecteur_transferts.json
collecteur/collecteur_incidents.json
collecteur/collecteur_decisions.json
collecteur/collecteur_sessions.json
collecteur_exercice/collecteur_exo_admin.json
collecteur_exercice/collecteur_exo_transferts.json
collecteur_exercice/collecteur_exo_incidents.json
collecteur_exercice/collecteur_exo_decisions.json
collecteur_exercice/collecteur_exo_prets.json
collecteur_exercice/collecteur_exo_sessions.json
```

## Validation

- **115 fichiers Python OK** (`ast.parse`)
- **0 fichier state résiduel** dans le workspace de build
- **Démarrage froid** testé : `transferts_inter == []`
- **Bench 5/5 vert** en 3.35s

## Fichiers modifiés

```
lancer_exercice.sh
  - --reset étendu aux fichiers JSON state collecteur

.gitignore
  - Ajout patterns fichiers state (12 fichiers)

COMPRESSION :
  - Retrait collecteur_exercice/collecteur_exo_transferts.json
  - Retrait collecteur_exercice/collecteur_exo_admin.json
  - Retrait collecteur/collecteur_admin.json
  - Retrait scribe_*.db résiduels

main.py, app/static/index.html, lancer_exercice.sh,
collecteur/collecteur.py : bumps version
```

## Bumps de version

| Fichier                                    | Avant   | Après   |
|--------------------------------------------|---------|---------|
| `main.py`                                  | v2.3.83 | v2.3.84 |
| `app/static/index.html`                    | v2.3.83 | v2.3.84 |
| `lancer_exercice.sh`                       | v2.3.83 | v2.3.84 |
| `collecteur_exercice.py`                   | 2.3.83  | 2.3.84  |
| `collecteur.py` (UI)                       | 2.3.31  | 2.3.32  |

## Action recommandée VPS

Avant de lancer v2205 :

```bash
# 1. Arrêter les services en cours
pkill -f "SCRIBE_EXERCICE_MODE=1"
pkill -f collecteur

# 2. Nettoyer manuellement les résidus du déploiement v2204
rm -f scribe_v2204/collecteur_exercice/collecteur_exo_*.json
rm -f scribe_v2204/collecteur/collecteur_admin.json
rm -f scribe_v2204/scribe_*.db

# 3. Déployer v2205
unzip scribe_v2205.zip
cd scribe_v2205
bash lancer_exercice.sh --reset
```

Vérifier après lancement : l'onglet TRANSFERTS de DEMO2 doit être vide
tant que tu n'as pas créé un transfert dans l'exercice courant.

## Mea culpa

C'est une erreur de build de ma part — je devrais avoir un processus
de pré-zip qui purge systématiquement ces fichiers. J'ajoute ça dans
ma checklist pour les futurs builds :

1. ✅ Purger `__pycache__`, `*.pyc`, `*.db`, `*.db-journal`
2. ✅ Purger `collecteur_exercice/collecteur_exo_*.json`
3. ✅ Purger `collecteur/collecteur_*.json`
4. ✅ Vérifier au grep qu'aucun secret/token local ne traîne
5. ✅ Test runtime démarrage froid (`transferts_inter == []`)
6. ✅ Bench 5/5 vert

Ces étapes seront systématiques à partir de maintenant.

## Prochaines étapes

Une fois v2205 validée terrain (UI clean sans relicats) :
- Release GitHub publique v1.0 (README, licence AGPL, screenshots, CI)
- Refactor v2.4.x en coulisse
