# Changelog — v3.0.0-alpha10 (build interne `v3000h3`)

**Date** : 30 mai 2026
**Base** : v3000h2
**Statut** : build privé interne — gestion des ports occupés.

---

## Libération prudente des ports SCRIBE (Linux + Windows)

Fini les `[Errno 10048]` / `[Errno 98]` "Address already in use" qui plantent
le démarrage des instances quand un process orphelin traîne sur un port.

### Stratégie validée (par décisions Hervé)

- **Prudente** : ne tue QUE les process clairement identifiables comme SCRIBE
  (ligne de commande contient `main.py`, `collecteur*.py`, `scribe`).
  Tout autre process est laissé intact et signalé à l'utilisateur — il décide.
- **Double vérification** : au lancement du master ET au lancement de chaque
  instance.
- **Ports protégés** : 9000 (master), 8000-8009 (instances master), 8565
  (collecteur exercice), 8660-8669 (instances exercice), 7474 (démo permanente),
  7373 (collecteur démo). Total : 24 ports.

### Nouveau module — `master/port_cleanup.py`

Module cross-platform autonome (~310 LOC) :

**Détection** (`is_port_in_use`) : bind socket localhost, fonctionne partout.

**Identification du process écoutant** (`identify_port_holder`) :
- **Linux** : `lsof -iTCP:PORT -sTCP:LISTEN -t` → PID → `/proc/<pid>/cmdline`
- **Linux fallback** : `ss -tlnpH` si `lsof` absent
- **Windows** : `netstat -ano -p TCP` → PID → `wmic process where ProcessId=...`
- **Windows fallback** : PowerShell `Get-CimInstance Win32_Process` puis `tasklist`

**Identification SCRIBE** (`_looks_like_scribe`) : la ligne de commande doit
contenir au moins un hint métier (`scribe`, `main.py`, `collecteur_exercice.py`,
`collecteur.py`). `uvicorn` seul ne suffit pas (faux positif possible).

**Terminaison** (`_terminate_pid`) :
- Linux : `SIGTERM` puis `SIGKILL` après 3 s d'attente
- Windows : `taskkill /PID` (gracieux) puis `taskkill /F /PID` (force)

**API publique** :
- `free_port_if_scribe(port)` → dict `{status, pid, detail, ...}` avec
  status ∈ `{free, freed, failed_kill, foreign, unidentified}`
- `free_all_scribe_ports()` → balaie tous les 24 ports
- `summarize_results(results)` → texte court pour les logs

### Intégrations

**1. Démarrage du master** (`main.py`, `if __name__ == "__main__"`)
- Libère systématiquement le port master (`SCRIBE_PORT` ou 8000)
- Si variable d'env `SCRIBE_PORT_CLEANUP_ALL=1` : grand ménage des 24 ports
- Non bloquant : un échec du cleanup ne bloque pas le démarrage (uvicorn
  tentera ensuite et lèvera son erreur claire si vraiment occupé)

**2. Démarrage des instances exercice** (`exercice_manager.py`)
- `start_collecteur()` libère 8565
- `start(port)` libère le port instance (8660-8669) avant `subprocess.Popen`
- Process tiers détecté → `ValueError` avec PID pour info utilisateur
- Process SCRIBE non terminable → `ValueError` explicite

**3. Démarrage des instances master classiques** (`instances_manager.py`)
- Idem `start(port)` (8000-8009)

**4. Bouton "🔓 Libérer ports"** dans la barre d'actions de l'UI master
   instances (`instances.html`) — clic → libère les 24 ports + rapport :
   - Liste des PID terminés
   - Liste des process tiers détectés (NON tués, à arrêter manuellement)
   - Liste des échecs de terminaison

   Route : `POST /api/master/free-ports` (admin requis)

### Sécurité garantie

Un process Windows Skype/Vue.js/PostgreSQL/Docker/etc. **ne sera jamais
touché**, même s'il occupe un port SCRIBE — la commande ne contient pas
nos hints métier. Seul le PID + nom est remonté pour info.

---

## Fichiers modifiés (vs v3000h2)

| Fichier | Modifs |
|---|---|
| `master/port_cleanup.py` | NOUVEAU — module cross-platform (310 LOC) |
| `main.py` | bloc `if __name__ == "__main__"` : cleanup port master + optionnel `SCRIBE_PORT_CLEANUP_ALL=1` |
| `master/exercice_manager.py` | `start()` et `start_collecteur()` : utilisent free_port_if_scribe |
| `master/instances_manager.py` | `start()` : utilise free_port_if_scribe |
| `master/master_routes.py` | nouvelle route `POST /free-ports` (admin) |
| `master/instances.html` | bouton "🔓 Libérer ports" + fonction JS freeAllPorts |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha9 → alpha10 |

## Validation pré-build
- ✅ `ast.parse` : port_cleanup.py, main.py, exercice_manager.py, instances_manager.py, master_routes.py
- ✅ `node --check` : JS instances.html
- ✅ Test logique `_looks_like_scribe` : "main.py"/"scribe" détectés, "uvicorn" seul / "node" non

## Tests à faire côté Hervé

**Scénario du bug initial (Errno 10048)**
1. Lancer une instance exercice sur 8660 → succès
2. Tuer brutalement le master (Ctrl-C dur, ou tuer le terminal) sans `stop_all`
3. Relancer le master → le port 8660 devrait être détecté occupé par SCRIBE et **libéré automatiquement**
4. Relancer l'instance 8660 → doit fonctionner sans erreur 10048

**Process tiers (à NE PAS tuer)**
5. Sous Windows : lancer un `python -m http.server 8660` dans un autre terminal
6. Tenter de lancer l'instance 8660 → doit échouer avec **message clair** mentionnant
   le PID du serveur Python tiers, sans le tuer
7. Arrêter manuellement ce serveur → relancer l'instance → OK

**Bouton "🔓 Libérer ports"**
8. UI master → cliquer le bouton → rapport détaillé
9. Vérifier qu'aucun process tiers n'a été terminé

**Cleanup étendu au boot du master**
10. Lancer le master avec `SCRIBE_PORT_CLEANUP_ALL=1 python main.py` (Linux) ou
    `set SCRIBE_PORT_CLEANUP_ALL=1 && python main.py` (Windows)
11. Logs : "Cleanup étendu ports SCRIBE : X libérés, Y libres"

## Non régression
- Stimuli toujours injectés correctement
- Splash screen toujours présent
- Widget Assistant toujours visible

## Reste à faire
- **v3000i** : pipeline `/analyser-to-tasks` + transformation recommandation → Kanban
- **v3000j** : prompt libre `/coach/ask`
- **v3000k** : bouton "🤖 → tâches" depuis messagerie
