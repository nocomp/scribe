# Guide d'évaluation — Test Assistant v3.1

**Scénario** : `test_assistant_v31.json`
**Durée** : 30 minutes
**Joueurs** : 1 directeur de crise sur EXO1 (port 8660). EXO2 (port 8661) lancé en parallèle pour le transfert entrant en S06.

---

## Préparation (5 min avant)

1. Décompresser `scribe_v3000h15.zip` dans un dossier propre
2. Vérifier : `curl http://localhost:8660/api/v1/chat/ui/version` → `"expected":"v3000h15","ok":true`
3. Lancer EXO1 + EXO2 + collecteur exercice
4. Charger le scénario `test_assistant_v31.json` côté animateur
5. Ouvrir EXO1 en **navigation privée** (Ctrl+Shift+N)
6. Login `dircrise / Exercice2026!`
7. F12 ouvert pour suivre la console (rien d'attendu sauf 3 x 401 initiaux puis silence)
8. **Important** : ne pas créer de tâches, ne pas créer de décisions au début. On veut observer les déclenchements.

---

## Grille d'évaluation

Pour chaque règle, 3 colonnes à cocher pendant l'exercice :
- **Détectée ?** → l'Assistant a-t-il bien créé un message ?
- **Niveau correct ?** → marker (bleu) ou alert (rouge + bip) selon spec ?
- **Message clair ?** → le texte fait sens pour un dircrise ?

| # | Règle | Déclencheur attendu | t+min | Niveau attendu | Détectée ? | Niveau OK ? | Message clair ? |
|---|-------|---------------------|-------|----------------|------------|-------------|-----------------|
| R1 | incident_critique_sans_tache | S01 sans tâche créée | ~3 min | marker | ☐ | ☐ | ☐ |
| R6 | pas_de_plan_blanc | 3 U3 cumulés (S01+S02+S03) | ~3-5 min | **ALERT** 🔴+bip | ☐ | ☐ | ☐ |
| R4 | contradiction_declaration_veille | S04 déclaration vigilance + U3 actifs | ~3-5 min | **ALERT** 🔴+bip | ☐ | ☐ | ☐ |
| R2 | cyber_sans_notification | S01 cyber + aucune décision ANSSI | ~5 min | marker | ☐ | ☐ | ☐ |
| R3 | sanitaire_sans_declaration | S05 sanitaire U3 + pas de déclaration sanitaire ≥ tension | ~6-8 min | marker | ☐ | ☐ | ☐ |
| R5 | contradiction_capacite_transfert | S06 transfert accepté + S07 capacité critique | ~9-11 min | **ALERT** 🔴+bip | ☐ | ☐ | ☐ |
| R7 | pole_critique_absent | Cyber sans incident DPI/IMAGERIE après 10 min (en mode exercice) | ~10-12 min | marker | ☐ | ☐ | ☐ |

**Note** : les règles sont évaluées toutes les 60 secondes par le poll `/coach/check`. Comptez 0-60s de latence après le déclencheur.

---

## Tests fonctionnels (S08-S12)

### Test 1 — Point de situation (t+10)
☐ Le bouton 🎯 ouvre une synthèse structurée en 5 blocs
☐ Les 5 blocs apparaissent : Situation / Court terme / Moyen terme / Long terme / Priorités
☐ La source est indiquée en bas (IA ou local)
☐ Les compteurs sont cohérents (~5 incidents, peu de tâches)

### Test 2 — Historique (t+13)
☐ Le bouton 🔔 affiche tous les messages reçus depuis le début
☐ Les messages traités (ack) sont grisés avec mention "(traité)"
☐ Les alertes ont une bordure rouge, les markers une bordure bleue
☐ L'horodatage est correct

### Test 3 — Création de 3 tâches (t+16)
☐ Le bouton ✨ ouvre une modale avec 3 actions proposées
☐ Les 3 actions sont éditables
☐ Au clic "Créer", 3 tâches arrivent dans Kanban (colonne BACKLOG)
☐ Les tâches sont liées au bon incident (visible dans la description)

### Test 4 — Question libre (t+20)
☐ Le champ "Poser une question" en bas est utilisable (Entrée envoie)
☐ Spinner pendant l'appel
☐ Réponse pertinente liée au contexte de l'exercice
☐ Source indiquée (IA si configurée, ou "configuration manquante")

### Test 5 — Extinction des alertes (t+25)
**Action joueur** : créer une décision "Plan Blanc activé" → R6 ne doit plus revenir
☐ Au prochain poll (60s max), R6 n'est plus dans la liste active
☐ Mais R6 reste visible dans 🔔 Historique (marquée traitée si ack)

**Action joueur** : requalifier la déclaration en niveau 2 (tension) → R4 ne doit plus revenir
☐ R4 disparaît de la liste active après le poll suivant

**Action joueur** : créer une décision "ANSSI notifiée à 14h22, CERT-Santé en copie" → R2 ne doit plus revenir
☐ R2 disparaît de la liste active

---

## Critères de réussite globale

| Niveau | Score | Verdict |
|--------|-------|---------|
| 🟢 Excellent | 7/7 règles + 5/5 tests | Build prêt pour validation utilisateur élargie |
| 🟡 Acceptable | 5/7 règles + 4/5 tests | Quelques règles à affiner, le cœur fonctionne |
| 🔴 À retravailler | < 5/7 règles | Vérifier les noms de colonnes en DB, logs serveur |

---

## Points d'attention pendant l'évaluation

**Le silence du joueur n'est PLUS un signal**
Si le joueur ne fait rien entre deux stimuli, **l'Assistant ne doit PAS dire** "il y a 3 min, aucune action". L'ancienne règle `stagnation_globale` a été retirée. Vérifiez qu'elle n'apparaît plus.

**Le bip d'alerte**
Joue 1 seule fois par batch de nouvelles alertes (pas par alerte). Si plusieurs alerts arrivent en même temps : 1 seul bip. C'est voulu pour ne pas être insupportable.

**Désactiver le son pour le test si besoin**
```js
// F12 console
localStorage.setItem('coach_mute_sound', '1');
```

**Diagnostics pendant l'exercice**

```bash
# Toutes les règles déclenchées dans la session courante
sqlite3 scribe_g7_exo1.db "SELECT rule_id, niveau, datetime(created_at) FROM plugin_tuteur_coach_messages ORDER BY created_at DESC LIMIT 20"

# Décisions enregistrées (utile pour comprendre pourquoi R2/R6 ne s'éteignent pas)
sqlite3 scribe_g7_exo1.db "SELECT id, datetime(timestamp), substr(contenu,1,80) FROM decisions ORDER BY id DESC LIMIT 10"
```

---

## Après l'exercice — analyse rapide

1. Compter les messages : `sqlite3 scribe_g7_exo1.db "SELECT COUNT(*) FROM plugin_tuteur_coach_messages"`
2. Vérifier qu'aucune règle n'est apparue plus que ce qui est légitime (anti-spam = 1 par 15 min par règle/cible)
3. Vérifier que les ack sont bien horodatés (`SELECT id, rule_id, datetime(ack_at) FROM ... WHERE ack_at IS NOT NULL`)
4. Faire un dernier 🎯 Point de situation pour voir la synthèse finale après corrections

**Si une règle n'a pas déclenché alors qu'elle aurait dû** : 90% du temps, c'est un nom de colonne qui diffère entre les modèles SCRIBE théoriques et la DB réelle. Logs serveur (`logs/scribe-EXO1.log`) → chercher `coach_rules` ou `WARNING`.
