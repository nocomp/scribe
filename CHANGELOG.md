# Changelog

Toutes les modifications notables de SCRIBE seront documentées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet utilise [Semantic Versioning](https://semver.org/lang/fr/).

---

## [2.0.1] — 2026-04-26

### 🐛 Corrections juridiques

- **Conformité licence OpenStreetMap** : ajout de l'attribution complète et cliquable sur toutes les cartes Leaflet (instances joueur + collecteur territorial). L'attribution suit désormais les exigences officielles de [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright) :
  - `© OpenStreetMap contributors` avec lien vers la page de copyright
  - Attribution `© CARTO` ajoutée pour les fonds CartoDB Light
  - Attribution `Tiles © Esri` complète pour le fond satellite
- Aucun changement fonctionnel — uniquement les chaînes d'attribution affichées sous chaque carte.

---

## [2.0.0] — 2026-04-26

Réécriture majeure du projet, passage en architecture plugins, ajout du mode exercice complet, vue mobile, MFA TOTP, multi-langue. Cette version introduit également un nouveau système de fédération inter-GHT avec collecteur dédié.

### ✨ Ajouts majeurs

#### 🎮 Mode exercice complet
- **Collecteur exercice dédié** sur port 8565 avec interface animateur (supervision, scénarios, bilan)
- **5 scénarios injectables prêts à jouer** : afflux post-accident A41, cyberattaque ransomware, panne électrique + cyber, crise obstétricale multi-sites, tension capacitaire aiguë
- **Bibliothèque de stimuli** : messages externes, incidents, transferts, décisions cellule, tensions capacitaires, brancardages
- **Compression temporelle** réglable (un exercice de 6h jouable en 1h30)
- **Génération IA assistée de scénarios** (formulaire guidé : contexte, durée, complexité, valeurs métiers, services impliqués, sites participants)
- **Création de scénario manuelle** avec stimuli timeline T+0, T+3, T+5...
- **SSO animateur → joueur** : un clic ouvre l'instance d'un site sans login manuel (autotoken)
- **Statuts publics supervisés** : l'animateur voit en temps réel quels joueurs publient leur statut public et avec quel message (vue pédagogique stratégique)
- **Stimuli capacité multi-unités** : sélection multiple via dropdown groupé par pôle hospitalier
- **Stimuli brancardage** avec presets (Polytrauma P1, Scan urgent, Bloc programmé, etc.)
- **Archivage → Scénario rejouable** : toute crise réelle archivée transformable automatiquement en exercice JSON injectable

#### 📱 Vue mobile autonome `/m`
- Vue dédiée aux usages terrain (RSSI en déplacement entre établissements, directeur de crise mobile, cadre de garde)
- Accessible sur n'importe quelle instance via `http://votre-instance/m`
- 5 écrans en navigation bottom-tab : Accueil (KPIs), Incidents, Messages, Capacité, Profil
- Cache localStorage : affiche le dernier état même hors réseau, bandeau d'alerte si offline
- Pull-to-refresh, auto-refresh 60s
- Compatible iOS (safe-area, notch) et Android
- SSO via `?autotoken=XXX` depuis la console animateur

#### 🔐 MFA TOTP (RFC 6238)
- **Activation depuis l'admin** : Section CONFIGURATION → 🔐 Sécurité MFA
- **Setup avec QR code** à scanner avec une app d'authentification
- **Apps compatibles** : Google Authenticator, Aegis, 2FAS, Microsoft Authenticator, FreeOTP, 1Password, Bitwarden, KeePassXC
- **10 codes de backup** générés à l'activation (à usage unique chacun) — téléchargeables en `.txt`
- **Régénération** des codes possible à tout moment (avec code TOTP actuel)
- **Désactivation** par l'utilisateur (mot de passe requis) ou par l'admin (cas de perte de téléphone)
- **Login phase 2** automatique : si MFA activé, le login bascule en mode prompt code TOTP après mot de passe
- **Auto-submit** quand 6 chiffres sont saisis (UX fluide)

#### 🌍 Multi-langue (i18n)
- Interface disponible en **8 langues** : FR, EN, DE, ES, IT, NL, PL, PT
- Sélecteur de langue dans l'admin (style WordPress)
- Système de clés `data-i18n-label` pour tagger les éléments traduisibles
- Navigation principale entièrement traduite

#### 📨 Messagerie & coordination
- **Fan-out automatique** des messages inter-GHT vers la messagerie interne de chaque destinataire
- **Filtrage des destinataires** au périmètre des sites engagés dans l'exercice
- **Reset des messages** à l'archivage de crise
- **Badge "NEW"** sur les messages non lus

#### 🏷️ Notifications
- Plugin **Web Push** avec VAPID (`pywebpush` + `py_vapid`)
- **Badges** sur tous les onglets : Incidents (rouge), Capacité (rouge), Brancardage (orange), Messages (rouge)
- **Marquage automatique "vu"** à l'ouverture de l'onglet correspondant

### 🔧 Améliorations

- **Renumérotation des ports** : 6660-6669 (bloqués par Chrome/Firefox comme ports IRC unsafe) → **8500-8666**
  - Collecteur prod : 8500
  - Collecteur exercice : 8565
  - Instances joueur exercice : 8660-8666
- **Match souple** des unités capacité : exact `service_nom` → exact `uf_code` → partiel
- **Match souple** des destinataires messagerie selon le sigle du site
- **Détail scénario enrichi** : objectifs pédagogiques, caractéristiques (durée jeu vs simulée, compression, complexité), chronologie complète des stimuli avec horodatage relatif
- **Statuts publics** : route `/api/v1/status/public` désormais correctement exposée (était définie mais router non inclus)
- **Bandeau MODE EXERCICE** rouge fixe en haut de page côté joueur
- **Console animateur** avec onglets Supervision / Scénarios / Exercice / Bilan

### 🐛 Corrections

- **Bug `access_token` vs `token`** : alignement des réponses login entre collecteur et instances
- **Stimuli messages perdus** : ajout des colonnes `expediteur_nom` / `destinataire_nom` + acceptation rôle collaborateur dans broadcast-externe
- **Sélecteur de langue inopérant** : ajout `data-i18n-label` qui préserve les enfants HTML
- **Capacité ne basculait pas** côté joueur : match `service_nom` au lieu de `nom`
- **Réponse multi-destinataires** : fan-out vers messagerie interne au lieu de canal inter-GHT (qui était désactivé)
- **SSO login persistant** : `login-overlay` non caché immédiatement + correction clé token
- **Badge brancardage absent** : injection du span à la volée si bouton créé avant la logique de badge
- **MFA pyotp absent** : à signaler clairement, le module plante au démarrage si lib non installée (pré-requis : `pip install pyotp qrcode`)
- **Archivage de crise** : ajout option "générer scénario rejouable" via checkbox

### 📚 Documentation

- **README** réécrit avec sections dédiées Mode exercice, Vue mobile, MFA, Multi-langue
- **CONTRIBUTING.md** : guide de contribution avec conventions de commit, structure plugins, multi-langue
- **SECURITY.md** : politique de divulgation responsable + bonnes pratiques déploiement (mots de passe, réseau, données, logs)
- **CODE_OF_CONDUCT.md** : Contributor Covenant 2.1 (FR + EN)
- **17 captures d'écran** dans `screenshots/` couvrant production et mode exercice :
  - Production : Veille, Soins, Cellule, Kanban, Capacité, Relève, Communiqué, Annuaire, Supervision collecteur, Cartographie collecteur, Analyse de crise, REX, Gestion capacitaire
  - Mode exercice : Console animateur supervision, Bibliothèque scénarios, Création de scénario, Détail scénario

### 🏗️ Infrastructure

- **`requirements.txt`** complet avec `pyotp>=2.9.0`, `qrcode[pil]>=7.4.0` pour MFA
- **Dockerfile** multi-stage avec utilisateur non-root + healthcheck
- **`docker-compose.yml`** + `docker-compose.production.yml`
- **CI GitHub Actions** : matrice Python 3.10/3.11/3.12, build Docker
- **`.gitignore`** strict filtrant configs spécifiques et secrets

### 🚧 Décisions architecturales

- **Onglet INTER-GHT désactivé par défaut** depuis v2307 (canal unifié via messagerie interne)
- **Plugin Telegram retiré par défaut** (CERT Santé : hors UE / NIS2)
- **Notifications par défaut** : Mail + SMS + WebPush (Telegram en opt-in via env var)

---

## [1.5.0-beta] — versions antérieures

Voir l'historique git pour les versions antérieures à 2.0.

---

## Format des versions

À partir de la v2.0, SCRIBE adopte une numérotation **MAJEURE.MINEURE.PATCH** :
- **MAJEURE** : changements incompatibles, refonte d'architecture
- **MINEURE** : nouvelles fonctionnalités rétrocompatibles
- **PATCH** : corrections de bugs et améliorations mineures

Les builds intermédiaires utilisent un suffixe `_public.zip` quand ils sont destinés à la release publique GitHub (filtre `.gitignore` appliqué).
