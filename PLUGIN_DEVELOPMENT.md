# SCRIBE — Plugin Development Guide

> **🇫🇷 Français** : voir la première moitié de ce document  
> **🇬🇧 English**: scroll down to the second half

---

## 🇫🇷 Guide de développement de plugins SCRIBE

Ce document décrit l'API et la structure à respecter pour développer un plugin SCRIBE qui s'intègre proprement à l'écosystème.

### 📌 Note importante avant de commencer

Je ne fournis pas de support de développement officiel pour les plugins tiers. Ce projet est mené sur mon temps libre. Si vous bloquez sur un point, **ouvrez une issue sur le dépôt GitHub** ([github.com/nocomp/scribe/issues](https://github.com/nocomp/scribe/issues)) en décrivant clairement votre problème, et je ferai au mieux pour vous aider quand mon emploi du temps le permet.

Les contributions, suggestions et retours sont les bienvenus.

---

### 🏗️ Vue d'ensemble

Un plugin SCRIBE est un **dossier autonome** dans `plugins/` qui ajoute :

- Une ou plusieurs routes API (FastAPI)
- Optionnellement, des modèles SQLAlchemy (tables dédiées)
- Optionnellement, une interface utilisateur (HTML/JS injecté ou page autonome)
- Un onglet dans la barre de navigation principale

Les plugins sont **auto-découverts** au démarrage : il suffit d'ajouter un dossier dans `plugins/` avec les bons fichiers, et SCRIBE les chargera automatiquement (sous réserve d'activation côté admin).

### 📁 Structure d'un plugin

Voici la structure type d'un plugin (exemple : un plugin "pharmacie") :

```
plugins/
└── pharmacie/
    ├── __init__.py        ← fichier vide (marqueur de package Python)
    ├── plugin.py          ← MANIFEST + fonction register()  [OBLIGATOIRE]
    ├── routes.py          ← Routes FastAPI (API REST)        [OBLIGATOIRE]
    ├── models.py          ← Modèles SQLAlchemy               [optionnel]
    └── ui.py              ← Interface HTML autonome          [optionnel]
```

Le **seul fichier obligatoire** est `plugin.py`. Les autres dépendent de ce que fait votre plugin.

### 📝 Le manifest (`plugin.py`)

C'est le point d'entrée de votre plugin. Il doit exposer :

1. Un dict `MANIFEST` avec les métadonnées
2. Une fonction `register(app: FastAPI)` qui enregistre les routes

#### Exemple minimal

```python
"""
plugins/pharmacie/plugin.py
Plugin PHARMACIE : suivi des stocks et commandes en mode crise.
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "pharmacie",                      # identifiant unique
    "label":       "PHARMACIE",                      # libellé dans le menu
    "icon":        "💊",                              # icône emoji
    "order":       90,                                # position dans le menu (0-100)
    "description": "Suivi des stocks pharmacie en crise",
    "requires":    [],                                # autres plugins requis
    "api_prefix":  "/api/v1/pharmacie",               # préfixe URL des routes API
    "tab_id":      "tab-pharmacie",                   # ID HTML de l'onglet
    "has_tab":     True,                              # créer un onglet ?
    "legacy":      False,                             # toujours False pour un nouveau plugin
}

def register(app: FastAPI) -> None:
    """Enregistre les routes API + crée les tables SQL si absentes."""
    # Si vous avez des modèles SQLAlchemy
    from plugins.pharmacie.models import Base
    from app.database import engine
    Base.metadata.create_all(bind=engine, checkfirst=True)
    
    # Enregistrement des routes API
    from plugins.pharmacie.routes import router
    app.include_router(router, prefix="/api/v1/pharmacie", tags=["PHARMACIE"])
    
    # Si vous avez une UI autonome
    from plugins.pharmacie.ui import ui_router
    app.include_router(ui_router, prefix="/api/v1/pharmacie", tags=["PHARMACIE UI"])
```

#### Champs du MANIFEST

| Champ | Type | Description |
|---|---|---|
| `id` | `str` | Identifiant unique. **Doit correspondre au nom du dossier**. Caractères : `a-z`, `0-9`, `_` |
| `label` | `str` | Libellé affiché dans le menu (en majuscules par convention) |
| `icon` | `str` | Emoji ou caractère unicode affiché à côté du label |
| `order` | `int` | Position dans le menu (0 = premier, 100 = dernier). Les onglets natifs sont à 10, 20, 30... laissez de la place |
| `description` | `str` | Phrase courte affichée dans l'admin (gestion des plugins) |
| `requires` | `list[str]` | IDs des plugins nécessaires (ex: `["messagerie"]`). Vide si aucun |
| `api_prefix` | `str` | Préfixe URL de toutes vos routes API. Par convention : `/api/v1/<id>` |
| `tab_id` | `str` | ID HTML de l'onglet généré. Par convention : `tab-<id>` |
| `has_tab` | `bool` | `True` pour ajouter un onglet dans le menu principal |
| `legacy` | `bool` | Toujours `False` pour un nouveau plugin |

### 🧭 Ajouter un lien dans la barre de menu (TRÈS IMPORTANT)

C'est le point le plus important pour rendre votre plugin accessible. SCRIBE crée automatiquement un onglet dans la navigation principale **si `has_tab: True` et `tab_id` est défini** dans le MANIFEST.

#### Mécanisme automatique

Au démarrage, le frontend SCRIBE (dans `app/static/js/scribe.js`) :

1. Récupère la liste des plugins actifs via l'endpoint `/api/v1/admin/plugins/active`
2. Pour chaque plugin avec `has_tab: True` qui n'est pas déjà dans le HTML statique :
   - Crée un bouton `<button id="tab-btn-{plugin_id}">` dans la barre de menu
   - Crée un conteneur `<div id="{tab_id}">` dans la zone de contenu
   - Le bouton affiche `{icon} {label}` et inclut un span pour les badges de notification

**Exemple de bouton généré automatiquement :**

```html
<button class="tab-btn" id="tab-btn-pharmacie">
  💊 PHARMACIE
  <span id="plugin-badge-pharmacie" style="display:none">3</span>
</button>
```

#### Que se passe-t-il quand l'utilisateur clique ?

Le frontend appelle `openPluginTab(plugin_id, tab_id, button)` qui :

1. Affiche le conteneur `<div id="{tab_id}">` (les autres onglets sont masqués)
2. Marque le bouton actif
3. Mémorise l'onglet sélectionné dans `localStorage` (`scribe_last_tab`)

#### Comment remplir le contenu de l'onglet ?

Vous avez **deux approches** :

**Approche 1 — UI autonome via iframe (RECOMMANDÉE pour les plugins lourds)**

Servez une page HTML complète depuis votre `ui.py` et chargez-la dans une iframe au moment où l'onglet s'ouvre. C'est l'approche utilisée par les plugins `brancardage`, `messagerie`, `kanban`.

```python
# plugins/pharmacie/ui.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()

PHARMACIE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Pharmacie</title>
  <style>/* votre CSS */</style>
</head>
<body>
  <h1>Pharmacie</h1>
  <!-- votre interface -->
  <script>
    // Récupérer le token JWT depuis le parent (iframe)
    const token = window.parent.localStorage.getItem('scribe_token');
    
    fetch('/api/v1/pharmacie/items', {
      headers: { 'Authorization': 'Bearer ' + token }
    })
    .then(r => r.json())
    .then(data => { /* ... */ });
  </script>
</body>
</html>
"""

@ui_router.get("/ui", response_class=HTMLResponse)
def get_ui():
    return HTMLResponse(PHARMACIE_HTML)
```

Côté frontend, vous devez ajouter un peu de code dans `app/static/js/scribe.js` pour charger l'iframe à l'ouverture de l'onglet (voir patterns existants dans le code des plugins `brancardage` et `kanban`).

**Approche 2 — Contenu HTML injecté directement (pour les plugins simples)**

Ajoutez du contenu HTML directement dans le conteneur `<div id="{tab_id}">` au moment de l'initialisation de votre plugin, depuis `scribe.js`. Plus léger mais moins isolé.

### 🔌 L'API REST

Vos routes FastAPI doivent suivre quelques conventions :

#### Authentification

Toutes les routes (sauf cas particuliers) doivent être authentifiées via le système JWT de SCRIBE :

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.auth import get_current_user

router = APIRouter()

@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(401, "Authentification requise")
    # ... votre logique métier
    return {"items": [...]}
```

#### Codes de retour

Suivez les conventions REST classiques :

- `200 OK` : succès
- `201 Created` : création réussie
- `400 Bad Request` : données invalides
- `401 Unauthorized` : non authentifié
- `403 Forbidden` : authentifié mais sans droits
- `404 Not Found` : ressource absente
- `409 Conflict` : conflit (doublon, état incohérent)

#### Format des erreurs

Utilisez `HTTPException` de FastAPI :

```python
raise HTTPException(status_code=404, detail="Item introuvable")
```

#### Validation des données

Utilisez Pydantic pour les bodies de requête :

```python
from pydantic import BaseModel

class ItemCreate(BaseModel):
    nom: str
    quantite: int
    
@router.post("/items")
def create_item(body: ItemCreate, db: Session = Depends(get_db)):
    # body.nom et body.quantite sont déjà validés
    ...
```

### 💾 Modèles SQLAlchemy

Si votre plugin a besoin de tables dédiées :

```python
# plugins/pharmacie/models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class PharmacieItem(Base):
    __tablename__ = "plugin_pharmacie_items"   # ← préfixe "plugin_<id>_" obligatoire
    
    id        = Column(Integer, primary_key=True, index=True)
    nom       = Column(String(200), nullable=False)
    quantite  = Column(Integer, default=0)
    cree_le   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

**Conventions :**

- **Préfixez vos noms de table par `plugin_<id>_`** (ex: `plugin_pharmacie_items`). Cela évite les conflits avec les tables natives et identifie clairement à quel plugin appartient quoi.
- **Utilisez votre propre `Base`** (créez un `declarative_base()` dans `models.py`). Ne réutilisez pas le `Base` de SCRIBE pour ne pas polluer son schéma.
- **Créez les tables via `register()`** dans `plugin.py` avec `Base.metadata.create_all(bind=engine, checkfirst=True)`.

### 🔔 Notifications et badges

Pour ajouter un badge de notification sur l'onglet de votre plugin (chiffre rouge à côté du label) :

1. Le span du badge est créé automatiquement avec l'ID `plugin-badge-{plugin_id}`
2. Depuis votre code JS (ou un fetch périodique dans `scribe.js`), mettez à jour le contenu du badge :

```javascript
const badge = document.getElementById('plugin-badge-pharmacie');
if (badge) {
    const count = 5;  // votre logique de comptage
    badge.textContent = count;
    badge.style.display = count > 0 ? 'inline' : 'none';
}
```

### 🪵 Loguer dans la main courante

Pour qu'une action de votre plugin apparaisse dans la main courante centrale :

```python
def _log_mc(db: Session, user, action: str, detail: str):
    from app.models import MainCourante
    from datetime import datetime, timezone
    entry = MainCourante(
        horodatage=datetime.now(timezone.utc),
        auteur=getattr(user, 'display_name', None) or getattr(user, 'username', '?'),
        urgence=1,
        type_incident="MIXTE",
        fait=f"💊 PHARMACIE — {action} : {detail}",
        consequence="",
        action="",
        responsable=""
    )
    db.add(entry)
    db.commit()
```

Appelez cette fonction depuis vos routes pour tracer les actions importantes (création, suppression, validation, etc.).

### ✅ Activer / désactiver votre plugin

Une fois votre plugin déployé dans `plugins/`, il est **automatiquement détecté** au prochain démarrage. Cependant, par sécurité, les plugins auto-découverts sont **désactivés par défaut**.

Pour les activer :

1. Connectez-vous en admin
2. Aller dans **Admin → Plugins**
3. Trouvez votre plugin dans la liste et activez-le
4. **Redémarrez SCRIBE** (les plugins ne se chargent qu'au démarrage)

### 🧪 Tester votre plugin

Quelques pistes pour tester :

```bash
# Vérification syntaxique Python
python -m compileall plugins/pharmacie

# Lancer SCRIBE et vérifier les logs
python main.py
# → cherchez "Plugin 'pharmacie' chargé" dans les logs

# Tester votre API
curl -H "Authorization: Bearer <votre_token>" http://localhost:8000/api/v1/pharmacie/items

# Vérifier l'onglet dans l'UI
# → ouvrez http://localhost:8000 dans le navigateur
# → l'onglet PHARMACIE doit apparaître dans la barre principale
```

### 📚 Exemples concrets dans le projet

Étudiez les plugins existants pour vous inspirer :

| Plugin | Complexité | Pattern intéressant |
|---|---|---|
| `brancardage` | Moyenne | UI autonome via iframe, modèles SQL, badges, log main courante |
| `messagerie` | Faible | Routes API simples, pas d'UI dédiée (utilise les onglets natifs) |
| `communique` | Moyenne | Plugin avec page publique `/status` |
| `kanban` | Élevée | Drag & drop, état complexe, intégration profonde |
| `notifications` | Élevée | Web Push, VAPID, service worker |

### 🚫 Ce qu'il NE faut PAS faire

- ❌ Modifier les fichiers du core SCRIBE (sauf bug fix à proposer en pull request)
- ❌ Créer des tables sans préfixe `plugin_<id>_`
- ❌ Stocker des secrets dans le code (utilisez la config admin et la base)
- ❌ Bypasser l'authentification JWT sans raison forte (et documenter alors clairement)
- ❌ Importer des dépendances non listées dans `requirements.txt` sans les ajouter
- ❌ Ouvrir des connexions externes (Internet, autre service) sans option de désactivation

### 📞 Support et contributions

Comme indiqué en début de document, je ne fournis pas de support officiel pour le développement de plugins. Cependant :

- **Question / problème** : ouvrez une issue sur [github.com/nocomp/scribe/issues](https://github.com/nocomp/scribe/issues)
- **Contribution** : ouvrez une pull request, je l'examinerai
- **Plugin réutilisable** : si votre plugin peut profiter à la communauté, n'hésitez pas à proposer son intégration au projet officiel via une PR

Merci de respecter le code de conduite ([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)) lors de vos échanges.

---

---

## 🇬🇧 SCRIBE Plugin Development Guide

This document describes the API and structure to follow when developing a SCRIBE plugin that integrates cleanly into the ecosystem.

### 📌 Important note before starting

I do not provide official development support for third-party plugins. This project is run in my spare time. If you get stuck, **open an issue on the GitHub repository** ([github.com/nocomp/scribe/issues](https://github.com/nocomp/scribe/issues)) clearly describing your problem, and I will do my best to help when my schedule allows.

Contributions, suggestions and feedback are welcome.

---

### 🏗️ Overview

A SCRIBE plugin is a **standalone folder** in `plugins/` that adds:

- One or more API routes (FastAPI)
- Optionally, SQLAlchemy models (dedicated tables)
- Optionally, a user interface (injected HTML/JS or standalone page)
- A tab in the main navigation bar

Plugins are **auto-discovered** at startup: just drop a folder in `plugins/` with the right files, and SCRIBE will load them automatically (subject to admin activation).

### 📁 Plugin structure

Here's the typical structure of a plugin (example: a "pharmacy" plugin):

```
plugins/
└── pharmacy/
    ├── __init__.py        ← empty file (Python package marker)
    ├── plugin.py          ← MANIFEST + register() function     [REQUIRED]
    ├── routes.py          ← FastAPI routes (REST API)          [REQUIRED]
    ├── models.py          ← SQLAlchemy models                  [optional]
    └── ui.py              ← Standalone HTML interface          [optional]
```

The **only required file** is `plugin.py`. Others depend on what your plugin does.

### 📝 The manifest (`plugin.py`)

This is your plugin's entry point. It must expose:

1. A `MANIFEST` dict with metadata
2. A `register(app: FastAPI)` function that registers the routes

#### Minimal example

```python
"""
plugins/pharmacy/plugin.py
PHARMACY Plugin: stock and order tracking during crisis mode.
"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "pharmacy",                       # unique identifier
    "label":       "PHARMACY",                       # menu label
    "icon":        "💊",                              # emoji icon
    "order":       90,                                # menu position (0-100)
    "description": "Pharmacy stock tracking in crisis",
    "requires":    [],                                # other required plugins
    "api_prefix":  "/api/v1/pharmacy",                # API URL prefix
    "tab_id":      "tab-pharmacy",                    # tab HTML ID
    "has_tab":     True,                              # create a tab?
    "legacy":      False,                             # always False for new plugins
}

def register(app: FastAPI) -> None:
    """Register API routes + create SQL tables if missing."""
    # If you have SQLAlchemy models
    from plugins.pharmacy.models import Base
    from app.database import engine
    Base.metadata.create_all(bind=engine, checkfirst=True)
    
    # Register API routes
    from plugins.pharmacy.routes import router
    app.include_router(router, prefix="/api/v1/pharmacy", tags=["PHARMACY"])
    
    # If you have a standalone UI
    from plugins.pharmacy.ui import ui_router
    app.include_router(ui_router, prefix="/api/v1/pharmacy", tags=["PHARMACY UI"])
```

#### MANIFEST fields

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique identifier. **Must match the folder name**. Characters: `a-z`, `0-9`, `_` |
| `label` | `str` | Menu label (uppercase by convention) |
| `icon` | `str` | Emoji or unicode character displayed next to label |
| `order` | `int` | Menu position (0 = first, 100 = last). Native tabs are at 10, 20, 30... leave room |
| `description` | `str` | Short sentence shown in admin (plugin management) |
| `requires` | `list[str]` | IDs of required plugins (e.g. `["messagerie"]`). Empty if none |
| `api_prefix` | `str` | URL prefix for all your API routes. Convention: `/api/v1/<id>` |
| `tab_id` | `str` | HTML ID of generated tab. Convention: `tab-<id>` |
| `has_tab` | `bool` | `True` to add a tab in the main menu |
| `legacy` | `bool` | Always `False` for a new plugin |

### 🧭 Adding a link in the menu bar (VERY IMPORTANT)

This is the most important point to make your plugin accessible. SCRIBE automatically creates a tab in the main navigation **if `has_tab: True` and `tab_id` is defined** in the MANIFEST.

#### Automatic mechanism

At startup, the SCRIBE frontend (in `app/static/js/scribe.js`):

1. Fetches the list of active plugins via `/api/v1/admin/plugins/active`
2. For each plugin with `has_tab: True` not already in static HTML:
   - Creates a `<button id="tab-btn-{plugin_id}">` in the menu bar
   - Creates a `<div id="{tab_id}">` container in the content area
   - The button displays `{icon} {label}` and includes a span for notification badges

**Example of automatically generated button:**

```html
<button class="tab-btn" id="tab-btn-pharmacy">
  💊 PHARMACY
  <span id="plugin-badge-pharmacy" style="display:none">3</span>
</button>
```

#### What happens when the user clicks?

The frontend calls `openPluginTab(plugin_id, tab_id, button)` which:

1. Shows the `<div id="{tab_id}">` container (other tabs are hidden)
2. Marks the button as active
3. Stores the selected tab in `localStorage` (`scribe_last_tab`)

#### How to fill the tab content?

You have **two approaches**:

**Approach 1 — Standalone UI via iframe (RECOMMENDED for heavy plugins)**

Serve a complete HTML page from your `ui.py` and load it in an iframe when the tab opens. This is the approach used by `brancardage`, `messagerie`, `kanban` plugins.

```python
# plugins/pharmacy/ui.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()

PHARMACY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pharmacy</title>
  <style>/* your CSS */</style>
</head>
<body>
  <h1>Pharmacy</h1>
  <!-- your interface -->
  <script>
    // Get JWT token from parent (iframe)
    const token = window.parent.localStorage.getItem('scribe_token');
    
    fetch('/api/v1/pharmacy/items', {
      headers: { 'Authorization': 'Bearer ' + token }
    })
    .then(r => r.json())
    .then(data => { /* ... */ });
  </script>
</body>
</html>
"""

@ui_router.get("/ui", response_class=HTMLResponse)
def get_ui():
    return HTMLResponse(PHARMACY_HTML)
```

On the frontend side, you need to add some code in `app/static/js/scribe.js` to load the iframe when the tab opens (see existing patterns in `brancardage` and `kanban` plugin code).

**Approach 2 — Directly injected HTML content (for simple plugins)**

Add HTML content directly into the `<div id="{tab_id}">` container during your plugin's initialization, from `scribe.js`. Lighter but less isolated.

### 🔌 The REST API

Your FastAPI routes should follow some conventions:

#### Authentication

All routes (except special cases) must be authenticated via SCRIBE's JWT system:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.auth import get_current_user

router = APIRouter()

@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(401, "Authentication required")
    # ... your business logic
    return {"items": [...]}
```

#### Status codes

Follow standard REST conventions:

- `200 OK`: success
- `201 Created`: successful creation
- `400 Bad Request`: invalid data
- `401 Unauthorized`: not authenticated
- `403 Forbidden`: authenticated but without rights
- `404 Not Found`: resource missing
- `409 Conflict`: conflict (duplicate, inconsistent state)

#### Error format

Use FastAPI's `HTTPException`:

```python
raise HTTPException(status_code=404, detail="Item not found")
```

#### Data validation

Use Pydantic for request bodies:

```python
from pydantic import BaseModel

class ItemCreate(BaseModel):
    name: str
    quantity: int
    
@router.post("/items")
def create_item(body: ItemCreate, db: Session = Depends(get_db)):
    # body.name and body.quantity are already validated
    ...
```

### 💾 SQLAlchemy models

If your plugin needs dedicated tables:

```python
# plugins/pharmacy/models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class PharmacyItem(Base):
    __tablename__ = "plugin_pharmacy_items"   # ← "plugin_<id>_" prefix mandatory
    
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(200), nullable=False)
    quantity   = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

**Conventions:**

- **Prefix your table names with `plugin_<id>_`** (e.g. `plugin_pharmacy_items`). This avoids conflicts with native tables and clearly identifies plugin ownership.
- **Use your own `Base`** (create a `declarative_base()` in `models.py`). Don't reuse SCRIBE's `Base` to avoid polluting its schema.
- **Create tables via `register()`** in `plugin.py` with `Base.metadata.create_all(bind=engine, checkfirst=True)`.

### 🔔 Notifications and badges

To add a notification badge on your plugin's tab (red number next to the label):

1. The badge span is automatically created with ID `plugin-badge-{plugin_id}`
2. From your JS code (or a periodic fetch in `scribe.js`), update the badge content:

```javascript
const badge = document.getElementById('plugin-badge-pharmacy');
if (badge) {
    const count = 5;  // your counting logic
    badge.textContent = count;
    badge.style.display = count > 0 ? 'inline' : 'none';
}
```

### 🪵 Logging to the main log

To make a plugin action appear in the central main log:

```python
def _log_mc(db: Session, user, action: str, detail: str):
    from app.models import MainCourante
    from datetime import datetime, timezone
    entry = MainCourante(
        horodatage=datetime.now(timezone.utc),
        auteur=getattr(user, 'display_name', None) or getattr(user, 'username', '?'),
        urgence=1,
        type_incident="MIXTE",
        fait=f"💊 PHARMACY — {action}: {detail}",
        consequence="",
        action="",
        responsable=""
    )
    db.add(entry)
    db.commit()
```

Call this function from your routes to trace important actions (creation, deletion, validation, etc.).

### ✅ Enable / disable your plugin

Once your plugin is deployed in `plugins/`, it is **automatically detected** at next startup. However, for safety, auto-discovered plugins are **disabled by default**.

To enable them:

1. Login as admin
2. Go to **Admin → Plugins**
3. Find your plugin in the list and enable it
4. **Restart SCRIBE** (plugins only load at startup)

### 🧪 Testing your plugin

Some hints for testing:

```bash
# Python syntax check
python -m compileall plugins/pharmacy

# Launch SCRIBE and check logs
python main.py
# → look for "Plugin 'pharmacy' loaded" in the logs

# Test your API
curl -H "Authorization: Bearer <your_token>" http://localhost:8000/api/v1/pharmacy/items

# Check the tab in the UI
# → open http://localhost:8000 in your browser
# → the PHARMACY tab should appear in the main bar
```

### 📚 Concrete examples in the project

Study existing plugins for inspiration:

| Plugin | Complexity | Interesting pattern |
|---|---|---|
| `brancardage` | Medium | Standalone UI via iframe, SQL models, badges, main log entry |
| `messagerie` | Low | Simple API routes, no dedicated UI (uses native tabs) |
| `communique` | Medium | Plugin with public page `/status` |
| `kanban` | High | Drag & drop, complex state, deep integration |
| `notifications` | High | Web Push, VAPID, service worker |

### 🚫 What NOT to do

- ❌ Modify SCRIBE core files (except bug fixes proposed via pull request)
- ❌ Create tables without `plugin_<id>_` prefix
- ❌ Store secrets in code (use admin config and database)
- ❌ Bypass JWT authentication without strong reason (and clearly document if so)
- ❌ Import dependencies not listed in `requirements.txt` without adding them
- ❌ Open external connections (Internet, other service) without an option to disable

### 📞 Support and contributions

As stated at the beginning of this document, I do not provide official support for plugin development. However:

- **Question / problem**: open an issue on [github.com/nocomp/scribe/issues](https://github.com/nocomp/scribe/issues)
- **Contribution**: open a pull request, I will review it
- **Reusable plugin**: if your plugin can benefit the community, feel free to propose its integration into the official project via a PR

Please respect the code of conduct ([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)) in your exchanges.

---

*Document version: 1.0 — corresponds to SCRIBE v2.0.x*
