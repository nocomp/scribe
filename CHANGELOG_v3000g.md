# Changelog — v3.0.0-alpha7 (build interne `v3000g`)

**Date** : 30 mai 2026
**Base** : v3000f
**Statut** : build privé interne.

---

## Corrections critiques mode exercice

### 1. Stimuli enfin injectés (fix renommage incomplet)

**Cause** : le renommage CHAG/GHTLMB → EXO1/EXO2 du build v3000f avait introduit
`EXO_INSTANCES_FULL` et `_canonical_sigle()` mais **ne les utilisait pas** dans les
fonctions d'injection. Résultat : un stimulus ciblant `"CHAG"` (depuis un scénario)
était traité comme **acteur externe inconnu**, et les sites des chips de la console UI
(qui restaient en CHAG/GHTLMB) n'étaient pas reconnus → 0 stimulus injecté.

**Corrections (4 endroits dans `collecteur_exercice.py`)** :
- `_do_inject` : normalise la cible via `_canonical_sigle()` avant lookup port/token
- `start_exercice` : normalise les sigles de `body.sites` reçus de l'UI
- `inject_adhoc` : idem pour l'injection manuelle (corrigé : "l'injection manuelle ne marche plus")
- Transferts inter-sites : normalisation de la destination

**Chips de l'UI réécrits** : `collecteur_exercice.html` ne contient plus `data-s="CHAG"`
mais `data-s="EXO1"` (et libellé "Site Exercice 1"). Idem pour les 6 autres.

### 2. Splash screen "Je suis prêt" — NOUVEAU

Tu as demandé : « quand on arrive sur l'interface joueur, un splash screen pour se
déclarer prêt serait bien et une fois validé on a le dashboard. »

**Implémentation** :
- Modale plein écran (`#exo-splash` dans `index.html`) avec :
  - Icône 🎯 et titre "Mode Exercice"
  - Sigle de l'instance affiché en sous-titre (ex: "EXO1")
  - Texte d'introduction (simulation, données fictives, attente de l'animateur)
  - Gros bouton vert "✋ Je suis prêt pour l'exercice"
- S'affiche **après le login**, dans `initAfterLogin()`, via `showExoSplashIfNeeded()`
- Condition : `SCRIBE_CONFIG.exercice.mode == true` ET pas encore validé dans la session
- Stockage : `sessionStorage.exo_pret_done = '1'` pour ne pas réafficher pendant la session
  (mais réaffichage à chaque nouvelle session navigateur, ce qui est le bon comportement)
- Clic sur le bouton → appel `/api/exercice/joueur-pret` du collecteur (8565) + fermeture
  immédiate du splash (UX non bloquante en cas d'erreur réseau)
- Le bouton "✋ Me déclarer PRÊT" du bandeau rouge en haut **reste disponible** comme
  indicateur permanent (passe à "✓ PRÊT" une fois validé)

### 3. Détection mode exercice corrigée (régression v3000f)

`initAfterLogin` lisait encore `SCRIBE_CONFIG.exercice_mode` (forme plate) alors que le
manager écrit `SCRIBE_CONFIG.exercice.mode` (imbriqué). Sans correction, le poll rapide
(3s) ne s'activait pas en mode exercice, et le splash ne se déclenchait pas.

### 4. Bonus : header neutralisé

`SCRIBE — ANIMATEUR EXERCICE ARC ALPIN` → `SCRIBE — ANIMATEUR EXERCICE`.

---

## Fichiers modifiés (vs v3000f)

| Fichier | Modifs |
|---|---|
| `collecteur_exercice/collecteur_exercice.py` | normalisation alias dans _do_inject, inject_adhoc, start_exercice, transferts |
| `collecteur_exercice/collecteur_exercice.html` | chips EXO1-7 + libellés "Site Exercice N" + header neutralisé |
| `app/static/index.html` | div #exo-splash (modale plein écran) |
| `app/static/js/scribe.js` | showExoSplashIfNeeded(), declareJoueurPretAndClose(), fix détection exercice_mode dans initAfterLogin |
| `main.py`, `collecteur/collecteur.py` | bump version |

## Validation pré-build
- ✅ `ast.parse` : collecteur_exercice.py
- ✅ `node --check` : scribe.js

## Tests à faire côté Hervé

**Stimuli (le bloquant)**
1. Console animateur → sélectionner sites (Site Exercice 1, 2, …) → DÉMARRER scénario
2. Vérifier dans les logs collecteur : `Token EXO1:8660 OK (depuis 'EXO1')` (ou avec alias si scénario contient CHAG)
3. Vérifier que les stimuli arrivent côté instances joueur (incidents, messages…)
4. **Injection manuelle** (bouton "Stimulus manuel") → doit aussi marcher

**Splash screen**
5. Ouvrir une instance joueur depuis « Afficher » → la modale plein écran doit apparaître
6. Cliquer "Je suis prêt" → modale se ferme, dashboard accessible
7. Le bouton "✋ Me déclarer PRÊT" du bandeau rouge en haut doit afficher "✓ PRÊT"
8. Côté animateur : le site apparaît dans "JOUEURS PRÊTS"
9. Rafraîchir la page → pas de re-splash (sauf si on ferme/réouvre l'onglet navigateur)

**Régression check**
10. Console animateur affiche bien "Site Exercice 1-7" dans les chips (et plus CHAG)
11. Pas de "ARC ALPIN" dans le header
12. Mdp Exercice2026! toujours visible/non éditable côté master exercice
