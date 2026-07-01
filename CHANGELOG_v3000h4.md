# Changelog — v3.0.0-alpha11 (build interne `v3000h4`)

**Date** : 30 mai 2026
**Base** : v3000h3
**Statut** : patch Windows 11 du cleanup ports.

---

## Correctifs Windows 11 — gestion des process orphelins

### Problème observé (capture Hervé)
- Erreur `[Errno 10048]` au démarrage du collecteur exercice (port 8565)
- `LANCER_SCRIBE.bat` ne faisait aucun nettoyage avant de démarrer
- Le `port_cleanup` (v3000h3) ne détectait pas correctement les python.exe sur W11
  parce que `wmic` est deprecated / parfois absent sur Win10 22H2+ et Win11 21H2+

### Corrections

**1. PowerShell prioritaire** (`port_cleanup.py` — détection PID et cmdline)
- Avant : `netstat -ano` + `wmic` (deprecated)
- Après : `Get-NetTCPConnection -LocalPort N -State Listen` pour le PID,
  `Get-CimInstance Win32_Process` pour la cmdline.
- Fallbacks conservés : netstat puis wmic puis tasklist.
- Bonus : détection insensitive à la locale (`LISTENING` en anglais, `ÉCOUTE` en français).

**2. Heuristique python.exe sur port SCRIBE** (`_looks_like_scribe`)
- Avant : il fallait IMPÉRATIVEMENT trouver `scribe` / `main.py` dans la cmdline.
  Si seul `python.exe` était disponible (cas tasklist sans CommandLine), le process
  était considéré comme tiers et NON tué → erreur 10048 persistante.
- Après : si seul le nom du process est dispo (`python.exe`, `pythonw.exe`) ET
  que le port appartient au périmètre SCRIBE protégé, on considère le process
  comme SCRIBE et on le termine.
- Restrictions de sécurité conservées :
  - Un `python.exe` sur un port HORS périmètre SCRIBE (ex: 5000) → NON tué
  - Un `chrome.exe` / `skype.exe` / autre nom sur un port SCRIBE → NON tué
- Tests automatiques inclus dans la suite de vérif.

**3. `LANCER_SCRIBE.bat` fait le cleanup au démarrage**
- Avant : aucun nettoyage, le master démarrait et plantait si port occupé
- Après : appelle `master.port_cleanup.free_all_scribe_ports()` AVANT de lancer
  le collecteur master. Affiche un résumé du cleanup.
- Idem pour `lancer_scribe.sh` (version Linux/macOS).
- Non bloquant : si le module n'est pas chargeable, on ignore et on lance quand
  même (l'utilisateur verra l'erreur 10048 normale s'il y a un vrai problème).

### Commandes de dépannage immédiat (PowerShell W11)

Au cas où ce build ne suffit pas, l'utilisateur peut nettoyer manuellement :

```powershell
# Voir qui occupe les ports SCRIBE (lecture seule, ne tue rien)
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 9000,8000..8009,8565,8660..8669,7474,7373 } | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; [PSCustomObject]@{Port=$_.LocalPort; PID=$_.OwningProcess; Name=$p.ProcessName} } | Format-Table -AutoSize

# Tuer SEULEMENT les python.exe sur ces ports
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 9000,8000..8009,8565,8660..8669,7474,7373 } | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p.ProcessName -in 'python','pythonw') { Stop-Process -Id $_.OwningProcess -Force } }
```

---

## Fichiers modifiés (vs v3000h3)

| Fichier | Modifs |
|---|---|
| `master/port_cleanup.py` | PowerShell prioritaire, heuristique python.exe sur port SCRIBE, locale FR/EN |
| `LANCER_SCRIBE.bat` | cleanup AVANT démarrage |
| `lancer_scribe.sh` | cleanup AVANT démarrage |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha10 → alpha11 |

## Validation pré-build
- ✅ `ast.parse` : port_cleanup.py
- ✅ Tests heuristique : main.py / scribe / collecteur_*.py → True, node / uvicorn-seul / autre process → False
- ✅ Tests Windows : python.exe sur port SCRIBE → True, python.exe sur port NON-SCRIBE → False

## Tests à faire côté Hervé (Windows 11)

1. **Dépanner l'état actuel** : exécuter les commandes PowerShell ci-dessus pour libérer tous les ports SCRIBE
2. **Lancer ce build** : double-clic sur `LANCER_SCRIBE.bat`
3. **Vérifier le log** : doit afficher `[boot] Nettoyage des ports SCRIBE orphelins...` puis un résumé
4. **Provoquer le bug initial** : démarrer une instance, tuer brutalement le master (fermer le terminal), relancer
5. Le port doit être libéré automatiquement, **plus d'erreur 10048**

## Reste à faire (rappel)
- v3000i : pipeline `/analyser-to-tasks` + transformation recommandation Assistant → Kanban
- v3000j : prompt libre `/coach/ask`
- v3000k : bouton "🤖 → tâches" depuis messagerie
