# Contribuer à SCRIBE

Merci de l'intérêt que tu portes à SCRIBE. Le projet est porté par et pour les équipes de sécurité des SI hospitaliers, et toute contribution est la bienvenue.

## Comment contribuer

### Signaler un bug

Ouvre une [issue](https://github.com/nocomp/scribe/issues) en décrivant :

- Ce qui était attendu
- Ce qui s'est passé à la place
- Étapes pour reproduire
- Version de SCRIBE et environnement (Python, OS)
- Logs pertinents si possible (sans données sensibles)

### Proposer une amélioration

Ouvre une issue avec le label `enhancement` pour discuter avant de coder. Cela évite les efforts perdus si l'idée ne s'aligne pas avec la direction du projet.

### Soumettre du code

1. Fork le dépôt
2. Crée une branche depuis `main` : `git checkout -b ma-fonctionnalite`
3. Commit avec des messages descriptifs en français ou en anglais
4. Push et ouvre une *pull request* vers `main`

## Conventions

### Style de commit

Format préféré : `type(scope): description courte`

Types : `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Exemples :

```
feat(mfa): ajout codes de backup régénérables
fix(capacite): match souple service_nom + uf_code
docs(readme): section Vue mobile
```

### Code Python

- Suivre PEP 8 (longueur de ligne tolérée jusqu'à 100 caractères)
- Docstrings en français pour les fonctions métier
- Type hints recommandés sur les nouvelles fonctions
- Pas de modification globale sans discussion préalable

### Code JavaScript

- Style cohérent avec l'existant (pas de framework JS lourd, pas de bundler)
- Eviter les dépendances externes nouvelles
- Commentaires en français pour les blocs métier

### Tests

Si tu ajoutes une fonctionnalité importante :

- Vérifie que `python -m pytest tests/` passe (si existant)
- Lance `python tests/bench/bench.py` pour vérifier les scénarios
- Ajoute des tests pour les nouveaux endpoints critiques

## Que NE PAS pousser sur GitHub

Le `.gitignore` bloque déjà la plupart des cas. Vérifie quand même que tu ne pousses jamais :

- Tokens API (Albert, OpenAI, Anthropic, Mistral…)
- Mots de passe ou hash en clair
- Configurations spécifiques à ton établissement (`config_chag.xml`, etc.)
- Bases SQLite contenant des données réelles
- Adresses IP / hostnames de production
- Logs avec données nominatives

En cas de doute, ne pousse pas. Demande-nous d'abord.

## Architecture du projet

```
scribe/
├── app/
│   ├── api/          ← Endpoints FastAPI principaux (auth, sitrep, capacité…)
│   ├── static/       ← Frontend SPA + vue mobile
│   ├── lang/         ← Fichiers de traduction (fr.json, en.json…)
│   ├── models.py     ← Modèles SQLAlchemy
│   └── database.py
├── plugins/
│   ├── brancardage/  ← Plugin gestion brancardage
│   ├── messagerie/   ← Plugin messagerie interne
│   ├── communique/   ← Plugin statut public
│   └── ...
├── core/             ← Système de plugins
├── collecteur/       ← Collecteur territorial (multi-établissements)
├── collecteur_exercice/  ← Collecteur exercice avec animateur
├── tests/            ← Tests + bench scénarios
└── scenarios/        ← Scénarios d'exercice JSON
```

## Ajouter un plugin

Un plugin SCRIBE est un dossier dans `plugins/` avec :

```
plugins/mon_plugin/
├── __init__.py
├── plugin.py     # MANIFEST + register
├── api.py        # Routes FastAPI
├── models.py     # Modèles SQLAlchemy
└── ui.py         # Snippets HTML/JS injectés
```

Voir les plugins existants (`brancardage`, `messagerie`) comme référence.

## Multi-langue

Pour ajouter une traduction d'une nouvelle clé :

1. Ajoute la clé dans `app/lang/fr.json` (référence)
2. Ajoute la traduction dans les autres fichiers `app/lang/*.json`
3. Dans le HTML : `<span data-i18n-label="ma.cle">Texte par défaut</span>`

Pour ajouter une nouvelle langue, copie `fr.json` et adapte. Le sélecteur admin la détecte automatiquement.

## Communication

- Issues GitHub pour bugs / propositions
- Pull requests pour code
- Pour les questions d'architecture ou les chantiers structurants : ouvre une issue `discussion` avant de coder

Merci !
