<div align="center">

```
███████╗ ██████╗██████╗ ██╗██████╗ ███████╗
██╔════╝██╔════╝██╔══██╗██║██╔══██╗██╔════╝
███████╗██║     ██████╔╝██║██████╔╝█████╗
╚════██║██║     ██╔══██╗██║██╔══██╗██╔══╝
███████║╚██████╗██║  ██║██║██████╔╝███████╗
╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
```

**Open-source hospital crisis management platform**
**Plateforme open-source de gestion de crise hospitalière**

[![Version](https://img.shields.io/badge/version-3.6.0--beta1-orange)](https://github.com/nocomp/scribe/tree/beta)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL_3.0-red)](https://github.com/nocomp/scribe/blob/main/LICENSE)
[![Stack](https://img.shields.io/badge/stack-Python%20%7C%20FastAPI%20%7C%20SQLite-orange)](https://github.com/nocomp/scribe)
[![EU languages](https://img.shields.io/badge/languages-24%20EU%20official-FFCE00)](https://github.com/nocomp/scribe)
[![Branch](https://img.shields.io/badge/branch-beta-yellow)](https://github.com/nocomp/scribe/tree/beta)

🇬🇧 [**English**](#-english) · 🇫🇷 [**Français**](#-français)

</div>

> **⚠ Beta branch** — This is an active development branch. APIs and DB schema may change between beta releases. For stable use, follow the `main` branch.

---

## 🇬🇧 English

SCRIBE is an open-source platform for **hospital crisis management and capacity monitoring**. It provides a complete digital logbook, real-time capacity tracking, a multi-establishment territorial collector, a **staff alert chain (personnel recall)**, and an AI-powered decision-support and post-crisis debriefing module.

### Dual-purpose design

SCRIBE is built to be useful **both in normal operations and during a crisis**:

- **Normal mode** — daily monitoring of service capacity (beds, HR, equipment), three-times-a-day declarations by ward managers, dashboard for medical direction and HR
- **Crisis mode** — incident logbook, crisis cell, operational kanban, public bulletins, staff recall, inter-hospital territorial coordination

Designed for **non-technical users** — clinical managers, directors, crisis coordinators — SCRIBE requires no cloud, no LDAP, and operates on an isolated network.

### 🇪🇺 Built for Europe — 24 EU languages

Every official language of the European Union is selectable from the login screen, before authentication:

🇫🇷 Français · 🇬🇧 English · 🇩🇪 Deutsch · 🇪🇸 Español · 🇮🇹 Italiano · 🇳🇱 Nederlands · 🇵🇹 Português · 🇵🇱 Polski · 🇷🇴 Română · 🇬🇷 Ελληνικά · 🇨🇿 Čeština · 🇸🇰 Slovenčina · 🇸🇪 Svenska · 🇩🇰 Dansk · 🇫🇮 Suomi · 🇭🇺 Magyar · 🇧🇬 Български · 🇭🇷 Hrvatski · 🇸🇮 Slovenščina · 🇪🇪 Eesti · 🇱🇹 Lietuvių · 🇱🇻 Latviešu · 🇲🇹 Malti · 🇮🇪 Gaeilge

- **5 fully native UI translations**: FR, EN, DE, ES, IT
- **19 essential native translations**: the most-used UI elements
- **Coherent English fallback** for the rest

### Architecture

Each hospital runs an **isolated SCRIBE instance** with its own SQLite database. Personal patient data **never leaves the establishment**, and so do staff contact details used for recall. The territorial collector only receives aggregated indicators (capacity levels, incident counts) — GDPR-compliant by design.

### Stack

| Component | Technology |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| ORM | SQLAlchemy |
| Database | SQLite (one per instance) |
| Frontend | Vanilla JS SPA |
| Mapping | Leaflet.js + OSRM |
| AI (optional) | Albert (French government LLM) |
| Design system | DSFR (French government) |
| Notifications | SMS, email (configurable gateways) |

### Key features

- 🚨 **Incident management** — typology (cyber / health / mixed), urgency levels, escalation
- 🔔 **Incident subscription** — subscribe to an incident to be notified by email on every status change *(new)*
- 🏥 **Capacity declarations** — per service / functional unit, with tension thresholds
- 📣 **Staff alert chain / recall** — import a directory, target by **site / unit (UF) / pole / name**, multi-channel **SMS + email** recall; each person declares their **ETA** via a link; real-time dashboard with response rate, per-UF gauges, reminders to non-responders and individual reply *(new)*
- 🤝 **Crisis cell** — roster, roles, meeting log
- 📋 **Kanban** — operational task tracking with priorities and assignment
- 🚑 **Patient transfers** — inter-hospital with destination, ETA, OSRM routing
- 🚒 **Porter service** — internal transport vouchers
- 📣 **Public bulletins** — situation page accessible at `/status`
- 💬 **Internal chat & messaging** — real-time channels and DMs
- 🔄 **Shift handover** — formal handover notes between teams
- 📊 **Post-crisis AAR** — automatic generation, decision analysis, lessons learned
- 🗺️ **Territorial supervision** — multi-hospital aggregated dashboard
- 🎓 **Exercise mode** — isolated drill instances with animator console
- 🤖 **AI decision support** — situational analysis via Albert; **now cross-references the competencies arriving (from the staff recall) with open incidents** to support the decision (it *proposes and observes* — the crisis cell decides) *(new)*
- 🌐 **Self-hosted** — no cloud, no telemetry, full sovereignty

### What's new in 3.6.0-beta1

- ✨ **Staff alert chain / personnel recall** — directory import (Excel), multi-criteria **and** by-name targeting, SMS + email dispatch, ETA responses via a tokenized link, real-time dashboard with per-UF gauges, reminders to non-responders, and individual reply by email/SMS
- ✨ **Incident subscription** — email notifications on status changes, to the right people, without flooding everyone
- ✨ **AI decision support** — the assistant crosses the arriving competencies with open incidents (e.g. *"2 technicians within 30 min: wait for their assessment before calling an external provider"*); only **anonymized aggregates** are sent to the AI, never personal identifiers
- ✨ **Scales to large directories** — search-driven targeting and previews built for thousands of staff
- ✨ **UI refresh** aligned with the French State design system (DSFR)
- 🔒 **Data minimization** — staff contact details stay local to the establishment

### Installation

```bash
git clone -b beta https://github.com/nocomp/scribe.git
cd scribe
pip install -r requirements.txt
python3 main.py
```

Open `http://localhost:8000` and follow the wizard at `http://localhost:9000` (master) to create your first instance.

Default credentials are shown on first connection. **Change them immediately.**

### Documentation

- [Security model](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- Installation guide *(coming)*
- Architecture overview *(coming)*

### Why open source?

Hospital crisis management software is too critical to be proprietary. When a CISO, a crisis director, or a clinical manager needs to coordinate a response, they need a tool they can **inspect, modify, and trust**. They need to know what data leaves their walls. They need to be able to fix bugs themselves if a vendor disappears.

SCRIBE is AGPL-3.0 — any modification or hosting must remain open-source. Forks welcome.

### License

[GNU Affero General Public License v3.0](LICENSE)

### Author

Designed and developed by **[Hervé Pellarin](https://www.linkedin.com/in/%D0%BD%D0%BE-%D0%BA%D0%BE%D0%BC%D0%BF/)** — Information Security Officer, healthcare sector.

This is a **personal open-source project**, independent of any employer.

---

## 🇫🇷 Français

SCRIBE est une plateforme open-source de **gestion de crise et de pilotage capacitaire hospitalier**. Elle fournit une main courante numérique complète, un suivi capacitaire en temps réel, un collecteur territorial multi-établissements, une **chaîne d'alerte (rappel du personnel)** et un module d'aide à la décision et de débriefing post-crise alimenté par l'IA.

### Double usage

SCRIBE est conçu pour être utile **aussi bien en mode nominal qu'en crise** :

- **Mode nominal** — suivi quotidien de la capacité des services (lits, RH, matériel), déclarations 3 fois/jour par les cadres, tableau de bord pour la direction des soins et la DRH
- **Mode crise** — main courante incidents, cellule de crise, kanban opérationnel, communiqués publics, rappel du personnel, coordination territoriale

Conçu pour les **non-techniciens** — cadres soignants, directeurs, gestionnaires de crise — SCRIBE ne nécessite aucun cloud, aucun LDAP et fonctionne en réseau isolé.

### 🇪🇺 Conçu pour l'Europe — 24 langues UE

Toutes les langues officielles de l'Union européenne sont sélectionnables dès la mire de connexion, avant authentification.

- **5 traductions UI complètement natives** : FR, EN, DE, ES, IT
- **19 traductions natives essentielles** : les éléments UI les plus utilisés
- **Fallback anglais cohérent** pour le reste

### Architecture

Chaque hôpital fait tourner une **instance SCRIBE isolée** avec sa propre base SQLite. **Aucune donnée patient nominative ne sort de l'établissement** — pas plus que les coordonnées du personnel utilisées pour le rappel. Le collecteur territorial ne reçoit que des indicateurs agrégés (niveaux de capacité, comptages d'incidents) — RGPD-compliant by design.

### Fonctionnalités principales

- 🚨 **Gestion d'incidents** — typologie (cyber / sanitaire / mixte), niveaux d'urgence, escalade
- 🔔 **Abonnement aux incidents** — s'abonner à un incident pour être notifié par e-mail à chaque changement de statut *(nouveau)*
- 🏥 **Déclarations capacitaires** — par service / UF, avec seuils de tension
- 📣 **Chaîne d'alerte / rappel du personnel** — import d'un annuaire, ciblage par **site / pôle / UF / nom**, envoi **multicanal SMS + e-mail** ; chaque personne déclare son **délai d'arrivée** via un lien ; tableau de bord temps réel avec taux de retour, jauges par UF, relance des non-répondants et réponse individuelle *(nouveau)*
- 🤝 **Cellule de crise** — présence, rôles, journal de réunion
- 📋 **Kanban** — suivi opérationnel des tâches avec priorités et assignation
- 🚑 **Transferts patients** — inter-établissements avec destination, ETA, routing OSRM
- 🚒 **Brancardage** — bons de transport intra-hospitaliers
- 📣 **Communiqués publics** — page situation accessible sur `/status`
- 💬 **Chat & messagerie interne** — salons temps réel et messages directs
- 🔄 **Relève de garde** — notes formelles entre équipes
- 📊 **REX post-crise** — génération automatique, analyse des décisions
- 🗺️ **Supervision territoriale** — dashboard agrégé multi-établissements
- 🎓 **Mode Exercice** — instances de simulation isolées avec console animateur
- 🤖 **Aide à la décision par IA** — analyse situationnelle via Albert ; **croise désormais les compétences qui arrivent (issues du rappel du personnel) avec les incidents en cours** pour éclairer la décision (il *propose et observe* — la cellule décide) *(nouveau)*
- 🌐 **Auto-hébergé** — pas de cloud, pas de télémétrie, souveraineté complète

### Nouveautés 3.6.0-beta1

- ✨ **Chaîne d'alerte / rappel du personnel** — import d'annuaire (Excel), ciblage multi-critères **et** par nom, envoi SMS + e-mail, réponses ETA via un lien tokenisé, tableau de bord temps réel avec jauges par UF, relance des non-répondants et réponse individuelle par e-mail/SMS
- ✨ **Abonnement aux incidents** — notifications e-mail sur les changements de statut, à la bonne personne, sans saturer tout le monde
- ✨ **Aide à la décision par IA** — l'assistant croise les compétences qui arrivent avec les incidents ouverts (ex. *« 2 techniciens sous 30 min : attendre leur constat avant d'engager un prestataire »*) ; seuls des **agrégats anonymisés** sont transmis à l'IA, jamais de nominatif
- ✨ **Tient à l'échelle des grands annuaires** — ciblage et aperçu pensés pour des milliers d'agents (recherche)
- ✨ **Refonte UI** alignée sur le système de design de l'État (DSFR)
- 🔒 **Minimisation des données** — les coordonnées du personnel restent locales à l'établissement

### Installation

```bash
git clone -b beta https://github.com/nocomp/scribe.git
cd scribe
pip install -r requirements.txt
python3 main.py
```

Ouvrir `http://localhost:8000` et suivre le wizard sur `http://localhost:9000` (master) pour créer la première instance.

Les identifiants par défaut sont affichés à la première connexion. **Changez-les immédiatement.**

### Licence

agpl v3

### Auteur

Conçu et développé par **[Hervé Pellarin](https://www.linkedin.com/in/%D0%BD%D0%BE-%D0%BA%D0%BE%D0%BC%D0%BF/)** — Responsable de la Sécurité des Systèmes d'Information, secteur santé.

C'est un **projet open-source personnel**, indépendant de tout employeur.

---

<div align="center">

**SCRIBE** · github.com/nocomp/scribe · AGPL-3.0
*Designed by Hervé Pellarin · Built for Europe*

</div>
