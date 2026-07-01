# Changelog — v3.0.0-alpha15 (build interne `v3000h8`)

**Date** : 30 mai 2026
**Base** : v3000h7
**Statut** : Assistant utile — création tâches Kanban via Albert + nettoyages UX.

---

## 1. Assistant proactif vraiment utile : génération de tâches Kanban

Avant : bouton "Suggérer 3 actions" → popup explicatif "arrive en v3000j". Inutile.

Après : bouton **"✨ Créer 3 tâches"** qui :
1. Appelle Albert (`/api/v1/tuteur/coach/suggest-tasks/{incident_id}`)
2. Affiche une **modale preview** avec 3 actions concrètes, éditables champ par champ
3. Au clic "Créer les tâches", crée 3 tâches Kanban liées à l'incident (colonne BACKLOG, priorité haute)
4. Affiche un toast de confirmation et acknowledge le message Assistant

Pipeline complet :
- **Backend**
  - `POST /api/v1/tuteur/coach/suggest-tasks/{incident_id}` — appelle Albert avec prompt structuré, parse les 3 actions du texte retourné (format ACTIONS: 1. ... 2. ... 3. ...)
  - **Fallback** générique si Albert indisponible : 3 actions adaptées au type de crise (CYBER ou SANITAIRE)
  - `POST /api/v1/tuteur/coach/create-tasks` — crée les tâches en base (max 5 par appel)
  - Parser robuste : gère format Albert numéroté, puces "-/•/*", fallback sur 3 premières lignes substantielles
- **Frontend** (`coach.js`)
  - Nouvelle modale `showSuggestModal` avec spinner pendant l'appel IA
  - Indicateur de source : "✨ Propositions Albert IA" ou "⚙️ Propositions génériques"
  - Inputs texte éditables pour chaque action
  - Boutons Annuler / Créer
  - Toast de succès (utilise `window.toast` si présent, sinon mini-toast natif)

## 2. Navigation "Voir l'incident" fonctionnelle

Avant : `open_tab` cherchait `[onclick*="tab-soins"]` qui ne matchait pas toujours.

Après : pattern SCRIBE standard `tab-btn-soins` essayé en priorité, puis variantes (`data-tab="soins"`).
Si trouvé, le widget se replie automatiquement pour laisser place à l'onglet ouvert.
Si introuvable, log console (au lieu d'échec silencieux).

## 3. Session tuteur garantie au démarrage

Avant : `tuteurStartSession` plantait silencieusement (`catch` sans log), le user terminait avec `session_id: null`.

Après :
- **Backend** `POST /api/v1/tuteur/session/start` est **idempotent** : si l'utilisateur a déjà une session active, la réutilise au lieu d'en créer une nouvelle.
- **Frontend** : retry 1 fois en cas d'échec réseau, avec log explicite si échec définitif.
- Combiné avec v3000h7 (création auto en mode exercice côté backend), la session est garantie d'exister dès le 1er stimulus reçu OU dès la 1ère action utilisateur.

## 4. Pollution console réduite

Les appels collecteur exercice (`/api/transferts-en-cours`, `/api/demandes`, `/api/messages`) depuis l'instance joueur retournaient 401 (token de fédération invalide) **toutes les 30s**, polluant la console.

Solution : **circuit breaker** — après 3 échecs 401 consécutifs, ces appels sont **désactivés pour la session**. Variable globale `_collecteurDisabled` + compteur `_collecteurFailCount`. Reset à 0 au premier succès.

Console : un seul warning `[fed] Appels collecteur désactivés (3 x 401)` au lieu de centaines d'erreurs.

## 5. Bonus : `/api/exercice/statuts-publics` ne renvoie plus 500

La route collecteur exercice plantait en 500 dans certains cas (probablement scénario malformé ou acteur sans port). Ajout d'un try/except global qui retourne `{running: False, sites: [], error: "..."}` au lieu d'exposer le 500.

## 6. Bonus : bouton "Lancer" instance exercice — feedback visuel immédiat

Avant : pas de retour visuel pendant les 2-5s de spawn → impression que le clic n'avait pas été pris en compte.

Après : au clic, le bouton passe immédiatement en état `⏳ Démarrage…` (désactivé, opacity 0.6, cursor wait). Rétabli en cas d'erreur, ou remplacé par les boutons "Ouvrir / Arrêter" en cas de succès.

---

## Fichiers modifiés (vs v3000h7)

| Fichier | Modifs |
|---|---|
| `plugins/tuteur/routes.py` | session_start idempotent, +2 routes coach (suggest-tasks, create-tasks), parser actions Albert |
| `plugins/tuteur/coach_rules.py` | label bouton "✨ Créer 3 tâches" au lieu de "💡 Suggérer 3 actions" + action_type generate_tasks |
| `app/static/js/coach.js` | modale preview tâches, ack après création, navigation onglet améliorée |
| `app/static/js/scribe.js` | tuteurStartSession retry, circuit breaker _collecteurDisabled dans loadTransfertsEntrants + pollIGHTBadge |
| `master/exercice.html` | feedback visuel immédiat sur startInstance |
| `collecteur_exercice/collecteur_exercice.py` | try/except global sur statuts-publics |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha14 → alpha15 |

## Validation pré-build
- ✅ `ast.parse` : routes.py, coach_rules.py, collecteur_exercice.py
- ✅ `node --check` : coach.js, scribe.js, exercice.html JS
- ✅ Test parser Albert : format numéroté + format puces + fallback

## Tests à faire côté Hervé

**Création de tâches via Assistant**
1. Démarrer scénario, attendre que l'Assistant émette un message sur un incident
2. Cliquer "✨ Créer 3 tâches"
3. Modale apparaît avec 3 actions
4. Éditer une action si besoin, cliquer "Créer les tâches dans le Kanban"
5. Toast vert "✓ 3 tâche(s) créée(s)"
6. Ouvrir l'onglet KANBAN → les 3 tâches sont en colonne BACKLOG, liées à l'incident

**Navigation incident**
7. Cliquer "📋 Voir l'incident" sur un message Assistant
8. L'onglet SOINS doit s'ouvrir, widget Assistant se replie

**Bouton Lancer instance**
9. Console animateur → cliquer "▶ Lancer" sur une instance
10. Le bouton passe **immédiatement** à "⏳ Démarrage…" (avant ça restait identique)

**Console plus propre**
11. F12 sur instance joueur après 2 min → maximum 3 erreurs 401, puis le circuit breaker prend le relais
12. Plus de pluie d'erreurs 401 toutes les 30 secondes

**Session jamais null**
13. F12 → `await fetch('/api/v1/tuteur/coach/check').then(r=>r.json()).then(console.log)`
14. `session_id` ne doit JAMAIS être null si on est dans une instance joueur en mode exercice

## Reste à faire
- **v3000i+** : prompt libre `/coach/ask` (input du widget activé, conversation contextualisée Albert)
- **v3000k** : bouton "🤖 → tâches" depuis messagerie collecteur
- (Plus tard) Étendre `observe_backend` aux décisions/transferts/messages
