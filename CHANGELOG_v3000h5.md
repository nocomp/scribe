# Changelog — v3.0.0-alpha12 (build interne `v3000h5`)

**Date** : 30 mai 2026
**Base** : v3000h4
**Statut** : patch CRITIQUE — l'Assistant ne fonctionnait pas du tout (500 sur /coach/check).

---

## Bug critique fixé : `/api/v1/tuteur/coach/check` retournait 500

### Diagnostic (depuis les logs console Hervé)

```
[tuteur] session restaurée: 1
[tuteur] armé en mode exercice — session 1
GET http://localhost:8660/api/v1/tuteur/coach/check 500 (Internal Server Error)
```

Côté serveur, la requête plantait sur `TuteurSession.timestamp_fin` et
`TuteurSession.timestamp_debut` — ces colonnes **n'existent pas** dans le modèle.
Les vrais noms sont `ended_at` et `started_at` (cf. `plugins/tuteur/models.py`).

C'est moi qui ai inventé les noms (`timestamp_fin`/`timestamp_debut`) en écrivant
les routes coach sans relire le modèle existant. SQLAlchemy levait une
`AttributeError`, attrapée par le wrapper → 500. Le widget polling échouait
silencieusement (try/catch dans `pollCheck`) → la bulle ne s'affichait jamais.

### Corrections

Dans `plugins/tuteur/routes.py`, fonctions `coach_check` et `coach_mute` :
- `TuteurSession.timestamp_fin.is_(None)` → `TuteurSession.ended_at.is_(None)`
- `TuteurSession.timestamp_debut.desc()` → `TuteurSession.started_at.desc()`

Aucun autre changement. C'est un patch chirurgical.

---

## Effet attendu après ce build

Sur l'instance joueur (`localhost:8660` ou autre port d'instance) :
1. La bulle 🎓 doit apparaître **immédiatement** bas-droite après le splash "Je suis prêt"
2. Le polling `/coach/check` toutes les 60s doit retourner **200** (au lieu de 500)
3. Au bout des seuils (3 min incident sans action, 2 min stagnation en mode exo),
   les messages doivent apparaître avec badge rouge sur la bulle

## Fichiers modifiés (vs v3000h4)

| Fichier | Modifs |
|---|---|
| `plugins/tuteur/routes.py` | corrige `timestamp_fin/debut` → `ended_at/started_at` (2 occurrences) |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha11 → alpha12 |

## Validation pré-build
- ✅ `ast.parse` : routes.py
- ✅ Champs réellement présents dans `TuteurSession` (models.py) : `started_at`, `ended_at`, `user_id`

## Tests à faire côté Hervé

1. Aller sur l'instance joueur 8660 + se connecter
2. Devtools (F12) → Console → onglet Réseau → filtrer "coach"
3. Au bout de quelques secondes : un appel `GET /api/v1/tuteur/coach/check` doit apparaître avec **200 OK**
4. La bulle 🎓 doit être visible en bas à droite
5. Si on a déjà des incidents non traités > 3 min ou pas d'action > 2 min :
   badge rouge + clic → message Assistant

## Bug pré-existant signalé (non corrigé, hors périmètre)

Les erreurs `GET http://localhost:8565/api/transferts-en-cours 401` dans la console
viennent de `loadTransfertsEntrants` (scribe.js:5875) : depuis l'instance joueur
8660, on appelle le collecteur exercice 8565 avec le mauvais token. Pré-existant,
sans impact sur l'Assistant. À traiter dans un autre passage.

## Reste à faire (rappel phases Assistant)
- v3000i : pipeline `/analyser-to-tasks` + transformation recommandation → Kanban
- v3000j : prompt libre `/coach/ask`
- v3000k : bouton "🤖 → tâches" depuis messagerie
