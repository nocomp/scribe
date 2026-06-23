# Changelog — v3.0.0-alpha9 (build interne `v3000h2`)

**Date** : 30 mai 2026
**Base** : v3000h
**Statut** : patch de v3000h (problèmes vus pendant test exercice).

---

## Ajustements assistant proactif

### 1. Renommage : COACH → ASSISTANT

Le terme "coach" sonnait trop "sport". Renommé partout en UI visible :
- Onglet menu : « 🎓 MON COACH » → « 🎓 MON ASSISTANT »
- Titre du widget : « Mon Coach » → « Mon Assistant »
- Tooltip de la bulle : « Coach SCRIBE » → « Assistant SCRIBE »
- Sous-titre du widget : « Compagnon d'aide à la décision » → « Aide à la décision en temps réel »

**Conservé en interne** (techniques, non visibles) : `coach.js`, `coach-bubble`, `tuteur_coach_messages`, `coach_rules.py`, routes `/api/v1/tuteur/coach/*`. Un renommage en cascade aurait été risqué pour aucun bénéfice visible.

### 2. Seuils raccourcis en mode exercice (3min / 2min)

Pendant un exercice avec ratio de compression typique (1 min réelle = 5-8 min scénario), les seuils de v3000h (15 min / 10 min) étaient beaucoup trop longs : un exercice dure souvent 30-60 min, donc aucun message ne se déclenchait avant la fin.

| Règle | Seuil exercice | Seuil production |
|---|---|---|
| Incident sans action | 3 min | 15 min |
| Stagnation globale | 2 min | 10 min |
| Anti-spam (re-déclenchement) | 5 min | 10-15 min |

Détection automatique via `SCRIBE_EXERCICE_MODE=1`. La signature des règles a évolué : `rule_xxx(db, session_id, *, is_exercice=False)`. L'orchestrateur `evaluate_all_rules` transmet le flag à chaque règle.

### 3. Apparition immédiate de la bulle

Avant : la bulle 🎓 était créée mais en `display:none`, et n'apparaissait qu'au retour du 1er `pollCheck()`. Sur l'image 2 du test Hervé, la bulle n'apparaissait jamais visiblement.

Maintenant : `buildDom()` force `bubble.style.display = 'flex'` immédiatement après la création. La bulle est visible **dès que le widget est initialisé** (avant même le 1er poll). Le polling continue à mettre à jour le compteur de messages comme avant.

---

## Fichiers modifiés (vs v3000h)

| Fichier | Modifs |
|---|---|
| `plugins/tuteur/plugin.py` | label MON COACH → MON ASSISTANT |
| `config.py` | label MON COACH → MON ASSISTANT |
| `app/static/js/scribe.js` | label MON COACH → MON ASSISTANT (panneau historique) |
| `app/static/js/coach.js` | titre, tooltip, sous-titre + affichage immédiat bulle |
| `plugins/tuteur/coach_rules.py` | seuils 3min/2min en exercice + signature des règles + orchestrateur |
| `plugins/tuteur/routes.py` | lit SCRIBE_EXERCICE_MODE et passe is_exercice à l'orchestrateur |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha8 → alpha9 |

## Validation pré-build
- ✅ `ast.parse` : routes.py, coach_rules.py, plugin.py, config.py
- ✅ `node --check` : coach.js, scribe.js

## Tests à faire côté Hervé

**Renommage**
1. Onglet « 🎓 MON ASSISTANT » (et plus « MON COACH ») dans la barre du SPA
2. Tooltip de la bulle flottante : « Assistant SCRIBE »
3. Titre du panneau : « Mon Assistant »

**Apparition immédiate**
4. Démarrer une instance exercice → la bulle 🎓 doit apparaître **immédiatement** en bas à droite, sans attendre 60 secondes

**Seuils raccourcis exercice**
5. Avec un exercice lancé qui injecte des incidents (comme la capture DÉMO Cyberattaque) : **ne pas agir pendant 3 minutes**
6. Au bout de ~3 min, le badge rouge doit apparaître + message « Il y a 3 min, vous avez déclaré [...] »
7. Pour la stagnation : laisser 2 min sans aucune action → message « Aucune action depuis 2 min »

**Pas de régression**
8. Stimuli toujours injectés
9. Splash screen prêt toujours présent
10. Pas de déconnexion intempestive

## Reste à faire (rappel)
- **v3000i** : pipeline `/analyser-to-tasks` + modale preview + bouton transformer en tâches
- **v3000j** : prompt libre `/coach/ask` (Albert contextualisé)
- **v3000k** : bouton 🤖 → tâches depuis messagerie
