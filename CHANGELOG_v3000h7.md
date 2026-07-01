# Changelog — v3.0.0-alpha14 (build interne `v3000h7`)

**Date** : 30 mai 2026
**Base** : v3000h6
**Statut** : patch — l'Assistant proactif voit enfin les incidents injectés.

---

## 3 corrections en cascade pour rendre l'Assistant fonctionnel

### Diagnostic des logs Hervé (build h6)

Image 1 console F12 :
```
{messages: Array(0), session_id: null}
```
→ Pas de session tuteur active côté backend.

Image 2 :
```
GET /api/v1/tuteur/historique?limit=20 → 500
SyntaxError: Unexpected token 'I', "Internal S"... is not valid JSON
```
→ La route historique plantait en 500 quand user non-auth.

### Trois causes empilées

**1. Session restaurée du localStorage mais inexistante en base**
- `tuteurInit` lisait `localStorage.tuteur_session_id` et faisait confiance aveuglément
- Or en mode exercice, la DB est reset à chaque démarrage de l'instance → l'ID stocké pointe vers une session qui n'existe plus
- Résultat : observations tuteur perdues, coach_check ne trouve pas la session

**Fix** : `tuteurInit` vérifie maintenant que la session existe vraiment via `GET /session/{id}`. Si absente/terminée, purge le localStorage et démarre une nouvelle session.

**2. Routes tuteur plantaient si user non-auth**
- `/historique` avait `user: User = Depends(get_current_user)` (sans Optional)
- `get_current_user` peut retourner None → `user.id` plantait → 500

**Fix** : `/historique` accepte `Optional[User]`, retourne liste vide si non-auth.
Nouvelle route `GET /session/{id}` (utilisée par le frontend pour vérifier la validité).

**3. Stimuli injectés invisibles au tuteur — LE VRAI BUG**

C'était le cœur du problème.

L'intercepteur tuteur (apiFetch dans scribe.js) capture les actions UNIQUEMENT
côté navigateur. Quand le collecteur exercice (port 8565) pousse un stimulus
via `POST /api/v1/sitrep/post` directement vers l'instance, aucun navigateur
n'est dans la boucle → aucune observation `INCIDENT_CREE` enregistrée.

Conséquence : la règle `rule_incident_sans_action` n'avait **aucun incident**
à surveiller. L'Assistant ne s'activait jamais sur les stimuli, même au bout
de plusieurs minutes.

**Fix** :
- **Nouveau module** `plugins/tuteur/backend_observer.py` (~95 LOC) :
  - Fonction `observe_backend()` appelée depuis les routes API
  - Résout user_id (admin par défaut)
  - Trouve OU crée une session active (création auto en mode exercice)
  - Crée une observation `TuteurObservation` rattachée à cette session
  - Fail-safe : aucune exception ne casse jamais la requête métier appelante
- **Hook dans `app/api/sitrep.py`** : appel `observe_backend(...)` en fin de
  `create_incident` (juste après les autres hooks non-bloquants existants).

À noter : ce build couvre **uniquement les incidents** (sitrep/post). Les
décisions, transferts, messages restent capturés via le frontend seulement.
À étendre dans un futur build si besoin.

**4. Bonus : coach_check crée une session automatiquement en mode exo**
- Si pas de session active ET mode exercice : `coach_check` la crée à la volée
- En prod, comportement inchangé (retourne vide pour ne pas créer de sessions parasites)

---

## Fichiers modifiés (vs v3000h6)

| Fichier | Modifs |
|---|---|
| `plugins/tuteur/backend_observer.py` | NOUVEAU — observation tuteur côté serveur |
| `plugins/tuteur/routes.py` | `/historique` Optional, nouvelle route GET /session/{id}, coach_check crée session auto |
| `app/api/sitrep.py` | hook `observe_backend("INCIDENT_CREE", …)` après création |
| `app/static/js/scribe.js` | tuteurInit vérifie la session backend avant de faire confiance au localStorage |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha13 → alpha14 |

## Validation pré-build
- ✅ `ast.parse` : routes.py, backend_observer.py, sitrep.py
- ✅ `node --check` : scribe.js

## Tests à faire côté Hervé

1. **Repartir propre** : arrêter SCRIBE, vider le localStorage navigateur (DevTools → Application → Local Storage → tout supprimer)
2. Relancer le master + instance EXO1 + démarrer un scénario depuis l'animateur
3. F12 → onglet Réseau → filtrer "coach"
4. Le premier `coach/check` doit retourner `{messages: [], session_id: 1}` (et plus null)
5. Attendre 3-4 min sans agir sur les incidents reçus
6. Le widget Assistant doit afficher un message "Il y a 3 min, vous avez déclaré..."
7. F12 → Console : `await fetch('/api/v1/tuteur/historique').then(r=>r.json()).then(console.log)`
   doit lister la session + ses observations (INCIDENT_CREE pour chaque stimulus reçu)

## Reste à faire
- v3000i : pipeline `/analyser-to-tasks` → tâches Kanban
- v3000j : prompt libre `/coach/ask`
- v3000k : "🤖 → tâches" depuis messagerie
- (Plus tard) Étendre `observe_backend` à transferts/décisions/messages si besoin
