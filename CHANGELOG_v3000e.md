# Changelog — v3.0.0-alpha5 (build interne `v3000e`)

**Date** : 28 mai 2026
**Base** : v2.5.0 VIERGE (remise à zéro complète — les builds a/b/c/d sont abandonnés)
**Statut** : build privé interne. Première version réellement saine après reset.

---

## Contexte : remise à zéro

Les builds v3000a→d avaient empilé des changements et introduit des régressions
(intercepteur tuteur enrichi avec await/clone suspecté, configs modifiées, etc.).
Décision : **repartir de v2.5.0 vierge** et ne corriger que les 2 bugs bloquants
identifiés, de façon chirurgicale.

**scribe.js n'est PAS modifié** — l'intercepteur tuteur reste l'original v2.5.0.
Seuls 3 fichiers changent, tous liés stimuli/auth exercice.

---

## Problème 1 — Stimuli jamais injectés (0 injecté après DÉMARRER)

**Cause racine** (triple désynchronisation) :
1. Le manager exercice générait un mot de passe **aléatoire** pour chaque instance
   (`generate_password()`), alors que le collecteur animateur se logge en dur avec
   `dircrise / Exercice2026!` → login échoue → aucun token → 0 stimulus.
2. Le manager passait les variables d'env `SCRIBE_ADMIN_LOGIN` / `SCRIBE_ADMIN_PWD`,
   mais `app/api/auth.py` lit `SCRIBE_ADMIN_USER` / `SCRIBE_ADMIN_PASS` → le mot de
   passe n'arrivait jamais jusqu'à `ensure_admin()`.
3. `ensure_admin()` ne resynchronisait le mdp d'un compte existant que lors de la
   migration SHA→bcrypt → une DB exercice existante gardait un ancien mdp.

**Corrections** :
- `exercice_manager.py` : mdp exercice fixé à **`Exercice2026!`** (plus de random).
- `exercice_manager.py` : ajout des variables `SCRIBE_ADMIN_USER` + `SCRIBE_ADMIN_PASS`
  (les noms réellement lus par auth.py), en plus des anciens pour compat.
- `auth.py` : en MODE EXERCICE uniquement, `ensure_admin()` force la resynchro du mdp
  admin sur `ADMIN_PASS` si le hash actuel ne correspond pas. Ne s'applique JAMAIS en
  production (protégé par `SCRIBE_EXERCICE_MODE == 1`).

**Décision produit** : le mdp exercice est désormais **fixe et non éditable**
(`Exercice2026!`). L'édition/random était une fausse bonne idée qui cassait l'injection.
- `exercice.html` : champ mdp affiché en clair, **lecture seule** (plus de regen 🎲).
- `exercice.html` : login figé `dircrise` en lecture seule.

## Problème 2 — Déconnexion au refresh

**Cause** (préexistante, aggravée par les redémarrages fréquents de test) : chaque
(re)démarrage d'instance exercice générait un `SECRET_KEY` JWT aléatoire (persisté
dans `data/.scribe_secret`, mais régénéré si DB/dossier réinitialisé) → les tokens des
sessions ouvertes devenaient invalides au refresh.

**Correction** :
- `exercice_manager.py` : injection d'un `SCRIBE_SECRET` **fixe et partagé** pour toutes
  les instances exercice. Les tokens survivent aux redémarrages. Acceptable car
  environnement d'exercice (données non réelles).

Combiné au mdp fixe (Problème 1), l'autologin SSO exercice (`?autotoken=`) et la
revalidation `/auth/me` au refresh deviennent fiables.

---

## Fichiers modifiés (vs v2.5.0 vierge)

| Fichier | Modifs |
|---|---|
| `master/exercice_manager.py` | mdp fixe Exercice2026!, vars SCRIBE_ADMIN_USER/PASS, SCRIBE_SECRET partagé |
| `app/api/auth.py` | resynchro mdp admin en mode exercice (ensure_admin) |
| `master/exercice.html` | mdp en clair lecture seule, login figé, pas de regen |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump version |

**Non modifié** : `app/static/js/scribe.js` (intercepteur tuteur = original v2.5.0).

## Validation pré-build
- ✅ `ast.parse` : main.py, auth.py, exercice_manager.py
- ✅ `node --check` : exercice.html

## Tests à faire côté Hervé (PRIORITAIRES)

**Stimuli**
1. Lancer les instances exercice depuis le master (port 9000)
2. Vérifier que le mdp affiché est « Exercice2026! » (en lecture seule)
3. Dans la console animateur (8565), sélectionner un scénario + des sites, DÉMARRER
4. Vérifier que « Tokens OK » liste bien les sites (login réussi)
5. Vérifier que les stimuli s'injectent (compteur monte, incidents apparaissent côté joueur)

**Refresh**
6. Ouvrir une instance joueur via « Afficher » (autologin)
7. Rafraîchir la page plusieurs fois → ne PAS être déconnecté
8. Redémarrer l'instance puis rafraîchir → toujours connecté (secret partagé)

## Reste à faire (builds suivants, isolés)
- **Renommage EXO1-EXO7** (remplacer CHAG/GHTLMB dans EXO_INSTANCES + configs + tokens) — validé sur le principe, à faire seul pour pouvoir le tester isolément
- **Catalogue 24 scénarios**
