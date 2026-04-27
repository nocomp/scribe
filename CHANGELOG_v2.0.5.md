# SCRIBE v2.0.5 — 27 avril 2026

## 🛠 Hotfix critique : sauvegarde de la clé API IA depuis l'admin

### Le bug

Dans toutes les versions précédentes (v2.0.0 à v2.0.4), il était **impossible
d'enregistrer une clé API IA depuis le panneau d'administration**. Le panneau
ne proposait qu'un bouton "Tester" — aucun bouton "Enregistrer" — et la
documentation affichée demandait de définir des variables d'environnement
côté serveur avant de redémarrer SCRIBE.

Conséquence pour les nouveaux utilisateurs (CHU, RSSI, ESN qui clonent le
repo) : impossible d'activer Albert ou tout autre fournisseur IA sans
toucher au shell du serveur, ce qui rend la démo OVH publique inutilisable
sur l'IA et bloque l'évaluation par les profils non-techniques.

### Le fix

Le panneau **Admin → APIs & IA** propose désormais 3 boutons distincts :

- **🧪 Tester la clé** — valide la connexion au fournisseur sans rien
  enregistrer (comportement de l'ancien bouton "Tester")
- **💾 Enregistrer & activer** — persiste la configuration dans
  `instance/ia_config.json` (permissions `0600`, fichier ignoré par Git)
  et recharge l'IA à chaud, sans redémarrage serveur
- **🗑 Supprimer la config sauvegardée** — supprime le fichier persisté et
  revient aux variables d'environnement (ou aux valeurs par défaut)

Le panneau permet aussi de saisir un **modèle** spécifique (optionnel) et,
pour les fournisseurs locaux (Ollama, OpenAI Compat), une **URL de serveur
local**. Les placeholders sont pré-remplis avec les modèles et URLs par
défaut de chaque fournisseur.

### Détails techniques

**Backend** :
- Nouvelles routes `POST /api/v1/admin/config/ia` et
  `DELETE /api/v1/admin/config/ia` dans `core/admin_plugins.py` (admin only)
- Persistance JSON dans `instance/ia_config.json` (créé à la demande,
  permissions `0600`)
- Fonctions `_load_persisted_ia()` et `save_persisted_ia()` dans `config.py`
- Fix critique dans `app/api/ai_router.py` : `AIConfig.__init__` lit
  désormais `config.IA` en priorité (qui a appliqué le fichier persisté),
  au lieu de relire directement `os.getenv()` à chaque création. Sans ce
  fix, la sauvegarde ne prenait pas effet sans redémarrage.
- Validation : providers cloud (`albert`, `openai`, `anthropic`, `gemini`,
  `mistral`) exigent une clé API ; providers locaux (`ollama`,
  `openai_compat`) acceptent une URL seule.

**Frontend** :
- `app/static/js/scribe.js` : refonte complète de `adminShowIaConfig()`,
  ajout des fonctions `adminTestIaKey()`, `adminSaveIaConfig()`, et
  `adminResetIaConfig()`. L'ancienne fonction `adminSaveIaKey()` est
  conservée comme stub de compatibilité.
- Le panneau expose maintenant clairement la persistance, sans message
  trompeur "(sauvegardée en variable d'env temporaire)".

**Sécurité** :
- Fichier `instance/ia_config.json` ajouté au `.gitignore` pour éviter
  toute fuite accidentelle de clé API en clair.
- Permissions `0600` posées au moment de l'écriture (Linux/macOS).

### Workflow utilisateur

1. **Admin** se connecte, clique sur le bouton ⚙ Administration
2. Choisit la section **APIs & IA** dans le menu latéral
3. Clique sur le fournisseur souhaité (ex : Albert)
4. Saisit sa clé API + un modèle (optionnel) + une URL si fournisseur local
5. **🧪 Tester la clé** pour valider la connexion → message vert
6. **💾 Enregistrer & activer** → la config est persistée et l'IA est
   utilisable immédiatement, sans redémarrer SCRIBE
7. Toutes les fonctions IA (Analyse incident, Situation globale,
   Génération scénario...) sont opérationnelles

### Compatibilité

- **Variables d'environnement** : si `SCRIBE_IA_PROVIDER`, `SCRIBE_IA_KEY`,
  etc. sont définies au lancement, elles servent de valeurs par défaut.
  Le fichier `instance/ia_config.json` (s'il existe) les surcharge.
  Pour revenir aux variables d'env : `🗑 Supprimer la config sauvegardée`.
- **Anciennes installations Docker** : compatibilité totale, le mode
  `docker run -e SCRIBE_IA_KEY=xxx` continue de fonctionner.

### Validation

- 118 fichiers Python validés (ast.parse)
- `node --check` OK sur scribe.js
- 10 tests fonctionnels TestClient :
  - GET initial avec/sans clé
  - POST avec validation provider/cloud-key/local-url
  - DELETE remise à zéro
  - Permissions 0600 du fichier persisté
  - Persistance survit au reload du process
  - Non-admin rejeté en 403
  - Le 400 `ia_not_configured` disparaît bien après save
- Bench `tests/bench/bench.py` : 4/5 OK (échec connu sur
  `04_transfert_federe`, non lié à ce fix)

### Mise à jour

```bash
cd votre-instance-scribe
git pull origin main
# Aucune migration de DB requise
# Aucune modification des configs existantes
# Le fichier instance/ia_config.json sera créé à la première sauvegarde admin
```
