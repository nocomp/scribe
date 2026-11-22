# Plugin BLUEFILES — Transfert sécurisé HDS

**Version v3.5.0-alpha1 (v1 de développement)**

Plugin SCRIBE qui intègre [Bluefiles](https://bluefiles.com) (Forecomm /
Orange Healthcare) pour les envois sécurisés HDS de fichiers volumineux
depuis SCRIBE vers l'extérieur de l'établissement.

## Cas d'usage v1

Joindre un dossier patient (compte-rendu, IRM, biologie) à un transfert
inter-établissement, avec chiffrement bout-en-bout côté client et
hébergement HDS.

## Modes de fonctionnement

| Mode | Condition | Comportement |
|---|---|---|
| **LIVE** | Variables d'env Bluefiles configurées | Appels réels à l'API Bluefiles |
| **DEV** | Aucune clé configurée | Simulation locale, ZÉRO appel réseau |

Le mode DEV est le mode par défaut. Il permet de tester l'UX du plugin
sans abonnement Bluefiles. Tous les envois sont marqués `delivered`
instantanément et reçoivent un UUID factice `dev-xxxxx`.

## Variables d'environnement (mode LIVE)

```bash
SCRIBE_BLUEFILES_API_URL=https://api.bluefiles.com/v1
SCRIBE_BLUEFILES_API_KEY=<votre_clé_api_bluefiles>
SCRIBE_BLUEFILES_ACCOUNT=<votre_compte_bluefiles>
SCRIBE_BLUEFILES_WEBHOOK_SECRET=<secret_partagé_pour_HMAC>
```

## Architecture

```
plugins/bluefiles/
├── __init__.py
├── plugin.py        ── MANIFEST + register(app)
├── models.py        ── BluefilesEnvoi (table d'audit)
├── client.py        ── wrapper API + mode DEV simulé
├── routes.py        ── endpoints REST /api/v1/bluefiles/...
├── ui.py            ── ui_router (admin health stub)
└── README.md        ── ce fichier
```

## Endpoints

| Verbe | Chemin | Description |
|---|---|---|
| GET | `/api/v1/bluefiles/status` | État du plugin (mode, version) |
| POST | `/api/v1/bluefiles/send` | Envoi multipart sécurisé |
| GET | `/api/v1/bluefiles/envoi/{id}` | Détail d'un envoi |
| GET | `/api/v1/bluefiles/by_ref?module=...&ref_id=...` | Envois liés à un objet métier |
| GET | `/api/v1/bluefiles/history` | Audit paginé |
| POST | `/api/v1/bluefiles/webhook` | Callback Bluefiles (HMAC vérifié) |
| GET | `/api/v1/bluefiles/admin/health` | Stats admin (mode + compteurs) |

## Sécurité

- **Aucun contenu de fichier en DB SCRIBE.** Seules les méta légères (nom,
  taille, MIME, hash SHA-256) sont conservées.
- **Aucun mot de passe destinataire en DB.** Généré et affiché 1× à
  l'expéditeur, jamais persisté.
- **Streaming** : les fichiers transitent en chunks, jamais bufferisés
  sur disque SCRIBE.
- **Hash SHA-256** : permet de prouver "j'ai bien envoyé ce fichier-là"
  sans pouvoir le reconstituer.
- **Webhook HMAC** : signature vérifiée avec `SCRIBE_BLUEFILES_WEBHOOK_SECRET`
  avant traitement.

## Roadmap

| Version | Périmètre |
|---|---|
| **v1 (alpha1)** | Intégration Transferts patients, mode DEV, audit DB |
| v1.1 | Intégration Communiqués (PJ sécurisées) |
| v1.2 | Intégration Cellule de crise (forensique) |
| v1.3 | Intégration REX + page admin HTML |
| v2 | Mode B asymétrique (clé publique destinataire) + détection auto |

## Activation par défaut

Pour cette version de dev (alpha1), le plugin est activé par défaut
dans `config.py` (`PLUGINS["bluefiles"] = True`). Il peut toujours être
désactivé via `/admin/plugins` ou en passant `False` dans le wizard.
