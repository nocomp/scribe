# SCRIBE — CHANGELOG v3000h70 (3.6.0-alpha36) — Annuaire fédéré symétrique

Base : v3000h69.

## Corrigé — asymétrie de l'annuaire inter-établissements
Symptôme : depuis 8001 on voyait bien les agents de 8000, mais depuis 8000 aucun
autre site n'apparaissait (seule « Supervision »).

Cause : le collecteur `/api/annuaire` sautait toute instance absente du dict
`etablissements` (`if not etab_data: continue`) — c.-à-d. enrôlée mais sans push
de données récent. La liste étant la même pour tous, si une instance n'avait pas
poussé, elle disparaissait pour TOUS, et celle qui s'exclut elle-même ne voyait
plus personne.

Correctif : `/api/annuaire` interroge maintenant TOUTE instance **enrôlée**
(présente dans `tokens`), en allant chercher son `annuaire-public` directement,
sans exiger un push récent. Dédup par sigle. Une instance injoignable est
renvoyée en `unavailable` (et masquée côté compositeur).

## Reste à faire — build suivant
**Bluefile depuis la supervision** : le plugin Bluefiles existe et la messagerie
gère déjà les PJ `kind="bluefiles"`, mais le compositeur de la SUPERVISION
(collecteur) ne propose pas encore l'envoi sécurisé Bluefile vers les instances.
Intégration dédiée à venir (UI compositeur supervision + appel plugin + relais).

## Confirmé OK par les tests
- Stimulus message en exercice → messagerie inbox (h68). ✅
- Messagerie nominative 8001 → agent de 8000 (h69). ✅

## Version & cache
`v3.6.0-alpha36`, `?v=3000h70`. Pied = alpha36.

## Vérifier l'annuaire symétrique (VPS)
TOK=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"username":"dircrise","password":"Scribe2026!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -H "Authorization: Bearer $TOK" http://localhost:8000/api/v1/messagerie/correspondants-federes | python3 -m json.tool
# Doit maintenant lister 8001 (et les autres) depuis 8000.
