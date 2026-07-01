```
███████╗ ██████╗██████╗ ██╗██████╗ ███████╗
██╔════╝██╔════╝██╔══██╗██║██╔══██╗██╔════╝
███████╗██║     ██████╔╝██║██████╔╝█████╗
╚════██║██║     ██╔══██╗██║██╔══██╗██╔══╝
███████║╚██████╗██║  ██║██║██████╔╝███████╗
╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
```

**Main courante numérique de gestion de crise hospitalière**  
**Digital Crisis Management Platform for Healthcare Facilities**

[![Version](https://img.shields.io/badge/version-3.6.0--beta-blue)](https://github.com/nocomp/scribe)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-green)](https://github.com/nocomp/scribe/blob/main/LICENSE)
[![Stack](https://img.shields.io/badge/stack-Python%20%7C%20FastAPI%20%7C%20SQLite-orange)](https://github.com/nocomp/scribe)
[![Languages](https://img.shields.io/badge/i18n-24%20EU%20languages-purple)](https://github.com/nocomp/scribe)
[![Branch](https://img.shields.io/badge/branch-beta-yellow)](https://github.com/nocomp/scribe/tree/beta)

---

> 🇫🇷 **[Français](#-scribe--main-courante-de-crise-hospitalière)** | 🇬🇧 **[English](#-scribe--hospital-crisis-management-platform)**

---

## 🇫🇷 SCRIBE — Main courante de crise hospitalière

SCRIBE est une plateforme open-source de **gestion de crise et de pilotage capacitaire hospitalier**. Elle fournit une main courante numérique complète, un suivi capacitaire en temps réel, un collecteur territorial multi-établissements, des modules de rappel du personnel et d'envoi sécurisé de fichiers, et un assistant IA de debriefing post-crise.

**Double usage — nominal et crise :**

- **Mode nominal** : suivi quotidien de la capacité (lits, RH, matériel), déclarations 3×/jour par les cadres, tableau de bord direction
- **Mode crise** : main courante incidents, cellule de crise, kanban opérationnel, rappel du personnel par vagues, communiqués publics, coordination territoriale GHT

**Conçu pour les non-techniciens** — aucun cloud, aucun LDAP, fonctionne en réseau isolé.

---

### Démarrage rapide

```bash
# Linux / macOS
pip install -r requirements.txt
python setup.py          # menu interactif : démo ou config personnalisée
# → http://localhost:8000  (login: dircrise / Scribe2026!)
```

```bat
REM Windows
SETUP.bat
```

```bash
# Docker
git clone https://github.com/nocomp/scribe
cd scribe && git checkout beta
docker compose up -d
# → http://localhost:8000
```

---

### Fonctionnalités v3.6.0-beta

#### 🌐 VEILLE — Main courante incidents

- Déclaration CYBER / SANITAIRE / MIXTE, niveaux 1 (VEILLE) à 4 (CRITIQUE)
- Jalons de résolution prédéfinis + personnalisés, export CSV
- Analyse IA (Albert DINUM, ou 6 autres fournisseurs)
- Timeline interactive avec projection de retour à la normale
- Filtres multi-critères : site, directeur, urgence, statut, type

#### 🏥 SOINS — Cartographie des pôles

- Vue par pôle avec statut OPÉRATIONNEL / MODE DÉGRADÉ / IMPACT CRITIQUE
- Coloration automatique selon incidents et déclarations capacitaires
- Carte Leaflet avec trajectoires de transferts patients (OSRM)

#### 🏛️ CELLULE — Salle de crise

- Registre des présences horodaté (entrée/sortie, nom, rôle)
- Chronologie décisionnelle avec base réglementaire (Plan Blanc, NIS2, ORSAN…)

#### 📋 KANBAN — Tableau opérationnel

- 4 colonnes (Backlog / En cours / En attente / Terminé), drag & drop
- Priorités, assignees, dates d'échéance, liens incidents

#### 📊 REX — Retour d'expérience

- Formulaire en langage opérationnel, pré-remplissage Albert, export DOCX

#### 🔄 RELÈVE — Passation de consignes

- Journal horodaté, accusé de réception nominatif

#### 📞 ANNUAIRE — Répertoire de crise

- Contacts nominaux + numéros de secours, bascule automatique en cas de crise CYBER (PABX impacté)

#### 📢 COMMUNIQUÉ — Statut public multi-sites

- Niveaux OPÉRATIONNEL / PERTURBÉ / DÉGRADÉ / ALERTE / CRITIQUE par service SI et prise en charge patients
- Page `/status` publique, sans authentification
- QR code d'accès rapide intégré

#### 🚑 TRANSFERTS — Gestion des patients inter-sites

- Suivi EN PRÉPARATION / EN COURS / ARRIVÉ / ANNULÉ
- Trajectoire OSRM + progression ambulance selon ETA sur la carte
- Données patients strictement locales — ne remontent jamais au collecteur (HDS/RGPD)

#### 🛏️ CAPACITÉ — Gestion capacitaire des lits

- Déclarations 3×/jour par les cadres (lits H/F/I, RH, matériel)
- Tableau de bord temps réel direction des soins
- Création automatique d'incident sur seuil d'alerte
- Push vers le collecteur territorial

#### 📡 INTER-GHT — Coordination territoriale

- Déclarations de situation (broadcast ou ciblé)
- Demandes inter-GHT (transfert patient, renfort RH, matériel)
- Messagerie inter-établissements via le collecteur

#### 📞 RAPPEL DU PERSONNEL *(nouveau v3.6.0)*

- Mobilisation de masse par type (direction, astreinte, cadres…) et par site
- **Presets** enregistrés pour déclencher un rappel en deux clics
- Envoi SMS (OVH, Twilio, Free…) et/ou e-mail (SMTP)
- **Widget jauge demi-cercle** : suivi temps réel — appelés / ont répondu / sont arrivés / manquent à l'appel
- Escalade par **vagues** : relance auto des non-répondants, validation cellule à chaque vague
- Bascule automatique vers numéros de secours si PABX impacté

#### 🔒 ENVOI SÉCURISÉ BLUEFILES *(nouveau v3.6.0)*

- Intégration native du service **BlueFiles** (Forecomm) — chiffrement bout-en-bout, hébergement HDS
- **Depuis l'instance établissement** : bouton « Envoi sécurisé par BlueFiles » dans la messagerie — glisser-déposer, destinataires email multiples, commentaire
- **Depuis la supervision** : bouton dédié dans la messagerie territoriale, visible uniquement si le plugin est configuré
- Le contenu ne transite jamais par SCRIBE — chiffré côté BlueFiles
- Chaque envoi tracé dans SCRIBE (audit HDS/RGPD)
- Configuration : login / mot de passe (Fernet au repos) / serveur, via l'admin de chaque instance et de la supervision
- Compatible crise inter-établissements : bilans patients, listes nominatives, documents sensibles

#### ✉️ MESSAGERIE — Communication interne et inter-GHT

- Messagerie interne : inbox, envoyés, brouillons, réponse/transfert, pièces jointes (10 Mo/PJ, 25 Mo total)
- Messagerie inter-GHT via collecteur (broadcast ou ciblé par établissement)
- Channels SMS et e-mail disponibles selon configuration

#### 💬 CHAT — Coordination temps réel

- Salons locaux (établissement) et territoriaux (partagés entre tous les GHTs)
- Mentions @, pièces jointes, historique
- Synchronisation inter-GHT via le collecteur

#### 🔬 ANALYSE — Debriefing de crise

- Chargement ZIP d'archive par glisser-déposer (100% hors-ligne)
- 8 métriques automatiques : durée crise, délais, incidents, décisions, kanban, jalons, participants
- Frise chronologique interactive (7 catégories), mode comparaison
- Analyse Albert, export rapport DOCX

#### 🎯 MODE EXERCICE

- Instances dédiées sur des bases isolées (zéro impact sur la production)
- Console animateur pour injecter des stimuli scénarisés vers les établissements joueurs
- Scénarios JSON v2 : acteurs, stimuli chronologiques, décisions attendues

#### 💾 SAUVEGARDE & RESTAURATION *(amélioré v3.6.0)*

- **Image complète chiffrée AES** depuis la supervision (onglet Instances → 💾 Sauvegarde complète)
- Capture : base SQLite de chaque instance (users, mots de passe, configs plugins, messagerie, capacité, salons chat), fichiers de configuration, secrets de plugins, pièces jointes (`uploads/`), archives de rapports (`archives/`)
- **Restauration plug-and-play** sur une nouvelle version de SCRIBE — anti-path-traversal, purge des fichiers WAL
- Archive non déchiffrable sans le mot de passe : à conserver hors-ligne

---

### Architecture

```
scribe/
├── main.py                       ← Point d'entrée FastAPI (instance établissement)
├── config.xml                    ← Configuration établissement (à personnaliser)
├── setup.py / SETUP.bat          ← Démarrage interactif Linux/Windows
├── requirements.txt
├── collecteur/                   ← Superviseur territorial (port 9000)
│   ├── collecteur.py             ← FastAPI — supervision + BlueFiles supervision
│   └── central_config_store.py  ← Config centrale chiffrée (IA, SMTP, SMS, BlueFiles)
├── master/                       ← Pilotage multi-instances (onboarding, backup, restore)
│   ├── master_routes.py
│   └── instances_manager.py
├── plugins/                      ← Plugins fonctionnels
│   ├── bluefiles/                ← Envoi sécurisé BlueFiles (CLI Forecomm)
│   ├── messagerie/               ← Messagerie interne (inbox, brouillons, PJ)
│   ├── capacite/                 ← Gestion capacitaire
│   ├── transferts/               ← Transferts patients
│   ├── notifications/            ← Rappel du personnel (SMS/SMTP)
│   ├── rapport/                  ← Archivage + export DOCX
│   ├── exercice/                 ← Mode exercice
│   └── ...
└── app/
    ├── static/index.html         ← SPA complète
    └── lang/                     ← i18n 24 langues UE
```

---

### Configuration (`config.xml`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<scribe>
  <etablissement>
    <nom>Centre Hospitalier de Valmont</nom>
    <sigle>CHV</sigle>
  </etablissement>

  <admin>
    <login>dircrise</login>
    <password>MotDePasse!</password>
  </admin>

  <!-- Langue interface : fr en de es it nl pl pt (+ 16 autres EU) -->
  <langue>fr</langue>

  <ia>
    <!-- albert | openai | anthropic | gemini | mistral | ollama | openai_compat -->
    <fournisseur>albert</fournisseur>
    <cle_api>sk-...</cle_api>
    <modele>mistralai/Ministral-3-8B-Instruct-2512</modele>
    <url_base>https://albert.api.etalab.gouv.fr/v1/chat/completions</url_base>
  </ia>

  <federation>
    <enabled>true</enabled>
    <collecteur_url>http://IP-COLLECTEUR:9000/api/push</collecteur_url>
    <token>TOKEN_16_CHARS_MIN</token>
    <intervalle_secondes>30</intervalle_secondes>
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

---

### Collecteur territorial (supervision)

Application indépendante (port 9000) agrégeant les remontées de plusieurs établissements.

```bash
cd collecteur/
pip install -r collecteur_requirements.txt
python collecteur.py
# → http://localhost:9000
```

Routes principales :

| Route | Usage |
|---|---|
| `POST /api/push` | État de crise (incidents, KPIs, statuts) |
| `POST /api/push-capacite` | État capacitaire (lits, RH, matériel) |
| `POST /api/push-status` | Statut public (communiqué) |
| `GET /api/summary` | Agrégation de tous les établissements |
| `GET /api/admin/bluefiles/status` | État plugin BlueFiles supervision |
| `POST /api/admin/bluefiles/send` | Envoi sécurisé depuis supervision |

---

### Déploiement multi-établissements

```bash
# 1. Démarrer le collecteur
cd collecteur && python collecteur.py &   # → http://localhost:9000

# 2. Configurer chaque établissement (config.xml avec token unique)
# <collecteur_url>http://localhost:9000/api/push</collecteur_url>
# <token>TOKEN_UNIQUE_ETABLISSEMENT</token>

# 3. Démarrer chaque instance
SCRIBE_PORT=8001 DATABASE_URL=sqlite:///site1.db python main.py &
SCRIBE_PORT=8002 DATABASE_URL=sqlite:///site2.db python main.py &

# 4. Accepter chaque établissement
# → http://localhost:9000 → ⏳ EN ATTENTE → ✓ ACCEPTER
```

---

### Conformité réglementaire

| Référentiel | Couverture |
|---|---|
| **NIS2** | Traçabilité décisions, jalons CERT Santé, chronologie, archivage |
| **Plan Blanc** | Activation cellule, registre présences, diffusion communiqués, rappel du personnel |
| **CERT Santé** | Jalon dédié, signalement intégré dans l'annuaire secours |
| **HDS / RGPD** | Déploiement local, données patients jamais transmises au collecteur, envoi sécurisé BlueFiles sans copie locale |
| **ORSAN** | Base réglementaire des décisions cellule |

---

## 🇬🇧 SCRIBE — Hospital Crisis Management Platform

SCRIBE is an open-source **hospital crisis management and bed capacity monitoring platform**. It provides a complete digital crisis log, real-time capacity tracking, a multi-facility territorial collector, staff recall, secure file transfer (BlueFiles), and an AI-powered post-crisis debriefing module.

**Dual use** — both in normal operations and during crises.  
**Designed for non-technical staff** — no cloud, no LDAP, fully offline capable.

---

### Quick Start

```bash
# Linux / macOS
pip install -r requirements.txt
python setup.py       # interactive menu: demo / custom config
# → http://localhost:8000  (login: dircrise / Scribe2026!)
```

```bat
REM Windows
SETUP.bat
```

```bash
# Docker
git clone https://github.com/nocomp/scribe && cd scribe && git checkout beta
docker compose up -d
# → http://localhost:8000
```

---

### Features v3.6.0-beta

#### 🌐 WATCH — Incident Log
Incident declaration (CYBER / HEALTH / MIXED, levels 1–4), predefined milestones, AI analysis (Albert DINUM), interactive timeline, CSV export.

#### 🏥 CARE — Clinical Map
Pole cards with automatic status coloring driven by incidents and capacity alerts. Leaflet map with OSRM patient transfer routes.

#### 🏛️ CELL — Crisis Room
Timestamped attendance register, decision log with regulatory basis (White Plan, NIS2, ORSAN…).

#### 📋 KANBAN — Operational Board
4-column board with drag & drop, priorities, assignees, due dates, incident links.

#### 📊 REX — After-Action Review
Plain-language form, Albert auto-fill, DOCX export.

#### 🔄 HANDOVER — Shift Handover
Timestamped log with named acknowledgement.

#### 📞 DIRECTORY — Crisis Directory
Standard and emergency contacts, automatic telephony failover when PBX is impacted.

#### 📢 BULLETIN — Public Status
Multi-site independent management. `/status` page without authentication. Built-in QR code.

#### 🚑 TRANSFERS — Patient Management
Transfer tracking across sites. Patient data stays strictly local, never reaching the collector (HDS/GDPR).

#### 🛏️ CAPACITY — Bed Capacity Management
3×/day nurse manager declarations, real-time director dashboard, automatic incident creation on alert threshold, push to collector.

#### 📡 INTER-GHT — Territorial Coordination
Situation declarations, inter-GHT requests (patient transfers, HR reinforcements), inter-establishment messaging.

#### 📞 STAFF RECALL *(new v3.6.0)*

- Mass mobilisation by type (management, on-call, nursing leads…) and site
- **Presets** — trigger a recall in two clicks
- SMS (OVH, Twilio, Free…) and/or email (SMTP)
- **Half-circle gauge widget**: real-time — called / responded / arrived / missing
- **Wave escalation**: auto re-contact non-responders, cell confirmation required per wave
- Automatic telephony failover to emergency numbers when PBX is impacted

#### 🔒 SECURE BLUEFILES TRANSFER *(new v3.6.0)*

- Native integration of **BlueFiles** (Forecomm) — end-to-end encrypted, HDS hosting
- **From an establishment instance**: "Secure send via BlueFiles" button in the messaging tab — drag-and-drop files, multiple email recipients, comment
- **From supervision**: dedicated button in the territorial messaging bar, visible only if the plugin is configured
- File content never transits through SCRIBE — encrypted on the BlueFiles side
- Every transfer logged in SCRIBE (HDS/GDPR audit trail)
- Configuration: login / password (Fernet at rest) / server, via admin of each instance and supervision
- Ideal for crisis inter-establishment use: patient summaries, staff lists, sensitive documents

#### ✉️ MESSAGING — Internal & Inter-GHT
Internal inbox (drafts, reply, forward, attachments up to 10 MB/file). Inter-GHT messaging via collector (broadcast or targeted).

#### 💬 CHAT — Real-Time Coordination
Local and territorial rooms, @ mentions, attachments, inter-GHT sync.

#### 🔬 ANALYSIS — Crisis Debrief
Offline ZIP archive upload, 8 automatic metrics, interactive timeline (7 categories), comparison mode, Albert analysis, DOCX export.

#### 🎯 EXERCISE MODE
Dedicated isolated instances, animator console for scripted stimulus injection.

#### 💾 BACKUP & RESTORE *(improved v3.6.0)*

- **Full AES-encrypted image** from supervision (Instances tab → 💾 Full backup)
- Captures: SQLite database (users, passwords, plugin configs, messaging, capacity, chat), config files, plugin secrets, attachments (`uploads/`), report archives (`archives/`)
- **Plug-and-play restore** on a fresh SCRIBE version — anti-path-traversal, WAL purge
- Archive unreadable without the password: keep offline

---

### Regulatory Compliance

| Framework | Coverage |
|---|---|
| **NIS2** | Decision traceability, CERT Santé milestones, timeline, archiving |
| **White Plan** | Cell activation, attendance register, staff recall with wave escalation |
| **CERT Santé** | Dedicated milestone, integrated emergency reporting |
| **HDS / GDPR** | Local deployment, patient data never leaves the establishment, BlueFiles secure transfer with no local copy |
| **ORSAN** | Regulatory basis for crisis room decisions |

---

## Changelog

### v3.6.0-beta (July 2026) — Security hardening

- **API access lockdown** — all data endpoints (reports, incidents, bed capacity, crisis cell, handover, REX, transfers, cartography, kanban, attachments, Albert AI, federation) now require a valid session by default (deny-by-default at router mount)
- **Authenticated `/uploads`** — incident attachments are no longer served as public static files; access requires a token (header or query) with path-traversal protection
- **Federation node token** — inter-instance endpoints (`/messagerie/ingest`, notifications sync, supervision) can be locked fleet-wide with a shared `SCRIBE_NODE_TOKEN`; collector now sends it on downstream delivery
- **Admin diagnostics** — `/debug` endpoints moved from optional auth to `require_admin`
- **Brute-force protection** — per-IP rate limiting plus per-account lockout on the login endpoint
- **Rate limiting** — costly (Albert AI) and real-world-effect flows (staff-recall SMS) are throttled per user
- **Account import** — each imported account now gets a unique random temporary password (bcrypt), forced change on first login (no shared default)
- **Plugin upload** — defense-in-depth zip-slip guard (per-member resolved-path confinement)
- **Dependencies** — upper version bounds added to reduce supply-chain / surprise-major risk

### v3.6.0-beta (June 2026)

- **NEW: Staff recall module** — mass mobilisation with presets, SMS/SMTP delivery, real-time response tracking (half-circle gauge widget), wave escalation, telephony failover
- **NEW: BlueFiles secure transfer** — native integration for end-to-end encrypted file sharing from both establishment messaging and territorial supervision; HDS-compatible, audit trail in SCRIBE
- **NEW: Full backup / restore** — AES-encrypted complete image of all instances including attachments, plugin secrets and report archives; plug-and-play restore on fresh install
- **NEW: BlueFiles in supervision messaging** — dedicated send button in territorial supervision messaging bar, enabled/disabled from admin panel
- **IMPROVED: Supervision UI** — DSFR Suite numérique alignment (menu bar, left column, status cards, detail panel)
- **IMPROVED: Detail panel (supervision)** — DSFR typography, clickable "Open public status page ↗" button
- **IMPROVED: i18n** — 24 EU languages now covering all new UI strings (staff recall, BlueFiles, supervision)
- **IMPROVED: Help center** — updated Staff Recall article (presets, gauge widget, wave escalation, telephony failover) + new BlueFiles article (setup, traceability, HDS compliance)

### v1.5.0-beta (March 2026)

- NEW: INTER-GHT tab — situation declarations, inter-GHT requests, collector messages
- NEW: TRANSFERS tab — patient transfer management, OSRM routing
- NEW: Unified inter-GHT messaging
- NEW: `setup.py` interactive menu (Linux/macOS)
- FIX: `federation.py` double router, logout, user menu, race conditions

### v1.3.0

- NEW: CAPACITY tab — bed capacity with nurse manager declarations, alert thresholds, automatic incident creation
- NEW: Albert capacity analysis, territorial collector capacity route

### v1.2.0

- ANALYSIS tab: offline ZIP debrief, 8 metrics, interactive timeline, comparison mode, DOCX export

### v1.1.0

- Internationalisation: 8 European languages
- Named acknowledgement in HANDOVER
- Collector login/password protection

---

## Contributors

- [@nocomp](https://github.com/nocomp) — project lead

---

## License

AGPL-3.0 — Free to use, modify and distribute (copyleft).  
Developed by and for public healthcare facilities.

**Repository**: https://github.com/nocomp/scribe  
**Branch**: `beta`  
**Version**: 3.6.0-beta — June 2026
