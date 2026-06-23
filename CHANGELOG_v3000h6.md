# Changelog — v3.0.0-alpha13 (build interne `v3000h6`)

**Date** : 30 mai 2026
**Base** : v3000h5
**Statut** : patch encodage Windows.

---

## Bug critique : `LANCER_SCRIBE.bat` cassé sur Windows FR

### Diagnostic

Sur Windows, `cmd.exe` lit les `.bat` avec sa **page de code locale** (CP-1252 ou CP-850 en français), pas UTF-8. Le fichier `LANCER_SCRIBE.bat` contenait :
- Tirets cadratins `—` (UTF-8 = `\xE2\x80\x94`, lus comme 3 octets aléatoires en CP-1252)
- Caractères accentués (`état`, `démarrage`, etc.)

Résultat : `cmd.exe` interprétait `'SCRIBE'`, `'v2.4.8.4'`, `'M'`, `'/i'`, `'echo'` (devenu `'ho'`) comme des commandes inconnues → cascade d'erreurs `n'est pas reconnu...`.

`chcp 65001` ligne 2 ne suffisait pas car la page de code change *après* lecture des premières lignes — trop tard pour les caractères déjà mal lus.

### Correction

`LANCER_SCRIBE.bat` réécrit en **ASCII pur + CRLF** :
- `—` → `-`
- `état` → `etat`, `démarrage` → `demarrage`, etc. (déaccentué)
- `→` → `->`
- Fins de ligne forcées en CRLF (canonique DOS/Windows)
- Plus aucun caractère hors ASCII

Vérification finale :
```
LANCER_SCRIBE.bat: DOS batch file, ASCII text, with CRLF line terminators
```

Le contenu fonctionnel n'est PAS modifié — seulement l'encodage et les caractères d'affichage.

---

## Fichiers modifiés (vs v3000h5)

| Fichier | Modifs |
|---|---|
| `LANCER_SCRIBE.bat` | UTF-8 → ASCII pur, accents retirés, CRLF |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha12 → alpha13 |

## Tests Hervé

1. Double-clic sur `LANCER_SCRIBE.bat`
2. La console doit afficher proprement le banner SCRIBE + démarrer le master sur :9000
3. Plus de `'XXX' n'est pas reconnu...`
4. La ligne `[boot] Nettoyage des ports SCRIBE orphelins...` doit apparaître

## À noter

Le fix v3000h5 (route /coach/check qui retournait 500) est conservé.
Une fois ce build lancé sans erreur, l'Assistant 🎓 devrait fonctionner sur
les instances joueur (port 8660+).

## Reste à faire
- v3000i : pipeline `/analyser-to-tasks` → tâches Kanban
- v3000j : prompt libre `/coach/ask`
- v3000k : "🤖 → tâches" depuis messagerie
