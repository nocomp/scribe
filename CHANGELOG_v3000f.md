# Changelog — v3.0.0-alpha6 (build interne `v3000f`)

**Date** : 28 mai 2026
**Base** : v3000e (qui était v2.5.0 vierge + fixes stimuli/refresh)
**Statut** : build privé interne.

---

## Contenu

### 1. Renommage EXO1-EXO7 (sigles techniques génériques)

**Avant** : sigles `CHAG/GHTLMB/CHRUMILLY/HDLEMAN/HPMB/CHB/CHPG` en dur dans le mode exercice.
**Après** : sigles techniques génériques `EXO1` à `EXO7`, mappés sur ports 8660-8666.

**Rétrocompat** : les anciens sigles G7 fonctionnent toujours comme **alias** vers les sigles
canoniques (CHAG→EXO1, GHTLMB→EXO2, etc.). Les scénarios existants qui ciblent `"CHAG"` dans
leurs stimuli continuent à fonctionner sans modification — ils sont automatiquement résolus
vers EXO1.

**Détails techniques** :
- `collecteur_exercice.py` : `EXO_INSTANCES` réécrit (EXO1-EXO7), ajout de `_EXO_ALIASES` et
  `EXO_INSTANCES_FULL` (vue complète avec alias).
- `load_tokens()` génère les tokens pour les sigles canoniques **ET** les alias historiques
  (`token_exo_chag_2026` → mappé sur EXO1, etc.) → les configs existantes restent valides.
- 7 fichiers `config_exo_*.xml` renommés et adaptés :
  - `config_exo_chag.xml` → `config_exo_exo1.xml` (sigle EXO1, nom "Site Exercice 1")
  - ... idem pour les 6 autres
- `exercice_manager.py` : sigle par défaut aligné sur EXO_INSTANCES (8660→EXO1, etc.) et nom
  par défaut "Site Exercice N".

### 2. Onglet EXERCICE supprimé de l'instance joueur
Le pilotage d'exercice est exclusivement sur la console animateur (port 8565). L'onglet
EXERCICE qui apparaissait dans l'instance joueur (Image 2 du message Hervé) était un doublon
trompeur — il est désormais retiré de la liste des onglets (`main.py` ligne 218). Le plugin
reste chargé en backend (tables, routes pour recevoir des stimuli).

### 3. Bouton "✋ Me déclarer PRÊT" réparé
Le JS lisait `SCRIBE_CONFIG.exercice_mode` (plat) alors que le manager écrit
`SCRIBE_CONFIG.exercice.mode` (imbriqué) → la bannière + bouton ne s'affichaient jamais.
Corrigé : le JS lit maintenant les deux formes. La bannière rouge "MODE EXERCICE" et son
bouton PRÊT apparaîtront enfin sur les instances exercice.

### 4. Module COACH (tuteur) activé
**Onglet "🎓 MON COACH"** : `has_tab` passé à `True` dans `plugins/tuteur/plugin.py`. Le plugin
était entièrement fonctionnel côté backend (568 LOC routes : sessions, observations, rappels
IA, debriefing) et avait une UI HTML prête (`plugins/tuteur/tuteur.html`, 265 LOC), mais
désactivé côté UI.

Maintenant visible. L'iframe charge `tuteur.html` depuis la route `/api/v1/tuteur/ui` (route
existante). L'apprenant peut :
- Démarrer/terminer une session d'apprentissage
- Voir ses observations (incidents, décisions, transferts, etc.) capturées automatiquement
  via l'intercepteur `apiFetch` (non modifié — original v2.5.0)
- Recevoir des rappels IA pendant l'inactivité
- Obtenir un debriefing IA personnalisé en fin de session

---

## Fichiers modifiés (vs v3000e)

| Fichier | Modifs |
|---|---|
| `main.py` | onglet EXERCICE jamais listé côté joueur + bump version |
| `app/static/js/scribe.js` | détection mode exercice (forme imbriquée + plate), bouton PRÊT réparé |
| `collecteur_exercice/collecteur_exercice.py` | EXO_INSTANCES en EXO1-7, alias rétrocompat, tokens alias, defaults |
| `master/exercice_manager.py` | sigle/nom par défaut alignés EXO1-7 + Site Exercice N |
| `plugins/tuteur/plugin.py` | `has_tab: True` → onglet 🎓 MON COACH visible |
| 7 × `config_exo_*.xml` | renommés et adaptés (sigles EXO1-7, tokens, noms) |

## Validation pré-build
- ✅ `ast.parse` : main.py, auth.py, exercice_manager.py, collecteur_exercice.py, tuteur/plugin.py
- ✅ `node --check` : scribe.js, exercice.html
- ✅ XML valides : 7 config_exo_exo*.xml

## Tests à faire côté Hervé

**1. Renommage**
- Console animateur (8565) → cartes affichent EXO1 à EXO7 (au lieu de CHAG/GHTLMB)
- Master exercice (9000) → sigles EXO1-7 dans la liste
- Les scénarios existants qui ciblent "CHAG" → toujours injectés (alias) sur EXO1

**2. Onglet EXERCICE retiré**
- Ouvrir une instance joueur (localhost:8660 etc.) → plus d'onglet 🎯 EXERCICE
- La bannière rouge "MODE EXERCICE" en haut doit apparaître avec le bouton "✋ Me déclarer PRÊT"

**3. Bouton PRÊT**
- Cliquer le bouton → passe à "✓ PRÊT"
- Côté animateur (8565), le site apparaît dans JOUEURS PRÊTS

**4. Module COACH**
- Onglet "🎓 MON COACH" présent dans la barre des onglets
- Clic → l'interface tuteur se charge (iframe)
- Démarrer une session → naviguer dans l'app → vérifier que les observations sont capturées

**5. Régression check (depuis v3000e qui marchait)**
- Stimuli s'injectent toujours (mdp Exercice2026!)
- Pas de déconnexion au refresh
