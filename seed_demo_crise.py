"""
seed_demo_crise.py — Scénario de crise complet sur 2 jours
Centre Hospitalier de Valmont (CHV)

Scénario : Cyberattaque par ransomware initiée dans la nuit du J1,
se propageant aux systèmes cliniques, entraînant des impacts sanitaires
sur plusieurs services. Activation cellule de crise, gestion de crise
sur 48h, retour progressif à la normale.

Usage :
  1. python setup_demo1.py      (crée la base avec sites + UF)
  2. python seed_demo_crise.py  (injecte le scénario de crise)
  3. python main.py
  4. Se connecter, exporter la main courante (EXPORT MAIN COURANTE)
  5. Aller dans l'onglet ANALYSE, charger le ZIP → démonstration complète

Identifiants : dircrise / Scribe2026!
"""

import sys, os, json, hashlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
import app.models
import app.api.status_page
from app.models import (
    SitrepEntry, Decision, Presence, Consigne,
    Task, RexEntry, User, Hospital, UniteFonctionnelle, ServiceStatus,
    TransfertPatient, MessageInterne, CapaciteDeclaration, CapaciteReferentiel,
)
from app.api.status_page import StatusPage, StatusPageChronologie
# v2320 — Enrichissement démo : brancardage (plugin)
try:
    from plugins.brancardage.models import BrcMission
    _HAS_BRANCARDAGE = True
except Exception:
    _HAS_BRANCARDAGE = False

print("\n" + "═"*62)
print("  🎭  SCRIBE — Injection scénario de crise (2 jours)")
print("═"*62)

# ── Vérification base existante ────────────────────────────────
db = SessionLocal()
sites = db.query(Hospital).all()
if not sites:
    print("\n  ✗ Base vide — lancez d'abord : python setup_demo1.py")
    sys.exit(1)

# Récupérer les IDs de sites
site_map = {s.nom: s.id for s in sites}
main_id  = next((v for k,v in site_map.items() if "Principal" in k or "Valmont" in k), 1)
sec_id   = next((v for k,v in site_map.items() if "Crestval" in k or "Secondaire" in k), 2)
psy_id   = next((v for k,v in site_map.items() if "Pins" in k or "Psy" in k), 3)
ehpad_id = next((v for k,v in site_map.items() if "EHPAD" in k or "Lac" in k), 4)
samu_id  = next((v for k,v in site_map.items() if "SAMU" in k or "Centre 15" in k), 5)

site_noms = {v:k for k,v in site_map.items()}
print(f"\n  Sites trouvés : {list(site_map.keys())}")

# Noms dynamiques pour les incidents (utilise les vrais noms du DB)
_site_list = list(site_map.keys())
_main_nom  = site_noms.get(main_id,  _site_list[0] if _site_list else "Site Principal")
_sec_nom   = site_noms.get(sec_id,   _site_list[1] if len(_site_list)>1 else _main_nom)
_psy_nom   = site_noms.get(psy_id,   _site_list[2] if len(_site_list)>2 else _main_nom)
_samu_nom  = site_noms.get(samu_id,  _site_list[-1] if _site_list else _main_nom)

# Nom de l'établissement depuis config.js
try:
    import re as _re, os as _os
    _cjs = open(_os.path.join(_os.path.dirname(__file__), "app", "static", "config.js"), encoding="utf-8").read()
    _m = _re.search(r'"nom"\s*:\s*"([^"]+)"', _cjs)
    etab_nom = _m.group(1) if _m else "L'établissement"
except Exception:
    etab_nom = "L'établissement"

# ── Nettoyage données opérationnelles (conserver sites/UF/users) ──
print("\n  Nettoyage des données existantes...")
for model in [StatusPageChronologie, StatusPage, RexEntry, Task, Consigne,
              Presence, Decision, SitrepEntry,
              # v2320 — enrichissement démo
              TransfertPatient, MessageInterne, CapaciteDeclaration]:
    db.query(model).delete()
if _HAS_BRANCARDAGE:
    try:
        db.query(BrcMission).delete()
    except Exception:
        pass  # table peut ne pas exister si plugin chargé tardivement
db.commit()
print("  ✓ Tables opérationnelles vidées")

# ── Temporalité ────────────────────────────────────────────────
# J1 = hier à 02h00, crise sur 48h
NOW   = datetime.now(timezone.utc)
J1_00 = NOW.replace(hour=2, minute=0, second=0, microsecond=0) - timedelta(days=1)

def t(h, m=0, day=0):
    """Retourne un datetime : day=0 → J1, day=1 → J2"""
    return J1_00 + timedelta(hours=h + day*24, minutes=m)

def ts(h, m=0, day=0):
    return t(h, m, day)

print(f"\n  Début de crise simulé : {J1_00.strftime('%d/%m/%Y %H:%M')} UTC")
print(f"  Fin de crise simulée  : {(J1_00+timedelta(hours=46)).strftime('%d/%m/%Y %H:%M')} UTC")

# ══════════════════════════════════════════════════════════════
#  INCIDENTS (15 alertes sur les 5 sites, UF variées)
# ══════════════════════════════════════════════════════════════
print("\n  [1/7] Création des incidents...")

JALONS_PREDEFINIS = [
    "Passé d'ordi","DSI contacté","RSSI alerté","Cellule activée",
    "CERT Santé","Isolation réseau","Sauvegarde OK","Retour normal"
]

def make_jalons(done_list, timestamps):
    jalons = []
    for i, label in enumerate(JALONS_PREDEFINIS):
        done = label in done_list
        jalons.append({
            "label": label,
            "done": done,
            "done_at": timestamps.get(label, "").isoformat() if done and label in timestamps else None,
            "done_by": "Équipe DSI" if done else None
        })
    return json.dumps(jalons)

incidents_data = [
    # ── J1 Nuit : premiers signaux ──────────────────────────────
    {
        "timestamp": ts(2, 14),
        "declarant_nom": "Cadre de nuit FME",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "FME",
        "type_crise": "CYBER",
        "urgency": 2,
        "fait": "Impossible d'accéder au DPI Axigate depuis les postes du service FME",
        "analyse": "Peut-être une panne serveur ou mise à jour non planifiée. 3 postes concernés.",
        "moyens_engages": "Appel astreinte DSI",
        "intervenant_nom": "Astreinte DSI",
        "intervenant_contact": "6501",
        "status": "RÉSOLU",
        "resolved_at": ts(4, 30),
        "jalons": make_jalons(
            ["Passé d'ordi","DSI contacté","Retour normal"],
            {"DSI contacté": ts(2,20), "Retour normal": ts(4,30)}
        ),
    },
    {
        "timestamp": ts(2, 47),
        "declarant_nom": "Cadre de nuit Chirurgie",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "CHIRURGIE ANESTHESIE",
        "type_crise": "CYBER",
        "urgency": 2,
        "fait": "Les postes du bloc opératoire affichent un message d'erreur inhabituel au démarrage. Système lent.",
        "analyse": "Comportement anormal généralisé. Possible infection malware.",
        "moyens_engages": "DSI alerté, vérification en cours",
        "intervenant_nom": "Technicien DSI",
        "intervenant_contact": "6502",
        "status": "RÉSOLU",
        "resolved_at": ts(18, 0),
        "jalons": make_jalons(
            ["Passé d'ordi","DSI contacté","RSSI alerté","Isolation réseau","Retour normal"],
            {"DSI contacté": ts(3,0), "RSSI alerté": ts(3,15), "Isolation réseau": ts(5,0), "Retour normal": ts(18,0)}
        ),
    },
    # ── J1 Matin : escalade ──────────────────────────────────────
    {
        "timestamp": ts(3, 52),
        "declarant_nom": "RSSI",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "DSI — Informatique",
        "type_crise": "CYBER",
        "urgency": 4,
        "fait": "Ransomware confirmé sur l'Active Directory. Chiffrement en cours sur les serveurs de fichiers. Attaque de type LockBit identifiée.",
        "analyse": "Compromission de l'AD. Propagation rapide. Tous les services connectés au réseau principal sont potentiellement touchés. Impact sur l'ensemble du CHV.",
        "moyens_engages": "Isolation réseau engagée. CERT Santé contacté. Cellule de crise activée.",
        "intervenant_nom": "CERT Santé",
        "intervenant_contact": "cyberveille@sante.gouv.fr",
        "status": "EN COURS",
        "jalons": make_jalons(
            ["Passé d'ordi","DSI contacté","RSSI alerté","Cellule activée","CERT Santé","Isolation réseau"],
            {"RSSI alerté": ts(3,52), "Cellule activée": ts(5,30), "CERT Santé": ts(6,0), "Isolation réseau": ts(5,0)}
        ),
    },
    {
        "timestamp": ts(5, 10),
        "declarant_nom": "Directeur des Soins",
        "directeur_crise": "DG",
        "site_id": _main_nom,
        "unite_fonctionnelle": "URGENCES",
        "type_crise": "MIXTE",
        "urgency": 3,
        "fait": "Le logiciel de régulation des urgences est inaccessible. Prise en charge patients en mode papier.",
        "analyse": "Impact direct sur la gestion des flux patients. Risque de délai de prise en charge.",
        "moyens_engages": "Procédure mode dégradé urgences activée. Fiches papier distribuées.",
        "intervenant_nom": "Cadre supérieur urgences",
        "intervenant_contact": "5001",
        "status": "RÉSOLU",
        "resolved_at": ts(14, 0),
        "jalons": make_jalons(
            ["Passé d'ordi","DSI contacté","Retour normal"],
            {"DSI contacté": ts(5,15), "Retour normal": ts(14,0)}
        ),
    },
    {
        "timestamp": ts(5, 35),
        "declarant_nom": "Cadre bloc opératoire",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "CHIRURGIE ANESTHESIE",
        "type_crise": "MIXTE",
        "urgency": 4,
        "fait": "Les postes de pilotage des respirateurs connectés au réseau sont inaccessibles. Passage en mode manuel sur 8 respirateurs en réanimation.",
        "analyse": "Risque patient direct. Équipes soignantes mobilisées en surveillance manuelle renforcée.",
        "moyens_engages": "Surveillance manuelle renforcée. Médecin senior rappelé.",
        "intervenant_nom": "Dr. MARTIN — Anesthésiste référent",
        "intervenant_contact": "5120",
        "status": "RÉSOLU",
        "resolved_at": ts(10, 0),
        "jalons": make_jalons(
            ["Passé d'ordi","DSI contacté","Retour normal"],
            {"DSI contacté": ts(5,40), "Retour normal": ts(10,0)}
        ),
    },
    {
        "timestamp": ts(6, 20),
        "declarant_nom": "Responsable téléphonie CHV",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "Services Techniques",
        "type_crise": "CYBER",
        "urgency": 3,
        "fait": "La centrale téléphonique IPBX est hors service. Seuls les téléphones fixes analogiques fonctionnent.",
        "analyse": "Communication interne sévèrement perturbée. Numéros courts inaccessibles.",
        "moyens_engages": "Activation téléphonie de secours. Distribution liste numéros fixes.",
        "intervenant_nom": "Prestataire téléphonie",
        "intervenant_contact": "0800 000 001",
        "status": "RÉSOLU",
        "resolved_at": ts(20, 0, 1),
        "jalons": make_jalons(
            ["Passé d'ordi","DSI contacté","Retour normal"],
            {"DSI contacté": ts(6,30), "Retour normal": ts(20,0,1)}
        ),
    },
    # ── J1 Matin : sites secondaires touchés ─────────────────────
    {
        "timestamp": ts(7, 5),
        "declarant_nom": "Cadre responsable site Crestval",
        "directeur_crise": "DSI",
        "site_id": _sec_nom,
        "unite_fonctionnelle": "DSI secondaire",
        "type_crise": "CYBER",
        "urgency": 3,
        "fait": "Site Crestval : tous les postes windows affichent une note de rançon. Réseau isolé en urgence par l'équipe locale.",
        "analyse": "Propagation via VPN inter-sites. Même souche que le site principal.",
        "moyens_engages": "VPN coupé. Réseau local isolé. Fonctionnement en mode île.",
        "intervenant_nom": "Technicien local Crestval",
        "intervenant_contact": "6601",
        "status": "EN COURS",
        "jalons": make_jalons(
            ["Isolation réseau","RSSI alerté","CERT Santé"],
            {"Isolation réseau": ts(7,10), "RSSI alerté": ts(7,15), "CERT Santé": ts(8,0)}
        ),
    },
    {
        "timestamp": ts(8, 30),
        "declarant_nom": "Directeur EHPAD",
        "directeur_crise": "DGA",
        "site_id": "EHPAD — Résidence du Lac",
        "unite_fonctionnelle": "EHPAD — Unité A",
        "type_crise": "MIXTE",
        "urgency": 2,
        "fait": "Le logiciel de gestion médicamenteuse est inaccessible. Distribution médicaments en cours avec fiches papier de sauvegarde.",
        "analyse": "Risque d'erreur médicamenteuse limité par les procédures papier. Situation maîtrisée mais contraignante.",
        "moyens_engages": "Procédure mode dégradé médicaments activée. Médecin coordinateur prévenu.",
        "intervenant_nom": "Médecin coordinateur EHPAD",
        "intervenant_contact": "6702",
        "status": "RÉSOLU",
        "resolved_at": ts(22, 0),
        "jalons": make_jalons(
            ["Passé d'ordi","Retour normal"],
            {"Retour normal": ts(22,0)}
        ),
    },
    {
        "timestamp": ts(9, 15),
        "declarant_nom": "RSSI",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "DSI — Informatique",
        "type_crise": "CYBER",
        "urgency": 4,
        "fait": "Identification complète de l'attaque : ransomware LockBit 3.0. Demande de rançon de 500 000€. Refus catégorique conforme à la politique ANSSI.",
        "analyse": "Attaque sophistiquée. Vecteur d'entrée : phishing ciblé reçu 4 jours avant. Données potentiellement exfiltrées avant chiffrement.",
        "moyens_engages": "ANSSI contacté. Prestataire cybersécurité mandaté. Investigations forensiques lancées.",
        "intervenant_nom": "Prestataire CERT privé",
        "intervenant_contact": "soc@prestataire.fr",
        "status": "EN COURS",
        "jalons": make_jalons(
            ["RSSI alerté","CERT Santé","Isolation réseau"],
            {"RSSI alerté": ts(3,52), "CERT Santé": ts(6,0), "Isolation réseau": ts(5,0)}
        ),
    },
    # ── J1 Après-midi ────────────────────────────────────────────
    {
        "timestamp": ts(11, 45),
        "declarant_nom": "Cadre service imagerie",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "MEDICO-TECHNIQUE ET REEDUCATION",
        "type_crise": "CYBER",
        "urgency": 3,
        "fait": "PACS et RIS (imagerie) hors service. Impossibilité de consulter les images radiologiques numériques.",
        "analyse": "Blocage des prescriptions d'imagerie urgente. Les examens en cours sont réalisés mais non lisibles.",
        "moyens_engages": "Contact fournisseur PACS. Solution de contournement en cours d'évaluation.",
        "intervenant_nom": "Support PACS",
        "intervenant_contact": "0800 000 002",
        "status": "RÉSOLU",
        "resolved_at": ts(8, 0, 1),
        "jalons": make_jalons(
            ["DSI contacté","Sauvegarde OK","Retour normal"],
            {"DSI contacté": ts(12,0), "Sauvegarde OK": ts(20,0), "Retour normal": ts(8,0,1)}
        ),
    },
    {
        "timestamp": ts(13, 0),
        "declarant_nom": "Directrice des soins",
        "directeur_crise": "DG",
        "site_id": _psy_nom,
        "unite_fonctionnelle": "Psychiatrie de liaison",
        "type_crise": "SANITAIRE",
        "urgency": 2,
        "fait": "Rupture de communication entre l'unité de psychiatrie Les Pins et le site principal. Prise en charge des patients en autonomie.",
        "analyse": "Pas de risque immédiat. Protocoles de crise internes activés. Liaison assurée par téléphone fixe.",
        "moyens_engages": "Liaison téléphonique fixe établie. Cadre de garde renforcé.",
        "intervenant_nom": "Cadre de garde Les Pins",
        "intervenant_contact": "04 50 00 03 01",
        "status": "RÉSOLU",
        "resolved_at": ts(19, 0),
        "jalons": make_jalons(
            ["Passé d'ordi","Retour normal"],
            {"Retour normal": ts(19,0)}
        ),
    },
    # ── J2 Matin : restauration progressive ─────────────────────
    {
        "timestamp": ts(6, 0, 1),
        "declarant_nom": "DSI",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "DSI — Informatique",
        "type_crise": "CYBER",
        "urgency": 2,
        "fait": "Restauration des serveurs de fichiers depuis les sauvegardes hors-ligne (J-3). Vérification d'intégrité en cours.",
        "analyse": "Sauvegardes saines. Perte de données limitée à 3 jours. Retour progressif prévu sur 8h.",
        "moyens_engages": "Équipe DSI au complet. Prestataire présent sur site.",
        "intervenant_nom": "Prestataire + équipe DSI",
        "intervenant_contact": "Salle informatique",
        "status": "RÉSOLU",
        "resolved_at": ts(16, 0, 1),
        "jalons": make_jalons(
            ["Sauvegarde OK","Retour normal"],
            {"Sauvegarde OK": ts(10,0,1), "Retour normal": ts(16,0,1)}
        ),
    },
    {
        "timestamp": ts(9, 30, 1),
        "declarant_nom": "Responsable pharmacie",
        "directeur_crise": "DGA",
        "site_id": _main_nom,
        "unite_fonctionnelle": "Pharmacie",
        "type_crise": "CYBER",
        "urgency": 2,
        "fait": "Le logiciel de prescription informatisée reste indisponible. Délai de retour estimé à 24h supplémentaires.",
        "analyse": "Mode dégradé papier maintenu. Procédure rodée depuis J1. Pas de rupture de soins.",
        "moyens_engages": "Mode dégradé pharmacie maintenu. Traçabilité papier.",
        "intervenant_nom": "Pharmacien chef",
        "intervenant_contact": "5300",
        "status": "RÉSOLU",
        "resolved_at": ts(22, 0, 1),
        "jalons": make_jalons(
            ["Retour normal"],
            {"Retour normal": ts(22,0,1)}
        ),
    },
    {
        "timestamp": ts(14, 0, 1),
        "declarant_nom": "DSI",
        "directeur_crise": "DSI",
        "site_id": _main_nom,
        "unite_fonctionnelle": "DSI — Informatique",
        "type_crise": "CYBER",
        "urgency": 1,
        "fait": "DPI Axigate restauré sur le site principal. Authentification testée et validée sur 20 postes pilotes.",
        "analyse": "Retour progressif. Montée en charge sur 4h. Surveillance renforcée.",
        "moyens_engages": "Équipe DSI en surveillance. Hotline interne activée.",
        "intervenant_nom": "DSI + support Axigate",
        "intervenant_contact": "6500",
        "status": "RÉSOLU",
        "resolved_at": ts(22, 0, 1),
        "jalons": make_jalons(
            ["Sauvegarde OK","Retour normal"],
            {"Sauvegarde OK": ts(14,30,1), "Retour normal": ts(22,0,1)}
        ),
    },
    {
        "timestamp": ts(20, 0, 1),
        "declarant_nom": "DG",
        "directeur_crise": "DG",
        "site_id": _main_nom,
        "unite_fonctionnelle": "Direction Générale",
        "type_crise": "CYBER",
        "urgency": 1,
        "fait": "Retour à la normale progressif constaté sur l'ensemble des sites. Maintien de la vigilance 72h.",
        "analyse": "Crise principale maîtrisée. Investigation forensique en cours. Plan de renforcement sécurité à élaborer.",
        "moyens_engages": "Surveillance maintenue. Rapport incident à transmettre à l'ARS.",
        "intervenant_nom": "Cellule de crise CHV",
        "intervenant_contact": "Salle de crise",
        "status": "RÉSOLU",
        "resolved_at": ts(22, 0, 1),
        "jalons": make_jalons(
            ["Retour normal"],
            {"Retour normal": ts(22,0,1)}
        ),
    },
]

inc_objects = []
for d in incidents_data:
    inc = SitrepEntry(**d)
    db.add(inc)
    db.flush()
    inc_objects.append(inc)
db.commit()
print(f"  ✓ {len(inc_objects)} incidents créés")

# ID des incidents principaux pour référence
INC_AD      = inc_objects[2].id   # Ransomware AD
INC_RESP    = inc_objects[4].id   # Respirateurs
INC_TEL     = inc_objects[5].id   # Téléphonie
INC_CRESTVAL= inc_objects[6].id   # Crestval
INC_PACS    = inc_objects[9].id   # PACS imagerie
INC_RESTORE = inc_objects[11].id  # Restauration

# ══════════════════════════════════════════════════════════════
#  PRÉSENCES CELLULE (entrées/sorties sur 2 jours)
# ══════════════════════════════════════════════════════════════
print("\n  [2/7] Création des présences cellule...")

PRESENCES = [
    # ── J1 Activation cellule 05h30 ──────────────────────────
    (ts(5, 30), "M. BERNARD",         "Directeur Général",           "ENTREE"),
    (ts(5, 32), "Mme LECONTE",   "Directrice Générale Adjointe","ENTREE"),
    (ts(5, 35), "M. DUPUIS",        "DSI",                         "ENTREE"),
    (ts(5, 38), "M. FONTAINE",          "RSSI",                        "ENTREE"),
    (ts(5, 45), "Mme AUBERT",       "Directrice des Soins",        "ENTREE"),
    (ts(6, 0), "M. GIRARD",            "DAF",                         "ENTREE"),
    (ts(6, 10), "Mme CHEVALIER",         "Direction Médicale",          "ENTREE"),
    (ts(6, 15), "M. LAMBERT",           "Direction Achats",            "ENTREE"),
    # ── J1 Rotations ────────────────────────────────────────
    (ts(12, 0), "M. BERNARD",         "Directeur Général",           "SORTIE"),
    (ts(12, 5), "Mme LECONTE",   "Directrice Générale Adjointe","SORTIE"),
    (ts(12,10), "M. MOREAU",           "DRH",                         "ENTREE"),
    (ts(12,15), "Mme PERRIN",    "DUQEP",                       "ENTREE"),
    (ts(14, 0), "M. ROUSSEAU",           "Direction",                   "ENTREE"),
    (ts(18, 0), "M. DUPUIS",        "DSI",                         "SORTIE"),
    (ts(18, 5), "M. FONTAINE",          "RSSI",                        "SORTIE"),
    (ts(18,10), "Mme RENARD",        "Direction soins (remplaçante)","ENTREE"),
    (ts(18,20), "M. SIMON",           "Direction",                   "ENTREE"),
    # ── J1 Nuit ─────────────────────────────────────────────
    (ts(22, 0), "M. MOREAU",           "DRH",                         "SORTIE"),
    (ts(22, 5), "Mme PERRIN",    "DUQEP",                       "SORTIE"),
    (ts(22,15), "M. GARCIA",        "Direction",                   "ENTREE"),
    # ── J2 Matin ────────────────────────────────────────────
    (ts(6, 0, 1), "M. BERNARD",       "Directeur Général",           "ENTREE"),
    (ts(6, 5, 1), "M. DUPUIS",      "DSI",                         "ENTREE"),
    (ts(6,10, 1), "M. FONTAINE",        "RSSI",                        "ENTREE"),
    (ts(6,30, 1), "Mme AUBERT",     "Directrice des Soins",        "ENTREE"),
    (ts(7, 0, 1), "Mme CHEVALIER",       "Direction Médicale",          "ENTREE"),
    (ts(8, 0, 1), "M. GARCIA",      "Direction",                   "SORTIE"),
    (ts(14, 0,1), "M. GIRARD",          "DAF",                         "ENTREE"),
    # ── J2 Fin de crise ──────────────────────────────────────
    (ts(21, 0,1), "M. BERNARD",        "Directeur Général",           "SORTIE"),
    (ts(21,10,1), "M. DUPUIS",      "DSI",                         "SORTIE"),
    (ts(21,15,1), "M. FONTAINE",        "RSSI",                        "SORTIE"),
    (ts(21,30,1), "Mme AUBERT",     "Directrice des Soins",        "SORTIE"),
    (ts(22, 0,1), "Mme CHEVALIER",       "Direction Médicale",          "SORTIE"),
]

for (time, nom, role, action) in PRESENCES:
    db.add(Presence(timestamp=time, nom=nom, role=role, action=action))
db.commit()
print(f"  ✓ {len(PRESENCES)} mouvements cellule créés")

# ══════════════════════════════════════════════════════════════
#  DÉCISIONS CELLULE
# ══════════════════════════════════════════════════════════════
print("\n  [3/7] Création des décisions...")

DECISIONS = [
    (ts(5,45), "Activation officielle de la cellule de crise CHV", "M. BERNARD", "Plan Blanc"),
    (ts(5,50), "Isolation complète du réseau informatique principal — coupure VPN inter-sites", "M. DUPUIS", "NIS2"),
    (ts(5,55), "Déclenchement du plan de continuité d'activité (PCA) informatique", "M. FONTAINE", "NIS2"),
    (ts(6, 0), "Contact immédiat du CERT Santé et signalement à l'ANS", "M. FONTAINE", "NIS2"),
    (ts(6, 5), "Activation des procédures mode dégradé sur tous les services cliniques", "Mme AUBERT", "Plan Blanc"),
    (ts(6,10), "Annulation des blocs opératoires programmés non urgents de la journée J1", "Mme CHEVALIER", "Plan Blanc"),
    (ts(6,20), "Information de l'ARS Auvergne-Rhône-Alpes — signalement obligatoire NIS2", "M. BERNARD", "NIS2"),
    (ts(6,30), "Refus catégorique de payer la rançon — conformité ANSSI et position nationale", "M. BERNARD", "Règlement intérieur"),
    (ts(7, 0), "Mandatement d'un prestataire de réponse à incident cybersécurité", "M. DUPUIS", "Plan Blanc"),
    (ts(8, 0), "Point de situation toutes les 2h — prochaine réunion 10h00", "M. BERNARD", "Plan Blanc"),
    (ts(10,0), "Maintien des urgences en mode dégradé — renfort infirmier bloc urgences", "Mme AUBERT", "Plan Blanc"),
    (ts(10,5), "Communication interne aux équipes : message rassurant, consignes pratiques", "Mme LECONTE", "Plan Blanc"),
    (ts(12,0), "Décision : pas de communication presse à ce stade — suivi ARS suffisant", "M. BERNARD", "Plan Blanc"),
    (ts(14,0), "Validation du plan de restauration par priorité : urgences > soins critiques > autres", "M. DUPUIS", "NIS2"),
    (ts(16,0), "Autorisation de rappel exceptionnel du personnel DSI — heures supplémentaires", "M. MOREAU", "Plan Blanc"),
    (ts(18,0), "Communiqué public sur le site CHV : information patients et familles", "M. BERNARD", "Plan Blanc"),
    # J2
    (ts(7, 0,1), "Levée partielle de l'isolation réseau sur le site principal après validation sécurité", "M. FONTAINE", "NIS2"),
    (ts(9, 0,1), "Priorisation de la restauration : DPI > PACS > téléphonie > autres", "M. DUPUIS", "NIS2"),
    (ts(12, 0,1), "Mise en place d'une surveillance SOC renforcée 24/7 pendant 30 jours", "M. FONTAINE", "NIS2"),
    (ts(16, 0,1), "Décision de levée de la cellule de crise à J+2 22h après retour à la normale confirmé", "M. BERNARD", "Plan Blanc"),
    (ts(18, 0,1), "Engagement d'un audit de sécurité complet dans les 30 jours", "M. BERNARD", "NIS2"),
    (ts(20, 0,1), "Levée officielle de la cellule de crise — passage en phase de surveillance", "M. BERNARD", "Plan Blanc"),
]

for (time, contenu, resp, base) in DECISIONS:
    db.add(Decision(timestamp=time, contenu=contenu, responsable=resp,
                    base_reglementaire=base, statut_validation="VALIDÉ"))
db.commit()
print(f"  ✓ {len(DECISIONS)} décisions créées")

# ══════════════════════════════════════════════════════════════
#  KANBAN
# ══════════════════════════════════════════════════════════════
print("\n  [4/7] Création des tâches kanban...")

TASKS = [
    # TERMINÉ
    (ts(5,50), "Couper le VPN inter-sites", "M. DUPUIS", 4, "TERMINÉ", INC_AD,
     "Isolation immédiate pour stopper la propagation"),
    (ts(5,55), "Contacter le CERT Santé", "M. FONTAINE", 4, "TERMINÉ", INC_AD,
     "Signalement obligatoire NIS2"),
    (ts(6, 0), "Activer la procédure mode dégradé urgences", "Mme AUBERT", 4, "TERMINÉ", None,
     "Distribution fiches papier + formation rapide cadres"),
    (ts(6, 5), "Prévenir le médecin senior réanimation", "Mme CHEVALIER", 4, "TERMINÉ", INC_RESP,
     "Surveillance manuelle des respirateurs"),
    (ts(6,10), "Informer l'ARS par écrit", "M. BERNARD", 3, "TERMINÉ", INC_AD,
     "Email + appel téléphonique"),
    (ts(6,30), "Mandater prestataire cybersécurité", "M. DUPUIS", 3, "TERMINÉ", INC_AD,
     "CERT privé — contrat cadre existant"),
    (ts(7, 0), "Activer liste de contacts téléphoniques de crise", "Mme LECONTE", 3, "TERMINÉ", INC_TEL,
     "Distribution physique aux cadres de chaque service"),
    (ts(7,30), "Annuler les blocs programmés du matin", "Mme CHEVALIER", 3, "TERMINÉ", None,
     "Contact chirurgiens + patients"),
    (ts(8, 0), "Vérifier intégrité des sauvegardes hors-ligne", "M. DUPUIS", 4, "TERMINÉ", INC_AD,
     "Sauvegardes J-3 confirmées saines"),
    (ts(10,0), "Préparer message interne aux équipes", "Mme LECONTE", 2, "TERMINÉ", None,
     "Ton rassurant, consignes pratiques mode dégradé"),
    (ts(12,0), "Rédiger communiqué ARS J1", "M. BERNARD", 3, "TERMINÉ", INC_AD,
     "Rapport intermédiaire"),
    # EN COURS
    (ts(14,0), "Restaurer les serveurs par priorité", "M. DUPUIS", 4, "EN COURS", INC_RESTORE,
     "Priorité : urgences > soins critiques > admin"),
    (ts(16,0), "Investigations forensiques — analyse des logs", "M. FONTAINE", 3, "EN COURS", INC_AD,
     "Prestataire CERT sur site"),
    (ts(18,0, 0), "Préparer rapport complet pour ARS sous 72h", "M. BERNARD", 3, "EN COURS", INC_AD,
     "Rapport obligatoire NIS2 art. 23"),
    # EN ATTENTE
    (ts(6,0,1), "Restaurer PACS imagerie", "M. DUPUIS", 3, "EN ATTENTE", INC_PACS,
     "En attente validation serveurs fichiers"),
    (ts(8,0,1), "Auditer tous les postes avant reconnexion réseau", "M. FONTAINE", 3, "EN ATTENTE", INC_AD,
     "Scan antivirus + validation individuelle"),
    (ts(10,0,1), "Former les équipes à la détection de phishing", "M. MOREAU", 2, "EN ATTENTE", None,
     "Plan de formation sécurité — à planifier sous 30j"),
    # BACKLOG
    (ts(12,0,1), "Réviser la politique de sauvegarde", "M. FONTAINE", 2, "BACKLOG", None,
     "Passer à une sauvegarde quotidienne hors-ligne"),
    (ts(12,5,1), "Tester le PCA complet sur scénario ransomware", "M. DUPUIS", 2, "BACKLOG", None,
     "Exercice à planifier dans les 6 mois"),
    (ts(12,10,1), "Déployer solution EDR sur tous les postes", "M. FONTAINE", 3, "BACKLOG", None,
     "Budget à valider en COPIL SI"),
]

for (time, titre, assignee, prio, col, inc_id, desc) in TASKS:
    db.add(Task(created_at=time, titre=titre, assignee=assignee,
                priorite=prio, colonne=col, incident_id=inc_id, description=desc))
db.commit()
print(f"  ✓ {len(TASKS)} tâches kanban créées")

# ══════════════════════════════════════════════════════════════
#  RELÈVE / CONSIGNES
# ══════════════════════════════════════════════════════════════
print("\n  [5/7] Création des consignes de relève...")

CONSIGNES = [
    # J1 matin → relève midi
    (ts(11,30), "Équipe de direction de l'après-midi",
     "Situation critique maintenue. VPN coupés, réseau isolé. Mode dégradé actif sur tous services. "
     "Prochain point cellule 14h. Contacter M. DUPUIS pour tout nouveau signe d'infection.",
     True, ts(12, 5), "Sophie"),
    (ts(11,45), "Cadres de nuit / Cadres de jour soins",
     "Procédure mode dégradé papier en vigueur. Ne pas reconnecter de poste au réseau sans accord DSI. "
     "Numéros de secours distribués. Signaler immédiatement toute anomalie informatique.",
     True, ts(12,10), "Jean-Marie"),
    (ts(11,50), "Directeur de nuit J1",
     "Cellule de crise active jusqu'à la fin de l'incident. Décisions prises : voir chronologie. "
     "CERT présent sur site à partir de 14h. Communiqué ARS envoyé.",
     True, ts(13, 0), "Pierre"),
    # J1 soir → relève nuit
    (ts(20,0), "Astreinte de nuit DSI",
     "Serveurs de fichiers en cours de restauration. Ne pas toucher. Sauvegardes validées. "
     "Si anomalie : appeler M. DUPUIS direct portable. Prochaine restauration DPI prévue J2 6h.",
     True, ts(20,30), "Karim"),
    (ts(20,15), "Directeur de nuit",
     "Cellule de crise en veille pour la nuit. Effectif réduit. Contacter M. GARCIA pour toute décision urgente. "
     "Pas de communication externe sans accord DG.",
     True, ts(20,45), "Nathalie"),
    (ts(20,30), "Cadres de nuit tous services",
     "Mode dégradé maintenu cette nuit. Pas de retour réseau prévu avant demain matin. "
     "Urgences opérationnelles en mode papier. Réanimation surveillée manuellement. Situation stable.",
     True, ts(21, 0), "Laurent"),
    # J2 matin → reprise
    (ts(5,45,1), "Équipe de direction J2",
     "Nuit calme. Pas de nouvel incident. Restauration prévue à partir de 6h. "
     "Cellule de crise reprend à 6h30. Point de situation toutes les 2h.",
     True, ts(6,10,1), "Sophie"),
    (ts(6, 0,1), "DSI — Équipe du matin",
     "Restauration AD et serveurs fichiers à lancer dès 6h00. Procédure documentée en salle serveurs. "
     "DPI Axigate à restaurer en priorité 1 dès validation AD.",
     True, ts(6,20,1), "Marc"),
    # J2 → fin de crise
    (ts(20,0,1), "Tous services",
     "Levée de la cellule de crise prévue à 22h. Retour à la normale confirmé sur 90% des systèmes. "
     "Téléphonie IPBX toujours en cours de restauration (24h). Mode de secours maintenu sur téléphonie.",
     False, None, None),
    (ts(21,0,1), "Cadres de nuit — post-crise",
     "Fin de crise officielle. Surveillance renforcée maintenue 72h. "
     "Signaler immédiatement tout comportement anormal des systèmes. SOC externe actif 24/7.",
     False, None, None),
]

for (time, pour, texte, accuse, accuse_at, accuse_par) in CONSIGNES:
    db.add(Consigne(timestamp=time, pour=pour, texte=texte,
                    accuse=accuse, accuse_at=accuse_at, accuse_par=accuse_par))
db.commit()
print(f"  ✓ {len(CONSIGNES)} consignes créées")

# ══════════════════════════════════════════════════════════════
#  REX — Retours d'expérience
# ══════════════════════════════════════════════════════════════
print("\n  [6/7] Création des fiches REX...")

REXES = [
    {
        "incident_id": INC_AD,
        "created_at": ts(10, 0, 1),
        "titre": "Cyberattaque ransomware LockBit — Site principal",
        "type_crise": "CYBER",
        "duree_minutes": 46*60,
        "nb_poles": 8,
        "nb_decisions": 22,
        "nb_jalons_total": 8,
        "nb_jalons_done": 6,
        "mttd_minutes": 172,
        "mttr_minutes": 46*60,
        "points_positifs": "Sauvegardes hors-ligne disponibles et saines\nActivation rapide de la cellule de crise (1h30 après détection)\nProcédures mode dégradé efficaces sur les urgences\nCoopération excellente entre équipes soignantes et DSI\nCommunication interne rassurante et réactive",
        "points_amelio": "Délai de détection trop long (172 min entre premiers signes et diagnostic)\nPas de détection automatique de la propagation réseau\nAnnuaire de crise papier non à jour sur certains services\nCommunication avec site Crestval difficile en début d'incident",
        "actions_futures": "Déployer solution EDR sur tous les postes sous 3 mois\nTester la détection réseau (segmentation VLAN)\nMettre à jour l'annuaire de crise tous les trimestres\nOrganiser exercice ransomware complet dans les 6 mois\nFormer 100% du personnel à la détection de phishing",
        "lecons": "Un ransomware peut rester silencieux plusieurs jours avant de s'activer. La sauvegarde hors-ligne est notre meilleure protection. La rapidité d'isolation du réseau a limité la propagation.",
        "redacteur": "M. FONTAINE — RSSI",
    },
    {
        "incident_id": INC_RESP,
        "created_at": ts(12, 0, 1),
        "titre": "Perte accès postes respirateurs — Réanimation",
        "type_crise": "MIXTE",
        "duree_minutes": 265,
        "nb_poles": 1,
        "nb_decisions": 3,
        "nb_jalons_total": 3,
        "nb_jalons_done": 3,
        "mttd_minutes": 45,
        "mttr_minutes": 265,
        "points_positifs": "Réactivité exemplaire de l'équipe médicale de réanimation\nPassage en mode manuel immédiat et efficace\nAucun événement indésirable patient",
        "points_amelio": "Les postes de pilotage ne devraient pas dépendre du réseau principal\nProcédure de basculement manuel pas connue de tous les infirmiers",
        "actions_futures": "Isoler les équipements biomédicaux critiques sur un réseau dédié\nFormation annuelle mode dégradé réanimation",
        "lecons": "Les équipements biomédicaux connectés représentent un risque majeur en cas de cyberattaque. L'isolation réseau doit être anticipée.",
        "redacteur": "Dr. MARTIN — Anesthésiste référent",
    },
    {
        "incident_id": INC_TEL,
        "created_at": ts(14, 0, 1),
        "titre": "Panne IPBX — Communication interne dégradée",
        "type_crise": "CYBER",
        "duree_minutes": 42*60,
        "nb_poles": 5,
        "nb_decisions": 2,
        "nb_jalons_total": 3,
        "nb_jalons_done": 2,
        "mttd_minutes": 250,
        "mttr_minutes": 42*60,
        "points_positifs": "Activation rapide de la téléphonie de secours\nAnnuaire de secours disponible et distribué efficacement",
        "points_amelio": "Délai trop long pour distribuer l'annuaire aux étages\nCertains cadres ne connaissaient pas la procédure de secours",
        "actions_futures": "Afficher l'annuaire de secours de façon permanente dans chaque service\nTest annuel de la bascule téléphonie de secours",
        "lecons": "La téléphonie est un service critique souvent sous-estimé. Sa dépendance au réseau IP la rend vulnérable lors d'une cyberattaque.",
        "redacteur": "Responsable téléphonie CHV",
    },
    {
        "incident_id": INC_CRESTVAL,
        "created_at": ts(16, 0, 1),
        "titre": "Propagation ransomware via VPN — Site Crestval",
        "type_crise": "CYBER",
        "duree_minutes": 18*60,
        "nb_poles": 3,
        "nb_decisions": 4,
        "nb_jalons_total": 5,
        "nb_jalons_done": 3,
        "mttd_minutes": 195,
        "mttr_minutes": 18*60,
        "points_positifs": "Isolation locale rapide effectuée par l'équipe sur place\nFonctionnement en mode île efficace",
        "points_amelio": "Le VPN inter-sites aurait dû être coupé plus tôt\nManque de coordination initiale avec le site principal",
        "actions_futures": "Mettre en place une coupure automatique VPN en cas d'alerte critique\nDotation d'un kit de crise cyber autonome sur chaque site secondaire",
        "lecons": "Les sites secondaires sont des vecteurs de propagation. Chaque site doit avoir la capacité d'isolement autonome.",
        "redacteur": "Cadre responsable site Crestval",
    },
    {
        "incident_id": INC_PACS,
        "created_at": ts(18, 0, 1),
        "titre": "PACS/RIS hors service — Impact imagerie médicale",
        "type_crise": "CYBER",
        "duree_minutes": 22*60,
        "nb_poles": 2,
        "nb_decisions": 2,
        "nb_jalons_total": 4,
        "nb_jalons_done": 3,
        "mttd_minutes": 365,
        "mttr_minutes": 22*60,
        "points_positifs": "Continuité des acquisitions d'images (réalisées mais non consultables)\nPas de report des examens urgents",
        "points_amelio": "Aucune procédure de visualisation d'images hors PACS n'existe\nLe délai de restauration (22h) est trop long pour un service critique",
        "actions_futures": "Mettre en place une solution de visualisation d'images hors-réseau\nPrioriser le PACS dans le plan de reprise informatique",
        "lecons": "L'imagerie médicale est désormais 100% numérique. Sa disponibilité doit être traitée comme un service vital au même titre que l'électricité.",
        "redacteur": "Cadre service imagerie",
    },
]

for d in REXES:
    db.add(RexEntry(**d))
db.commit()
print(f"  ✓ {len(REXES)} fiches REX créées")

# ══════════════════════════════════════════════════════════════
#  COMMUNIQUÉS PUBLICS
# ══════════════════════════════════════════════════════════════
print("\n  [7/7] Création des communiqués publics...")

# Récupérer le site principal de StatusPage ou créer
def get_or_create_sp(site_id, site_nom):
    row = db.query(StatusPage).filter_by(site_id=site_id).first()
    if not row:
        row = StatusPage(site_id=site_id, site_nom=site_nom)
        db.add(row)
        db.flush()
    return row

# Communiqué global établissement
sp_global = get_or_create_sp(0, "")
sp_global.niveau_global = "PERTURBE"
sp_global.message_public = (
    f"L'établissement {etab_nom} a été victime d'une cyberattaque dans la nuit du "
    + J1_00.strftime("%d/%m/%Y") +
    ". Nos équipes travaillent activement au rétablissement complet de nos systèmes. "
    "La continuité des soins est assurée. Toutes les urgences sont opérationnelles."
)
sp_global.services_si = json.dumps([
    {"id": "dpi",       "label": "Logiciels métier / DPI",    "statut": "DEGRADE"},
    {"id": "pacs",      "label": "Imagerie (PACS / RIS)",     "statut": "CRITIQUE"},
    {"id": "telephonie","label": "Téléphonie",                "statut": "DEGRADE"},
    {"id": "messagerie","label": "Messagerie interne",        "statut": "DEGRADE"},
    {"id": "internet",  "label": "Accès Internet",            "statut": "CRITIQUE"},
    {"id": "vpn",       "label": "Accès distants / VPN",      "statut": "CRITIQUE"},
])
sp_global.prise_en_charge = json.dumps([
    {"id": "urgences",    "label": "Urgences",               "statut": "OK"},
    {"id": "blocs",       "label": "Blocs opératoires",      "statut": "DEGRADE"},
    {"id": "consultations","label": "Consultations",         "statut": "OK"},
    {"id": "hospit",      "label": "Hospitalisations programmées", "statut": "DEGRADE"},
    {"id": "imagerie",    "label": "Imagerie patients",      "statut": "CRITIQUE"},
    {"id": "labo",        "label": "Laboratoire",            "statut": "OK"},
])
sp_global.faq = json.dumps([
    {"question": "Mes données personnelles sont-elles compromises ?",
     "reponse": "Une enquête est en cours. Par précaution, considérez que vos données ont pu être exposées. Nous vous tiendrons informés.",
     "visible": True},
    {"question": "Puis-je venir à mes rendez-vous prévus ?",
     "reponse": "Les consultations urgentes et les hospitalisations en cours sont maintenues. Les consultations programmées non urgentes peuvent être reportées. Contactez votre service.",
     "visible": True},
    {"question": "Les urgences sont-elles opérationnelles ?",
     "reponse": "Oui, les urgences restent pleinement opérationnelles. Une procédure de prise en charge adaptée est en place.",
     "visible": True},
])
sp_global.published = True
sp_global.updated_by = "M. BERNARD — DG"
db.flush()

# Communiqué site secondaire Crestval
sp_crestval = get_or_create_sp(sec_id, "Site Secondaire — Crestval")
sp_crestval.niveau_global = "ALERTE"
sp_crestval.message_public = "Site Crestval : systèmes informatiques isolés par mesure de précaution. Les soins sont assurés en mode dégradé. Retour à la normale en cours."
sp_crestval.services_si = json.dumps([
    {"id": "dpi",       "label": "DPI",           "statut": "CRITIQUE"},
    {"id": "telephonie","label": "Téléphonie",     "statut": "DEGRADE"},
    {"id": "internet",  "label": "Accès Internet", "statut": "CRITIQUE"},
])
sp_crestval.published = True
sp_crestval.updated_by = "Cadre Crestval"
db.flush()

# Chronologie publique
chrons = [
    (ts(6, 30),  "Incident informatique en cours — nos équipes mobilisées. Urgences opérationnelles.", "M. BERNARD"),
    (ts(8, 0),   "Cyberattaque confirmée. Cellule de crise activée. Autorités compétentes prévenues (ARS, CERT Santé).", "M. BERNARD"),
    (ts(12, 0),  "Situation stabilisée. Soins continus assurés en mode adapté. Restauration en cours.", "Mme LECONTE"),
    (ts(18, 0),  "Bilan J1 : pas d'impact patient. Restauration des systèmes prioritaires entamée.", "M. BERNARD"),
    (ts(8, 0, 1), "J+1 : restauration progressive. DPI en cours de remise en service.", "M. DUPUIS"),
    (ts(16, 0,1), "Retour à la normale en cours. DPI opérationnel sur le site principal.", "M. DUPUIS"),
    (ts(22, 0,1), "Fin de la phase de crise. Surveillance renforcée maintenue 72h. Merci de votre compréhension.", "M. BERNARD"),
]
for (time, texte, auteur) in chrons:
    db.add(StatusPageChronologie(timestamp=time, texte=texte, publie_par=auteur))
db.commit()
print(f"  ✓ Communiqué global publié + {len(chrons)} entrées chronologie")

# ══════════════════════════════════════════════════════════════
#  v2320 — ENRICHISSEMENT DÉMO : TRANSFERTS + BRANCARDAGE + CAPACITÉ + MESSAGERIE
#  Objectif : faire vivre toutes les fonctionnalités SCRIBE dans la démo,
#  en cohérence avec le scénario ransomware en cours.
# ══════════════════════════════════════════════════════════════

# ── 8. TRANSFERTS PATIENTS (cohérent ransomware : évacuation imagerie) ──
print("\n  [8/11] Création des transferts patients...")

# Récupérer le sigle de l'établissement courant pour les transferts
try:
    _cjs = open(os.path.join(os.path.dirname(__file__), "app", "static", "config.js"),
                encoding="utf-8").read()
    import re as _re
    _ms = _re.search(r'"sigle"\s*:\s*"([^"]+)"', _cjs)
    etab_sigle = _ms.group(1) if _ms else "CHV"
except Exception:
    etab_sigle = "CHV"

TRANSFERTS = [
    # Pendant la crise — évacuations vers Crestval (PACS HS chez nous)
    dict(nom="DUVAL", prenom="Jeanne", date_naissance="1955-03-12", ipp="IPP-200103",
         unite_origine="Imagerie scanner — Site Principal",
         etablissement_origine=etab_sigle,
         unite_destination="Imagerie scanner",
         etablissement_destination=etab_sigle,
         site_destination=_sec_nom,
         statut="ARRIVE",
         t_creation=t(8,15), t_depart=t(8,30), t_arrivee=t(9,15),
         redacteur="Dr. M. RENARD",
         commentaire="Scanner thoraco-abdo urgent — PACS Valmont HS, transfert vers Crestval"),
    dict(nom="MORIN", prenom="Pierre", date_naissance="1968-09-04", ipp="IPP-200218",
         unite_origine="Urgences",
         etablissement_origine=etab_sigle,
         unite_destination="Imagerie IRM",
         etablissement_destination=etab_sigle,
         site_destination=_sec_nom,
         statut="ARRIVE",
         t_creation=t(11,5), t_depart=t(11,20), t_arrivee=t(12,10),
         redacteur="Dr. C. MOREAU",
         commentaire="IRM cérébrale céphalées brutales — programmation Crestval"),
    dict(nom="GIRAUD", prenom="Lucie", date_naissance="1982-11-22", ipp="IPP-200305",
         unite_origine="Maternité",
         etablissement_origine=etab_sigle,
         unite_destination="Maternité",
         etablissement_destination=etab_sigle,
         site_destination=_sec_nom,
         statut="EN_COURS",
         t_creation=t(14,40), t_depart=t(14,55), t_arrivee=None,
         eta=t(15,40).strftime("%Y-%m-%dT%H:%M"),
         redacteur="Sage-femme N. PETIT",
         commentaire="Transfert maternité — saturation J1 sur site principal"),
    dict(nom="ROUSSEAU", prenom="André", date_naissance="1948-05-30", ipp="IPP-200421",
         unite_origine="Urgences",
         etablissement_origine=etab_sigle,
         unite_destination="USIC",
         etablissement_destination=etab_sigle,
         site_destination=_sec_nom,
         statut="ARRIVE",
         t_creation=t(20,10), t_depart=t(20,25), t_arrivee=t(21,5),
         redacteur="Dr. L. BLANC",
         commentaire="SCA ST+ — coronarographie urgente Crestval (cathlab Valmont en mode dégradé)"),
    # J2 — retours progressifs
    dict(nom="LEROY", prenom="Sophie", date_naissance="1975-01-18", ipp="IPP-200512",
         unite_origine="Imagerie scanner",
         etablissement_origine=etab_sigle,
         unite_destination="Imagerie scanner",
         etablissement_destination=etab_sigle,
         site_destination=_main_nom,
         statut="EN_PREPARATION",
         t_creation=t(10,30, day=1), t_depart=None, t_arrivee=None,
         eta=t(11,15, day=1).strftime("%Y-%m-%dT%H:%M"),
         redacteur="Dr. M. RENARD",
         commentaire="J2 — Retour vers Valmont après bilan, PACS rétabli en mode lecture"),
]

for tdat in TRANSFERTS:
    tr = TransfertPatient(
        nom=tdat["nom"], prenom=tdat["prenom"], date_naissance=tdat["date_naissance"],
        ipp=tdat["ipp"],
        unite_origine=tdat["unite_origine"],
        etablissement_origine=tdat["etablissement_origine"],
        unite_destination=tdat["unite_destination"],
        etablissement_destination=tdat["etablissement_destination"],
        site_destination=tdat["site_destination"],
        statut=tdat["statut"],
        horodatage_depart=tdat["t_depart"],
        horodatage_arrivee=tdat["t_arrivee"],
        eta=tdat.get("eta"),
        redacteur=tdat["redacteur"],
        commentaire=tdat["commentaire"],
    )
    # Override de horodatage_creation (sinon server_default = now)
    db.add(tr); db.flush()
    tr.horodatage_creation = tdat["t_creation"]
db.commit()
print(f"  ✓ {len(TRANSFERTS)} transferts patients créés (4 vers Crestval, 1 retour J2)")

# ── 9. BRANCARDAGE (missions internes pendant crise) ──
print("\n  [9/11] Création des missions de brancardage...")

BRANCARDAGES = []
if _HAS_BRANCARDAGE:
    # v2320 — créer la table à la volée si absente (cas seed lancé hors main.py
    # qui sinon créerait la table via plugin.register()).
    try:
        from plugins.brancardage.models import Base as _BrcBase
        _BrcBase.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as _e:
        print(f"  ⚠ Création table brancardage : {_e}")
    BRANCARDAGES = [
        # Missions internes site principal
        dict(ref_type="IPP", ref_patient="IPP-200103",
             uf_origine="URG-Box5", uf_destination="Imagerie-Scanner",
             type_transport="LIT", priorite="P1", motif="Scanner urgence",
             statut="TERMINEE", agent_nom="J. FONTAINE",
             demandeur_nom="Dr. M. RENARD",
             t_create=t(8,10), t_pec=t(8,15), t_term=t(8,28)),
        dict(ref_type="IPP", ref_patient="IPP-200421",
             uf_origine="URG-Salle déchoc", uf_destination="USIC",
             type_transport="LIT", priorite="P1", motif="SCA ST+ — coronaro Crestval",
             statut="TERMINEE", agent_nom="A. MOLINA",
             demandeur_nom="Dr. L. BLANC",
             transport_externe=1, etab_destination=etab_sigle,
             t_create=t(20,5), t_pec=t(20,10), t_term=t(20,25)),
        dict(ref_type="NOM", ref_patient="MORIN P.",
             uf_origine="URG-Box2", uf_destination="Imagerie-IRM",
             type_transport="FAUTEUIL", priorite="P2", motif="IRM céphalées",
             statut="TERMINEE", agent_nom="J. FONTAINE",
             demandeur_nom="Dr. C. MOREAU",
             t_create=t(11,0), t_pec=t(11,8), t_term=t(11,18)),
        dict(ref_type="NOM", ref_patient="ROUSSEAU A.",
             uf_origine="USIC", uf_destination="Bloc-Cathlab",
             type_transport="LIT", priorite="P1", motif="Coronarographie",
             statut="EN_COURS", agent_nom="A. MOLINA",
             demandeur_nom="Dr. L. BLANC",
             t_create=t(21,5), t_pec=t(21,10), t_term=None),
        dict(ref_type="IPP", ref_patient="IPP-200305",
             uf_origine="Maternité-Salle1", uf_destination="Bloc-Obstetrical",
             type_transport="LIT", priorite="P1", motif="Césarienne urgente",
             statut="EN_ATTENTE", agent_nom=None,
             demandeur_nom="Sage-femme N. PETIT",
             t_create=t(14,30), t_pec=None, t_term=None),
        # J2 — reprise normale, missions prévues
        dict(ref_type="AUTRE", ref_patient="DEMO-J2-1",
             uf_origine="Médecine-3A", uf_destination="Imagerie-Scanner",
             type_transport="FAUTEUIL", priorite="P3", motif="Bilan programmé",
             statut="EN_ATTENTE", agent_nom=None,
             demandeur_nom="Cadre Médecine 3A",
             programmee=1, heure_prevue="10:30",
             t_create=t(9,0, day=1), t_pec=None, t_term=None),
    ]
    for bd in BRANCARDAGES:
        m = BrcMission(
            ref_type=bd["ref_type"], ref_patient=bd["ref_patient"],
            uf_origine=bd["uf_origine"], uf_destination=bd["uf_destination"],
            type_transport=bd["type_transport"], priorite=bd["priorite"],
            motif=bd["motif"], statut=bd["statut"],
            agent_nom=bd.get("agent_nom"),
            demandeur_nom=bd.get("demandeur_nom"),
            transport_externe=bd.get("transport_externe", 0),
            etab_destination=bd.get("etab_destination"),
            programmee=bd.get("programmee", 0),
            heure_prevue=bd.get("heure_prevue"),
            created_at=bd["t_create"],
            prise_en_charge_at=bd.get("t_pec"),
            termine_at=bd.get("t_term"),
        )
        db.add(m)
    db.commit()
    print(f"  ✓ {len(BRANCARDAGES)} missions de brancardage créées")
else:
    print("  ⚠ Plugin brancardage absent — skip")

# ── 10. DÉCLARATIONS CAPACITAIRES (saturation lits/RH/matériel) ──
print("\n  [10/11] Création des déclarations capacitaires...")

# Récupérer le référentiel existant pour générer des déclarations cohérentes
referentiels = db.query(CapaciteReferentiel).limit(8).all()
# v2320 — Fallback : si aucun référentiel n'a été créé par setup_capacite_*.py,
# on en crée 6 minimaux pour que la démo capacité soit fonctionnelle.
if not referentiels:
    print("  ⚠ Aucun référentiel capacitaire — création fallback démo (6 services)")
    SERVICES_DEMO = [
        ("Médecine 3A",       "MED-3A",     "Médecine",     30, 32, 35),
        ("Chirurgie viscérale","CHIR-VISC", "Chirurgie",    25, 27, 30),
        ("Cardiologie / USIC", "USIC",      "Cardio-Vasc",  18, 20, 22),
        ("Réanimation",        "REA",       "Réanimation",  12, 14, 16),
        ("Maternité",          "MAT",       "Mère-Enfant",  20, 22, 24),
        ("Urgences (UHCD)",    "UHCD",      "Urgences",     16, 18, 20),
    ]
    for idx, (nom, code, pole, capa, t1, t2) in enumerate(SERVICES_DEMO):
        db.add(CapaciteReferentiel(
            service_nom=nom, uf_code=code, pole=pole,
            site=_main_nom,
            capacite_totale=capa, tension_1=t1, tension_2=t2,
            accept_homme=True, accept_femme=True, accept_indiffer=True,
            ordre_affichage=idx, actif=True,
        ))
    db.commit()
    referentiels = db.query(CapaciteReferentiel).limit(8).all()
    print(f"  ✓ {len(referentiels)} référentiels capacitaires démo créés")
CAPA_DECL = []
if referentiels:
    # Pour chaque référentiel, créer 3 déclarations : J1 matin (normal),
    # J1 soir (tension, mode dégradé), J2 matin (retour normal)
    for idx, ref in enumerate(referentiels[:6]):
        # J1 matin — état initial
        CAPA_DECL.append(dict(
            referentiel_id=ref.id, redacteur="C. DUBOIS (cadre matin)",
            point="matin", t=t(7, 0),
            lits_vides_h=2, lits_vides_f=2, lits_vides_i=1,
            tension_activee=0, statut_lits="normal", statut_rh="complet", statut_materiel="ok",
            commentaire_general="État initial avant alerte cyber",
        ))
        # J1 soir — tension en pleine crise
        is_critique = idx in (0, 1)  # 2 premiers services en critique
        CAPA_DECL.append(dict(
            referentiel_id=ref.id, redacteur="P. ROUX (cadre soir)",
            point="soir", t=t(19, 0),
            lits_vides_h=0, lits_vides_f=0 if is_critique else 1, lits_vides_i=0,
            tension_activee=2 if is_critique else 1,
            lits_sup=4 if is_critique else 2,
            statut_lits="critique" if is_critique else "tension",
            statut_rh="tension", statut_materiel="degrade",
            alerte_lits=is_critique, alerte_materiel=True,
            mode_degrade=True, besoin_renfort=3 if is_critique else 1,
            commentaire_lits="Mode dégradé activé suite à la crise cyber" if is_critique else "Tension lits",
            commentaire_rh="Cadres mobilisés sur procédures papier",
            commentaire_materiel="Imagerie HS, supports manuels en place",
            commentaire_general="Pic de tension pendant cyberattaque",
        ))
        # J2 matin — début de retour à la normale
        CAPA_DECL.append(dict(
            referentiel_id=ref.id, redacteur="C. DUBOIS (cadre matin)",
            point="matin", t=t(7, 0, day=1),
            lits_vides_h=1, lits_vides_f=2, lits_vides_i=0,
            tension_activee=1 if is_critique else 0,
            statut_lits="tension" if is_critique else "normal",
            statut_rh="complet", statut_materiel="degrade",
            commentaire_general="Retour progressif, SI partiellement rétabli",
        ))
    for d in CAPA_DECL:
        time = d.pop("t")
        decl = CapaciteDeclaration(**d)
        db.add(decl); db.flush()
        decl.horodatage = time
    db.commit()
    print(f"  ✓ {len(CAPA_DECL)} déclarations capacitaires créées sur {len(referentiels[:6])} services")
else:
    print("  ⚠ Aucun référentiel capacitaire — skip déclarations")

# ── 11. MESSAGERIE INTERNE (échanges cellule) ──
print("\n  [11/11] Création des messages internes...")

# Récupérer un user expéditeur (admin par défaut)
admin_user = db.query(User).filter(User.role == "admin").first() or db.query(User).first()
MSGS_CREES = 0
if admin_user:
    MESSAGES = [
        # Messages externes simulés (broadcast ARS, CERT)
        dict(expediteur_nom="ARS Auvergne-Rhône-Alpes",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom=admin_user.display_name or "Direction",
             sujet="🚨 Notification incident cyber — accusé de réception",
             contenu=("Bonjour,\n\nNous accusons réception de votre déclaration d'incident cyber "
                      "du jour. Un référent ARS sera mobilisé pour suivi.\n\n"
                      "Coordonnées 24/7 : pc-sante@ars.sante.fr — 04 72 34 74 00\n\n"
                      "Cellule régionale de gestion des incidents santé"),
             ght_source="ARS-ARA",
             t=t(4, 30)),
        dict(expediteur_nom="CERT Santé",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom=admin_user.display_name or "RSSI",
             sujet="📞 Mobilisation experts CERT-Santé",
             contenu=("Notre équipe de réponse aux incidents est mobilisée sur votre dossier. "
                      "Un appel de coordination technique vous sera proposé dans l'heure. "
                      "Préparez : logs SIEM, IOCs identifiés, périmètre d'isolation actuel.\n\n"
                      "L. BERTRAND — Responsable d'astreinte CERT-Santé"),
             ght_source="CERT-SANTE",
             t=t(5, 15)),
        # Messages internes (entre comptes)
        dict(expediteur_nom="K. BELKACEM (RSSI)",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom="Direction",
             sujet="Point de situation isolation réseau",
             contenu=("Isolation effective sur le périmètre serveurs fichiers à 04h45. "
                      "VPN externe coupé. Prochaine étape : analyse forensique avec CERT. "
                      "Plan de récupération sauvegardes en cours d'évaluation."),
             t=t(5, 0)),
        dict(expediteur_nom="Dr. P. MARTIN (Pdt CME)",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom="Cellule de crise",
             sujet="Coordination médicale — pôles impactés",
             contenu=("Réunion CME extraordinaire convoquée à 09h. Pôles impactés : Imagerie, "
                      "Biologie, Urgences. Procédures dégradées affichées dans les services. "
                      "Demande de renforts internes en cours."),
             t=t(7, 30)),
        dict(expediteur_nom="S. LAMBERT (Cadre sup. de garde)",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom="Direction",
             sujet="Urgences — saturation",
             contenu=("Activité urgences en hausse. Mode papier en place. "
                      "Demande renfort 2 IDE depuis pool. Capacité hospitalisation aval saturée. "
                      "Convention Crestval activée pour transferts."),
             t=t(10, 15)),
        # Réponse direction
        dict(expediteur_nom="H. DUBOIS (Direction)",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom="Cadre supérieure de garde",
             sujet="RE: Urgences — saturation",
             contenu=("Validé. Renforts mobilisés depuis pool. Convention Crestval OK. "
                      "Communication interne prévue à 12h. Tenez-moi informée."),
             t=t(10, 30)),
        # J2 — sortie de crise
        dict(expediteur_nom="K. BELKACEM (RSSI)",
             expediteur_id=admin_user.id, destinataire_id=admin_user.id,
             destinataire_nom="Direction",
             sujet="J2 — restauration progressive",
             contenu=("Restauration sauvegardes terminée à 06h. "
                      "DPI accessible en lecture/écriture sur 80% des services. "
                      "PACS partiellement rétabli. Surveillance renforcée maintenue."),
             t=t(7, 0, day=1)),
    ]
    for m in MESSAGES:
        time = m.pop("t")
        msg = MessageInterne(**m)
        db.add(msg); db.flush()
        msg.created_at = time
        MSGS_CREES += 1
    db.commit()
    print(f"  ✓ {MSGS_CREES} messages internes créés (ARS, CERT, cellule, direction)")


# ══════════════════════════════════════════════════════════════
#  RÉCAPITULATIF
# ══════════════════════════════════════════════════════════════
db.close()

print("\n" + "═"*62)
print("  ✅  Scénario de crise injecté avec succès !")
print("═"*62)
print(f"""
  Contenu injecté :
  • {len(incidents_data)} incidents  (J1 02h → J2 22h)
  • {len(PRESENCES)} mouvements cellule de crise
  • {len(DECISIONS)} décisions actées
  • {len(TASKS)} tâches kanban
  • {len(CONSIGNES)} consignes de relève
  • {len(REXES)} fiches REX
  • 1 communiqué public + {len(chrons)} entrées chronologie
  • {len(TRANSFERTS)} transferts patients (avec ETA carte temps réel)
  • {len(BRANCARDAGES)} missions de brancardage interne
  • {len(CAPA_DECL)} déclarations capacitaires (J1 matin/soir + J2 matin)
  • {MSGS_CREES} messages internes (ARS, CERT, cellule, direction)

  ─── DÉMARRAGE ──────────────────────────────────────────
  $ python main.py
  Puis ouvrez : http://localhost:8000

  ─── CONNEXION ──────────────────────────────────────────
  Login    : dircrise
  Mot de passe : Scribe2026!

  ─── POUR TESTER L'ONGLET ANALYSE ───────────────────────
  1. Connectez-vous sur http://localhost:8000
  2. Onglet VEILLE → bouton 📋 EXPORT MAIN COURANTE
  3. Bouton 🔄 NOUVELLE CRISE → archiver → ZIP créé dans archives/
  4. Onglet ANALYSE → glisser le ZIP
  5. Explorer la frise chronologique, poser des questions à Albert
  6. Exporter le rapport DOCX de debriefing

  ─── SCÉNARIO ───────────────────────────────────────────
  Cyberattaque ransomware LockBit sur le CHV Valmont
  Début : {J1_00.strftime('%d/%m/%Y %H:%M')} UTC
  Fin   : {(J1_00+timedelta(hours=46)).strftime('%d/%m/%Y %H:%M')} UTC
  Impact : 5 sites, 8 pôles cliniques, 15 incidents

""")
