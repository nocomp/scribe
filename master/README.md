# SCRIBE — Pilotage des instances depuis l'admin

**Version :** v2.1.0-master / build v2323
**Date :** mai 2026

---

## 1. Quoi de neuf

À partir de cette version, **un seul script** lance SCRIBE :

```bash
bash lancer_scribe.sh        # Linux / macOS
LANCER_SCRIBE.bat            # Windows
```

Le script démarre **uniquement la supervision** sur `http://localhost:9000`.
Toutes les instances SCRIBE sont ensuite lancées, configurées et arrêtées
**depuis l'interface web** (onglet 📦 INSTANCES), sans toucher à un terminal.

Les anciens scripts (`lancer_g7.sh`, `lancer_exercice.sh`, etc.) restent
disponibles pour ceux qui préfèrent. Aucun comportement existant n'est cassé.

---

## 2. Workflow

```
1. bash lancer_scribe.sh
   → Supervision démarrée sur :9000

2. Ouvrir http://localhost:9000 → onglet "📦 INSTANCES"

3. 10 lignes pré-remplies (ports 8000 à 8009) :
   - Sigle (éditable, défaut "Site_8000", "Site_8001", ...)
   - Adresse + bouton "🌍 Géocoder" (Nominatim OSM)
   - Login admin (éditable, défaut "dircrise")
   - Mot de passe (auto-généré, modifiable, bouton 🎲)

4. Clic ▶ LANCER → l'instance démarre :
   - Génère son config XML depuis le profil de base
   - Crée la DB SQLite avec UF + capacité du profil
   - Lance le subprocess SCRIBE
   - Auto-enrôle dans la fédération de supervision
   - Statut bascule en 🟢 Actif

5. Bouton 📋 → copie URL + login + mdp dans le presse-papier

6. Clic ⏸ ARRÊTER → l'instance s'arrête proprement (SIGTERM)

7. Ctrl+C sur lancer_scribe.sh → toutes les instances filles s'arrêtent
```

---

## 3. Profil de base

Le **profil de base** est un fichier `master/profil_base.xlsx` qui contient :

- **ETABLISSEMENT** : nom, sigle, adresse par défaut
- **DIRECTEURS** : liste des directeurs d'astreinte
- **TELEPHONIE** : annuaire de crise
- **UF_INCIDENTS** : unités fonctionnelles (~54 UF par défaut)
- **SERVICES_CAPACITE** : services avec gestion capacitaire (~60 services)

**Édition depuis l'UI** (onglet "🏥 Profil de base") :
- ✅ Activer / désactiver une UF (case à cocher)
- ✅ Renommer une UF (libellé, pôle, site)
- ✅ Ajouter / supprimer des UF
- ✅ Télécharger le profil xlsx complet
- ✅ Uploader un nouveau profil xlsx

**Édition fine** (DIRECTEURS, TÉLÉPHONIE, SERVICES_CAPACITE) :
- Téléchargez le xlsx, modifiez-le dans Excel/LibreOffice, ré-uploadez

**Important** : les modifications du profil de base **s'appliquent uniquement
aux nouvelles instances**. Les instances déjà lancées conservent leur
configuration. Pour propager une modif, arrêtez l'instance, modifiez le
profil, relancez l'instance.

---

## 4. Architecture

```
scribe_v2323/
├── lancer_scribe.sh           ← UN SEUL script à lancer
├── LANCER_SCRIBE.bat          ← Version Windows
├── master/                    ← Module pilotage d'instances
│   ├── instances_manager.py   ← Subprocess + state + auto-enrôlement
│   ├── master_routes.py       ← 16 routes API FastAPI
│   ├── geocoding.py           ← Nominatim OSM (porté de CIAE)
│   ├── instances.html         ← UI panneau "Instances"
│   ├── profil_base.xlsx       ← Template d'init des instances
│   └── master_instances.json  ← État persisté (gitignored)
├── data/instances/            ← Bases SQLite des instances filles
│   ├── Site_8000/
│   │   ├── scribe.db
│   │   └── scribe.log
│   └── ...
└── collecteur/
    └── collecteur.py          ← Modifié : import master + onglet UI
```

---

## 5. Sécurité

- **Auth admin** : toutes les routes `/api/master/*` exigent le token admin
  du collecteur (Bearer dans Authorization)
- **Token persistant** : injecté dans le localStorage du navigateur via
  `PLACEHOLDER_ADMIN_TOKEN` du dashboard collecteur
- **Pas d'écoute publique par défaut** : le collecteur écoute sur 0.0.0.0
  pour faciliter l'usage local + LAN, mais le master refuse toute requête
  sans token admin
- **Subprocess détachés** : `start_new_session=True` → les instances
  filles survivent à un crash du master et peuvent être tuées proprement
- **Mots de passe** : générés cryptographiquement (`secrets`), excluant les
  caractères ambigus (I, l, O, 0, 1)
- **Stockage des mdp** : en clair dans `master/master_instances.json`
  (mode dev/évaluation). Fichier en mode 600 recommandé en prod sensible.

---

## 6. Limites connues / TODO

- L'auto-enrôlement utilise la route `/api/admin/tokens` du collecteur.
  Si le collecteur n'est pas le master (cas LAN multi-machines), il faut
  configurer manuellement `_master_collecteur_url` dans master_routes.
- Pas encore de mode équipe (plusieurs admins simultanés sur le master).
- Mode exercice (collecteur 8565 + 7 joueurs 8660-8666) non encore intégré
  au master — utiliser `lancer_exercice.sh` séparément.

---

## 7. Inspiration

L'architecture du module `master/` est inspirée du module `flotte/` du
projet CIAE (Centre Interministériel d'Analyse Stratégique), qui a la même
problématique de pilotage multi-instances depuis l'admin web. Pattern
SubprocessDeployer simplifié au strict nécessaire pour SCRIBE.

---

*Document généré le 8 mai 2026 pour la livraison v2.1.0-master.*
