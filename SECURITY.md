# SCRIBE — Politique de sécurité

## Modèle de menace (threat model)

**SCRIBE est conçu pour fonctionner dans un contexte hospitalier critique :**
- Réseau interne (intranet hospitalier ou VPN sécurisé)
- Air gap possible (déploiement isolé d'Internet)
- Continuité requise même en mode dégradé (panne réseau, cyberattaque)

**Attaquants pris en compte :**
- Acteur externe via Internet (si SCRIBE exposé publiquement)
- Acteur interne malveillant (utilisateur avec compte légitime cherchant à élever ses privilèges)
- Compromission d'un poste utilisateur (vol de token, replay)
- Compromission d'une instance fédérée (le collecteur ne fait pas confiance aveuglément)

**Hors périmètre :**
- Attaques physiques sur le serveur (responsabilité de l'hébergeur)
- Compromission de la chaîne de build Python/pip (responsabilité système)
- Acteurs étatiques avec capacités cryptographiques exotiques

## Données protégées

| Catégorie | Niveau | Stockage |
|---|---|---|
| Identité utilisateurs (login, hash mdp bcrypt) | Confidentiel | DB locale, chmod 600 |
| Données patients nominatives | **Strictement local** | **Jamais envoyées au collecteur** |
| Incidents et main courante | Sensible | DB locale + push agrégé vers collecteur |
| Configuration (token fédération, clés IA) | Confidentiel | Variables d'environnement |
| Clé JWT (SCRIBE_SECRET) | Critique | Env var en prod, sinon `data/.scribe_secret` chmod 600 |

## Mesures de sécurité

### Authentification
- bcrypt pour les mots de passe (avec migration transparente depuis SHA-256 legacy)
- JWT HS256 avec algorithme explicite (immunité CVE-2025-61152 alg=none)
- MFA TOTP optionnel (pyotp + qrcode)
- Rate limiting login (10 tentatives / 60s, lockout 5min par IP)
- TTL JWT 8h par défaut (configurable via `SCRIBE_TOKEN_TTL_HOURS`)

### Autorisation
- RBAC : rôles `admin`, `directeur`, `observateur`
- `require_admin` dependency sur toutes les routes sensibles
- `_check_admin` pattern sur les routes master
- Pas de cookies session → pas de CSRF (Bearer JWT)

### Transport & headers
- HTTPS recommandé (HSTS activé si scheme=https)
- CSP avec `default-src 'self'`, frame-ancestors restreint
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: geolocation=(), camera=(), microphone=()
- CORS restreint, pas de wildcard, `allow_credentials=False`

### Données
- ORM SQLAlchemy (pas de SQL dynamique sur input utilisateur)
- Upload : whitelist MIME + extension + taille max + sanitisation filename
- Path traversal protection (`_safe_filename`)
- ZIP slip protection sur upload plugin

## Variables d'environnement de sécurité

| Variable | Obligatoire en prod | Description |
|---|---|---|
| `SCRIBE_SECRET` | **Oui** | Clé JWT (>= 32 caractères, généré aléatoirement) |
| `SCRIBE_ADMIN_USER` | Non (default: dircrise) | Login admin |
| `SCRIBE_ADMIN_PASS` | **Oui** | Mot de passe admin (>= 12 caractères) |
| `SCRIBE_REQUIRE_ADMIN_PASS` | Recommandé prod | Si `=1`, fail-fast si `SCRIBE_ADMIN_PASS` absent |
| `SCRIBE_TOKEN_TTL_HOURS` | Non (default: 8) | TTL des JWT en heures |
| `SCRIBE_ALLOWED_ORIGINS` | Recommandé prod | Liste CSV des origines CORS autorisées |
| `SCRIBE_FRAME_ANCESTORS` | Recommandé prod | Origines autorisées dans des iframes |
| `SCRIBE_MAX_UPLOAD_MB` | Non (default: 10) | Taille max upload (Mo) |

## Procédure de déploiement sécurisé

```bash
# 1. Générer un secret fort
export SCRIBE_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

# 2. Définir un mot de passe admin fort
export SCRIBE_ADMIN_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

# 3. Forcer le fail-fast
export SCRIBE_REQUIRE_ADMIN_PASS=1

# 4. Restreindre les origines CORS
export SCRIBE_ALLOWED_ORIGINS="https://scribe.mon-hopital.fr"

# 5. Lancer
bash lancer_scribe.sh
```

## Signaler une vulnérabilité

**Email** :  (PGP key disponible sur demande)

Merci de ne pas ouvrir d'issue GitHub publique pour les vulnérabilités de sécurité.
Délai de réponse cible : 72h. Délai de correction : 30 jours pour les critiques.

## Audit pré-ANSSI

Un audit complet pré-ANSSI a été réalisé en mai 2026. Les correctifs C1-C4, E1-E6, M1-M7
identifiés ont été appliqués dans la v2.5.0. Le rapport détaillé est conservé en interne.

**Points résiduels documentés pour audit ANSSI complet** :
- C4 : la CSP contient encore `'unsafe-inline'` sur script-src/style-src. Refactor en
  cours pour passer aux nonces.
- E2 : rate limiting login en mémoire. Migration vers compteur persistant prévue v2.6.
- E3 : fallback SHA-256 sur l'auth (migration legacy). Plan de dépréciation prévu.
