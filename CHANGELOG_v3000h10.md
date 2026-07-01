# Changelog — v3.0.0-alpha17 (build interne `v3000h10`)

**Date** : 30 mai 2026
**Base** : v3000h9
**Statut** : patch — fix scope variables circuit breaker chat.

---

## Bug introduit en h9 : ReferenceError chat_syncCollecteur

J'avais mis les variables du circuit breaker chat (`_chatCollFailCount`, `_chatCollDisabled`, `_chatSyncTimer`, `_chatPresenceTimer`) **à l'intérieur** de la fonction `chat_init()` au build h9, alors que `chat_syncCollecteur` et `chat_pushPresence` (définies plus bas dans le fichier, au scope global) tentaient de les lire.

Résultat : `Uncaught ReferenceError: _chatCollDisabled is not defined` à chaque tick du setInterval (toutes les 3 secondes). Le circuit breaker ne se déclenchait jamais.

### Correction

Variables déplacées **avant** `function chat_init()`, au scope global du script chat.html. Désormais accessibles par toutes les fonctions du fichier.

Vérification automatique ajoutée au build :
```
Position var _chatCollFailCount: 2063  ← avant chat_init
Position function chat_init:     2665
Position chat_syncCollecteur:    33993  ← peut lire les vars
Position chat_pushPresence:      38238  ← idem
```

## Méthodologie : pourquoi ça aurait dû être attrapé

Le `node --check` ne lève qu'une erreur de syntaxe, pas de scope/runtime. J'aurais dû faire un test plus poussé (extraction du JS + analyse de portée). Ajouté dans la validation pré-build pour les fichiers HTML avec JS embarqué.

## Fichiers modifiés (vs v3000h9)

| Fichier | Modifs |
|---|---|
| `plugins/chat/chat.html` | vars circuit breaker sorties au scope global (avant chat_init) |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha16 → alpha17 |

## Validation pré-build
- ✅ `node --check` : chat.html JS
- ✅ Test scope : vars déclarées avant chat_init, accessibles par chat_syncCollecteur et chat_pushPresence
- ✅ Aucune `var _chatColl...` à l'intérieur de chat_init

## Tests à faire côté Hervé

1. **Vider le cache navigateur** (Ctrl+Shift+Suppr ou navigation privée) sinon l'ancien chat.html reste en cache
2. Ouvrir l'instance joueur → F12 → Console
3. **Plus aucune** erreur `Uncaught ReferenceError: _chatCollDisabled is not defined`
4. Au démarrage : maximum ~9 erreurs 401 (3 par source × 3 sources)
5. Puis warning `"SCRIBE Chat: sync collecteur désactivée (3 x 401)"`
6. **Silence total ensuite**

## Reste à faire (rappel)
- v3000j : prompt libre `/coach/ask`
- v3000k : "🤖 → tâches" depuis messagerie
