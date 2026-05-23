# SCRIBE — Changelog v2.1.0-master / build v2323

**Date :** 8 mai 2026
**Type :** ajout fonctionnalité majeure (non breaking)

---

## ✨ Nouveautés

### Pilotage d'instances depuis l'admin web

Un seul script (`lancer_scribe.sh` / `LANCER_SCRIBE.bat`) lance désormais
**uniquement la supervision** sur `:9000`. Les instances SCRIBE sont
ensuite lancées, configurées et arrêtées **depuis l'interface web**, sans
recourir à la ligne de commande.

**Onglet "📦 INSTANCES"** dans l'admin de la supervision :

- 10 instances pré-remplies (ports 8000 à 8009)
- Pour chacune : sigle, adresse + bouton 🌍 géocoder, login admin, mot de
  passe auto-généré modifiable
- Bouton ▶ LANCER : démarre le subprocess, crée la DB depuis le profil de
  base, auto-enrôle dans la fédération
- Bouton ⏸ ARRÊTER : SIGTERM propre
- Bouton 📋 : copie URL + login + mdp dans le presse-papier
- Ajout d'instances custom (port libre)
- Persistance d'état (sigles, ports, mdp, adresses) entre redémarrages

**Onglet "🏥 Profil de base (UF)"** :

- Édition fine des UF : activer/désactiver/renommer/ajouter/supprimer
- Upload / download du profil xlsx complet
- Visualisation lecture seule des autres feuilles (DIRECTEURS, TÉLÉPHONIE,
  SERVICES_CAPACITE)

**Module nouveau** : `master/`
- `instances_manager.py` : subprocess + state JSON
- `master_routes.py` : 16 routes API FastAPI (/api/master/*)
- `geocoding.py` : Nominatim OSM (porté du projet CIAE)
- `instances.html` : UI panneau

**Modifications du collecteur** : intégration chirurgicale (3 changements,
~30 lignes ajoutées), aucune route existante touchée.

### Géocodage Nominatim

Adresse → lat/lon automatique via OpenStreetMap Nominatim. Cache mémoire,
throttling 1 req/s pour respect des CGU. User-Agent SCRIBE identifiable.

---

## 🔧 Modifications techniques

- `main.py` : version `2.1.0-master`, build `v2323`
- `collecteur/collecteur.py` :
  - Import optionnel du module `master` après les exception handlers
  - Onglet "INSTANCES" ajouté à la barre de tabs
  - `<div id="pane-instances">` avec iframe vers `/api/master/ui`
  - Handler `switchTab('instances')` qui injecte le token admin via
    localStorage
- `collecteur/collecteur_requirements.txt` : ajout `python-multipart>=0.0.6`
  pour les uploads xlsx

---

## ✅ Compatibilité

- **Aucune régression** sur l'existant
- Les anciens scripts (`lancer_g7.sh`, `lancer_exercice.sh`,
  `lancer_demo.sh`) continuent à fonctionner
- Les configs XML existantes (`config_chag.xml`, `config_g7_*.xml`,
  `config_exo_*.xml`) ne sont pas touchées
- Le module `master/` est chargé en `try/except` dans le collecteur :
  s'il manque, le collecteur tourne normalement sans le panneau Instances

---

## 📁 Fichiers ajoutés

```
master/
├── __init__.py
├── instances_manager.py       (~ 380 lignes)
├── master_routes.py           (~ 360 lignes)
├── geocoding.py               (porté CIAE, ~ 100 lignes)
├── instances.html             (UI DSFR ~ 530 lignes)
├── profil_base.xlsx           (copie de SCRIBE_config_etablissement.xlsx)
└── README.md                  (doc utilisateur master)

lancer_scribe.sh               (Linux/macOS)
LANCER_SCRIBE.bat              (Windows)
data/instances/                (créé au runtime, vide à la livraison)
```

---

## 🧪 Tests effectués

- ✅ Validation Python sur tous les .py
- ✅ Validation JS (node --check) sur le bloc <script> de instances.html
- ✅ Démarrage du collecteur avec module master chargé
- ✅ Endpoint `GET /api/master/instances` retourne 10 instances pré-remplies
- ✅ Lecture du profil de base xlsx : 54 UF lues
- ✅ Mots de passe masqués dans la liste publique (sécurité)

## ⚠ Tests non effectués (à faire chez l'utilisateur)

- Lancement réel d'une instance fille en subprocess (nécessite un
  environnement complet avec uvicorn, sqlalchemy, etc.)
- Auto-enrôlement effectif dans la fédération
- Géocodage Nominatim (nécessite Internet)
- UI cliquable de bout en bout

---

## 🛣 Roadmap

**Pour ce build (v2323)** : pilotage prod (8000-8009).

**v2324 ou ultérieur** :
- Intégration du mode exercice (8565 + 8660-8666) au master
- Mode équipe master (plusieurs admins simultanés)
- Sync automatique du profil de base (option C de la spec)
