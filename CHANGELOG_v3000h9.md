# Changelog — v3.0.0-alpha16 (build interne `v3000h9`)

**Date** : 30 mai 2026
**Base** : v3000h8
**Statut** : patch — pollution console chat.html.

---

## Pourquoi tant de 401 même avant que l'exercice commence ?

C'était exactement la question. Réponse : **3 sources d'appels au collecteur 8565 depuis l'instance joueur** tournent en parallèle, dès le chargement de la page (avant même le démarrage du scénario) :

| Source | Fréquence | Routes ciblées |
|---|---|---|
| `loadTransfertsEntrants` (scribe.js) | au `refreshAll` (30s) | `/api/transferts-en-cours` |
| `pollIGHTBadge` (scribe.js) | toutes les 30s | `/api/messages`, `/api/demandes` |
| **`chat_syncCollecteur` (chat.html)** | **toutes les 3 secondes !** | `/api/chat/salons`, `/api/chat/messages`, `/api/chat/presence` |
| **`chat_pushPresence` (chat.html)** | toutes les 30s | `POST /api/chat/presence` |

Le 3e était le coupable principal — **toutes les 3 secondes** → 20 appels par minute → 60 erreurs/min dans la console.

Le build v3000h8 avait ajouté un circuit breaker dans scribe.js MAIS **pas dans chat.html**. Comme chat.html a son propre fichier et ses propres `setInterval`, il continuait de polluer la console.

## Correction

**Circuit breaker chat** (`plugins/chat/chat.html`) :
- Variables `_chatCollFailCount`, `_chatCollDisabled`, références aux timers (`_chatSyncTimer`, `_chatPresenceTimer`)
- Fonction `window._chatCollNoteFail()` : incrémente le compteur, arrête les `setInterval` après 3 échecs
- Tous les `fetch` chat collecteur (`/api/chat/salons`, `/messages`, `/presence` GET et POST) appellent `_chatCollNoteFail()` quand ils reçoivent 401
- Après 3 x 401 :
  - `clearInterval` sur `_chatSyncTimer` (sync 3s) et `_chatPresenceTimer` (presence 30s)
  - 1 warning console : "SCRIBE Chat: sync collecteur désactivée (3 x 401). Probablement mode exercice sans token fédération valide."
  - Plus aucun appel ensuite — silence radio

## Effet attendu

Avant ce build :
- Console : ~60 erreurs 401 par minute, **en boucle**
- Quasi-inutilisable pour debug

Après ce build :
- Console : **maximum 9 erreurs 401** (3 par circuit breaker × 3 sources) au démarrage
- Puis **silence total** + 1-2 warnings explicatifs
- Console parfaitement lisible après ~10 secondes

## Note technique

Le pourquoi du 401 reste : depuis l'instance joueur (port 8660), le token JWT utilisateur (`dircrise/Exercice2026!`) est valide sur l'instance MAIS pas sur le collecteur exercice (port 8565) qui a son propre auth (`animateur/Animateur2026!` ou token admin). Le `_fedStatus.token` censé être utilisé pour la fédération n'est probablement pas non plus accepté sur ces routes "chat" (qui ont leur propre logique d'auth).

Fix de fond futur : soit revoir l'auth fédération sur ces routes côté collecteur, soit définitivement désactiver le chat inter-GHT en mode exercice (probablement la bonne solution car le chat inter-GHT n'a pas vraiment de sens en simulation).

## Fichiers modifiés (vs v3000h8)

| Fichier | Modifs |
|---|---|
| `plugins/chat/chat.html` | circuit breaker + détection 401 sur les 4 routes chat collecteur |
| `main.py`, `collecteur/collecteur.py`, `app/static/index.html` | bump alpha15 → alpha16 |

## Validation pré-build
- ✅ `node --check` : JS chat.html

## Tests à faire côté Hervé

1. Recharger l'instance joueur (Ctrl+F5 pour forcer rechargement chat.html)
2. F12 → Console → onglet "Network"
3. Au démarrage, observer max 3-9 erreurs 401 vers :8565
4. Après ~10 secondes : 1 warning "SCRIBE Chat: sync collecteur désactivée..."
5. **Plus aucune erreur** en boucle ensuite
6. La console est propre, on peut voir les vrais logs

## Reste à faire
- v3000j : prompt libre `/coach/ask`
- v3000k : "🤖 → tâches" depuis messagerie
- Fix de fond auth fédération chat (gros chantier, peut attendre)
