# SCRIBE 3.6.3-beta

> ## ⚠ À traiter avant tout déploiement
>
> Cette release retire du dépôt cinq fichiers de secrets qui y étaient
> versionnés. **Les retirer ne suffit pas** : ils restent dans l'historique
> git et doivent être considérés comme compromis.
>
> | Fichier | Contenu |
> |---|---|
> | `collecteur/collecteur_tokens.json` | 9 jetons de fédération + sigles d'établissements réels |
> | `collecteur/collecteur_admin.json` | jeton admin du collecteur de supervision |
> | `collecteur_demo/collecteur_admin.json` | jeton admin du collecteur de démonstration |
> | `collecteur_demo/collecteur_tokens.json` | jeton de démonstration |
> | `data/.scribe_secret` | **clé de signature des jetons JWT** |
>
> Le dernier est le plus grave : il permet de forger un jeton valide pour toute
> instance qui l'utiliserait encore.
>
> `.gitignore` mentionnait déjà `collecteur/collecteur_tokens.json`, mais le
> fichier avait été committé avant l'ajout de la règle. `.gitignore` n'a aucun
> effet sur un fichier déjà suivi : il faut un `git rm --cached` en plus.
>
> ```bash
> git rm --cached collecteur/collecteur_tokens.json collecteur/collecteur_admin.json \
>                 collecteur_demo/collecteur_tokens.json collecteur_demo/collecteur_admin.json \
>                 data/.scribe_secret
> git commit -m "Retrait des secrets versionnes"
> ```
>
> Puis, dans l'ordre : régénérer la clé `SCRIBE_SECRET` et les jetons admin,
> réenrôler les instances, et purger l'historique du dépôt (`git filter-repo`
> ou BFG) avant force-push. Tant que l'historique n'est pas purgé, les secrets
> restent lisibles par n'importe qui.
>
> Tous ces fichiers sont régénérés automatiquement au premier démarrage s'ils
> sont absents : leur retrait ne casse rien.


Trois correctifs de fond, tous découverts en préparant une démonstration.
Deux d'entre eux empêchaient silencieusement des fonctionnalités de marcher,
sans jamais produire la moindre erreur visible.

---

## 1. Le collecteur perdait ses jetons à chaque redémarrage

**Symptôme.** Le démarrage affichait « Tokens enregistrés : [...] » avec la
bonne liste, mais `GET /health` répondait `tokens: 0`. Toute instance poussant
avec un jeton pourtant présent dans `collecteur_tokens.json` recevait un 401
« Non autorisé ». Après chaque redémarrage, les établissements déjà acceptés
retombaient en attente et devaient être réacceptés à la main.

**Cause.** La dernière ligne du collecteur lance uvicorn avec une chaîne
d'import :

```python
uvicorn.run("collecteur:app", host="0.0.0.0", port=_port, reload=False)
```

Uvicorn réimporte alors le module sous le nom `collecteur`, dans un espace de
noms distinct de `__main__`. Or c'est le bloc `if __name__ == "__main__"` qui
appelle `load_tokens()`, `load_data()`, `load_pending()`,
`load_messages_inter()` et `load_relay()`. Ces appels remplissaient les
dictionnaires de `__main__`, tandis que l'application servie vivait dans le
module `collecteur`, avec des dictionnaires vides.

**Correctif.** Les chargements passent dans le gestionnaire `startup` de
FastAPI, qui s'exécute dans le processus servant l'application — quelle que
soit la manière dont il a été lancé : `python3 collecteur.py`,
`uvicorn collecteur:app`, systemd ou conteneur. Les fonctions de chargement
fusionnent avec les valeurs par défaut et sont idempotentes.

**Vérification.**

```bash
curl -s http://127.0.0.1:9000/health
```

Le champ `tokens` doit correspondre au nombre d'entrées de
`collecteur_tokens.json`, et non plus valoir 0.

---

## 2. Les archives de crise étaient créées mais jamais téléchargeables

**Symptôme.** Le bouton d'archivage semblait échouer. Les fichiers ZIP étaient
pourtant bien écrits dans `archives/`.

**Cause.** `scribe.js` fabriquait un `<a href="...">` vers la route de
téléchargement et le cliquait. Un clic sur un lien déclenche une navigation du
navigateur, qui n'envoie pas l'en-tête `Authorization`. La route étant protégée
par `get_current_user`, elle répondait 401 et rien n'arrivait. C'est la même
classe de défaut que celle corrigée sur `/uploads` en h169.

**Correctif.** Le téléchargement passe par `apiFetch`, qui porte le jeton, puis
le contenu est remis au navigateur via un objet blob. Le jeton ne circule donc
jamais dans une URL : ni dans les journaux du serveur, ni dans l'historique du
navigateur, ni dans un en-tête `Referer`. C'est préférable à l'ajout d'un
paramètre `?token=` sur la route.

---

## 3. Le scénario rejouable n'était jamais inclus dans l'archive

**Symptôme.** La case « générer un scénario rejouable » n'avait aucun effet :
le ZIP sortait sans `scenario.json`, et le message de confirmation ne
mentionnait jamais le scénario.

**Cause.** Il existait deux implémentations de `POST /archiver-crise` :

| Fichier | État | Routé |
|---|---|---|
| `app/api/rapport.py` | à jour, sait produire le scénario | **non** |
| `plugins/rapport/api.py` | copie divergente, ignore le paramètre | oui |

L'interface envoyait bien `?generer_scenario=true`, mais FastAPI ignore
silencieusement un paramètre que la signature ne déclare pas.

**Correctif.** La génération est portée dans le plugin, avec trois
améliorations :

- le sigle de l'acteur est lu depuis la configuration de fédération au lieu
  d'être codé en dur — un scénario dont l'acteur porte le mauvais sigle n'est
  pas rejouable tel quel ;
- le `README.txt` n'est plus écrit deux fois, ce qui produisait une entrée en
  double dans le ZIP ;
- la réponse expose `scenario_inclus`, que l'interface attendait déjà.

En cas d'échec de la génération, l'archive CSV reste produite et un
`scenario_error.txt` explique ce qui s'est passé.

**Vérification.**

```bash
unzip -l archives/crise_*.zip | grep scenario
```

**Dette restante.** `app/api/rapport.py` demeure une copie non routée, désormais
en retard sur le plugin. Deux implémentations divergentes du même endpoint sont
exactement ce qui a coûté cette fonctionnalité : à terme, le plugin devrait
importer le module plutôt que le dupliquer.

---

## Nouveaux outils

### `tools/demo_data.py`

Jeu de données de démonstration complet pour produire des captures d'écran sans
jamais toucher à des données réelles : incidents, kanban, main courante,
décisions, relève, capacité, transferts, messagerie, chaîne d'alerte, page de
statut public, REX, plus les tables des plugins présents.

```bash
python3 tools/demo_data.py --inject --pivot CHVAL
python3 tools/demo_data.py --refresh    # remet les transferts à l'heure
python3 tools/demo_data.py --clean
```

Le retour arrière est doublé : une sauvegarde complète de chaque base est prise
avant écriture, et chaque ligne insérée est journalisée. Le cycle complet rend
la base identique à l'octet près.

Le scénario est asymétrique — un établissement subit l'attaque, les autres en
encaissent les conséquences. Les identités, sigles et destinations sont lues
dans le `config.js` de chaque instance : les transferts désignent de vraies
instances du territoire, sans quoi ni la carte ni la supervision ne pourraient
les résoudre.

### `tools/push_transferts.py`

Les transferts ne remontent pas par le push périodique de fédération : ils sont
envoyés un par un par `trPushCollecteur()` au moment de l'action utilisateur.
Des transferts écrits directement en base restent donc invisibles en
supervision. Ce script rejoue ce push.

```bash
python3 tools/push_transferts.py --dry-run
python3 tools/push_transferts.py
```

La supervision affiche les transferts à deux endroits, alimentés
différemment — le script remplit les deux :

| Vue | Stockage | Alimentée par |
|---|---|---|
| Cartographie | liste `transferts_inter` | jeton de fédération de l'instance |
| Transferts (kanban) | base SQLite dédiée | jeton admin du collecteur |

Aucune donnée patient n'est transmise : seuls le flux, l'âge estimé et le motif
circulent.

### `tools/build_basemap.py`

Fabrication d'un fond de carte local, pour un fonctionnement totalement
hors-ligne.

```bash
python3 tools/build_basemap.py --bbox 45.4,5.5,46.4,7.0 --min-zoom 8 --max-zoom 14
python3 tools/build_basemap.py --monde
```

---

## Mise à jour

Le paramètre de cache-busting passe à `?v=363beta` sur les trois surfaces.
Sans cet alignement, le navigateur servirait l'ancien `scribe.js` depuis son
cache et le téléchargement d'archive échouerait encore.

```bash
pkill -f collecteur.py && pkill -f main.py
# déployer, puis relancer
curl -s http://127.0.0.1:9000/health          # tokens doit être > 0
curl -s http://127.0.0.1:8000/api/v1/config/basemap | python3 -m json.tool
```

Puis Ctrl+Shift+R sur l'interface et sur la supervision.
