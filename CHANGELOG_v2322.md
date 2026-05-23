# SCRIBE v2.1.0-alpha — build v2322 — Tuteur Hooks 2A + 3 (build privé)

**Date :** 27 avril 2026 — soir, en prévision démo 9h30 le 28
**Base :** scribe_v2321 (jour 1 + fix admin clé IA)

---

## Ce qui marche maintenant (testable en démo)

### Hook 2A — Rappel discret pendant l'exercice ✅

Quand l'utilisateur joue un exercice et reste **inactif plus de 8 minutes**
alors qu'il y a des incidents OUVERT/EN_COURS, un pop-up DSFR coin
bas-droit s'affiche avec un message d'aide bienveillant généré par l'IA
(Albert) à partir du contexte réel : intention pédagogique, incidents
ouverts, durée d'inactivité.

**Anti-spam** : 1 rappel max toutes les 10 minutes par session
(côté serveur ET côté client).

**Boutons d'action** : `✓ Compris` / `Pas pertinent` / `Pas maintenant`
(traçabilité dans `tuteur_rappels.action_apres`).

**Auto-fermeture** : 90 secondes si pas d'interaction.

**Fallback IA** : si Albert plante, message statique "💡 Petit point
d'étape : prends un moment pour relire les incidents ouverts..."

### Hook 3 — Debriefing post-exercice ✅

À la fin d'un exercice, l'onglet **🎓 Mon coach** liste les sessions
récentes. Pour chaque session terminée, bouton "🎯 Mon debriefing" qui :

1. Récupère toutes les observations de la session (incidents créés,
   décisions, transferts, messages, rappels affichés)
2. Construit une timeline résumée (max 30 obs)
3. Demande à Albert un debriefing structuré JSON :
   - **Synthèse** (2-3 phrases)
   - **Points forts** (3-5 items concrets)
   - **Axes d'amélioration** (3-5 items formulés en suggestions)
   - **Recommandations** pour le prochain exercice (2-4 items)
   - **Score d'engagement** (30-95, indicateur, pas une note)
4. Stocke dans `tuteur_debriefings` (1 seul par session, regénérable
   avec `?force=true`)

**UI DSFR** : sections, score coloré (vert/orange selon valeur), grid
2 colonnes points forts / axes amélioration. Bouton "🔄 Régénérer".

### Capture automatique des observations ✅

Le `apiFetch` du frontend tague automatiquement les POST réussis sur :
- `/api/v1/sitrep` → `INCIDENT_CREE`
- `/api/v1/decisions` → `DECISION`
- `/api/v1/transferts` → `TRANSFERT`
- `/api/v1/messagerie` → `MESSAGE_ENVOYE`
- `/api/v1/tasks`, `/api/v1/cellule/presences` → `ACTION`
- `RAPPEL_AFFICHE` (côté backend, automatique)

Aucune modification des endpoints existants — capture transparente.

### Démarrage automatique en mode exercice ✅

Quand `SCRIBE_CONFIG.exercice_mode === true` (déjà le cas sur les
instances exercice ports 8660+), le tuteur :
- Démarre une session automatiquement après login
- Stocke `tuteur_session_id` dans localStorage (survit aux reloads)
- Lance un poller d'inactivité toutes les 60s
- Hook les events `click`, `keydown`, `submit` pour tracker l'activité

---

## Routes API (toutes sous `/api/v1/tuteur/`)

| Route | Méthode | Rôle | État |
|---|---|---|---|
| `session/start` | POST | Démarre session | ✅ jour 1 |
| `session/end` | POST | Termine session | ✅ jour 1 |
| `observation` | POST | Trace une obs | ✅ jour 1 |
| `historique` | GET | Liste sessions user | ✅ jour 1 |
| `config` | GET/PUT | Config seuils | ✅ jour 1 |
| **`rappel`** | **POST** | **Génère rappel IA** | ✅ **v2322** |
| **`rappel/ack`** | **POST** | **Ack rappel** | ✅ **v2322** |
| **`debriefing/{id}`** | **POST** | **Génère debriefing IA** | ✅ **v2322** |
| **`debriefing/{id}`** | **GET** | **Récupère debriefing** | ✅ **v2322** |
| `equipe/{id}` | GET | Bilan équipe | stub jour 6 |

---

## Validations

- 135 fichiers Python OK
- `node --check scribe.js` OK
- 8 tests fonctionnels TestClient :
  - Session start → 5 obs → rappel fallback (sans IA) → ack → end
  - Anti-spam rappel (skip si <10min)
  - Debriefing sans IA → 400 ia_not_configured (modale frontend OK)
  - Debriefing avec clé → call_ai signature OK (passe à 503 réseau,
    normal sans vraie clé valide en environnement de test)
- Bench `tests/bench/bench.py` : **5/5 OK**

---

## Configuration Albert pour la démo

**Important** : avant de démontrer, t'assurer que ta clé Albert est
enregistrée via l'admin (panneau corrigé en v2321).

1. Connecté en admin → ⚙ Administration → APIs & IA
2. Sélectionner Albert
3. Coller la clé → 🧪 Tester (vert) → 💾 Enregistrer & activer
4. Vérifier le badge "Clé API configurée"
5. Le tuteur utilisera automatiquement cette clé pour les rappels et
   debriefings

---

## Scénario de démo recommandé

1. **Lancer un exercice** sur l'instance exercice (port 8660+)
2. Connection en tant que joueur → l'onglet **🎓 Mon coach** apparaît
3. **Jouer activement** : créer 3-4 incidents, prendre 2-3 décisions,
   créer 1 transfert, envoyer 1 message
4. **Faire une pause** (5-8 min) — ne rien faire, ne pas cliquer
5. Au bout de 8 min d'inactivité, le pop-up rappel s'affiche en bas-droite
   avec un message d'aide IA contextualisé sur les incidents ouverts
6. Cliquer "✓ Compris" → le pop-up disparaît
7. Reprendre l'exercice 1-2 min, puis **terminer la session** (dans
   l'onglet exercice ou en cliquant "Stop")
8. Ouvrir l'onglet **🎓 Mon coach** → la session apparaît avec badge
   "Terminé" et bouton "🎯 Mon debriefing"
9. Cliquer → IA génère synthèse + points forts + axes + reco + score
10. Optionnel : cliquer "🔄 Régénérer" pour montrer la diversité des
    réponses IA

**Durée totale démo** : 12-15 minutes.

---

## Ce qui n'est PAS dans v2322 (à venir aux jours suivants)

- Hook 1 (intention pédagogique injectée dans le prompt de génération
  scénario IA) — non démontré ce matin, à coder Jour 2 normal
- Hook 2B (mode prod activable via PUT /config) — Jour 4
- Hook 4 (mode équipe agrégé) — Jour 6
- Tests de charge avec vraies sessions Albert
