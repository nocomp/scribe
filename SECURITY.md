# Politique de sécurité — SCRIBE

## Versions supportées

Les corrections de sécurité sont appliquées sur la branche `main` (dernière version stable).

## Signaler une vulnérabilité

Si tu découvres une faille de sécurité dans SCRIBE, **merci de ne pas ouvrir d'issue publique**. Contacte directement le mainteneur :

- **Email** : hpellarin @ ch-annecygenevois.fr
- **Sujet** : `[SCRIBE Security] Description courte`

Inclus dans ton message :

- Une description de la vulnérabilité
- Les étapes pour la reproduire
- L'impact potentiel
- Une suggestion de correctif si tu en as une

Engagement de réponse :

- Accusé de réception sous 72h ouvrées
- Évaluation initiale sous 7 jours
- Correctif déployé dans les meilleurs délais selon criticité

## Bonnes pratiques côté déploiement

SCRIBE est un outil sensible (gestion de crise hospitalière). Quelques règles à respecter dans tout déploiement :

### Mots de passe

- Changer immédiatement les mots de passe par défaut (`Scribe2026!`, `Exercice2026!`, `Demo2026!`) après installation
- Imposer une longueur minimale et une rotation régulière
- Activer le MFA TOTP sur les comptes admin et collaborateur

### Réseau

- Déployer SCRIBE sur un **réseau isolé** ou un VLAN dédié à la gestion de crise
- Ne pas exposer SCRIBE directement sur Internet sans reverse proxy avec TLS et authentification renforcée
- Whitelist IP en frontend si l'accès externe est nécessaire

### Données

- Activer un **backup périodique** de la base SQLite (`scribe.db`) et du dossier `uploads/`
- Stocker les backups dans un emplacement sécurisé
- En cas de fin d'exercice, archiver puis purger la base

### Logs

- Conserver les logs FastAPI pour traçabilité
- Ne pas y inclure de mots de passe ou de tokens (le code SCRIBE ne le fait pas, mais vérifie tes intégrations)

### Mode démonstration

- Le mode démo embarque des credentials génériques connus du public. **Ne jamais utiliser le mode démo en production**.
- Les fichiers `*.example` ne doivent jamais être renommés en `.xml` direct sur un serveur productif sans modification

### Clés API

- Les clés API IA (Albert, OpenAI, Anthropic…) doivent être chargées depuis `config.xml` ou des variables d'environnement, jamais hardcodées
- Restreindre les clés API au strict nécessaire (quota, domaine autorisé)

## Architecture de sécurité

SCRIBE applique :

- Authentification **JWT HS256** avec secret dérivé d'un sel local persistant
- Hash mots de passe **bcrypt** (passlib)
- **Rate limiting** sur le login (slowapi)
- **CSP** (Content Security Policy) configurée
- **MFA TOTP** RFC 6238 avec codes de backup à usage unique
- Pas d'envoi de télémétrie, pas de données qui sortent du SI

## Audit

L'audit du code et des configurations est encouragé. Si tu mènes un audit de sécurité sur SCRIBE et trouves quelque chose, contacte-nous selon la procédure ci-dessus.

Merci de contribuer à la sécurité du projet.
