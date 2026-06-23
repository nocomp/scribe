# Changelog — v3.0.0-alpha8 (build interne `v3000h`)

**Date** : 30 mai 2026
**Base** : v3000g
**Statut** : build privé interne. Phase 1/4 du coach proactif.

---

## Coach proactif — Phase 1 : widget flottant + 2 règles

C'est le premier des 4 builds prévus pour le coach proactif (cf. propositions
validées). Cette phase pose **l'infrastructure** : widget UI, polling backend,
moteur de règles persisté en DB. Les phases suivantes (i, j, k) ajouteront les
fonctionnalités IA.

### 1. Backend — Moteur de règles

**Nouveau modèle SQL** `TuteurCoachMessage` (table `plugin_tuteur_coach_messages`) :
- Persiste les messages émis par les règles
- Champs anti-spam (target_type, target_id, snooze_until, ack_at)
- Création automatique via `create_all(checkfirst=True)` au démarrage

**Nouveau module** `plugins/tuteur/coach_rules.py` :
- Architecture extensible : chaque règle est une fonction qui examine la timeline
  d'une session et retourne 0, 1 ou plusieurs candidats
- Anti-spam intégré : aucun ré-déclenchement d'une règle sur la même cible
  dans une fenêtre de 10-15 min
- Une règle qui plante ne casse pas les autres (try/except orchestrateur)

**Règles v3000h** (2) :
- `rule_incident_sans_action` : incident créé > 15 min, aucune DECISION/TRANSFERT/ACTION/JALON/INCIDENT_RESOLU posée après → priorité 2 (warning)
- `rule_stagnation_globale` : aucune observation utilisateur active > 10 min → priorité 1 (info)

**3 nouvelles routes** dans `plugins/tuteur/routes.py` :
- `GET /api/v1/tuteur/coach/check` : évalue les règles, persiste les nouveaux candidats, retourne les messages actifs (non-ack, non-snoozés). Résolution automatique de la session active si non fournie.
- `POST /api/v1/tuteur/coach/ack/{id}` : dismiss définitif OU snooze (avec `snooze_minutes`)
- `POST /api/v1/tuteur/coach/mute?minutes=10` : snooze tous les messages actifs (bouton 🔕)

### 2. Frontend — Widget flottant

**Nouveau fichier** `app/static/js/coach.js` (auto-portant, ~360 LOC).

**Comportement** :
- Pastille 🎓 ronde 56px en bas à droite, fixed position
- Badge rouge avec compteur de messages non lus
- Animation pulse quand nouveaux messages non lus
- Clic → panneau 380×520 (responsive) avec :
  - Header (sigle, bouton 🔕 mute 10 min, bouton réduire)
  - Liste des messages triés par priorité (critique → faible)
  - Border-left coloré selon priorité (rouge/orange/bleu)
  - Boutons d'actions par message (premier en bleu primary, autres outline)
  - Input "Demander un conseil…" (désactivé en v3000h, actif en v3000j)

**Polling** : `/coach/check` toutes les 60s, démarré uniquement si le plugin
tuteur est actif (vérifié via `/api/v1/plugins/active`).

**Initialisation** : `window.coachInit()` appelée à la fin de `initAfterLogin()`
(juste après `tuteurInit()`). Auto-détection plugin actif → si plugin tuteur
n'est pas chargé, le widget reste invisible.

**Actions disponibles v3000h** :
- `snooze` (✓ fonctionne) — re-snooze 10 min
- `open_tab` (✓) — navigation vers un onglet
- `focus_prompt` (✓) — donne le focus à l'input prompt
- `dismiss` (✓) — marquer lu définitivement
- `ask_ai` (⏳ v3000j) — pour l'instant alerte explicative
- `generate_tasks` (⏳ v3000i) — idem

### 3. Bonus : fix détection mode exercice dans tuteurInit

`tuteurInit` lisait encore `SCRIBE_CONFIG.exercice_mode` (forme plate). Sans ça,
le tuteur ne s'armait pas en mode exercice → pas de session → coach sans données.
Corrigé pour lire les deux formes (cohérent avec les autres fixes v3000f/g).

---

## Fichiers modifiés (vs v3000g)

| Fichier | Modifs |
|---|---|
| `plugins/tuteur/models.py` | nouvelle classe `TuteurCoachMessage` |
| `plugins/tuteur/routes.py` | imports + 3 routes coach (check, ack, mute) |
| `plugins/tuteur/coach_rules.py` | NOUVEAU — moteur de règles + 2 règles initiales |
| `app/static/js/coach.js` | NOUVEAU — widget complet (styles + DOM + polling) |
| `app/static/js/scribe.js` | fix `isExercice` dans `tuteurInit`, appel `coachInit()` |
| `app/static/index.html` | inclusion `coach.js` |
| `main.py`, `collecteur/collecteur.py` | bump version |

## Validation pré-build
- ✅ `ast.parse` : models.py, routes.py, coach_rules.py
- ✅ `node --check` : scribe.js, coach.js

## Tests à faire côté Hervé

**Apparition du widget**
1. Démarrer une instance exercice + se connecter → la bulle 🎓 doit apparaître bas-droite
2. Cliquer la bulle → panneau s'ouvre avec "Aucun message pour l'instant"

**Règle stagnation (la plus facile à tester)**
3. Une fois connecté, **ne rien faire pendant 10+ min** (juste laisser tourner)
4. Au bout de ~10 min, le badge rouge doit apparaître (1 message)
5. Cliquer la bulle → message "Aucune action depuis X min..." s'affiche
6. Cliquer "Pas maintenant" (snooze) → le message disparaît

**Règle incident sans action**
7. Créer un incident dans l'instance
8. Ne pas y donner suite (pas de décision, pas de transfert, pas de tâche)
9. Au bout de 15 min, badge rouge → message "Il y a X min, vous avez déclaré..."
10. Boutons : "💡 Suggérer 3 actions" (alerte v3000j), "📋 Voir l'incident" (navigue), "⏰ Pas maintenant"

**Mute global**
11. Cliquer 🔕 dans le header du widget → tous les messages disparaissent
12. Confirmer → "Mute 10 min"

**Pas d'apparition en cas de plugin tuteur désactivé**
13. Désactiver le plugin tuteur dans admin → la bulle ne doit plus apparaître

**Régression check**
14. Stimuli toujours injectés correctement (fix v3000g)
15. Splash screen exercice toujours présent
16. Pas de déconnexion intempestive

## Reste à faire (suite du phasage)
- **v3000i** : route `/api/v1/albert/analyser-to-tasks` + modale preview tâches + bouton "Transformer en tâches" sur messages coach
- **v3000j** : route `/api/v1/tuteur/coach/ask` (prompt libre contextualisé) + activation de l'input du widget
- **v3000k** : bouton "🤖 → tâches" dans les messages de la messagerie
