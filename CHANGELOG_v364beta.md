# SCRIBE 3.6.4-beta

Quatre défauts du chat territorial, découverts en cascade. Aucun ne produisait
d'erreur visible. Chacun, isolément, donnait la même impression : les autres
établissements ne répondent plus.

C'est exactement le mode de défaillance qu'un outil de crise ne peut pas se
permettre. Une panne bruyante se voit et se traite ; une coordination qui
s'éteint en silence se paie en décisions non prises.

---

## 1. Une exception avalée coupait la réception sur les instances les plus actives

**Symptôme.** Une instance qui avait elle-même posté dans un salon territorial
cessait de recevoir les messages des autres. Les instances n'ayant pas posté les
recevaient normalement. Aucune erreur, ni en console, ni côté serveur.

**Cause.** `_messages` est un tableau plat contenant le fil du salon affiché :

```js
var _messages = [];
_messages.push(m);          // partout dans le fichier
```

Mais `chat_syncCollecteur()` le traitait comme un dictionnaire indexé par salon :

```js
if (!_messages[salon.id]) _messages[salon.id] = [];
var dup = _messages[salon.id].some(...)
```

Dès que le fil comptait au moins `salon.id + 1` messages, `_messages[salon.id]`
n'était plus `undefined` : c'était un objet message. Il échappait donc à
l'initialisation, puis `.some()` était appelé dessus. `TypeError`.

Cette exception tombait dans le `catch` de fin de boucle, commenté « erreur
réseau silencieuse ». Et comme le filigrane de synchronisation était mis à jour
**avant** le plantage, il continuait d'avancer : vu de l'extérieur, la
synchronisation avait l'air de fonctionner parfaitement.

**Correctif.** L'injection se fait dans le tableau plat. La synchronisation ne
traite plus que le salon affiché, puisque `_messages` ne contient que celui-là.
Le filigrane du salon repart de zéro à chaque changement de salon, pour que
l'historique distant soit repris. Et le `catch` journalise désormais.

---

## 2. Le chat n'était pas persisté

`chat_messages` et `_chat_msg_counter` vivaient uniquement en mémoire du
collecteur. Chaque redémarrage effaçait l'historique territorial et faisait
repartir les identifiants de 1.

Deux conséquences. Le chat est aussi une trace de décisions : la perdre à
chaque redémarrage est un problème en soi. Et des identifiants qui reculent
bloquent les filigranes de synchronisation des instances (voir ci-dessous).

**Correctif.** Le chat est écrit sur disque à chaque message et rechargé au
démarrage. Le compteur est restauré depuis le plus grand identifiant connu :
les identifiants ne reculent plus jamais.

`collecteur_chat.json` contient des échanges territoriaux et a été ajouté au
`.gitignore`.

---

## 3. Un filigrane bloqué ne se rattrapait jamais

`_chatLastSyncId` ne fait que croître, en mémoire de l'onglet. Après un
redémarrage du collecteur sans persistance, un onglet déjà ouvert continuait de
demander `since_id=47` alors que le collecteur n'avait plus que les messages 1
et 2. Il ne recevait plus rien, définitivement, jusqu'au rechargement de la
page.

**Correctif.** Toutes les vingt boucles, environ une minute, la synchronisation
redemande l'historique complet au lieu de repartir du filigrane. Celui-ci se
recale seul, et le dédoublonnage par contenu évite les doublons. C'est un filet
de sécurité : même face à un collecteur d'une version antérieure, non
persistante, la synchronisation se rétablit en une minute.

---

## 4. Trois erreurs suffisaient à éteindre le chat pour la session

```js
if (_chatCollFailCount >= 3 && !_chatCollDisabled) {
  _chatCollDisabled = true;
  if (_chatSyncTimer) clearInterval(_chatSyncTimer);
  if (_chatPresenceTimer) clearInterval(_chatPresenceTimer);
}
```

Les minuteries étaient arrêtées et rien ne les réarmait. Seul un rechargement
de page rétablissait la situation, et rien ne le signalait à l'utilisateur.

Trois causes suffisent à déclencher la coupure sans qu'il y ait de panne réelle :
un collecteur redémarré, un jeton en cours de réenrôlement, une coupure réseau
de quelques secondes. Autrement dit, exactement ce qui arrive un jour de crise.

**Correctif.** La coupure devient une suspension, avec reprise à 30 secondes,
1 minute, 2 puis 5 au maximum. Le compteur repart à zéro dès qu'un appel
aboutit, donc une panne passagère ne laisse aucune trace.

Diagnostic depuis la console du navigateur, dans l'iframe du chat :

```js
window._chatCollEtat()
```

---

## Fichiers modifiés

| Fichier | Objet |
|---|---|
| `plugins/chat/chat.html` | injection, réconciliation du filigrane, reprise, journalisation |
| `plugins/chat/ui.py` | version du chat alignée sur la release |
| `collecteur/collecteur.py` | persistance du chat territorial |
| `.gitignore` | `collecteur_chat.json` |

---

## Mise à jour

Le paramètre de cache-busting passe à `?v=364beta`.

`chat.html` est relu à chaque requête : aucun redémarrage d'instance n'est
nécessaire pour les correctifs 1, 3 et 4. En revanche, l'iframe du chat doit
être rechargée — un Ctrl+Shift+R sur l'onglet suffit. Le correctif 2 exige un
redémarrage du collecteur.

```bash
pkill -f collecteur.py && sleep 2
cd collecteur && nohup python3 collecteur.py >> ../logs/collecteur.log 2>&1 &
```

**Vérification.** Envoyer un message depuis une instance, le voir apparaître en
moins de cinq secondes sur une instance **ayant déjà posté** dans ce salon —
c'est le cas qui échouait. Puis redémarrer le collecteur : l'historique doit
être intact et la synchronisation reprendre sans recharger les onglets.

```bash
curl -s http://127.0.0.1:8000/api/v1/chat/ui/version
ls -la collecteur/collecteur_chat.json
```

---

## Rappel de la 3.6.3-beta

Si vous partez d'une version antérieure, l'avertissement sur les secrets
versionnés reste entièrement valable : voir `CHANGELOG_v363beta.md`. Cinq
fichiers contenant des jetons de fédération, des jetons d'administration et la
clé de signature JWT étaient présents dans le dépôt public. Les retirer ne
suffit pas — ils demeurent dans l'historique git et doivent être considérés
comme compromis.
