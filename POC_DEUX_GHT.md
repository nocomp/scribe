# POC deux GHT — SCRIBE v1.4.0

## Principe

Chaque instance SCRIBE est autonome :
- Sa propre base SQLite (`scribe_chag.db` / `scribe_ght2.db`)
- Son propre dossier d'uploads
- Son propre port (8000 / 8001)
- Sa propre config.xml

Un seul dossier scribe, deux launchers BAT.

## Architecture cible

```
Poste Windows
├── Instance 1 — CHV       → http://localhost:8000   (scribe_chag.db)
├── Instance 2 — GHT2 demo  → http://localhost:8001   (scribe_ght2.db)
└── Collecteur Ubuntu 192.168.1.109 → http://192.168.1.109:9000
```

---

## Étape 1 — Préparer le dossier

Décompresser le ZIP. Dans le dossier racine, placer :

```
scribe_v140_clean/
├── config_chag.xml      ← VOTRE FICHIER (renommé config_chag.xml)
├── uf.xlsx              ← VOTRE EXPORT FICOM (optionnel)
├── config_demo2.xml     ← fourni dans le ZIP (GHT2 fictif)
├── LANCER_CHAG.bat      ← fourni
├── LANCER_GHT2_DEMO.bat ← fourni
└── ... (autres fichiers)
```

> Renommez simplement votre fichier de config CHV en `config_chag.xml`
> et placez-le à la racine du dossier.

---

## Étape 2 — Lancer l'instance CHV (port 8000)

Double-clic sur **LANCER_CHAG.bat**

À la première exécution, le script :
1. Copie `config_chag.xml` → `config.xml`
2. Initialise `scribe_chag.db` avec vos sites et directeurs
3. Importe vos UF depuis `uf.xlsx` (si présent)
4. Charge le référentiel capacitaire CHV (58 unités)
5. Démarre sur http://localhost:8000

Login : `dircrise` + mot de passe de votre `config_chag.xml`

---

## Étape 3 — Lancer l'instance GHT2 (port 8001)

Ouvrir **une deuxième fenêtre PowerShell** et double-clic sur **LANCER_GHT2_DEMO.bat**

À la première exécution :
1. Initialise `scribe_ght2.db` avec les données CSBM Montrelay (fictives)
2. Charge le référentiel capacitaire démo
3. Injecte le scénario de crise ransomware 48h
4. Démarre sur http://localhost:8001

Login : `dircrise` / `Scribe2026!`

---

## Étape 4 — Connecter les deux instances au collecteur

### Sur le collecteur Ubuntu (192.168.1.109)

Si le collecteur ne tourne pas encore :
```bash
cd ~/tools/scribe
python3 collecteur.py &
```

Notez le **token admin** affiché au démarrage.

### Enregistrer l'instance CHV

Dans `config_chag.xml`, activer la fédération :
```xml
<federation>
  <enabled>true</enabled>
  <collecteur_url>http://192.168.1.109:9000/api/push</collecteur_url>
  <token>token_chag_2026</token>    <!-- choisissez librement -->
  <sync_crise>true</sync_crise>
  <sync_sanitaire>true</sync_sanitaire>
</federation>
```

Puis enregistrer côté collecteur :
```bash
curl -X POST http://localhost:9000/api/admin/tokens \
  -H "Authorization: Bearer TOKEN_ADMIN_COLLECTEUR" \
  -H "Content-Type: application/json" \
  -d '{"sigle":"CHV","token":"token_chag_2026"}'
```

### Enregistrer l'instance GHT2

Dans `config_demo2.xml`, activer la fédération :
```xml
<federation>
  <enabled>true</enabled>
  <collecteur_url>http://192.168.1.109:9000/api/push</collecteur_url>
  <token>token_ght2_2026</token>    <!-- token DIFFÉRENT du CHV -->
  <sync_crise>true</sync_crise>
  <sync_sanitaire>true</sync_sanitaire>
</federation>
```

Puis enregistrer :
```bash
curl -X POST http://localhost:9000/api/admin/tokens \
  -H "Authorization: Bearer TOKEN_ADMIN_COLLECTEUR" \
  -H "Content-Type: application/json" \
  -d '{"sigle":"CSBM","token":"token_ght2_2026"}'
```

Relancer les deux instances BAT après modification des XML.

---

## Repartir à zéro

Pour réinitialiser une instance :
```powershell
del scribe_chag.db   # ou scribe_ght2.db
```
Puis relancer le BAT correspondant.

---

## Résumé des commandes

| Action | Commande |
|--------|---------|
| Lancer CHV | Double-clic `LANCER_CHAG.bat` |
| Lancer GHT2 | Double-clic `LANCER_GHT2_DEMO.bat` |
| Reset CHV | `del scribe_chag.db` puis relancer |
| Reset GHT2 | `del scribe_ght2.db` puis relancer |
| Voir les tokens collecteur | `cat ~/tools/scribe/collecteur_tokens.json` |
