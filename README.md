<p align="center">
  <img src="app/static/logo-scribe.png" alt="SCRIBE" height="80">
</p>

<h1 align="center">SCRIBE</h1>

<p align="center">
  <b>Plateforme open-source de gestion de crise hospitalière & coordination territoriale</b><br>
  <i>Open-source hospital crisis management & territorial coordination platform</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-3.6.0--beta-003189">
  <img src="https://img.shields.io/badge/license-AGPL--3.0-e1000f">
  <img src="https://img.shields.io/badge/i18n-24%20langues-003189">
  <img src="https://img.shields.io/badge/DSFR-conforme-000091">
</p>

<p align="center">
  <a href="#-français">🇫🇷 Français</a> · <a href="#-english">🇬🇧 English</a>
</p>

---

## 🇫🇷 Français

SCRIBE est une plateforme de **main courante de crise** et de **coordination
capacitaire** pour établissements de santé. Elle sert aussi bien au suivi quotidien
des lits qu'à la gestion d'une cellule de crise et à la coordination d'un réseau
territorial d'établissements (supervision fédérée).

Conçue selon le **Système de Design de l'État (DSFR)**, respectueuse des contraintes
**HDS / RGPD** (les données nominatives patients ne quittent jamais l'instance locale),
et disponible en **24 langues**.

### Démarrage rapide

```bash
# Linux / macOS
pip install -r requirements.txt
python3 main.py
# → http://localhost:8000   (démo : dircrise / Scribe2026! — changement forcé à la 1re connexion)

# Docker
docker build -t scribe . && docker run -p 8000:8000 scribe
```

### Fonctionnalités

**Gestion de crise**
- **Main courante / incidents** — niveaux d'urgence 1–4, pôles, types (cyber, sanitaire, mixte), jalons, archivage
- **Cellule de crise** — décisions tracées, registre des présences
- **Kanban** — tâches de crise (colonnes, glisser-déposer)
- **Relève de garde** — passation avec accusé de réception
- **Communiqués** — diffusion interne
- **REX** — retour d'expérience, fiches par incident, tableau de bord
- **Annuaire** — contacts internes
- **Archivage** — export ZIP téléchargeable de la crise

**Capacité & cartographie**
- **Capacité en lits** — référentiel par pôle/site, déclarations, évolution, export CSV, import XLSX
- **Cartographie** (Leaflet + fond CartoDB Light) — sites, unités, statuts de service
- **Transferts inter-établissements** — trajectoire ambulance temps réel (OSRM), progression selon l'ETA

**Communication & logistique**
- **Messagerie interne** unifiée (3 canaux) avec pièces jointes
- **Fichiers** — espace de partage par rôle, répertoire établissement ↔ supervision
- **Chat** temps réel · **Brancardage** · **Lignes** téléphoniques
- **Mobilisation du personnel** — alertes SMS avec relance
- **Répondeur téléphonique** — synthèse vocale, intégration Twilio / OVH

**Intelligence artificielle**
- **7 fournisseurs** supportés, dont **Albert** (LLM souverain de l'État français)
- Analyse d'incident, analyse de crise, situation globale, assistant

**Coordination territoriale (fédération)**
- **Collecteur de supervision** — vue consolidée multi-établissements, niveau = pire(incidents, statut déclaré)
- **Push automatique** vers le collecteur, **transferts** et **messagerie inter-établissements**
- **Statuts publics** (page `/status`)

**Mode exercice**
- Instances isolées (bases dédiées), console animateur, scénarios injectables

**Sécurité** (voir section dédiée)
- Authentification bcrypt + **MFA (TOTP)**, verrouillage API par défaut, uploads authentifiés,
  jeton de fédération, rate-limiting, verrou de compte, **tableau de bord de télémétrie**

**Internationalisation**
- **24 langues** de l'UE (structure JSON), bascule à chaud

**Client mobile**
- Application **Android** native (Kotlin / Jetpack Compose) — dépôt séparé

### Architecture

| Composant | Technologie |
|-----------|-------------|
| Backend | FastAPI (Python) + SQLAlchemy |
| Base de données | SQLite (une par instance) |
| Frontend | Vanilla JS (SPA) + DSFR |
| Cartographie | Leaflet.js + OSRM (routing, sans clé) |
| IA | 7 fournisseurs (dont Albert) |
| Architecture | Cœur + **plugins** (messagerie, fichiers, chat, fédération, exercice, répondeur…) |

### Configuration (`config.xml`)

```xml
<scribe>
  <etablissement><sigle>CHV</sigle><nom>Centre Hospitalier de Valmont</nom></etablissement>
  <federation>
    <collecteur_url>http://localhost:9000/api/push</collecteur_url>
    <token>TOKEN_UNIQUE_ETABLISSEMENT</token>
  </federation>
</scribe>
```

### IA — 7 fournisseurs

Albert (souverain FR) et fournisseurs compatibles OpenAI. La clé se configure via la
variable d'environnement `SCRIBE_IA_KEY` ou l'interface admin — **jamais** commitée.

### Collecteur territorial (supervision)

```bash
cd collecteur && python3 collecteur.py
# → http://localhost:9000
```

Vue consolidée du réseau : chaque établissement pousse son statut ; le collecteur
agrège et affiche le niveau de tension. Aucune donnée patient nominative ne remonte.

### Déploiement multi-établissements

```bash
# 1. Démarrer le collecteur (port 9000)
# 2. Configurer chaque établissement (config.xml, token unique)
# 3. Démarrer chaque instance (ports 8000, 8001, …)
# 4. Accepter chaque établissement depuis le collecteur (⏳ EN ATTENTE → ✓ ACCEPTER)
```

### Sécurité

- **Authentification** bcrypt, **MFA TOTP**, JWT (expiration), changement de mot de passe forcé
- **Anti-bourrage** : rate-limiting par IP **et** verrou par compte
- **Verrouillage API par défaut** : les endpoints de données exigent une session valide
- **Uploads authentifiés** : les pièces jointes ne sont pas servies en statique public (jeton + anti-path-traversal)
- **Fédération** : canal inter-instances protégé par jeton de nœud partagé (`SCRIBE_NODE_TOKEN`)
- **Rate-limiting** des endpoints coûteux (IA) et à effet réel (SMS)
- **En-têtes** de sécurité (CSP, nosniff, Referrer-Policy, Permissions-Policy), CORS restreint, Swagger désactivé
- **Chiffrement des secrets** au repos (Fernet)
- **Télémétrie sécurité** — un middleware d'observation capte les requêtes, classe les
  scanners/bots (chemins de scan, agents connus, sondages 404) et alimente un **tableau
  de bord visuel** (`/api/v1/securite/dashboard`) : indicateurs, top IP suspectes,
  chemins ciblés, timeline, journal d'événements. *Observation seule — ne bloque pas.*
- **HTTPS** recommandé en production (reverse-proxy TLS ou Caddy).

### Conformité réglementaire

- **RGPD** : minimisation, finalités documentées, rétention bornée (journaux/télémétrie), IP = donnée personnelle traitée pour la sécurité du SI
- **HDS** : les données nominatives patients **ne quittent jamais** l'instance locale — seuls des agrégats/statuts remontent au collecteur

---

## 🇬🇧 English

SCRIBE is a **crisis logbook** and **bed-capacity coordination** platform for healthcare
facilities. It serves both daily bed monitoring and full crisis-cell management, and
coordinates a territorial network of facilities (federated supervision).

Built on the **French State Design System (DSFR)**, compliant with **HDS / GDPR**
constraints (patient-identifying data never leaves the local instance), available in
**24 languages**.

### Quick Start

```bash
# Linux / macOS
pip install -r requirements.txt
python3 main.py
# → http://localhost:8000   (demo: dircrise / Scribe2026! — forced change on first login)

# Docker
docker build -t scribe . && docker run -p 8000:8000 scribe
```

### Features

**Crisis management**
- **Crisis logbook / incidents** — urgency levels 1–4, divisions, types (cyber, health, mixed), milestones, archiving
- **Crisis cell** — logged decisions, attendance register
- **Kanban** — crisis tasks (columns, drag & drop)
- **Shift handover** — with acknowledgement
- **Bulletins** — internal broadcast
- **After-action review (REX)** — per-incident sheets, dashboard
- **Directory** — internal contacts
- **Archiving** — downloadable crisis ZIP export

**Capacity & mapping**
- **Bed capacity** — reference by division/site, declarations, trend, CSV export, XLSX import
- **Mapping** (Leaflet + CartoDB Light) — sites, units, service statuses
- **Inter-facility transfers** — real-time ambulance route (OSRM), ETA-based progress

**Communication & logistics**
- **Unified internal messaging** (3 channels) with attachments
- **Files** — role-based sharing space, facility ↔ supervision directory
- **Real-time chat** · **Porter dispatch** · **Phone lines**
- **Staff recall** — SMS alerts with follow-up
- **Phone answering** — text-to-speech, Twilio / OVH integration

**Artificial intelligence**
- **7 supported providers**, including **Albert** (French sovereign LLM)
- Incident analysis, crisis analysis, global situation, assistant

**Territorial coordination (federation)**
- **Supervision collector** — consolidated multi-facility view, level = worst(incidents, declared status)
- **Automatic push** to the collector, **transfers** and **inter-facility messaging**
- **Public statuses** (`/status` page)

**Exercise mode**
- Isolated instances (dedicated databases), facilitator console, injectable scenarios

**Security** (see dedicated section)
- bcrypt auth + **MFA (TOTP)**, deny-by-default API, authenticated uploads,
  federation token, rate-limiting, account lockout, **telemetry dashboard**

**Internationalization**
- **24 EU languages** (JSON structure), hot switching

**Mobile client**
- Native **Android** app (Kotlin / Jetpack Compose) — separate repository

### Architecture

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python) + SQLAlchemy |
| Database | SQLite (one per instance) |
| Frontend | Vanilla JS (SPA) + DSFR |
| Mapping | Leaflet.js + OSRM (keyless routing) |
| AI | 7 providers (incl. Albert) |
| Architecture | Core + **plugins** (messaging, files, chat, federation, exercise, answering…) |

### Configuration (`config.xml`)

```xml
<scribe>
  <etablissement><sigle>CHV</sigle><nom>Valmont Hospital Center</nom></etablissement>
  <federation>
    <collecteur_url>http://localhost:9000/api/push</collecteur_url>
    <token>UNIQUE_FACILITY_TOKEN</token>
  </federation>
</scribe>
```

### AI — 7 providers

Albert (FR sovereign) plus OpenAI-compatible providers. The key is set via the
`SCRIBE_IA_KEY` environment variable or the admin UI — **never** committed.

### Territorial collector (supervision)

```bash
cd collecteur && python3 collecteur.py
# → http://localhost:9000
```

Consolidated network view: each facility pushes its status; the collector aggregates and
displays the tension level. No patient-identifying data is sent upstream.

### Multi-facility deployment

```bash
# 1. Start the collector (port 9000)
# 2. Configure each facility (config.xml, unique token)
# 3. Start each instance (ports 8000, 8001, …)
# 4. Accept each facility from the collector (⏳ PENDING → ✓ ACCEPT)
```

### Security

- **Authentication** bcrypt, **MFA TOTP**, JWT (expiry), forced password change
- **Anti-brute-force**: per-IP rate limiting **and** per-account lockout
- **Deny-by-default API**: data endpoints require a valid session
- **Authenticated uploads**: attachments are not served as public static files (token + path-traversal protection)
- **Federation**: inter-instance channel protected by a shared node token (`SCRIBE_NODE_TOKEN`)
- **Rate limiting** on costly (AI) and real-effect (SMS) endpoints
- **Security headers** (CSP, nosniff, Referrer-Policy, Permissions-Policy), restricted CORS, Swagger disabled
- **Secret encryption** at rest (Fernet)
- **Security telemetry** — an observation middleware captures requests, classifies
  scanners/bots (scan paths, known agents, 404 sweeps) and feeds a **visual dashboard**
  (`/api/v1/securite/dashboard`): indicators, top suspicious IPs, targeted paths,
  timeline, event log. *Observation only — does not block.*
- **HTTPS** recommended in production (TLS reverse-proxy or Caddy).

### Regulatory Compliance

- **GDPR**: minimization, documented purposes, bounded retention (logs/telemetry), IP = personal data processed for information-system security
- **HDS**: patient-identifying data **never leaves** the local instance — only aggregates/statuses are sent to the collector

---

## Changelog

### v3.6.0-beta — Security hardening & telemetry (July 2026)
- Security telemetry middleware + visual dashboard (observe-only)
- Deny-by-default lockdown of all data endpoints
- Authenticated `/uploads`, federation node token, admin-only `/debug`
- Per-account lockout, rate limiting on AI & SMS flows
- Random per-account import passwords, plugin-upload zip-slip hardening
- Dependency upper bounds

### v3.6.0-beta (June 2026)
- Federation, transfers, unified messaging, file sharing, phone answering, 24 languages

### v1.5.0-beta (March 2026)
- Bed capacity, mapping, OSRM transfers

## Contributors

Open to contributions — issues and pull requests welcome.

## License

Distributed under the **GNU Affero General Public License v3.0** (AGPL-3.0).
See [`LICENSE`](LICENSE).
