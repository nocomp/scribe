<div align="center">

```
███████╗ ██████╗██████╗ ██╗██████╗ ███████╗
██╔════╝██╔════╝██╔══██╗██║██╔══██╗██╔════╝
███████╗██║     ██████╔╝██║██████╔╝█████╗
╚════██║██║     ██╔══██╗██║██╔══██╗██╔══╝
███████║╚██████╗██║  ██║██║██████╔╝███████╗
╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
```

**Main courante numérique de gestion de crise hospitalière**
**Digital Crisis Management Log for Healthcare Facilities**

[![Version](https://img.shields.io/badge/version-1.3.0-blue)](https://github.com/nocomp/scribe)
[![License: GNU AGPLv3](https://img.shields.io/badge/GNU AGPLv3-orange)](LICENSE)
[![Stack](https://img.shields.io/badge/stack-Python%20%7C%20FastAPI%20%7C%20SQLite-orange)](https://github.com/nocomp/scribe)
[![Languages](https://img.shields.io/badge/languages-FR%20EN%20DE%20ES%20IT%20NL%20PL%20PT-purple)](https://github.com/nocomp/scribe)

</div>

---

> 🇫🇷 **[Français](#-scribe--main-courante-de-crise-hospitalière)** | 🇬🇧 **[English](#-scribe--hospital-crisis-management-log)**

---

## 🇫🇷 SCRIBE — Main courante de crise hospitalière

SCRIBE est une plateforme open-source de **gestion de crise et de pilotage capacitaire hospitalier** développée par le RSSI du Centre Hospitalier Annecy-Genevois (CHAG). Elle fournit une main courante numérique complète, un suivi capacitaire en temps réel, un collecteur territorial multi-établissements, et un module de debriefing post-crise alimenté par l'IA.

**Double usage** — SCRIBE est conçu pour être utile **aussi bien en mode nominal qu'en crise** :
- **Mode nominal** : suivi quotidien de la capacité des services (lits, RH, matériel), déclarations 3 fois/jour par les cadres, tableau de bord pour la direction des soins et le DRH
- **Mode crise** : main courante incidents, cellule de crise, kanban opérationnel, communiqués publics, coordination territoriale GHT/ARS

**Conçu pour les non-techniciens** — cadres soignants, directeurs, gestionnaires de crise — SCRIBE ne nécessite aucun cloud, aucun LDAP et fonctionne en réseau isolé.

---

### Captures d'écran

| Onglet VEILLE — Gestion des incidents | Onglet SOINS — Cartographie de situation |
|---|---|
| ![Veille](screenshots/veille.png) | ![Soins](screenshots/soins.png) |

| Onglet CELLULE — Salle de crise | Onglet KANBAN — Tableau opérationnel |
|---|---|
| ![Cellule](screenshots/cellule.png) | ![Kanban](screenshots/kanban.png) |

| Onglet COMMUNIQUÉ — Statut public | Collecteur territorial — Supervision |
|---|---|
| ![Communiqué](screenshots/communique.png) | ![Supervision collecteur](screenshots/supervision_collecteur.png) |

| Collecteur territorial — Cartographie |
|---|
| ![Cartographie collecteur](screenshots/cartographie_collecteur.png) |

| Analyse de gestion des crises |
|---|
| ![analyse de crise ](screenshots/analyse.png) |

| Gestion capacitaire des lits et RH |
|---|
| ![Gestion capacitaire ](screenshots/capa.png) | 
| ![Gestion capacitaire ](screenshots/capad.png) |
---

### Démarrage rapide

```powershell
# Windows — double-clic sur SETUP.bat ou depuis PowerShell :
.\SETUP.bat
# Choisir [1] pour la démo avec scénario ransomware pré-rempli
```

```bash
# Linux
pip install -r requirements.txt
python setup_demo1.py && python seed_demo_crise.py
python main.py
# → http://localhost:8000  (login: dircrise / Scribe2026!)
```

---

### Fonctionnalités v1.3.0

#### 🌐 VEILLE — Main courante incidents
- Déclaration d'incident : CYBER / SANITAIRE / MIXTE, niveaux 1 (VEILLE) à 4 (CRITIQUE)
- Jalons de résolution prédéfinis (DSI contacté, CERT Santé, Isolation réseau, Sauvegarde OK…) + jalons personnalisés
- Analyse IA par Albert (DINUM) — cyber ou sanitaire selon le type d'incident
- **Analyse globale** : Albert analyse tous les incidents ouverts + décisions cellule en une requête
- Timeline interactive avec projection de retour à la normale
- Export CSV, export main courante complète (tous modules)
- Filtres multi-critères : site, directeur, urgence, statut, type

#### 🏥 SOINS — Cartographie des pôles
- Vue par pôle clinique (14 pôles CHAG) avec statut : OPÉRATIONNEL / MODE DÉGRADÉ / IMPACT CRITIQUE
- **Coloration automatique** selon les incidents ouverts rattachés au pôle (via code UF ou mots-clés dans le texte)
- **Coloration capacitaire** : si un cadre déclare une alerte dans CAPACITÉ, le pôle concerné se colore dans SOINS
- Analyse capacitaire Albert
- Frise temporelle de projection retour à la normale
- Services transverses (Sécurité physique, Logistique) avec statut dégradé

#### 🏛️ CELLULE — Salle de crise
- Registre des présences horodaté (entrée/sortie, nom, rôle)
- Chronologie décisionnelle avec base réglementaire (Plan Blanc, NIS2, ORSAN…)
- Bouton ACTER pour enregistrer les décisions

#### 📋 KANBAN — Tableau opérationnel
- 4 colonnes : BACKLOG / EN COURS / EN ATTENTE / TERMINÉ
- Drag & drop entre colonnes, priorités, assignees, dates d'échéance, liens incidents

#### 📊 REX — Retour d'expérience
- Formulaire en langage opérationnel (non-technicien), 3 étapes
- Pré-remplissage automatique par Albert depuis les données de l'incident
- Export DOCX rapport de clôture

#### 🔄 RELÈVE — Passation de consignes
- Journal horodaté, **accusé de réception nominatif** (prénom + horodatage tracés)

#### 📞 ANNUAIRE — Répertoire de crise
- Contacts nominaux et de secours (téléphonie cyber/IPBX)
- Bascule automatique vers numéros de secours en cas de crise

#### 📢 COMMUNIQUÉ — Statut public multi-sites
- Gestion indépendante par site géographique
- Niveaux : OPÉRATIONNEL / PERTURBÉ / DÉGRADÉ / ALERTE / CRITIQUE
- Services SI, prise en charge patients, FAQ, chronologie
- Page `/status?site_id=N` accessible sans authentification
- Push vers le collecteur territorial

#### 🛏️ CAPACITÉ — Gestion capacitaire des lits *(nouveau v1.3.0)*

**Usage en mode nominal (hors crise)** :
- Les cadres de service déclarent leur situation 3 fois/jour (matin, après-midi, soir/relève)
- Formulaire rapide (< 2 min) : lits disponibles H/F/I, statut RH, statut matériel, commentaire
- Le directeur des soins dispose d'un tableau de bord temps réel de tous les services
- Historique complet conservé pour le REX et les graphiques d'évolution

**Usage en mode crise** :
- Déclaration de seuil d'alerte par le cadre → **création automatique d'un incident dans VEILLE**
- Impact visuel immédiat sur les cartes de pôles dans l'onglet SOINS
- Alertes silence si un service ne déclare pas depuis > 6h
- Push vers le collecteur territorial GHT/ARS (route `/api/push-capacite`)

**Spécificités CHAG** :
- 58 unités pré-chargées depuis le BedManager (ANNECY : MÉDECINE, CHIRURGIE, REA/URGENCES, SP, FME, PSY + SAINT-JULIEN + RUMILLY + USLD/EHPAD)
- Gestion H/F/I par unité : une chambre homme ne peut pas accueillir une femme dans les unités mixtes (GYNÉCO = F uniquement, OBSTÉTRIQUE = F uniquement, REA = I uniquement…)
- **Albert CAPACITÉ** : analyse IA de la situation capacitaire globale avec 4 questions rapides + champ libre

#### 🔬 ANALYSE — Debriefing de crise
- Chargement ZIP d'archive par glisser-déposer (JSZip 3.10.1 embarqué — 100% hors-ligne)
- Console de logs visible pour diagnostic
- **8 métriques automatiques** : durée crise, délai activation cellule, délai communication publique, nb incidents, nb décisions, taux kanban, jalons validés, participants max
- **Frise chronologique interactive** : 7 catégories (incidents, décisions, cellule, kanban, relève, communiqués, REX + **déclarations capacitaires**)
- Mode comparaison : deux archives côte à côte pour mesurer la progression
- Annotations persistantes (localStorage) par archive
- Albert Analyse : 6 questions rapides + question libre + synthèse
- Export rapport DOCX

#### 📦 Gestion de fin de crise
- **Bouton ARCHIVER** : crée un ZIP horodaté `archives/crise_YYYYMMDD_HHMMSS.zip` sans toucher aux données
- Le ZIP contient : incidents, décisions, présences, relève, kanban, REX, communiqués, **déclarations capacitaires**, chronologie publique
- **Bouton NOUVEAU** : remet le tableau de bord à zéro (double confirmation requise)

---

### Architecture

```
scribe_suite/
├── SETUP.bat                     ← Script de démarrage interactif (Windows)
├── README.md                     ← Documentation bilingue FR/EN
├── screenshots/                  ← Captures d'écran v1.3.0
├── scribe/                       ← Application établissement (port 8000)
│   ├── SETUP.bat                 ← Menu interactif : démo / config personnalisée
│   ├── CHAG-MODE.bat             ← Mode CHAG (avec UF FICOM)
│   ├── main.py                   ← Point d'entrée FastAPI
│   ├── setup.py                  ← Initialisation universelle depuis config.xml
│   ├── setup_demo1.py            ← Démo CHV Valmont (5 sites, 106 UF)
│   ├── setup_demo2.py            ← Démo CSBM Montrelay
│   ├── setup_capacite_chag.py    ← Référentiel 58 unités BedManager CHAG
│   ├── seed_demo_crise.py        ← Scénario ransomware LockBit 48h
│   ├── import_uf2.py             ← Import UF depuis export FICOM (.xlsx)
│   ├── config_demo1.xml          ← Config démo 1 — CHV Valmont
│   ├── config_demo2.xml          ← Config démo 2 — CSBM Montrelay
│   └── app/
│       ├── static/index.html     ← SPA complète (~390 Ko, JSZip embarqué)
│       ├── lang/                 ← i18n : fr en de es it nl pl pt
│       └── api/
│           ├── sitrep.py         ← Incidents (CRUD, jalons, PJ)
│           ├── cellule.py        ← Présences + décisions
│           ├── tasks.py          ← Kanban
│           ├── releve.py         ← Consignes + accusés nominatifs
│           ├── rex.py            ← Retour d'expérience
│           ├── rapport.py        ← Export DOCX, archivage, fin de crise
│           ├── albert.py         ← Endpoints IA (incidents, crise, capacité)
│           ├── ai_router.py      ← Abstraction 7 fournisseurs IA
│           ├── capacite.py       ← Gestion capacitaire lits/RH/matériel ★ v1.3.0
│           ├── cartographie.py   ← UF, pôles, mapping UF→pôle
│           ├── federation.py     ← Push collecteur (crise + sanitaire)
│           └── status_page.py    ← Communiqués publics
└── collecteur/                   ← Superviseur territorial (port 9000)
    ├── collecteur.py             ← FastAPI mono-fichier
    └── setup_collecteur_auth.py  ← Login/mdp interface web
```

---

### Configuration (`config.xml`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<scribe>
  <etablissement>
    <nom>Centre Hospitalier de Valmont</nom>
    <sigle>CHV</sigle>
    <finess>000000001</finess>
  </etablissement>

  <admin>
    <login>dircrise</login>
    <password>MotDePasse!</password>
    <nom_affiche>Directeur de Crise</nom_affiche>
  </admin>

  <sites>
    <site>
      <nom>Site Principal — Valmont</nom>
      <adresse>1 avenue de l'Hôpital, 74000 Valmont</adresse>
      <latitude>46.2012</latitude>
      <longitude>6.1445</longitude>
      <telephone_garde>04 50 00 00 01</telephone_garde>
    </site>
  </sites>

  <!-- Langue interface : fr en de es it nl pl pt -->
  <langue>fr</langue>

  <ia>
    <fournisseur>albert</fournisseur>  <!-- albert | openai | anthropic | gemini | mistral | ollama | openai_compat -->
    <cle_api>sk-...</cle_api>
    <modele>mistralai/Ministral-3-8B-Instruct-2512</modele>
    <url_base>https://albert.api.etalab.gouv.fr/v1/chat/completions</url_base>
  </ia>

  <federation>
    <enabled>true</enabled>
    <collecteur_url>http://IP-COLLECTEUR:9000/api/push</collecteur_url>
    <token>TOKEN_16_CHARS_MIN</token>
    <intervalle_secondes>30</intervalle_secondes>
    <!-- Synchronisation état de crise (incidents/KPIs) → CERT Santé -->
    <sync_crise>true</sync_crise>
    <share_details>true</share_details>
    <share_min_urgency>1</share_min_urgency>
    <!-- Synchronisation état sanitaire (capacitaire) → ARS/GHT -->
    <sync_sanitaire>true</sync_sanitaire>
    <share_capacite_details>true</share_capacite_details>
  </federation>
</scribe>
```

---

### IA — 7 fournisseurs supportés

| Fournisseur | `<fournisseur>` | Notes |
|---|---|---|
| **Albert (DINUM)** | `albert` | ✅ Recommandé ES publics français — souverain |
| **Ollama** | `ollama` | 100% local, hors-ligne |
| OpenAI | `openai` | GPT-4 |
| Anthropic | `anthropic` | Claude |
| Mistral | `mistral` | api.mistral.ai |
| Gemini | `gemini` | Google |
| Compatible OpenAI | `openai_compat` | LM Studio, vLLM, Jan |

Changement de fournisseur sans modification de code — uniquement dans `config.xml`.

---

### Collecteur territorial

Application indépendante (port 9000) agrégeant les remontées de plusieurs établissements.

**Deux routes de push distinctes** pour deux usages séparés :
- `/api/push` → **état de crise** (incidents, KPIs, niveaux d'alerte) — destinataire : CERT Santé
- `/api/push-capacite` → **état sanitaire** (lits, RH, matériel) — destinataire : ARS, GHT

**Onglets collecteur** : Supervision (établissements + incidents), Cartographie (GPS par niveau), Statuts publics, Aide à la décision (Albert territorial).

**Flux incidents** : groupé par établissement puis par site géographique.

```bash
cd collecteur/
pip install -r collecteur_requirements.txt
python setup_collecteur_auth.py    # optionnel — login/mdp
python collecteur.py
# → http://localhost:9000

# Enregistrer un établissement
curl -X POST http://localhost:9000/api/admin/tokens \
  -H "Authorization: Bearer TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"sigle":"MONCH","token":"TOKEN_ETABLISSEMENT"}'
```

---

### Scénario de démonstration

`seed_demo_crise.py` génère un scénario **ransomware LockBit complet (48h)** :
- 15 incidents sur 5 sites, 8 pôles cliniques
- 22 décisions actées (Plan Blanc, NIS2, ORSAN)
- 20 tâches kanban (dont 11 TERMINÉES)
- 10 consignes de relève avec accusés nominatifs
- 5 fiches REX
- 2 communiqués publics multi-sites

**Test du module ANALYSE** : après avoir lancé la démo, cliquer sur `📦 ARCHIVER` puis glisser le ZIP dans l'onglet ANALYSE pour voir les 8 métriques automatiques et la frise chronologique complète.

---

### Conformité réglementaire

| Référentiel | Couverture |
|---|---|
| **NIS2** | Traçabilité décisions, jalons CERT Santé, chronologie, archivage |
| **Plan Blanc** | Activation cellule, registre présences, diffusion communiqués |
| **CERT Santé** | Jalon dédié, signalement intégré dans l'annuaire secours |
| **HDS / RGPD** | Déploiement local, zéro cloud obligatoire, données souveraines |
| **ORSAN** | Base réglementaire des décisions cellule |

---

---

### 🐳 Déploiement Docker

#### Démarrage rapide (mode démo)

```bash
git clone https://github.com/nocomp/scribe
cd scribe/scribe
docker compose up -d
# → http://localhost:8000   login: dircrise / Scribe2026!
```

#### Avec votre configuration personnalisée

```bash
# 1. Remplir SCRIBE_config_etablissement.xlsx
# 2. Générer config.xml depuis le fichier Excel
python import_config_xlsx.py SCRIBE_config_etablissement.xlsx

# 3. Lancer Docker avec votre config
docker compose up -d \
  -e SCRIBE_IA_KEY=votre_cle_albert
# La base est initialisée automatiquement au premier démarrage
```

Ou en montant directement `config.xml` :

```yaml
# docker-compose.yml — décommentez le volume :
volumes:
  - ./config.xml:/data/config.xml:ro
```

#### Variables d'environnement Docker

| Variable | Défaut | Description |
|---|---|---|
| `SCRIBE_IA_PROVIDER` | `albert` | Fournisseur IA (surpasse config.xml) |
| `SCRIBE_IA_KEY` | — | Clé API IA |
| `SCRIBE_IA_MODEL` | — | Modèle IA |
| `SCRIBE_IA_URL` | — | URL base IA (Ollama, LM Studio…) |
| `SCRIBE_PORT` | `8000` | Port d'écoute |
| `LOG_LEVEL` | `info` | Niveau de log uvicorn |

#### Données persistantes

Le volume Docker `scribe_data` contient :
- `/data/db/scribe.db` — base SQLite
- `/data/uploads/` — pièces jointes incidents
- `/data/config.js` — configuration frontend
- `/data/config.xml` — (optionnel) config montée en volume

#### Collecteur territorial Docker

```bash
cd scribe/collecteur
docker compose up -d
# → http://localhost:9000

# Enregistrer un établissement
curl -X POST http://localhost:9000/api/admin/tokens \
  -H "Authorization: Bearer TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"sigle":"MON_CH","token":"TOKEN_ETABLISSEMENT"}'
```

### Déploiement production (Linux systemd)

```ini
[Unit]
Description=SCRIBE Crisis Management
After=network.target

[Service]
User=scribe
WorkingDirectory=/opt/scribe
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 🇬🇧 SCRIBE — Hospital Crisis Management Log

SCRIBE is an open-source **hospital crisis management and bed capacity monitoring platform** developed by the CISO of Centre Hospitalier Annecy-Genevois (CHAG). It provides a complete digital crisis log, real-time capacity tracking, a multi-facility territorial collector, and an AI-powered post-crisis debriefing module.

**Dual use** — SCRIBE is designed to be useful **both in normal operations and during crises**:
- **Normal mode**: daily capacity tracking (beds, staff, equipment), 3 declarations/day by nurse managers, dashboard for nursing directors and HR
- **Crisis mode**: incident log, crisis room, operational kanban, public bulletins, territorial GHT/ARS coordination

**Designed for non-technical staff** — nurse managers, directors, crisis coordinators — SCRIBE requires no cloud, no LDAP, and runs fully offline on an isolated network.

---

### Quick Start

#### Docker (quick start)

```bash
git clone https://github.com/nocomp/scribe
cd scribe/scribe
docker compose up -d
# → http://localhost:8000   login: dircrise / Scribe2026!
```

With custom config:
```bash
# Mount your config.xml
docker compose up -d  # edit docker-compose.yml to uncomment the config.xml volume
```

For the territorial collector:
```bash
cd scribe/collecteur && docker compose up -d
# → http://localhost:9000
```


```powershell
# Windows — double-click SETUP.bat or from PowerShell:
.\SETUP.bat
# Choose [1] for the demo with pre-filled ransomware scenario
```

```bash
# Linux
pip install -r requirements.txt
python setup_demo1.py && python seed_demo_crise.py
python main.py
# → http://localhost:8000  (login: dircrise / Scribe2026!)
```

---

### Features v1.3.0

#### 🌐 WATCH — Incident Log
- Incident declaration: CYBER / HEALTH / MIXED, levels 1 (WATCH) to 4 (CRITICAL)
- Predefined resolution milestones + custom milestones
- AI analysis (Albert DINUM), global situation analysis
- Interactive timeline with return-to-normal projection
- CSV export, complete activity log export (all modules)

#### 🏥 CARE — Capacity Mapping
- 14 clinical department cards with automatic status coloring
- Color driven by open incidents (UF code or keyword matching in incident text)
- **Capacity color override**: nurse manager alert in CAPACITY tab immediately colors the pole in CARE
- Albert capacity analysis
- Transverse services status (Physical Security, Logistics)

#### 🏛️ CELL — Crisis Room
- Timestamped attendance register (entry/exit, name, role)
- Decision log with regulatory basis (White Plan, NIS2, ORSAN)

#### 📋 KANBAN — Operational Board
- 4 columns: BACKLOG / IN PROGRESS / WAITING / DONE
- Drag & drop, priorities, assignees, due dates, incident links

#### 📊 REX — Experience Feedback
- Plain-language form, Albert auto-fill, DOCX export

#### 🔄 HANDOVER — Shift Handover
- Timestamped log, **named acknowledgement** (first name + timestamp)

#### 📞 DIRECTORY — Crisis Directory
- Standard and emergency contacts, automatic telephone failover

#### 📢 BULLETIN — Public Status
- Multi-site independent management
- Levels: OPERATIONAL / DISRUPTED / DEGRADED / ALERT / CRITICAL
- Public page `/status?site_id=N` without authentication

#### 🛏️ CAPACITY — Bed Capacity Management *(new v1.3.0)*

**Normal operations use**:
- Nurse managers declare their service status 3×/day (morning, afternoon, evening/handover)
- Quick form (< 2 min): available beds M/F/N, HR status, equipment status, comment
- Real-time dashboard for nursing directors and HR managers
- Full history for REX and trend graphs

**Crisis use**:
- Alert threshold declared by nurse manager → **automatic incident creation in WATCH**
- Immediate visual impact on department cards in CARE tab
- Silence alerts if service hasn't declared in > 6h
- Push to territorial collector GHT/ARS (route `/api/push-capacite`)

**CHAG specifics**:
- 58 units pre-loaded from BedManager (ANNECY: MEDICINE, SURGERY, ICU/EMERGENCY, PALLIATIVE, FME, PSYCH + SAINT-JULIEN + RUMILLY + LTCU/NURSING HOME)
- M/F/N bed management per unit: male room cannot accommodate female patients in mixed units
- **Albert CAPACITY**: AI analysis of global capacity situation with 4 quick questions + free field

#### 🔬 ANALYSIS — Crisis Debrief
- ZIP archive upload by drag-and-drop (embedded JSZip — 100% offline)
- **8 automatic metrics** + interactive timeline of all activities including **capacity declarations**
- Comparison mode: two archives side by side
- Albert Analysis with 6 quick questions + free question
- DOCX report export

#### 📦 End-of-Crisis Management
- **ARCHIVE button**: creates timestamped ZIP (incidents, decisions, attendance, handover, kanban, REX, bulletins, **capacity declarations**, public timeline)
- **NEW button**: resets dashboard (double confirmation)

---

### Regulatory Compliance

| Framework | Coverage |
|---|---|
| **NIS2** | Decision traceability, CERT Santé milestones, timeline |
| **White Plan** | Cell activation, attendance register, communications |
| **CERT Santé** | Dedicated milestone, integrated reporting |
| **HDS / GDPR** | Local deployment, zero mandatory cloud |
| **ORSAN** | Regulatory basis for decisions |

---

### AI — 7 supported providers

| Provider | Config | Notes |
|---|---|---|
| **Albert (DINUM)** | `albert` | ✅ Recommended for French public health — sovereign |
| **Ollama** | `ollama` | 100% local, fully offline |
| OpenAI | `openai` | GPT-4 |
| Anthropic | `anthropic` | Claude |
| Mistral | `mistral` | api.mistral.ai |
| Gemini | `gemini` | Google |
| OpenAI-compatible | `openai_compat` | LM Studio, vLLM, Jan |

---

## Changelog

### v1.3.0 (current — March 2026)
- **NEW: CAPACITY tab** — bed capacity management with nurse manager declarations (M/F/N beds, HR, equipment), alert thresholds, automatic incident creation, dashboard for nursing directors
- **NEW: Albert CAPACITY** — AI analysis of capacity situation with pre-formed questions
- **NEW: Territorial collector capacity route** — `/api/push-capacite` for ARS/GHT dashboard
- **NEW: `sync_crise` / `sync_sanitaire` config flags** — separate pushes for CERT Santé vs ARS
- Fix: CARE tab coloring — `uf-to-pole` mapping now uses keyword matching first, FICOM pole as fallback (fixes "Total CARDIOVASCULAIRE" misclassification)
- Fix: CARE tab real-time update on new incident (refreshAll now calls renderSoins)
- Fix: Capacity declarations included in main courante export and crisis archive ZIP
- Interactive `SETUP.bat` for Windows (demo / custom config menu)
- PR #4 Elched (SOC-HCL): Docker ai_router.py fix

### v1.2.0
- ANALYSIS tab: offline ZIP debrief, 8 metrics, interactive timeline, comparison mode, Albert analysis, DOCX export
- ARCHIVE / NEW buttons separated
- JSZip 3.10.1 embedded inline (offline)
- Debug console for ANALYSIS tab

### v1.1.1
- Named acknowledgement in HANDOVER (first name + timestamp)
- Full activity log CSV export
- Collector login/password protection
- NEW CRISIS button: ZIP archive + dashboard reset

### v1.1.0
- Internationalisation: 8 European languages
- Collector: distinct GPS markers per geographic site

---

## Contributors

- [@nocomp](https://github.com/nocomp) — RSSI CHAG — project lead
- [@charles-chu-lyon](https://github.com/charles-chu-lyon) — CHU Lyon — PR #1 ai_router fix
- [@Elched](https://github.com/Elched) — SOC-HCL — PR #2-#4 Dockerfile, ai_router fix

---

## License

MIT — Free to use, modify and distribute.
Developed by and for French public healthcare facilities.

**Repository**: https://github.com/nocomp/scribe
**Version**: 1.3.0 — March 2026
