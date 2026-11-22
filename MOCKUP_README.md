# SCRIBE Mockup — Génération de captures d'écran

Ce fichier explique comment peupler SCRIBE avec un scénario de crise complet
pour faire des **captures d'écran de démonstration** (LinkedIn, README, slides).

## Scénario pré-chargé : "Cyber + Bronchiolite"

| Donnée | Quantité |
|---|---|
| Sites hospitaliers | 2 |
| Unités fonctionnelles | 12 (réparties sur 6 pôles) |
| Utilisateurs | 8 (mix admin / directeur / observateur) |
| Incidents en cours | 9 (5 cyber, 3 sanitaire, 1 mixte) |
| Décisions cellule de crise | 8 |
| Présences cellule | 12 acteurs |
| Consignes affichées | 5 |
| Déclarations capacitaires | 12 (mix normal/tension/critique) |
| Services transverses | 8 (DPI HS, messagerie HS, biologie dégradée, etc.) |
| Transferts patients | 4 (1 ARRIVE, 2 EN_COURS, 1 EN_PREPARATION) |
| Messages chat cellule | 12 |
| Mains courantes | 10 |
| REX archivé | 1 |

**Tous les timestamps sont relatifs au moment d'exécution du script** — donc
les captures montrent toujours des horaires "frais" (incidents récents,
ETA dans les minutes à venir, etc.).

## Procédure (5 minutes)

### 1. Lancer SCRIBE normalement

```
LANCER_SCRIBE.bat
```

### 2. Créer une instance via le wizard

- Ouvrir http://localhost:9000
- Login : `supervision` / `changeme`
- Wizard → Mode démo (crée une instance sur le port **8000**)
- **Important** : attendre que l'instance soit bien démarrée et qu'elle ait
  son sigle final (pas `Site_8000`)

### 3. Injecter le scénario mockup

Dans un autre terminal, à la racine du projet :

```
python seed_mockup.py --port 8000
```

Le script résout automatiquement la bonne DB :
- d'abord en lisant `master/master_instances.json` (mapping port → db_path)
- sinon par scan automatique de `data/instances/*/scribe.db`

Tu peux aussi passer le chemin direct si tu préfères :

```
python seed_mockup.py --db data/instances/HDEMO/scribe.db
```

Le script ajoute toutes les données fictives à la DB de l'instance.

### 4. Recharger l'instance dans le navigateur

- Ouvrir http://localhost:8000
- Login : `dircrise` / `changeme`
- → Toutes les vues sont remplies, prêtes pour captures

## Comptes utiles pour les captures

| Login | Mot de passe | Rôle | Usage |
|---|---|---|---|
| `dircrise` | `changeme` | admin | Vue Directeur de Crise — toutes fonctions |
| `admin` | `admin123` | admin | Vue admin pure |
| `m.lefevre` | `demo2026` | admin (RSSI) | Pour les captures côté SI |
| `c.bernard` | `demo2026` | directeur (médecin) | Pour les captures côté médical |

## Réinitialiser

Pour remettre à zéro et recommencer :

```
LANCER_SCRIBE.bat --reset
```

Cela supprime toutes les instances et permet de relancer le scénario propre.

## Captures recommandées (7 essentielles)

1. **Splash wizard** (page bienvenue avec logo SCRIBE)
2. **Wizard étape 2** (sélecteur de fuseau horaire, 16 options)
3. **Supervision territoriale** (le collecteur :9000 avec les sites)
4. **Onglet CAPACITÉ** (grille colorée avec services en tension)
5. **Onglet TRANSFERTS** (kanban + carte Leaflet + 1 transfert EN_COURS)
6. **Onglet CELLULE** (chronologie décisions + présences + consignes)
7. **Fiche transfert avec historique** (modal montrant le suivi)

Bonus mobile : 2-3 captures depuis le téléphone (login + 1 ou 2 vues).
