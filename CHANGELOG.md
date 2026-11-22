# Changelog — SCRIBE

Toutes les évolutions notables de SCRIBE sont consignées ici. /
All notable changes to SCRIBE are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/).

[🇫🇷 Français](#-français) · [🇬🇧 English](#-english)

---

## 🇫🇷 Français

### [3.6.1-beta] — 2026-11-22

#### 🔒 Sécurité — correctif critique (signalé par [@kemrec](https://github.com/kemrec))

- **Le collecteur n'expose plus son token admin maître** (`collecteur/collecteur.py`)
  - `GET /` servait la page de supervision **sans authentification** en y injectant
    le vrai `ADMIN_TOKEN` (dans une variable JS, l'iframe messagerie et un en-tête).
    Un visiteur anonyme récupérait donc le token maître (`curl / | grep ADMIN_TOKEN`)
    et obtenait un contrôle admin complet (enrôler de faux établissements, révoquer
    des hôpitaux réels…). Cela **réouvrait aussi** les lectures agrégées corrigées en
    3.6.0 (puisque `require_any_auth` accepte le token maître).
  - Correctif : le token maître **n'est plus jamais injecté** dans la page. L'UI
    s'authentifie via le login (`/api/ui/login`) et utilise une **session de rôle**
    (`ui_sessions`, stockée en `coll_session`) pour tous ses appels, y compris
    l'iframe messagerie.
  - `require_admin` (collecteur) et `_check_admin` (routes `/api/master`) acceptent
    désormais une **session UI de rôle admin** en plus du token maître — lequel reste
    valable uniquement en server-to-server. Les sessions **viewer** sont refusées sur
    les actions admin.

---

### [3.6.0-beta] — 2026-11-22

#### 🔒 Sécurité — correctifs signalés par audit externe

Trois vulnérabilités de divulgation d'informations ont été corrigées à la suite
d'un audit indépendant mené par **[@kemrec](https://github.com/kemrec)**
(voir **Remerciements**).

- **Le token de fédération ne fuit plus** (`plugins/federation/api.py`)
  - `GET /api/v1/federation/status` ne renvoie plus le token en clair ; seul un
    aperçu non exploitable (`token_preview`) est exposé. Ce token est le credential
    `Bearer` utilisé par l'établissement pour pousser vers le collecteur : son
    exposition permettait d'usurper l'établissement auprès de la supervision.
  - `GET /api/v1/federation/info` est désormais **réservé à l'administrateur**
    (`require_admin`) et ne renvoie plus de champ `token` brut.
- **Supervision — lectures agrégées multi-établissements authentifiées**
  (`collecteur/collecteur.py`)
  - Nouvelle dépendance `require_any_auth` : bloque l'accès **anonyme** tout en
    acceptant le token admin, une session UI de supervision, ou le token de
    fédération d'une instance enrôlée.
  - Appliquée à `GET /api/summary`, `/api/etablissement/{sigle}`, `/api/capacite`,
    `/api/status/{sigle}`, `/api/annuaire`. Ces routes exposaient auparavant les
    données de tous les établissements connectés (niveau de crise, KPIs, sites
    géolocalisés, incidents, capacité) sans authentification.
  - Appelants légitimes mis en conformité (instance : carte inter-GHT ; UI du
    collecteur).

#### ✨ Fonctionnalités & corrections

- **Slots d'établissements configurables** — limite portée de 10 à **50 par
  déploiement**, ajustable via `SCRIBE_MAX_SLOTS` (défaut 50).
- **Wizard d'onboarding — fin du blocage** (issue #12) — sortie explicite vers la
  gestion des instances quand il n'y a plus de slot libre, + lien de sortie
  permanent. Fini le piège sans échappatoire.

#### 🔭 Télémétrie sécurité (observation)

- Middleware d'observation + **tableau de bord** (`/api/v1/securite/dashboard`) :
  classification des scanners/bots, top IP suspectes, chemins ciblés, timeline.
  *Observation seule — ne bloque pas.* Résolution correcte de l'IP derrière proxy
  (`SCRIBE_TRUSTED_PROXIES`).

#### 🌐 Déploiement

- **HTTPS multi-ports via Caddy** — Uvicorn en loopback (`SCRIBE_BIND=127.0.0.1`,
  `SCRIBE_PROXY=1`), Caddy termine le TLS sur l'IP publique du même port. Le
  collecteur honore `COLLECTEUR_BIND` / `COLLECTEUR_PROXY`.

#### 🛡️ Durcissement (même cycle)

- Deny-by-default sur les endpoints de données ; `/uploads` authentifié ; jeton de
  nœud de fédération ; rate-limiting (IA, SMS) + verrou de compte ; `/debug`
  réservé admin ; mots de passe d'import aléatoires par compte.

---

## 🇬🇧 English

### [3.6.1-beta] — 2026-11-22

#### 🔒 Security — critical fix (reported by [@kemrec](https://github.com/kemrec))

- **The collector no longer exposes its master admin token** (`collecteur/collecteur.py`)
  - `GET /` served the supervision page **without authentication** while injecting the
    real `ADMIN_TOKEN` into it (a JS variable, the messagerie iframe, and a header). An
    anonymous visitor could therefore recover the master token
    (`curl / | grep ADMIN_TOKEN`) and gain full admin control (enroll rogue
    establishments, revoke real hospitals…). It **also re-opened** the aggregate reads
    fixed in 3.6.0 (since `require_any_auth` accepts the master token).
  - Fix: the master token is **never injected** into the page. The UI authenticates via
    login (`/api/ui/login`) and uses a **role-scoped session** (`ui_sessions`, stored as
    `coll_session`) for all calls, including the messagerie iframe.
  - `require_admin` (collector) and `_check_admin` (`/api/master` routes) now accept a
    **role-admin UI session** in addition to the master token — which remains valid for
    server-to-server only. **Viewer** sessions are rejected on admin actions.

---

### [3.6.0-beta] — 2026-11-22

#### 🔒 Security — fixes reported by external audit

Three information-disclosure vulnerabilities were fixed following an independent
audit by **[@kemrec](https://github.com/kemrec)** (see **Credits**).

- **Federation token no longer leaks** (`plugins/federation/api.py`)
  - `GET /api/v1/federation/status` no longer returns the token in clear text; only
    a non-exploitable preview (`token_preview`) is exposed. This token is the
    `Bearer` credential a hospital uses to push to the collector — leaking it let an
    attacker impersonate the hospital to the supervision node.
  - `GET /api/v1/federation/info` is now **admin-only** (`require_admin`) and no
    longer returns a raw `token` field.
- **Supervision — authenticated multi-hospital aggregate reads**
  (`collecteur/collecteur.py`)
  - New `require_any_auth` dependency: blocks **anonymous** access while accepting
    the admin token, a supervision UI session, or an enrolled instance's federation
    token.
  - Applied to `GET /api/summary`, `/api/etablissement/{sigle}`, `/api/capacite`,
    `/api/status/{sigle}`, `/api/annuaire`. These routes previously exposed every
    connected hospital's data (crisis level, KPIs, geolocated sites, incidents,
    capacity) with no authentication.
  - Legitimate callers brought into compliance (instance inter-GHT map; collector UI).

#### ✨ Features & fixes

- **Configurable establishment slots** — limit raised from 10 to **50 per
  deployment**, tunable via `SCRIBE_MAX_SLOTS` (default 50).
- **Onboarding wizard — no more dead-end** (issue #12) — explicit exit to instance
  management when no slot is free, plus a permanent exit link. No more being trapped.

#### 🔭 Security telemetry (observe-only)

- Observation middleware + **dashboard** (`/api/v1/securite/dashboard`):
  scanner/bot classification, top suspicious IPs, targeted paths, timeline.
  *Observe-only — does not block.* Correct client-IP resolution behind a proxy
  (`SCRIBE_TRUSTED_PROXIES`).

#### 🌐 Deployment

- **Multi-port HTTPS via Caddy** — Uvicorn on loopback (`SCRIBE_BIND=127.0.0.1`,
  `SCRIBE_PROXY=1`), Caddy terminates TLS on the public IP of the same port. The
  collector honors `COLLECTEUR_BIND` / `COLLECTEUR_PROXY`.

#### 🛡️ Hardening (same cycle)

- Deny-by-default on data endpoints; authenticated `/uploads`; federation node
  token; rate-limiting (AI, SMS) + account lockout; admin-only `/debug`; random
  per-account import passwords.

---

## Remerciements / Credits

🇫🇷 Un grand merci à **[@kemrec](https://github.com/kemrec)** pour son audit de
SCRIBE et le signalement responsable de plusieurs vulnérabilités de divulgation
d'informations : la fuite du token de fédération via `/federation/status` et
`/info` et l'accès anonyme aux lectures agrégées du collecteur (corrigées en
3.6.0), puis — après re-test — l'**exposition du token admin maître sur la page
d'accueil du collecteur** (corrigée en 3.6.1), la plus grave car elle redonnait un
contrôle admin complet. Ses rapports précis, accompagnés de preuves de concept
reproductibles et de correctifs suggérés, ont permis des remédiations rapides et
ciblées. Ce type de signalement rigoureux est précieux pour un outil de gestion de
crise hospitalière, où la confidentialité des données inter-établissements est
critique. Merci. 🙏

🇬🇧 Many thanks to **[@kemrec](https://github.com/kemrec)** for auditing SCRIBE and
responsibly reporting several information-disclosure vulnerabilities: the
federation-token leak via `/federation/status` and `/info` and anonymous access to
the collector's aggregate reads (fixed in 3.6.0), then — after re-testing — the
**exposure of the master admin token on the collector's home page** (fixed in
3.6.1), the most serious as it restored full admin control. The reports were
precise, with reproducible proofs of concept and suggested fixes, enabling fast,
targeted remediations. This kind of rigorous disclosure is invaluable for a
hospital crisis-management tool, where the confidentiality of cross-hospital data
is critical. Thank you. 🙏

---

## Versions antérieures / Earlier versions

### [1.5.0-beta] — 2026-03
- Capacité en lits, cartographie, transferts OSRM. /
  Bed capacity, mapping, OSRM transfers.
