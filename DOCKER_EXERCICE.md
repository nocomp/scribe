# SCRIBE — Mode Exercice avec Docker

> 🇫🇷 Ce document explique comment lancer le **mode exercice** SCRIBE
> (1 collecteur animateur + 7 instances joueur) avec Docker Compose.
> 🇬🇧 English version below.

---

## 🇫🇷 Mode exercice Docker

### Architecture

Le mode exercice de SCRIBE simule plusieurs établissements de santé en parallèle pour entraîner des cellules de crise multi-sites. Concrètement :

- **1 collecteur animateur** (port 8565) : interface de pilotage de l'animateur, gestion des scénarios, supervision en temps réel
- **6-7 instances joueur** (ports 8660-8666) : SCRIBE classique en mode exercice, données fictives, bandeau rouge "MODE EXERCICE — SIMULATION"

C'est le scénario joué par le collecteur qui injecte les stimuli (incidents, messages, tensions, transferts...) dans les instances joueur, à mesure que le temps simulé avance.

### Lancement rapide

```bash
# 1. Cloner le projet
git clone https://github.com/nocomp/scribe.git
cd scribe

# 2. Lancer le mode exercice
docker compose -f docker-compose.exercice.yml up -d

# 3. Suivre les logs (optionnel)
docker compose -f docker-compose.exercice.yml logs -f
```

Au bout de 30-60 secondes, tous les services sont prêts.

### Connexion

| Service | URL | Identifiants |
|---|---|---|
| **Collecteur animateur** | http://localhost:8565 | `dircrise` / `Exercice2026!` |
| Joueur CH_NORD | http://localhost:8660 | `dircrise` / `Exercice2026!` |
| Joueur CH_SUD | http://localhost:8661 | `dircrise` / `Exercice2026!` |
| Joueur CHU_CENTRE | http://localhost:8662 | `dircrise` / `Exercice2026!` |
| Joueur CH_EST | http://localhost:8663 | `dircrise` / `Exercice2026!` |
| Joueur CH_OUEST | http://localhost:8664 | `dircrise` / `Exercice2026!` |
| Joueur CLINIQUE_DEMO | http://localhost:8665 | `dircrise` / `Exercice2026!` |

### Lancer un exercice

1. Ouvrir le **collecteur animateur** sur http://localhost:8565
2. Onglet **Scénarios** → choisir un scénario (par exemple "DÉMO — Afflux massif victimes")
3. Cliquer **Utiliser**
4. Onglet **Exercice** → **Démarrer en mode auto**
5. Les stimuli sont automatiquement injectés dans les instances joueur selon la timeline du scénario

### Personnalisation

#### Changer les ports

Éditez `docker-compose.exercice.yml` ou créez un fichier `.env` à la racine :

```bash
# .env
SCRIBE_EXO_COLLECTEUR_PORT=18565
```

#### Ajouter un 7ᵉ site

1. Créez `config_exo_ch_nord_2.xml` (s'inspirer des autres `config_exo_*.xml`)
2. Décommentez la section `joueur_ch_nord_2` dans `docker-compose.exercice.yml`
3. Mettez à jour la variable `SCRIBE_EXO_INSTANCES` du service `collecteur_exo` :
   ```
   SCRIBE_EXO_INSTANCES=CH_NORD:8660,CH_SUD:8661,CHU_CENTRE:8662,CH_EST:8663,CH_OUEST:8664,CLINIQUE_DEMO:8665,CH_NORD_2:8666
   ```
4. Relancez : `docker compose -f docker-compose.exercice.yml up -d`

#### Configurer l'IA (Albert ou autre LLM)

Pour activer la génération de scénarios par IA dans le collecteur, créez `.env` :

```bash
# .env
SCRIBE_IA_PROVIDER=albert
SCRIBE_IA_KEY=votre-cle-albert
SCRIBE_IA_URL=https://albert.api.etalab.gouv.fr/v1/chat/completions
SCRIBE_IA_MODEL=albert-large
```

Autres providers supportés : `openai`, `anthropic`, `mistral`, `ollama`, `groq`.

### Reset complet

Pour repartir de zéro (efface toutes les données exercice) :

```bash
docker compose -f docker-compose.exercice.yml down -v
docker compose -f docker-compose.exercice.yml up -d
```

L'option `-v` supprime aussi le volume `scribe_exo_data` (les bases SQLite).

### Arrêt

```bash
# Arrêt propre (conserve les données)
docker compose -f docker-compose.exercice.yml down

# Arrêt + suppression volumes (efface tout)
docker compose -f docker-compose.exercice.yml down -v
```

### Mode prod et mode exercice en parallèle

Vous pouvez lancer les deux en parallèle :

```bash
# Terminal 1 — Production (port 8000)
docker compose up -d

# Terminal 2 — Exercice (ports 8565, 8660-8666)
docker compose -f docker-compose.exercice.yml up -d
```

Les deux n'utilisent pas les mêmes ports ni les mêmes volumes : aucun conflit.

### Pourquoi `network_mode: host` ?

Le collecteur exercice doit pouvoir joindre les instances joueur sur `localhost:866X` (le code Python utilise cette URL pour pousser les stimuli). En `network_mode: host`, tous les services partagent l'interface réseau de l'hôte, ce qui simplifie le routing.

**Limite** : ne fonctionne que sous Linux. Sous macOS/Windows, il faudra adapter la stratégie réseau (réseau Docker dédié + DNS interne par alias service).

### Dépannage

**Le collecteur démarre mais les joueurs ne sont pas visibles**

Attendez 30 secondes après le démarrage : chaque instance joueur fait son init au premier démarrage. Sur la console animateur, cliquez ↻ Actualiser.

**Erreur "address already in use"**

Un autre service utilise les ports 8565 ou 8660-8666. Identifiez le coupable :
```bash
sudo ss -tlnp | grep -E "8565|866[0-6]"
```

**Le scénario s'injecte mais aucun stimulus n'arrive côté joueur**

Vérifiez dans les logs du collecteur :
```bash
docker compose -f docker-compose.exercice.yml logs collecteur_exo | grep -i "token\|inject\|404\|401"
```

Possible : le collecteur n'arrive pas à se logger sur les joueurs (le mot de passe `Exercice2026!` doit correspondre à celui défini dans les configs `config_exo_*.xml`).

**Une instance joueur ne démarre pas**

Vérifier les logs :
```bash
docker compose -f docker-compose.exercice.yml logs joueur_ch_nord
```

Souvent : config XML manquante ou mal formée → ajoutez/corrigez le fichier `config_exo_ch_nord.xml`.

---

## 🇬🇧 Exercise mode (Docker)

### Architecture

SCRIBE exercise mode simulates multiple healthcare facilities in parallel to train multi-site crisis cells:

- **1 animator collector** (port 8565): facilitator dashboard, scenario management, real-time supervision
- **6-7 player instances** (ports 8660-8666): standard SCRIBE in exercise mode, fictitious data, red banner "EXERCISE MODE — SIMULATION"

The scenario played by the collector injects stimuli (incidents, messages, capacity strain, transfers...) into the player instances as simulated time advances.

### Quick start

```bash
git clone https://github.com/nocomp/scribe.git
cd scribe
docker compose -f docker-compose.exercice.yml up -d
docker compose -f docker-compose.exercice.yml logs -f
```

After 30-60 seconds, all services are ready.

### Connect

| Service | URL | Credentials |
|---|---|---|
| **Animator collector** | http://localhost:8565 | `dircrise` / `Exercice2026!` |
| Player CH_NORD | http://localhost:8660 | `dircrise` / `Exercice2026!` |
| Player CH_SUD | http://localhost:8661 | `dircrise` / `Exercice2026!` |
| ... | ports 8662-8665 | same |

### Run an exercise

1. Open animator: http://localhost:8565
2. **Scenarios** tab → pick a scenario → **Use**
3. **Exercise** tab → **Start auto mode**
4. Stimuli are automatically injected into player instances per the scenario timeline

### Customization

See French section above for details on:
- Changing ports
- Adding a 7th site
- Configuring AI (Albert, OpenAI, Anthropic, Mistral, Ollama, Groq)
- Reset / shutdown
- Running prod and exercise in parallel

### Notes

- `network_mode: host` is required so the collector can reach players on `localhost:866X`. Linux only — adapt for macOS/Windows.
- Each instance has its own SQLite DB stored in the `scribe_exo_data` volume.

### Troubleshooting

**Players not visible from collector**: wait 30s after startup, click ↻ Refresh.

**Port already in use**:
```bash
sudo ss -tlnp | grep -E "8565|866[0-6]"
```

**Stimuli sent but not arriving on players**: check collector logs for auth/login errors:
```bash
docker compose -f docker-compose.exercice.yml logs collecteur_exo | grep -i "token\|inject"
```

---

*Document version 1.0 — corresponds to SCRIBE v2.0.2+*
