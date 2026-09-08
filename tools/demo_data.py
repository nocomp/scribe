#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/demo_data.py — Jeu de donnees de demonstration pour SCRIBE.

A quoi ca sert
--------------
Remplir les instances lancees par lancer_scribe.sh avec un scenario de crise
complet et coherent, pour produire des captures d ecran de presentation sans
jamais toucher a des donnees reelles. Puis tout retirer, proprement.

    python3 tools/demo_data.py --inject      # remplir
    python3 tools/demo_data.py --clean       # revenir a l etat anterieur
    python3 tools/demo_data.py --status      # ou en est-on

Comment le retour arriere est garanti
-------------------------------------
Deux mecanismes superposes, parce qu un seul ne suffit pas :

1. Une sauvegarde complete de chaque base est prise avant toute ecriture, dans
   data/demo_backup/. Le nettoyage restaure ces fichiers : l etat retrouve est
   exactement l etat de depart, y compris pour ce que le script n aurait pas
   prevu.

2. Chaque ligne inseree est enregistree dans une table _scribe_demo_ledger.
   Si la sauvegarde a disparu, le nettoyage supprime ligne par ligne ce qui a
   ete ajoute, sans toucher au reste.

En pratique le mecanisme 1 suffit. Le mecanisme 2 existe parce qu une demo se
prepare souvent dans l urgence et qu on efface parfois le mauvais repertoire.

Ce que le script ne fait pas
----------------------------
Il n ecrit rien dans le collecteur de supervision. Les instances y poussent
elles-memes leur situation toutes les 30 secondes : il suffit qu elles
tournent et que la synchronisation soit active. La carte territoriale, les
niveaux par etablissement et les transferts inter-etablissements apparaissent
donc seuls, une minute apres l injection.

Toutes les donnees sont fictives. Aucun etablissement, aucune commune et
aucune personne reelle n y figure.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import shutil
import sqlite3
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = pathlib.Path(os.environ.get("SCRIBE_DATA_DIR") or (RACINE / "data" / "instances"))
STATE_FILE = pathlib.Path(os.environ.get("SCRIBE_STATE_FILE") or (RACINE / "master" / "master_instances.json"))
BACKUP_DIR = RACINE / "data" / "demo_backup"
LEDGER = "_scribe_demo_ledger"
SAUVE = "_scribe_demo_avant"

PORTS_DEFAUT = list(range(8000, 8008))

# Graine fixe : deux executions produisent le meme jeu de donnees, donc des
# captures reproductibles si une seule slide est a refaire.
RNG = random.Random(20261008)


# ═════════════════════════════════════════════════════════════════════════════
#  Univers fictif
# ═════════════════════════════════════════════════════════════════════════════

# Huit etablissements imaginaires, repartis sur un territoire fictif mais
# geographiquement plausible, afin que la carte et les trajets d ambulance
# aient du sens sans designer un territoire reel.
ETABLISSEMENTS = [
    {"sigle": "CHVAL", "nom": "Centre Hospitalier de Valmont",
     "lat": 47.081, "lon": 2.398, "type": "CH pivot", "lits": 620},
    {"sigle": "CHSTJ", "nom": "Centre Hospitalier Saint-Julien",
     "lat": 47.242, "lon": 2.611, "type": "CH", "lits": 310},
    {"sigle": "CHPLA", "nom": "Centre Hospitalier de Plainville",
     "lat": 46.918, "lon": 2.104, "type": "CH", "lits": 245},
    {"sigle": "HLBEA", "nom": "Hopital Local de Beaucourt",
     "lat": 47.355, "lon": 2.192, "type": "Hopital local", "lits": 88},
    {"sigle": "CHMOR", "nom": "Centre Hospitalier de Morville",
     "lat": 46.774, "lon": 2.549, "type": "CH", "lits": 178},
    {"sigle": "CLARC", "nom": "Clinique des Arcelles",
     "lat": 47.019, "lon": 2.735, "type": "ESPIC", "lits": 132},
    {"sigle": "EHPRE", "nom": "EHPAD Les Pres-Hauts",
     "lat": 47.168, "lon": 2.318, "type": "EHPAD", "lits": 96},
    {"sigle": "CHRIV", "nom": "Centre Hospitalier de Rivelune",
     "lat": 46.860, "lon": 2.812, "type": "CH", "lits": 204},
]

SITES = ["Valmont", "Saint-Julien", "Plainville", "USLD"]

POLES = ["Urgences-Reanimation", "Medecine", "Chirurgie", "Femme-Mere-Enfant",
         "Geriatrie", "Medico-technique", "Psychiatrie"]

# Personnels fictifs. Prenoms et noms courants, aucune personne identifiable.
AGENTS = [
    ("Claire", "Rouvier", "Directrice de crise", "direction"),
    ("Marc", "Delaunay", "RSSI", "dsi"),
    ("Sophie", "Bertholet", "Cadre superieur de sante", "soins"),
    ("Ludovic", "Menard", "Directeur des soins", "soins"),
    ("Nadia", "Kessler", "Coordonnatrice des transferts", "soins"),
    ("Pierre", "Vasseur", "Responsable technique", "technique"),
    ("Helene", "Bonnifay", "Chargee de communication", "communication"),
    ("Thomas", "Reynier", "Praticien urgentiste", "medical"),
    ("Amina", "Ferrand", "Cadre de sante urgences", "soins"),
    ("Julien", "Prevost", "Ingenieur biomedical", "technique"),
    ("Camille", "Aubertin", "Pharmacienne", "medical"),
    ("Olivier", "Sabatier", "Responsable logistique", "logistique"),
]

SERVICES = [
    ("Urgences", "Urgences-Reanimation", 24),
    ("Reanimation polyvalente", "Urgences-Reanimation", 16),
    ("Soins continus", "Urgences-Reanimation", 12),
    ("Medecine polyvalente", "Medecine", 32),
    ("Cardiologie", "Medecine", 24),
    ("Pneumologie", "Medecine", 22),
    ("Chirurgie viscerale", "Chirurgie", 26),
    ("Chirurgie orthopedique", "Chirurgie", 28),
    ("Maternite", "Femme-Mere-Enfant", 20),
    ("Pediatrie", "Femme-Mere-Enfant", 18),
    ("Court sejour geriatrique", "Geriatrie", 30),
    ("SSR polyvalent", "Geriatrie", 40),
]

# Identifiants repris tels quels de app/api/status_page.py : la page publique
# n affiche que les entrees dont l identifiant lui est connu.
SERVICES_SI = [
    {"id": "messagerie",   "label": "Messagerie interne"},
    {"id": "dpi",          "label": "Logiciels metier / DPI"},
    {"id": "pacs",         "label": "Imagerie (PACS / RIS)"},
    {"id": "telephonie",   "label": "Telephonie"},
    {"id": "internet",     "label": "Acces Internet"},
    {"id": "vpn",          "label": "VPN / acces distants"},
    {"id": "applications", "label": "Applications metier"},
]

PRISE_EN_CHARGE = [
    {"id": "urgences",         "label": "Urgences"},
    {"id": "blocs",            "label": "Blocs operatoires"},
    {"id": "consultations",    "label": "Consultations"},
    {"id": "hospitalisations", "label": "Hospitalisations programmees"},
    {"id": "imagerie",         "label": "Imagerie patients"},
    {"id": "laboratoire",      "label": "Laboratoire"},
]

SERVICES_TRANSVERSES = [
    ("securite_physique", "Securite physique", "OK"),
    ("logistique", "Logistique et approvisionnements", "DEGRADE"),
    ("restauration", "Restauration", "OK"),
    ("blanchisserie", "Blanchisserie", "OK"),
    ("informatique", "Systeme d information", "CRITIQUE"),
    ("biomedical", "Biomedical", "DEGRADE"),
    ("transport", "Transport sanitaire", "OK"),
]


def scenario_incidents(sigle, pivot):
    """Incidents adaptes au role de l etablissement dans le scenario.

    L etablissement pivot subit l attaque ; les autres en encaissent les
    consequences. Cela evite le defaut classique des jeux de demonstration ou
    tous les sites affichent exactement la meme chose.
    """
    if pivot:
        return [
            dict(t=-1440, type="CYBER", urg=1, statut="EN_COURS", pct=45,
                 fait="Chiffrement massif detecte sur les serveurs de fichiers. "
                      "Les partages reseau sont inaccessibles depuis 06h12.",
                 analyse="Rancongiciel, vecteur d entree probable via un acces "
                         "distant prestataire non revoque. Propagation stoppee par "
                         "isolation du VLAN serveurs.",
                 moyens="Cellule de crise activee. CERT sectoriel saisi. "
                        "Prestataire d investigation numerique mandate.",
                 actions="Isolation des sous-reseaux, coupure des acces distants, "
                         "bascule des services critiques en procedure degradee.",
                 impact=True, global_=True, soignant=True),
            dict(t=-1425, type="CYBER", urg=1, statut="EN_COURS", pct=30,
                 fait="Dossier patient informatise indisponible sur l ensemble "
                      "des services.",
                 analyse="Serveur applicatif isole par precaution. Restauration "
                         "conditionnee a la validation de l integrite des sauvegardes.",
                 moyens="Procedure papier activee. Impression des dossiers des "
                        "patients hospitalises depuis la derniere sauvegarde saine.",
                 actions="Verification de l integrite des sauvegardes en cours.",
                 impact=True, global_=True, soignant=True),
            dict(t=-1380, type="MIXTE", urg=2, statut="EN_COURS", pct=60,
                 fait="Telephonie sur IP degradee, standard sature.",
                 analyse="Le coeur de reseau telephonique dependait du meme "
                         "socle de virtualisation.",
                 moyens="Lignes analogiques de secours reactivees dans les "
                        "services critiques.",
                 actions="Diffusion des numeros de secours a l ensemble des cadres.",
                 impact=True, global_=False, soignant=True),
            dict(t=-900, type="SANITAIRE", urg=2, statut="EN_COURS", pct=25,
                 fait="Tension capacitaire aux urgences : 14 patients en attente "
                      "d hospitalisation.",
                 analyse="La bascule en mode degrade ralentit les sorties. "
                         "Effet cumulatif attendu sur 48 heures.",
                 moyens="Deprogrammation partielle de l activite reglee. "
                        "Ouverture de 6 lits de tension en medecine.",
                 actions="Point capacitaire toutes les 4 heures.",
                 impact=True, global_=False, soignant=True),
            dict(t=-720, type="MIXTE", urg=3, statut="RESOLU", pct=100,
                 fait="Groupe electrogene du batiment nord en defaut au test "
                      "hebdomadaire.",
                 analyse="Defaut de demarrage lie au circuit de prechauffage.",
                 moyens="Intervention du prestataire de maintenance sous 2 heures.",
                 actions="Piece remplacee, essai en charge concluant.",
                 impact=False, global_=False, soignant=False),
            dict(t=-2880, type="SANITAIRE", urg=4, statut="RESOLU", pct=100,
                 fait="Rupture d approvisionnement sur une solution injectable.",
                 analyse="Tension nationale sur le fournisseur.",
                 moyens="Depannage aupres d un etablissement partenaire.",
                 actions="Protocole de substitution valide par la commission "
                         "du medicament.",
                 impact=False, global_=False, soignant=False, archive=True),
        ]
    return [
        dict(t=-1200, type="SANITAIRE", urg=2, statut="EN_COURS", pct=40,
             fait="Afflux de patients reorientes depuis un etablissement "
                  "voisin en situation degradee.",
             analyse="Augmentation de 35 pour cent des passages aux urgences "
                     "sur 12 heures.",
             moyens="Rappel de deux medecins et trois infirmiers.",
             actions="Ouverture des lits de tension niveau 1.",
             impact=True, global_=False, soignant=True),
        dict(t=-960, type="MIXTE", urg=3, statut="EN_COURS", pct=55,
             fait="Liaison de messagerie securisee avec l etablissement pivot "
                  "interrompue.",
             analyse="Coupure volontaire cote pivot pour confinement.",
             moyens="Bascule sur la messagerie de la plateforme territoriale.",
             actions="Point de situation telephonique toutes les 2 heures.",
             impact=False, global_=False, soignant=False),
        dict(t=-600, type="SANITAIRE", urg=3, statut="EN_COURS", pct=20,
             fait="Tension sur les effectifs de nuit en medecine.",
             analyse="Deux arrets maladie non remplaces.",
             moyens="Chaine d alerte declenchee sur le pole.",
             actions="Trois reponses positives, renfort couvert.",
             impact=False, global_=False, soignant=True),
        dict(t=-2400, type="MIXTE", urg=4, statut="RESOLU", pct=100,
             fait="Ascenseur du batiment principal immobilise.",
             analyse="Defaut de porte palier au troisieme etage.",
             moyens="Prestataire intervenu dans la journee.",
             actions="Remise en service apres controle.",
             impact=False, global_=False, soignant=True),
    ]


TACHES = [
    ("Isoler les sous-reseaux serveurs", "TERMINE", 4, "Marc Delaunay"),
    ("Notifier le CERT sectoriel", "TERMINE", 4, "Marc Delaunay"),
    ("Activer la procedure papier dans tous les services", "TERMINE", 4, "Sophie Bertholet"),
    ("Verifier l integrite des sauvegardes", "EN_COURS", 4, "Marc Delaunay"),
    ("Imprimer les dossiers des patients hospitalises", "EN_COURS", 3, "Amina Ferrand"),
    ("Recenser les equipements biomedicaux connectes", "EN_COURS", 3, "Julien Prevost"),
    ("Preparer le communique a destination des familles", "EN_ATTENTE", 2, "Helene Bonnifay"),
    ("Organiser la deprogrammation de l activite reglee", "EN_COURS", 3, "Ludovic Menard"),
    ("Etablir la liste des transferts prioritaires", "EN_COURS", 4, "Nadia Kessler"),
    ("Reactiver les lignes telephoniques de secours", "TERMINE", 3, "Pierre Vasseur"),
    ("Recenser les stocks de pharmacie critique", "BACKLOG", 2, "Camille Aubertin"),
    ("Preparer le point de situation de 18h00", "BACKLOG", 2, "Claire Rouvier"),
    ("Organiser la releve de la cellule de crise", "BACKLOG", 2, "Claire Rouvier"),
    ("Contacter les prestataires de transport sanitaire", "TERMINE", 3, "Olivier Sabatier"),
]

DECISIONS = [
    ("Activation du plan blanc a compter de 07h00.", "Claire Rouvier", "Plan Blanc"),
    ("Deprogrammation de l activite chirurgicale reglee pour 48 heures.",
     "Ludovic Menard", "Plan Blanc"),
    ("Coupure de l ensemble des acces distants prestataires.",
     "Marc Delaunay", "PSSI etablissement"),
    ("Bascule des services critiques en procedure papier.",
     "Sophie Bertholet", "Plan de continuite"),
    ("Ouverture de 12 lits de tension repartis sur trois services.",
     "Ludovic Menard", "Plan Blanc"),
    ("Information de l autorite de tutelle et depot de plainte.",
     "Claire Rouvier", "Obligation reglementaire"),
]

CONSIGNES = [
    ("Equipe de nuit",
     "Poursuivre la saisie papier. Ne rebrancher aucun poste sur le reseau "
     "sans validation du RSSI. Point de situation a 02h00."),
    ("Cadres de garde",
     "Remonter tout dysfonctionnement d equipement biomedical connecte "
     "directement au biomedical de garde, sans passer par le standard."),
    ("Urgences",
     "Maintenir le circuit de reorientation vers les etablissements "
     "partenaires. Tracer chaque reorientation sur le registre papier."),
    ("Pharmacie",
     "Delivrance nominative suspendue. Dotation par service selon le "
     "protocole degrade. Tracabilite papier obligatoire."),
    ("Standard",
     "Utiliser exclusivement les lignes de secours. La liste des numeros "
     "est affichee en salle de crise et au poste de securite."),
]

MESSAGES = [
    ("Point de situation 08h00",
     "Cellule de crise reunie depuis 06h45. Perimetre confirme : serveurs de "
     "fichiers et dossier patient. Aucun impact sur les dispositifs medicaux "
     "a ce stade. Prochain point a 12h00."),
    ("Procedure degradee - rappel",
     "Les fiches papier sont disponibles dans chaque poste de soins. En cas "
     "de rupture de stock, contacter la logistique par les lignes de secours."),
    ("Renforts de nuit",
     "Trois reponses positives sur la chaine d alerte du pole medecine. "
     "Couverture assuree jusqu a 06h00."),
    ("Transferts en cours",
     "Deux transferts vers les etablissements partenaires sont partis. "
     "Un troisieme est en preparation, depart estime dans 40 minutes."),
    ("Communique presse",
     "Le projet de communique est pret. Validation de la direction attendue "
     "avant diffusion."),
    ("Retour du prestataire d investigation",
     "Premiers elements en fin de journee. Aucune exfiltration de donnees "
     "confirmee a ce stade, investigation en cours."),
    ("Capacitaire - point de 14h00",
     "Quatorze patients en attente d hospitalisation aux urgences. Six lits "
     "de tension ouverts en medecine, quatre en chirurgie."),
    ("Reunion de coordination territoriale",
     "Visioconference avec les etablissements partenaires a 17h00. Ordre du "
     "jour : capacites d accueil et transferts prioritaires."),
]

TRANSFERTS = [
    dict(t=-180, statut="ARRIVE", origine="Reanimation polyvalente",
         dest="Reanimation", eta_min=45,
         com="Patient stable, transfert programme."),
    # Les deux transferts EN_COURS sont volontairement calibres pour que
    # l ambulance soit a mi-parcours au moment de la capture : depart passe,
    # heure d arrivee estimee encore dans le futur.
    dict(t=-25, statut="EN_COURS", origine="Urgences",
         dest="Soins continus", eta_min=55,
         com="Surveillance continue pendant le transport."),
    dict(t=-40, statut="EN_COURS", origine="Medecine polyvalente",
         dest="Medecine", eta_min=75,
         com="Transfert pour poursuite de prise en charge."),
    dict(t=-15, statut="EN_PREPARATION", origine="Chirurgie viscerale",
         dest="Chirurgie", eta_min=60,
         com="Attente de confirmation du lit d aval."),
    dict(t=-300, statut="ARRIVE", origine="Court sejour geriatrique",
         dest="SSR polyvalent", eta_min=30,
         com="Transfert realise sans incident."),
    dict(t=-260, statut="ANNULE", origine="Pediatrie",
         dest="Pediatrie", eta_min=40,
         com="Annule : amelioration clinique, maintien sur site."),
]

MAIN_COURANTE = [
    ("INCIDENT", "CREE", "Incident CYBER declare : chiffrement des serveurs de fichiers", "CRITIQUE"),
    ("CONNEXION", "OUVERTURE", "Ouverture de la cellule de crise", "WARN"),
    ("DECISION", "VALIDEE", "Activation du plan blanc", "CRITIQUE"),
    ("KANBAN", "CREE", "Creation de 8 taches de remediation", "INFO"),
    ("INCIDENT", "MODIFIE", "Perimetre etendu : dossier patient informatise", "CRITIQUE"),
    ("DECISION", "VALIDEE", "Coupure des acces distants prestataires", "WARN"),
    ("MESSAGE", "ENVOYE", "Diffusion de la procedure degradee a tous les cadres", "INFO"),
    ("KANBAN", "TERMINEE", "Isolation des sous-reseaux serveurs", "INFO"),
    ("NOTIFICATION", "ENVOYEE", "Notification au CERT sectoriel", "WARN"),
    ("TRANSFERT", "CREE", "Transfert vers etablissement partenaire", "INFO"),
    ("DECISION", "VALIDEE", "Deprogrammation de l activite reglee", "WARN"),
    ("MESSAGE", "RECU", "Accuse de reception de l autorite de tutelle", "INFO"),
    ("INCIDENT", "CREE", "Telephonie sur IP degradee", "WARN"),
    ("KANBAN", "TERMINEE", "Reactivation des lignes de secours", "INFO"),
    ("RELEVE", "CREE", "Consigne transmise a l equipe de nuit", "INFO"),
    ("TRANSFERT", "MODIFIE", "Transfert passe en statut EN_COURS", "INFO"),
    ("MESSAGE", "ENVOYE", "Point de situation de 12h00 diffuse", "INFO"),
    ("INCIDENT", "MODIFIE", "Tension capacitaire aux urgences signalee", "WARN"),
    ("DECISION", "VALIDEE", "Ouverture de 12 lits de tension", "WARN"),
    ("KANBAN", "MODIFIEE", "Verification des sauvegardes en cours", "INFO"),
    ("NOTIFICATION", "ENVOYEE", "Chaine d alerte declenchee sur le pole medecine", "WARN"),
    ("TRANSFERT", "TERMINE", "Transfert arrive a destination", "INFO"),
    ("MESSAGE", "ENVOYE", "Communique aux familles soumis a validation", "INFO"),
    ("CONNEXION", "RELEVE", "Releve de la cellule de crise", "INFO"),
    ("INCIDENT", "RESOLU", "Groupe electrogene remis en service", "INFO"),
    ("KANBAN", "CREE", "Recensement des equipements biomedicaux connectes", "INFO"),
    ("MESSAGE", "RECU", "Reponse d un etablissement partenaire : 4 lits disponibles", "INFO"),
    ("DECISION", "VALIDEE", "Depot de plainte engage", "WARN"),
]

REX = [
    dict(titre="Retour d experience - incident cyber majeur",
         type_crise="CYBER", duree=2880, poles=6, decisions=6,
         jalons_total=14, jalons_done=11, mttd=95, mttr=1740,
         positifs="Cellule de crise reunie en moins de 45 minutes. "
                  "Procedure papier deja imprimee et distribuee dans les services. "
                  "Coordination territoriale efficace pour les transferts.",
         amelio="Delai de detection trop long : 95 minutes entre les premiers "
                "signaux et la declaration. Annuaire de crise partiellement obsolete. "
                "Aucun exercice n avait ete joue depuis 2024.",
         actions="Mettre en place une supervision des volumes de chiffrement. "
                 "Mettre a jour l annuaire tous les trimestres. "
                 "Programmer un exercice semestriel a partir du prochain trimestre.",
         lecons="Le mode degrade fonctionne quand il a ete repete. Les services "
                "qui avaient participe au dernier exercice ont bascule en vingt "
                "minutes ; les autres ont mis plus de trois heures."),
    dict(titre="Retour d experience - tension capacitaire hivernale",
         type_crise="SANITAIRE", duree=5760, poles=4, decisions=3,
         jalons_total=9, jalons_done=9, mttd=40, mttr=5400,
         positifs="Anticipation par le suivi capacitaire quotidien. "
                  "Ouverture des lits de tension fluide.",
         amelio="Coordination des sorties trop lente le week-end.",
         actions="Renforcer la presence d assistantes sociales le samedi.",
         lecons="Le point capacitaire de 14h00 est le plus utile de la journee."),
]

DEMANDES_GHT = [
    ("transfert", "Reanimation",
     "Recherche de 2 places de reanimation adulte dans les 6 heures. "
     "Patients stables, transport SMUR possible.", "transmis",
     "2 places confirmees, coordination directe avec le cadre de garde."),
    ("ressources", "Pharmacie",
     "Depannage en solutes de remplissage pour 48 heures.", "traite",
     "Livraison effectuee. Reapprovisionnement prevu sous 72 heures."),
    ("cyber", None,
     "Demande de partage d indicateurs de compromission avec les "
     "etablissements du territoire.", "en_attente", None),
]

COMMUNIQUES = [
    ("Information aux patients et aux familles",
     "Notre etablissement fait face depuis ce matin a un incident informatique "
     "majeur. La continuite des soins est assuree. Les prises en charge urgentes "
     "sont maintenues sans restriction. Les consultations non urgentes sont "
     "reportees et seront reprogrammees. Nous vous remercions de votre "
     "comprehension."),
    ("Information aux professionnels adresseurs",
     "Les admissions programmees sont suspendues jusqu a nouvel ordre. Les "
     "urgences vitales sont accueillies normalement. Merci de privilegier un "
     "contact telephonique prealable via les lignes de secours."),
]


# ═════════════════════════════════════════════════════════════════════════════
#  Infrastructure
# ═════════════════════════════════════════════════════════════════════════════

MAINTENANT = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def horodatage(minutes_avant):
    """Horodatage UTC naif, au format attendu par SQLAlchemy/SQLite."""
    d = MAINTENANT - dt.timedelta(minutes=minutes_avant)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f")


def iso_court(minutes_apres):
    d = MAINTENANT + dt.timedelta(minutes=minutes_apres)
    return d.strftime("%Y-%m-%dT%H:%M")


class Base:
    """Acces a une base d instance, avec journal des insertions.

    Toutes les ecritures passent par inserer(), qui filtre les colonnes selon
    le schema reellement present. Le script survit ainsi a l ajout ou au
    retrait d une colonne, et aux plugins desactives dont les tables n existent
    pas.
    """

    def __init__(self, chemin, sigle):
        self.chemin = pathlib.Path(chemin)
        self.sigle = sigle
        self.cx = sqlite3.connect(str(chemin), timeout=15)
        self.cx.execute("PRAGMA busy_timeout = 15000")
        self._colonnes = {}
        self.compte = {}
        self.ignores = []
        self.cx.execute(
            "CREATE TABLE IF NOT EXISTS %s "
            "(tbl TEXT NOT NULL, rid INTEGER NOT NULL)" % LEDGER
        )
        self.cx.execute(
            "CREATE TABLE IF NOT EXISTS %s "
            "(tbl TEXT, rid INTEGER, col TEXT, val BLOB)" % SAUVE
        )
        self.cx.commit()

    def ecraser(self, table, rid, valeurs):
        """Modifie une ligne existante en memorisant les valeurs d origine.

        Sans cela, le nettoyage par journal laisserait en place des donnees de
        demonstration ecrites par-dessus des lignes preexistantes : la page de
        statut public ou les coordonnees de l etablissement, par exemple.
        """
        if not self.existe(table):
            return
        cols = self.colonnes(table)
        retenu = {k: v for k, v in valeurs.items() if k in cols}
        if not retenu:
            return
        champs = ", ".join(retenu)
        ligne = self.cx.execute(
            "SELECT %s FROM %s WHERE id = ?" % (champs, table), (rid,)
        ).fetchone()
        if ligne:
            for i, col in enumerate(retenu):
                self.cx.execute(
                    "INSERT INTO %s VALUES (?,?,?,?)" % SAUVE,
                    (table, rid, col, ligne[i]),
                )
        sets = ", ".join("%s = ?" % k for k in retenu)
        self.cx.execute(
            "UPDATE %s SET %s WHERE id = ?" % (table, sets),
            list(retenu.values()) + [rid],
        )
        self.compte[table + " (maj)"] = self.compte.get(table + " (maj)", 0) + 1

    # ── introspection ────────────────────────────────────────────────────
    def existe(self, table):
        cur = self.cx.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        return cur.fetchone() is not None

    def colonnes(self, table):
        if table not in self._colonnes:
            self._colonnes[table] = {
                r[1] for r in self.cx.execute("PRAGMA table_info(%s)" % table)
            }
        return self._colonnes[table]

    def vide(self, table):
        if not self.existe(table):
            return True
        n = self.cx.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
        return n == 0

    # ── ecriture ─────────────────────────────────────────────────────────
    def inserer(self, table, valeurs):
        """Insere une ligne et l enregistre au journal. Retourne l id, ou None
        si la table n existe pas (plugin desactive)."""
        if not self.existe(table):
            return None
        cols = self.colonnes(table)
        retenu = {k: v for k, v in valeurs.items() if k in cols}
        if not retenu:
            return None
        champs = ", ".join(retenu)
        trous = ", ".join("?" for _ in retenu)
        try:
            cur = self.cx.execute(
                "INSERT INTO %s (%s) VALUES (%s)" % (table, champs, trous),
                list(retenu.values()),
            )
        except sqlite3.Error as exc:
            # Le schema d une table de plugin a pu evoluer. On note et on
            # continue : une ligne manquante vaut mieux qu une injection
            # interrompue au milieu.
            self.ignores.append("%s : %s" % (table, exc))
            return None
        rid = cur.lastrowid
        self.cx.execute("INSERT INTO %s VALUES (?,?)" % LEDGER, (table, rid))
        self.compte[table] = self.compte.get(table, 0) + 1
        return rid

    def maj(self, table, rid, valeurs):
        if not self.existe(table):
            return
        cols = self.colonnes(table)
        retenu = {k: v for k, v in valeurs.items() if k in cols}
        if not retenu:
            return
        sets = ", ".join("%s = ?" % k for k in retenu)
        self.cx.execute(
            "UPDATE %s SET %s WHERE id = ?" % (table, sets),
            list(retenu.values()) + [rid],
        )

    def valider(self):
        self.cx.commit()

    def fermer(self):
        self.cx.commit()
        self.cx.close()

    # ── journal ──────────────────────────────────────────────────────────
    def lignes_demo(self):
        return list(self.cx.execute("SELECT tbl, rid FROM %s" % LEDGER))

    def purger_journal(self):
        n = 0
        for tbl, rid in reversed(self.lignes_demo()):
            if self.existe(tbl):
                try:
                    self.cx.execute("DELETE FROM %s WHERE id = ?" % tbl, (rid,))
                    n += 1
                except sqlite3.Error:
                    pass
        # Restauration des valeurs ecrasees, avant de vider le journal.
        try:
            for tbl, rid, col, val in self.cx.execute(
                    "SELECT tbl, rid, col, val FROM %s" % SAUVE):
                if self.existe(tbl):
                    self.cx.execute(
                        "UPDATE %s SET %s = ? WHERE id = ?" % (tbl, col), (val, rid)
                    )
                    n += 1
        except sqlite3.Error:
            pass
        # Les deux tables techniques sont supprimees : la base retrouve
        # exactement la forme qu elle avait avant l injection.
        self.cx.execute("DROP TABLE IF EXISTS %s" % LEDGER)
        self.cx.execute("DROP TABLE IF EXISTS %s" % SAUVE)
        self.cx.commit()
        return n


def _collecter(obj, sortie):
    """Parcourt recursivement la structure et ramasse tout dictionnaire
    ressemblant a une configuration d instance.

    master_instances.json a pris au moins quatre formes selon les versions :
    dictionnaire indexe par port, liste d objets, liste de paires, et
    dictionnaire contenant une liste sous une clef. Plutot que d enumerer les
    cas, on descend dans la structure et on ramasse ce qui a un port.
    """
    if isinstance(obj, dict):
        if "port" in obj:
            sortie.append(obj)
        cfg = obj.get("config")
        if isinstance(cfg, dict) and "port" in cfg:
            sortie.append(cfg)
        for v in obj.values():
            _collecter(v, sortie)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collecter(v, sortie)


def instances(ports):
    """Instances a traiter, dans l ordre des ports demandes.

    On croise l etat du master avec ce qui existe reellement sur le disque.
    Si l etat est illisible ou incomplet, les repertoires de donnees restants
    sont attribues aux ports encore libres, dans l ordre alphabetique.
    """
    par_port = {}

    if STATE_FILE.exists():
        try:
            brut = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            trouves = []
            _collecter(brut, trouves)
            for e in trouves:
                try:
                    port = int(e.get("port"))
                except (TypeError, ValueError):
                    continue
                sigle = str(e.get("sigle") or "").strip()
                if port in ports and sigle and port not in par_port:
                    par_port[port] = sigle
        except Exception as exc:
            print("  Lecture de %s impossible (%s), balayage du disque."
                  % (STATE_FILE.name, exc))

    # Repertoires de donnees reellement presents
    dossiers = []
    if DATA_DIR.exists():
        for d in sorted(DATA_DIR.iterdir()):
            if (d / "scribe.db").exists():
                dossiers.append(d)

    resultat = []
    utilises = set()

    # 1er passage : les ports dont le sigle est connu et le repertoire present
    for port in ports:
        sigle = par_port.get(port)
        if not sigle:
            continue
        db = DATA_DIR / sigle / "scribe.db"
        if db.exists():
            resultat.append((port, sigle, db))
            utilises.add(db.parent)

    # 2e passage : les repertoires restants vont aux ports encore libres.
    # Le port affiche est alors indicatif ; le sigle, lui, est exact.
    libres = [p for p in ports if p not in {r[0] for r in resultat}]
    restants = [d for d in dossiers if d not in utilises]
    for port, d in zip(libres, restants):
        resultat.append((port, d.name, d / "scribe.db"))

    resultat.sort(key=lambda r: r[0])
    return resultat


def lire_config_js(db):
    """Lit le config.js voisin de la base : sigle, nom, URL du collecteur et
    jeton de federation. C est le fichier que federation.py consulte lui-meme,
    donc la source de verite pour parler au collecteur."""
    chemin = pathlib.Path(db).parent / "config.js"
    if not chemin.is_file():
        return {}
    try:
        brut = chemin.read_text(encoding="utf-8")
        i = brut.index("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
        cfg = json.loads(brut[i:brut.rindex(";")])
    except Exception:
        return {}
    etb = cfg.get("etablissement", {}) or {}
    fed = cfg.get("federation", {}) or {}
    return {
        "sigle": (etb.get("sigle") or "").strip(),
        "nom": (etb.get("nom") or "").strip(),
        "collecteur_url": (fed.get("collecteur_url") or "").strip(),
        "token": (fed.get("token") or "").strip(),
        "enabled": str(fed.get("enabled", "false")).lower() == "true",
    }


def sauvegarder(db, sigle):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    cible = BACKUP_DIR / ("%s.scribe.db" % sigle)
    shutil.copy2(db, cible)
    for suffixe in ("-wal", "-shm"):
        annexe = pathlib.Path(str(db) + suffixe)
        if annexe.exists():
            shutil.copy2(annexe, str(cible) + suffixe)
    return cible


def restaurer(db, sigle):
    source = BACKUP_DIR / ("%s.scribe.db" % sigle)
    if not source.exists():
        return False
    shutil.copy2(source, db)
    for suffixe in ("-wal", "-shm"):
        annexe = pathlib.Path(str(source) + suffixe)
        cible = pathlib.Path(str(db) + suffixe)
        if annexe.exists():
            shutil.copy2(annexe, cible)
        elif cible.exists():
            cible.unlink()
    try:
        os.chmod(db, 0o600)
    except OSError:
        pass
    return True


def hash_mdp(mot_de_passe):
    """Empreinte bcrypt si la bibliotheque est la, sinon aucun compte n est
    cree. On ne fabrique jamais d empreinte de secours : un compte de demo
    avec un hachage faible finirait par se retrouver dans une installation
    reelle."""
    try:
        import bcrypt
        return bcrypt.hashpw(mot_de_passe.encode(), bcrypt.gensalt()).decode()
    except Exception:
        try:
            from passlib.hash import bcrypt as pl_bcrypt
            return pl_bcrypt.hash(mot_de_passe)
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════════════════
#  Injection
# ═════════════════════════════════════════════════════════════════════════════

def remplir(b, rang, port, mdp_demo, voisins=None, identite=None):
    """Remplit une base. `rang` fixe le role de l etablissement dans le
    scenario : le premier est celui qui subit l attaque."""
    pivot = (rang == 0)

    # Identite : celle de l instance, pas celle du catalogue fictif. Un
    # transfert emis par un sigle inconnu du territoire n est resolu ni sur la
    # carte des instances, ni sur celle de la supervision : ni marqueur, ni
    # trajectoire, ni ambulance. Le catalogue ne sert plus que de repli pour
    # les coordonnees quand l instance n en a pas.
    repli = ETABLISSEMENTS[rang % len(ETABLISSEMENTS)]
    ident = {
        "sigle": (identite or {}).get("sigle") or repli["sigle"],
        "nom": (identite or {}).get("nom") or repli["nom"],
        "lat": repli["lat"], "lon": repli["lon"],
    }

    # ── Etablissement et unites ──────────────────────────────────────────
    hid = None
    if b.existe("hospitals"):
        ligne = b.cx.execute("SELECT id, latitude, longitude FROM hospitals LIMIT 1").fetchone()
        if ligne:
            hid = ligne[0]
            # Coordonnees renseignees seulement si absentes : on ne deplace pas
            # un etablissement deja positionne par l administrateur. L ancienne
            # valeur est memorisee pour que le nettoyage par journal restaure
            # exactement l etat de depart, sans dependre de la sauvegarde.
            if not ligne[1] or not ligne[2]:
                b.ecraser("hospitals", hid,
                          {"latitude": ident["lat"], "longitude": ident["lon"]})
        else:
            hid = b.inserer("hospitals", {
                "nom": ident["nom"], "latitude": ident["lat"],
                "longitude": ident["lon"],
                "adresse": "Rue des Hospices, %s" % ident["sigle"],
                "telephone_garde": "0X XX XX XX XX",
            })

    if b.vide("unites_fonctionnelles") and hid:
        for i, (nom, pole, _cap) in enumerate(SERVICES):
            b.inserer("unites_fonctionnelles", {
                "code_uf": "UF%03d" % (100 + i), "libelle": nom,
                "pole": pole, "hospital_id": hid, "actif": 1,
            })

    # ── Comptes ──────────────────────────────────────────────────────────
    if b.existe("users") and mdp_demo:
        h = hash_mdp(mdp_demo)
        if h:
            existants = {r[0] for r in b.cx.execute("SELECT username FROM users")}
            for prenom, nom, fonction, _svc in AGENTS[:8]:
                login = ("%s.%s" % (prenom[0], nom)).lower()
                if login in existants:
                    continue
                role = "admin" if fonction.startswith("Directrice") else (
                    "soignant" if "sante" in fonction or "Coordonnatrice" in fonction
                    else "cellule_crise")
                b.inserer("users", {
                    "username": login,
                    "display_name": "%s %s" % (prenom, nom),
                    "role": role, "hashed_password": h,
                    "perimetre": fonction, "active": 1,
                    "must_change_password": 0,
                    "created_at": horodatage(4320),
                })

    # ── Capacite ─────────────────────────────────────────────────────────
    # Si l instance possede deja son referentiel capacitaire, on s y rattache
    # au lieu d en creer un second : sinon la vue capacite affiche les vrais
    # services en « Non declare » et les services de demonstration a cote.
    refs = []
    if b.existe("capacite_referentiel"):
        existants = list(b.cx.execute(
            "SELECT id, service_nom, capacite_totale FROM capacite_referentiel"
        ))
        if existants:
            refs = [(r[0], r[1], r[2] or 20) for r in existants]
        else:
            for i, (nom, pole, cap) in enumerate(SERVICES):
                site = SITES[i % len(SITES)]
                rid = b.inserer("capacite_referentiel", {
                    "service_nom": nom, "uf_code": "UF%03d" % (100 + i),
                    "pole": pole, "site": site, "capacite_totale": cap,
                    "tension_1": max(2, cap // 8), "tension_2": max(4, cap // 5),
                    "accept_homme": 1, "accept_femme": 1, "accept_indiffer": 1,
                    "telephone_cadre": "poste %d" % (4000 + i),
                    "ordre_affichage": i, "actif": 1,
                })
                if rid:
                    refs.append((rid, nom, cap))

    for idx, (rid, nom, cap) in enumerate(refs):
        # Repartition volontairement contrastee : sans tension visible, une
        # capture de la vue capacitaire ne montre rien d interessant.
        if pivot and idx < 3:
            statut, tension, alerte = "critique", 2, 1
        elif idx % 4 == 0:
            statut, tension, alerte = "tension", 1, 1
        else:
            statut, tension, alerte = "normal", 0, 0
        libres = max(0, (cap // 10) - (3 if statut == "critique" else 0))
        for point, decalage in (("matin", 480), ("aprem", 240), ("soir", 30)):
            b.inserer("capacite_declarations", {
                "referentiel_id": rid, "horodatage": horodatage(decalage),
                "redacteur": AGENTS[(idx + 2) % len(AGENTS)][0] + " "
                             + AGENTS[(idx + 2) % len(AGENTS)][1],
                "point": point,
                "lits_vides_h": max(0, libres - 1), "lits_vides_f": libres,
                "lits_vides_i": max(0, libres - 2),
                "tension_activee": tension,
                "lits_sup": 4 if tension else 0,
                "statut_lits": statut,
                "statut_rh": "tension" if alerte else "complet",
                "statut_materiel": "degrade" if (pivot and idx < 2) else "ok",
                "alerte_lits": alerte, "alerte_rh": alerte,
                "alerte_materiel": 1 if (pivot and idx < 2) else 0,
                "commentaire_lits": "Aucune sortie prevue avant demain matin."
                                    if alerte else None,
                "commentaire_rh": "Deux postes non couverts sur la nuit."
                                  if alerte else None,
                "commentaire_general": "Point transmis a la cellule de crise."
                                       if point == "soir" else None,
                "mode_degrade": 1 if (pivot and idx < 3) else 0,
                "besoin_renfort": 2 if alerte else 0,
                "peut_preter": 0 if alerte else 1,
            })

    if b.existe("capacite_medicotech"):
        b.inserer("capacite_medicotech", {
            "site_id": SITES[0],
            "blocs_total": 8, "blocs_operationnels": 3 if pivot else 7,
            "blocs_commentaire": "Activite reglee deprogrammee, urgences seules."
                                 if pivot else "Fonctionnement nominal.",
            "dialyse_postes_total": 12,
            "dialyse_postes_actifs": 8 if pivot else 12,
            "dialyse_sessions_24h": 21 if pivot else 34,
            "dialyse_commentaire": "Seances reparties sur trois vacations."
                                   if pivot else None,
            "pharmacie_statut": "degrade" if pivot else "normal",
            "pharmacie_urgences_vitales": 1,
            "pharmacie_commentaire": "Delivrance nominative suspendue, dotation "
                                     "par service." if pivot else None,
            "updated_by": "Camille Aubertin",
            "updated_at": horodatage(120),
        })

    # ── Services transverses ─────────────────────────────────────────────
    if b.existe("service_status"):
        deja = {r[0] for r in b.cx.execute("SELECT service_id FROM service_status")}
        for sid, libelle, statut in SERVICES_TRANSVERSES:
            if sid in deja:
                continue
            b.inserer("service_status", {
                "service_id": sid, "libelle": libelle,
                "statut": statut if pivot else "OK",
                "commentaire": "Mode degrade actif." if (pivot and statut != "OK") else None,
                "updated_at": horodatage(90),
            })

    # ── Incidents, taches, notifications ─────────────────────────────────
    incidents = []
    for inc in scenario_incidents(ident["sigle"], pivot):
        iid = b.inserer("sitrep_entries", {
            "timestamp": horodatage(-inc["t"]),
            "declarant_nom": AGENTS[1][0] + " " + AGENTS[1][1],
            "directeur_crise": AGENTS[0][0] + " " + AGENTS[0][1],
            "site_id": SITES[0],
            "unite_fonctionnelle": SERVICES[RNG.randrange(len(SERVICES))][0],
            "type_crise": inc["type"], "urgency": inc["urg"],
            "fait": inc["fait"], "analyse": inc["analyse"],
            "moyens_engages": inc["moyens"],
            "actions_remediation": inc["actions"],
            "intervenant_nom": AGENTS[RNG.randrange(len(AGENTS))][0] + " "
                               + AGENTS[RNG.randrange(len(AGENTS))][1],
            "intervenant_contact": "poste %d" % (4100 + RNG.randrange(60)),
            "status": inc["statut"], "completion_percent": inc["pct"],
            "resolved_at": horodatage(-inc["t"] - 240) if inc["statut"] == "RESOLU" else None,
            "archived": 1 if inc.get("archive") else 0,
            "archived_at": horodatage(-inc["t"] - 300) if inc.get("archive") else None,
            "impact_fonctionnel": 1 if inc["impact"] else 0,
            "visible_soignant": 1 if inc["soignant"] else 0,
            "impact_global": 1 if inc["global_"] else 0,
        })
        if iid:
            incidents.append(iid)

    taches = TACHES if pivot else TACHES[4:11]
    for i, (titre, colonne, prio, assignee) in enumerate(taches):
        b.inserer("tasks", {
            "incident_id": incidents[i % len(incidents)] if incidents else None,
            "titre": titre,
            "description": "Tache issue du plan d action de la cellule de crise.",
            "assignee": assignee, "priorite": prio, "colonne": colonne,
            "created_at": horodatage(1400 - i * 45),
            "updated_at": horodatage(200 - i * 5),
            "due_at": horodatage(-360 - i * 60),
        })

    if b.existe("notifications") and b.existe("users"):
        uids = [r[0] for r in b.cx.execute("SELECT id FROM users LIMIT 5")]
        titres = [
            ("Incident critique declare", "INCIDENT"),
            ("Nouvelle tache assignee", "TACHE"),
            ("Point de situation disponible", "SYSTEME"),
            ("Transfert en attente de validation", "SYSTEME"),
            ("Consigne de releve a accuser", "SYSTEME"),
        ]
        for i, (titre, typ) in enumerate(titres):
            if not uids:
                break
            b.inserer("notifications", {
                "user_id": uids[i % len(uids)],
                "timestamp": horodatage(300 - i * 40),
                "titre": titre,
                "message": "Consulter l onglet correspondant pour le detail.",
                "type_notif": typ,
                "incident_id": incidents[0] if incidents else None,
                "lu": 1 if i > 2 else 0,
            })

    # ── Decisions, presences, consignes ──────────────────────────────────
    for i, (contenu, resp, base_reg) in enumerate(DECISIONS if pivot else DECISIONS[:3]):
        b.inserer("decisions", {
            "timestamp": horodatage(1400 - i * 120), "contenu": contenu,
            "responsable": resp, "base_reglementaire": base_reg,
            "statut_validation": "VALIDE",
        })

    for i, (prenom, nom, fonction, _s) in enumerate(AGENTS[:8]):
        b.inserer("presences", {
            "timestamp": horodatage(1420 - i * 12),
            "nom": "%s %s" % (prenom, nom), "role": fonction,
            "action": "ARRIVEE" if i < 6 else "DEPART",
        })

    for i, (pour, texte) in enumerate(CONSIGNES if pivot else CONSIGNES[:3]):
        accuse = 1 if i < 2 else 0
        b.inserer("consignes", {
            "timestamp": horodatage(400 - i * 55), "pour": pour, "texte": texte,
            "accuse": accuse,
            "accuse_at": horodatage(300 - i * 40) if accuse else None,
            "accuse_par": AGENTS[i % len(AGENTS)][0] if accuse else None,
        })

    # ── Main courante ────────────────────────────────────────────────────
    entrees = MAIN_COURANTE if pivot else MAIN_COURANTE[8:22]
    for i, (cat, action, detail, niveau) in enumerate(entrees):
        agent = AGENTS[i % len(AGENTS)]
        b.inserer("main_courante_logs", {
            "timestamp": horodatage(1440 - i * (1380 // max(1, len(entrees)))),
            "auteur": "%s %s" % (agent[0], agent[1]), "auteur_role": agent[2],
            "categorie": cat, "action": action, "detail": detail,
            "site": SITES[i % len(SITES)], "niveau": niveau,
        })

    # ── Transferts ───────────────────────────────────────────────────────
    # Les destinations doivent designer de VRAIES instances du territoire :
    # un transfert vers un sigle inconnu du collecteur reste invisible sur la
    # carte de supervision, faute de coordonnees a resoudre.
    if voisins:
        autres = [{"sigle": sg, "nom": nm} for sg, nm in voisins]
    else:
        autres = [e for e in ETABLISSEMENTS if e["sigle"] != ident["sigle"]]
    for i, tr in enumerate(TRANSFERTS if pivot else TRANSFERTS[:3]):
        cible = autres[i % len(autres)]
        depart = horodatage(-tr["t"]) if tr["statut"] != "EN_PREPARATION" else None
        arrivee = horodatage(-tr["t"] - tr["eta_min"]) if tr["statut"] == "ARRIVE" else None
        b.inserer("transferts_patients", {
            # Donnees patient volontairement neutres : elles ne quittent jamais
            # l instance, mais une capture d ecran, elle, circule.
            "nom": "PATIENT", "prenom": "Demo %d" % (i + 1),
            "ipp": "DEMO%05d" % (10000 + i * 7),
            "date_naissance": "19%02d-%02d-%02d" % (50 + i * 3, 1 + i % 12, 1 + i % 28),
            "unite_origine": tr["origine"],
            "etablissement_origine": ident["sigle"],
            "unite_destination": tr["dest"],
            "etablissement_destination": cible["sigle"],
            "site_destination": cible["nom"],
            "statut": tr["statut"],
            "horodatage_creation": horodatage(-tr["t"] + 20),
            "horodatage_depart": depart,
            "horodatage_arrivee": arrivee,
            "eta": iso_court(tr["eta_min"] + tr["t"]),
            "redacteur": "Nadia Kessler", "commentaire": tr["com"],
            "historique_json": json.dumps([
                {"ts": horodatage(-tr["t"] + 20), "from": "", "to": "EN_PREPARATION",
                 "user": "Nadia Kessler"},
            ]),
        })

    # ── Messagerie interne ───────────────────────────────────────────────
    if b.existe("messages_internes") and b.existe("users"):
        uids = [r[0] for r in b.cx.execute("SELECT id FROM users ORDER BY id LIMIT 6")]
        if uids:
            for i, (sujet, contenu) in enumerate(MESSAGES if pivot else MESSAGES[:5]):
                b.inserer("messages_internes", {
                    "expediteur_id": uids[i % len(uids)],
                    "expediteur_nom": "%s %s" % AGENTS[i % len(AGENTS)][:2],
                    "destinataire_id": uids[(i + 1) % len(uids)],
                    "destinataire_nom": "%s %s" % AGENTS[(i + 3) % len(AGENTS)][:2],
                    "sujet": sujet, "contenu": contenu,
                    "lu": 1 if i > 3 else 0,
                    "created_at": horodatage(700 - i * 70),
                })
            # Deux messages entrants d acteurs exterieurs, pour montrer le fil
            # inter-etablissements dans l inbox.
            for i, (src, sujet, texte) in enumerate([
                ("ARS", "Demande de point de situation",
                 "Merci de transmettre un point de situation actualise avant 18h00."),
                (autres[0]["sigle"], "Capacites disponibles",
                 "Nous pouvons accueillir 4 patients en medecine et 2 en chirurgie."),
            ]):
                b.inserer("messages_internes", {
                    "expediteur_id": uids[0], "expediteur_nom": src,
                    "destinataire_id": uids[0], "destinataire_nom": "Cellule de crise",
                    "sujet": sujet, "contenu": texte, "lu": 0,
                    "ght_source": src,
                    "created_at": horodatage(200 - i * 60),
                })

    # ── Supervision territoriale ─────────────────────────────────────────
    if b.existe("declarations_situation"):
        b.inserer("declarations_situation", {
            "site_id": SITES[0],
            "unite_fonct": "Etablissement",
            "type_crise": "cyber" if pivot else "tension_capacitaire",
            "niveau_tension": 3 if pivot else 2,
            "description": ("Incident informatique majeur, mode degrade actif "
                            "sur l ensemble des services.") if pivot else
                           ("Tension capacitaire liee a la reorientation des "
                            "patients d un etablissement voisin."),
            "actif": 1, "created_by": "Claire Rouvier",
            "created_at": horodatage(1380),
        })

    for i, (typ, unite, desc, statut, reponse) in enumerate(
            DEMANDES_GHT if pivot else DEMANDES_GHT[:1]):
        b.inserer("demandes_interght", {
            "type_situation": typ, "unite_concernee": unite,
            "description": desc, "ght_emetteur": ident["sigle"],
            "ght_destinataire": autres[i % len(autres)]["sigle"],
            "statut": statut, "reponse": reponse,
            "created_at": horodatage(600 - i * 90),
        })

    # La page de statut public est declarative : SCRIBE ne la deduit pas des
    # incidents, c est la communication de l etablissement qui la pilote. Une
    # instance qui a deja publie un statut garde donc le sien, meme avec 36
    # incidents actifs. Pour une demonstration, il faut donc l ecrire
    # explicitement — y compris en ecrasant une publication anterieure.
    if b.existe("status_page"):
        if pivot:
            niveau = "INCIDENT_MAJEUR"
            si = {"messagerie": "HS", "dpi": "HS", "pacs": "HS",
                  "telephonie": "DEGRADE", "internet": "DEGRADE",
                  "vpn": "HS", "applications": "HS"}
            soins = {"urgences": "OK", "blocs": "DEGRADE",
                     "consultations": "HS", "hospitalisations": "HS",
                     "imagerie": "DEGRADE", "laboratoire": "DEGRADE"}
            message = ("Notre etablissement fait face depuis ce matin a un "
                       "incident informatique majeur. La continuite des soins "
                       "est assuree et les urgences sont accueillies "
                       "normalement. Les consultations et les hospitalisations "
                       "programmees sont reportees : vous serez recontacte "
                       "pour une nouvelle date.")
        else:
            niveau = "PERTURBE"
            si = {"messagerie": "OK", "dpi": "OK", "pacs": "DEGRADE",
                  "telephonie": "DEGRADE", "internet": "OK",
                  "vpn": "OK", "applications": "OK"}
            soins = {"urgences": "DEGRADE", "blocs": "OK",
                     "consultations": "OK", "hospitalisations": "DEGRADE",
                     "imagerie": "DEGRADE", "laboratoire": "OK"}
            message = ("Activite soutenue liee a la situation d un "
                       "etablissement voisin. Les urgences vitales sont "
                       "assurees. Un temps d attente allonge est possible.")

        services_si = json.dumps(
            [dict(d, statut=si.get(d["id"], "OK")) for d in SERVICES_SI],
            ensure_ascii=False)
        prise_en_charge = json.dumps(
            [dict(d, statut=soins.get(d["id"], "OK")) for d in PRISE_EN_CHARGE],
            ensure_ascii=False)
        faq = json.dumps([
            {"question": "Mon rendez-vous est-il maintenu ?",
             "reponse": "Les consultations non urgentes sont reportees. Vous "
                        "serez recontacte pour une nouvelle date.",
             "visible": True},
            {"question": "Les urgences sont-elles operationnelles ?",
             "reponse": "Oui. L accueil des urgences fonctionne normalement.",
             "visible": True},
            {"question": "Peut-on envoyer des donnees ou de l imagerie a "
                         "l etablissement ?",
             "reponse": "Non. Les echanges numeriques sont suspendus. "
                        "Privilegier le contact telephonique.",
             "visible": True},
        ], ensure_ascii=False)

        contenu = {
            "niveau_global": niveau, "message_public": message,
            "services_si": services_si, "prise_en_charge": prise_en_charge,
            "faq": faq, "published": 1,
            "updated_at": horodatage(45), "updated_by": "Helene Bonnifay",
        }
        existant = b.cx.execute("SELECT id FROM status_page LIMIT 1").fetchone()
        if existant:
            b.ecraser("status_page", existant[0], contenu)
        else:
            contenu["site_id"] = hid
            contenu["site_nom"] = ident["nom"]
            b.inserer("status_page", contenu)

    if b.existe("status_chronologie"):
        for i, txt in enumerate([
            "Detection de l incident et ouverture de la cellule de crise.",
            "Isolation des sous-reseaux : la propagation est stoppee.",
            "Bascule complete des services en procedure degradee.",
            "Reprise progressive des consultations urgentes.",
        ]):
            b.inserer("status_chronologie", {
                "texte": txt, "timestamp": horodatage(1400 - i * 300),
                "publie_par": "Helene Bonnifay",
            })

    # ── REX ──────────────────────────────────────────────────────────────
    for i, r in enumerate(REX if pivot else REX[1:]):
        b.inserer("rex_entries", {
            "incident_id": incidents[0] if incidents else None,
            "created_at": horodatage(180 - i * 60),
            "titre": r["titre"], "type_crise": r["type_crise"],
            "duree_minutes": r["duree"], "nb_poles": r["poles"],
            "nb_decisions": r["decisions"],
            "nb_jalons_total": r["jalons_total"],
            "nb_jalons_done": r["jalons_done"],
            "mttd_minutes": r["mttd"], "mttr_minutes": r["mttr"],
            "points_positifs": r["positifs"], "points_amelio": r["amelio"],
            "actions_futures": r["actions"], "lecons": r["lecons"],
            "redacteur": "Claire Rouvier",
        })

    # ── Chaine d alerte ──────────────────────────────────────────────────
    if b.existe("contacts_mobilisation"):
        contacts = []
        for i in range(28):
            prenom, nom, fonction, _s = AGENTS[i % len(AGENTS)]
            suffixe = "" if i < len(AGENTS) else " %d" % (i // len(AGENTS) + 1)
            svc, pole, _c = SERVICES[i % len(SERVICES)]
            cid = b.inserer("contacts_mobilisation", {
                "cle": "DEMO%03d" % i,
                "nom": nom + suffixe, "prenom": prenom,
                # Numeros de la plage reservee aux fictions : jamais attribues.
                "tel1": "+3363998%04d" % (1000 + i),
                "tel2": "", "email": "contact%02d@exemple.invalid" % i,
                "fonction": fonction, "service": svc,
                "uf": "UF%03d" % (100 + (i % len(SERVICES))),
                "grade": fonction, "pole": pole,
                "site": SITES[i % len(SITES)],
                "perimetre_abonnement": "pole", "priorite": 1 + (i % 4),
                "actif": 1, "created_at": horodatage(4320),
            })
            if cid:
                contacts.append((cid, "%s %s" % (prenom, nom + suffixe), fonction,
                                 SITES[i % len(SITES)], "+3363998%04d" % (1000 + i),
                                 "contact%02d@exemple.invalid" % i, 1 + (i % 4)))

        if b.existe("alertes_mobilisation") and contacts:
            for j, (titre, message, archived) in enumerate([
                ("Plan blanc - rappel du personnel",
                 "Plan blanc active. Merci d indiquer votre delai de retour "
                 "sur site en repondant a ce message.", 0),
                ("Renfort de nuit - pole medecine",
                 "Deux postes non couverts sur la nuit. Renfort recherche "
                 "pour 21h00.", 0),
                ("Exercice du trimestre precedent",
                 "Mobilisation de test. Aucune action requise.", 1),
            ]):
                aid = b.inserer("alertes_mobilisation", {
                    "titre": titre, "message": message,
                    "criteres": json.dumps({"pole": POLES[:2], "site": SITES[:2]}),
                    "incident_id": incidents[0] if incidents else None,
                    "cree_par": "Claire Rouvier", "archived": archived,
                    "vague_courante": 1 if j == 0 else 0,
                    "created_at": horodatage(800 - j * 200),
                })
                if not aid:
                    continue
                cibles = contacts[: 18 if j == 0 else 8]
                for k, (cid, nom, fonction, site, tel, mail, prio) in enumerate(cibles):
                    repondu = k % 3 != 2
                    choix = ["15", "30", "60", "indispo"][k % 4]
                    b.inserer("alerte_cibles", {
                        "alerte_id": aid, "contact_id": cid, "nom": nom,
                        "fonction": fonction, "site": site, "tel": tel,
                        "email": mail,
                        "token": hashlib.sha256(
                            ("demo-%d-%d-%d" % (rang, j, k)).encode()
                        ).hexdigest()[:32],
                        "canaux": "sms,mail",
                        "statut": "repondu" if repondu else "envoye",
                        "eta_choice": choix if repondu else None,
                        "commentaire": "Disponible immediatement." if choix == "15" and repondu else None,
                        "responded_at": horodatage(700 - k * 12) if repondu else None,
                        "vague": prio, "livraison": "ok",
                    })

        if b.existe("mob_presets"):
            for nom, criteres in [
                ("Plan blanc - tous poles", {"pole": POLES}),
                ("Rappel bloc operatoire", {"pole": ["Chirurgie"]}),
                ("Astreinte technique", {"fonction": ["Responsable technique"]}),
            ]:
                b.inserer("mob_presets", {
                    "nom": nom, "criteres": json.dumps(criteres),
                    "canaux": "sms,mail", "escalade": 1,
                    "cree_par": "Claire Rouvier", "created_at": horodatage(4000),
                })

    # ── Tables de plugins ────────────────────────────────────────────────
    uids = []
    if b.existe("users"):
        uids = [r[0] for r in b.cx.execute("SELECT id FROM users ORDER BY id LIMIT 8")]
    remplir_plugins(b, ident, pivot, incidents, autres, uids)

    b.valider()


def remplir_plugins(b, ident, pivot, incidents, autres, uids):
    """Tables des plugins. Chacune est optionnelle : un plugin desactive n a
    pas de table, l insertion est simplement ignoree."""

    # Chat territorial
    if b.existe("chat_salons"):
        salons = [
            ("cellule-de-crise", "Coordination de la cellule", "local", "#003189", "\U0001F6A8"),
            ("technique", "Echanges DSI et biomedical", "local", "#0891b2", "\U0001F527"),
            ("coordination-territoriale", "Echanges entre etablissements",
             "territorial", "#7c3aed", "\U0001F310"),
        ]
        for nom, desc, typ, couleur, icone in salons:
            sid = b.inserer("chat_salons", {
                "nom": nom, "description": desc, "type": typ,
                "couleur": couleur, "icone": icone,
                "created_by": "Claire Rouvier", "cree_par": "Claire Rouvier",
                "created_at": horodatage(1440), "actif": 1,
            })
            if not sid or not b.existe("chat_messages"):
                continue
            fil = [
                ("Claire Rouvier", "Cellule ouverte. Point de situation dans 15 minutes."),
                ("Marc Delaunay", "Isolation des serveurs terminee. Propagation stoppee."),
                ("Sophie Bertholet", "Procedure papier distribuee dans tous les services."),
                ("Nadia Kessler", "Deux transferts partis, un troisieme en preparation."),
                ("Claire Rouvier", "Merci. On refait un point a 12h00."),
            ]
            for k, (auteur, texte) in enumerate(fil):
                b.inserer("chat_messages", {
                    "salon_id": sid, "auteur_nom": auteur,
                    "auteur_sigle": ident["sigle"], "contenu": texte,
                    "mentions": "[]", "supprime": 0,
                    "horodatage": horodatage(1400 - k * 90),
                    "created_at": horodatage(1400 - k * 90),
                })

    # Messagerie (plugin)
    if b.existe("messagerie_messages"):
        for i, (sujet, contenu) in enumerate(MESSAGES[:6]):
            entrant = i % 2 == 0
            b.inserer("messagerie_messages", {
                "canal": "interne",
                "direction": "in" if entrant else "out",
                "expediteur_id": uids[i % len(uids)] if uids else None,
                "expediteur_nom": "%s %s" % AGENTS[i % len(AGENTS)][:2],
                "expediteur_addr": ("%s.%s" % AGENTS[i % len(AGENTS)][:2]).lower(),
                "destinataires": json.dumps(["Cellule de crise"]),
                "destinataires_cc": json.dumps([]),
                "destinataires_bcc": json.dumps([]),
                "sujet": sujet, "contenu": contenu,
                "contenu_format": "plain", "contenu_redacted": 0,
                "thread_id": "demo-thread-%02d" % i,
                "statut": "received" if entrant else "sent",
                "flag_important": 1 if i == 0 else 0,
                "attachments_count": 0,
                "lu": 1 if i > 2 else 0,
                "lu_at": horodatage(500 - i * 60) if i > 2 else None,
                "created_at": horodatage(600 - i * 70),
                "sent_at": None if entrant else horodatage(600 - i * 70),
            })

    # Brancardage
    if b.existe("plugin_brc_missions"):
        missions = [
            ("Urgences", "Imagerie", "TERMINE", "Brancardier 3"),
            ("Medecine polyvalente", "Bloc operatoire", "EN_COURS", "Brancardier 1"),
            ("Reanimation polyvalente", "Scanner", "EN_COURS", "Brancardier 2"),
            ("Chirurgie viscerale", "Salle de reveil", "EN_ATTENTE", None),
            ("Urgences", "Court sejour geriatrique", "EN_ATTENTE", None),
        ]
        for i, (origine, dest, statut, agent) in enumerate(missions):
            b.inserer("plugin_brc_missions", {
                "ref_type": "IPP", "ref_patient": "DEMO%05d" % (20000 + i),
                "uf_origine": origine, "uf_destination": dest,
                "chambre_depart": "%d%02d" % (2 + i % 4, 10 + i),
                "chambre_arrivee": None,
                "type_transport": ["BRANCARD", "FAUTEUIL", "LIT"][i % 3],
                "transport_externe": 0,
                "priorite": ["P1", "P2", "P3"][i % 3],
                "motif": ["Examen d imagerie", "Bloc operatoire", "Scanner",
                          "Retour de salle", "Mutation de service"][i % 5],
                "commentaire": "Oxygene requis pendant le transport." if i == 2 else None,
                "programmee": 1 if i > 2 else 0,
                "heure_prevue": "1%d:30" % (4 + i) if i > 2 else None,
                "avec_retour": 1 if i == 0 else 0,
                "statut": statut,
                "arrivee_confirmee": 1 if statut == "TERMINE" else 0,
                "agent_nom": agent, "agent_tel": "poste 42%02d" % (10 + i),
                "demandeur_nom": "Amina Ferrand",
                "created_at": horodatage(300 - i * 40),
                "updated_at": horodatage(200 - i * 30),
                "prise_en_charge_at": horodatage(280 - i * 40) if statut != "EN_ATTENTE" else None,
                "termine_at": horodatage(240 - i * 40) if statut == "TERMINE" else None,
            })

    # Lignes telephoniques de secours
    if b.existe("plugin_lignes_ligne"):
        lignes = [
            ("Cellule de crise", "poste 4000", "OK"),
            ("Standard de secours", "poste 4001", "OK"),
            ("Urgences", "poste 4002", "OK"),
            ("Reanimation", "poste 4003", "OK"),
            ("Pharmacie", "poste 4004", "DEGRADE"),
            ("Securite", "poste 4005", "OK"),
        ]
        for i, (libelle, numero, statut) in enumerate(lignes):
            b.inserer("plugin_lignes_ligne", {
                "libelle": libelle, "nom": libelle, "numero": numero,
                "statut": statut, "actif": 1, "ordre": i,
                "created_at": horodatage(4000),
            })

    # Scenarios d exercice
    if b.existe("plugin_exo_scenarios"):
        for titre, desc in [
            ("Cyberattaque - rancongiciel sur le SI hospitalier",
             "Scenario genere depuis la crise du trimestre precedent. "
             "12 stimuli repartis sur 4 heures, 6 decisions attendues."),
            ("Tension capacitaire hivernale",
             "Afflux progressif sur 8 heures, coordination territoriale requise."),
        ]:
            b.inserer("plugin_exo_scenarios", {
                "titre": titre, "nom": titre, "description": desc,
                "contenu_json": json.dumps({
                    "meta": {"titre": titre, "duree_min": 240},
                    "acteurs": [{"sigle": e["sigle"], "role": "joueur",
                                 "port": 6660 + i}
                                for i, e in enumerate(autres[:4])],
                    "stimuli": [
                        {"id": "S%02d" % k, "t_min": k * 20,
                         "cible": autres[k % len(autres)]["sigle"],
                         "type": "message",
                         "contenu": "Stimulus de demonstration %d" % k}
                        for k in range(1, 13)
                    ],
                    "decisions_attendues": [
                        "Ouverture de la cellule de crise",
                        "Isolation des sous-reseaux",
                        "Bascule en procedure degradee",
                        "Information de la tutelle",
                        "Organisation des transferts",
                        "Preparation du communique",
                    ],
                }),
                "cree_par": "Claire Rouvier", "created_at": horodatage(2000),
            })

    # Fichiers
    if b.existe("plugin_fichiers_dossiers") and uids:
        for nom in ["Plans de crise", "Procedures degradees", "Annuaires",
                    "Comptes rendus de cellule"]:
            b.inserer("plugin_fichiers_dossiers", {
                "nom": nom, "proprietaire_id": uids[0], "parent_id": None,
                "type": "perso", "etablissement": ident["sigle"],
                "created_at": horodatage(3000),
            })


# ═════════════════════════════════════════════════════════════════════════════
#  Commandes
# ═════════════════════════════════════════════════════════════════════════════

def cmd_inject(args):
    cibles = instances(args.ports)
    if not cibles:
        print("\n  Aucune instance trouvee.")
        print("  Verifie que lancer_scribe.sh a bien cree les instances,")
        print("  et que %s existe.\n" % DATA_DIR)
        return 1

    deja = [s for _p, s, _d in cibles
            if (BACKUP_DIR / ("%s.scribe.db" % s)).exists()]
    if deja and not args.force:
        print("\n  Des donnees de demonstration semblent deja injectees")
        print("  (%d sauvegarde(s) presente(s) dans %s)." % (len(deja), BACKUP_DIR))
        print("  Lance --clean d abord, ou --inject --force pour ecraser.\n")
        return 1

    mdp = None
    if not args.sans_comptes:
        mdp = "Demo-" + hashlib.sha256(os.urandom(16)).hexdigest()[:12] + "!"
        if hash_mdp("test") is None:
            print("\n  bcrypt indisponible : aucun compte de demonstration ne sera cree.")
            print("  Le reste des donnees sera injecte normalement.\n")
            mdp = None

    # L etablissement pivot est celui qui subit l attaque. Par defaut le
    # premier port ; --pivot permet de designer celui qui sera capture.
    if args.pivot:
        vise = args.pivot.strip().upper()
        pos = next((i for i, c in enumerate(cibles) if c[1].upper() == vise), None)
        if pos is None:
            print("\n  Sigle « %s » introuvable. Disponibles : %s\n"
                  % (args.pivot, ", ".join(c[1] for c in cibles)))
            return 1
        cibles.insert(0, cibles.pop(pos))

    print("\n  Injection des donnees de demonstration")
    print("  " + "-" * 62)
    total = 0
    # Identite reelle de chaque instance, lue dans son config.js.
    identites = {}
    for _p, sg, dbp in cibles:
        c = lire_config_js(dbp)
        identites[sg] = c.get("nom") or sg

    for rang, (port, sigle, db) in enumerate(cibles):
        voisins = [(sg, identites[sg]) for _p, sg, _d in cibles if sg != sigle]
        moi = {"sigle": sigle, "nom": identites.get(sigle, sigle)}
        sauvegarder(db, sigle)
        b = Base(db, sigle)
        try:
            remplir(b, rang, port, mdp, voisins, moi)
            n = sum(b.compte.values())
            total += n
            role = "etablissement en crise" if rang == 0 else "etablissement partenaire"
            print("  %-6s port %d  %5d lignes   %s" % (sigle, port, n, role))
            for msg in dict.fromkeys(b.ignores):
                print("         ignore : %s" % msg)
        finally:
            b.fermer()

    print("  " + "-" * 62)
    print("  %d lignes injectees dans %d instance(s)." % (total, len(cibles)))
    print("  Sauvegardes : %s" % BACKUP_DIR)
    if mdp:
        print("\n  Comptes de demonstration (c.rouvier, m.delaunay, ...)")
        print("  Mot de passe commun genere pour cette session :")
        print("      %s" % mdp)
        print("  Il n est stocke nulle part : note-le si tu veux t y connecter.")
    print("\n  Les instances relisent la base a chaque requete : un simple")
    print("  rafraichissement du navigateur suffit, sans redemarrage.")
    print("  La supervision se remplit seule au prochain push, sous 30 secondes.\n")
    return 0


def cmd_clean(args):
    cibles = instances(args.ports)
    if not cibles:
        print("\n  Aucune instance trouvee.\n")
        return 1

    print("\n  Retrait des donnees de demonstration")
    print("  " + "-" * 62)
    restaures = supprimes = 0
    for _rang, (port, sigle, db) in enumerate(cibles):
        if not args.sans_restauration and restaurer(db, sigle):
            print("  %-6s port %d  base restauree depuis la sauvegarde" % (sigle, port))
            restaures += 1
            continue
        b = Base(db, sigle)
        try:
            n = b.purger_journal()
            supprimes += n
            if n:
                print("  %-6s port %d  %5d lignes supprimees (journal)" % (sigle, port, n))
            else:
                print("  %-6s port %d  rien a retirer" % (sigle, port))
        finally:
            b.fermer()

    if restaures and BACKUP_DIR.exists() and not args.garder_sauvegardes:
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)

    print("  " + "-" * 62)
    print("  %d base(s) restauree(s), %d ligne(s) supprimee(s) au journal."
          % (restaures, supprimes))
    print("  Rafraichis le navigateur pour voir l etat nominal.\n")
    return 0


def cmd_refresh(args):
    """Recalibre les horodatages des transferts de demonstration sur l heure
    courante.

    Les heures d arrivee estimees sont figees au moment de l injection. Une
    heure plus tard, la carte affiche « en retard » et l ambulance a fini son
    trajet : plus rien a capturer. Cette commande replace les departs dans le
    passe proche et les arrivees estimees dans le futur, sans toucher au reste
    du jeu de donnees.
    """
    cibles = instances(args.ports)
    if not cibles:
        print("\n  Aucune instance trouvee.\n")
        return 1

    print("\n  Recalibrage des transferts sur l heure courante")
    print("  " + "-" * 62)
    total = 0
    for port, sigle, db in cibles:
        b = Base(db, sigle)
        try:
            ids = [rid for tbl, rid in b.lignes_demo() if tbl == "transferts_patients"]
            if not ids:
                print("  %-8s port %d  aucun transfert de demonstration" % (sigle, port))
                continue
            gabarit = TRANSFERTS if len(ids) > 3 else TRANSFERTS[:3]
            n = 0
            for rid, tr in zip(ids, gabarit):
                depart = horodatage(-tr["t"]) if tr["statut"] != "EN_PREPARATION" else None
                arrivee = (horodatage(-tr["t"] - tr["eta_min"])
                           if tr["statut"] == "ARRIVE" else None)
                b.cx.execute(
                    "UPDATE transferts_patients SET horodatage_creation=?, "
                    "horodatage_depart=?, horodatage_arrivee=?, eta=? WHERE id=?",
                    (horodatage(-tr["t"] + 20), depart, arrivee,
                     iso_court(tr["eta_min"] + tr["t"]), rid),
                )
                n += 1
            b.valider()
            total += n
            print("  %-8s port %d  %d transfert(s) recalibre(s)" % (sigle, port, n))
        finally:
            b.fermer()

    print("  " + "-" * 62)
    print("  %d transfert(s) remis a l heure." % total)
    print("  Relancer ensuite tools/push_transferts.py pour propager")
    print("  les nouvelles heures a la supervision.\n")
    return 0


def cmd_status(args):
    cibles = instances(args.ports)
    print("\n  Etat des instances")
    print("  " + "-" * 62)
    if not cibles:
        print("  Aucune instance trouvee dans %s\n" % DATA_DIR)
        return 1
    for port, sigle, db in cibles:
        b = Base(db, sigle)
        try:
            n = len(b.lignes_demo())
            sauve = (BACKUP_DIR / ("%s.scribe.db" % sigle)).exists()
            inc = 0
            if b.existe("sitrep_entries"):
                inc = b.cx.execute("SELECT COUNT(*) FROM sitrep_entries").fetchone()[0]
            etat = "DEMO" if n else "nominal"
            print("  %-6s port %d  %-8s %5d lignes de demo  %3d incidents  %s"
                  % (sigle, port, etat, n, inc,
                     "sauvegarde presente" if sauve else ""))
        finally:
            b.fermer()
    print("  " + "-" * 62 + "\n")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="Donnees de demonstration SCRIBE (injection et retrait)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples
  python3 tools/demo_data.py --inject
  python3 tools/demo_data.py --inject --ports 8000 8001 8002
  python3 tools/demo_data.py --status
  python3 tools/demo_data.py --clean

Toutes les donnees sont fictives : etablissements, communes, personnes,
numeros de telephone et adresses electroniques sont inventes.
""")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true", help="injecter le jeu de demonstration")
    g.add_argument("--clean", action="store_true", help="revenir a l etat anterieur")
    g.add_argument("--status", action="store_true", help="afficher l etat des instances")
    g.add_argument("--refresh", action="store_true",
                   help="remettre les transferts a l heure (ambulances a mi-parcours)")

    p.add_argument("--ports", nargs="+", type=int, default=PORTS_DEFAUT,
                   help="ports a traiter (defaut : 8000 a 8007)")
    p.add_argument("--pivot", default=None, metavar="SIGLE",
                   help="etablissement qui subit l attaque (defaut : le premier port)")
    p.add_argument("--force", action="store_true",
                   help="reinjecter meme si des sauvegardes existent")
    p.add_argument("--sans-comptes", action="store_true",
                   help="ne pas creer de comptes de demonstration")
    p.add_argument("--sans-restauration", action="store_true",
                   help="nettoyer par le journal au lieu de restaurer les sauvegardes")
    p.add_argument("--garder-sauvegardes", action="store_true",
                   help="conserver data/demo_backup apres le nettoyage")
    a = p.parse_args()

    if a.inject:
        return cmd_inject(a)
    if a.clean:
        return cmd_clean(a)
    if a.refresh:
        return cmd_refresh(a)
    return cmd_status(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Sortie tronquee par un `| head` : ce n est pas une erreur.
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n  Interrompu.\n")
        sys.exit(130)
