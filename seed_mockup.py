"""
seed_mockup.py — Peuple une instance SCRIBE avec un scénario de crise complet
pour génération de captures d'écran de démonstration.

Scénario : "Cyber + Bronchiolite" — relatif à NOW
  - Cyberattaque sur le SIH depuis ~3h (DPI HS, messagerie HS, biologie dégradée)
  - Pic épidémique bronchiolite : urgences pédia saturées
  - Plan Blanc déclenché ~1h45 avant NOW
  - Cellule de crise activée ~1h30 avant NOW
  - 4 transferts inter-établissements (1 ARRIVE, 2 EN_COURS, 1 EN_PREPARATION)
  - 9 incidents à des stades de progression variés
  - 14 messages dans le chat cellule de crise
  - Déclarations capacitaires complètes (mélange normal/tension/critique)

Tous les timestamps sont RELATIFS à l'heure de lancement → captures fraîches.

Usage :
    python seed_mockup.py                  # DB par défaut (scribe.db racine)
    python seed_mockup.py --port 8000      # DB de l'instance master sur 8000
    python seed_mockup.py --db <path>      # DB explicite
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────── Résolution DB ─────────────────────────
def _resolve_db_url(argv):
    db_path = None
    port = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1]); i += 2; continue
        if a == "--db" and i + 1 < len(argv):
            db_path = argv[i + 1]; i += 2; continue
        if a in ("-h", "--help"):
            print(__doc__); sys.exit(0)
        i += 1
    if port is not None and db_path is None:
        base = os.path.dirname(os.path.abspath(__file__))
        # v2.5.0 : le master place les DBs dans data/instances/<SIGLE>/scribe.db
        # (et non /<PORT>/). On lit master_instances.json pour trouver le sigle.
        state_file = os.path.join(base, "master", "master_instances.json")
        if os.path.exists(state_file):
            try:
                import json as _json
                with open(state_file, encoding="utf-8") as f:
                    state = _json.load(f)
                # Le JSON peut être un dict {port: instance} ou une liste
                instances = state.values() if isinstance(state, dict) else state
                for inst in instances:
                    inst_port = inst.get("config", {}).get("port") or inst.get("port")
                    if str(inst_port) == str(port):
                        # Récupérer db_path direct si présent
                        candidate = inst.get("db_path")
                        if candidate and os.path.exists(candidate):
                            db_path = candidate
                            break
            except Exception as e:
                print(f"  ⚠ Lecture master_instances.json échouée : {e}")
        # Fallback 1 : ancienne convention par port
        if db_path is None:
            candidate = os.path.join(base, "data", "instances", str(port), "scribe.db")
            if os.path.exists(candidate):
                db_path = candidate
        # Fallback 2 : scan du dossier data/instances/ — prendre la 1ère DB
        # trouvée si une seule instance (cas mockup typique)
        if db_path is None:
            inst_dir = os.path.join(base, "data", "instances")
            if os.path.isdir(inst_dir):
                candidates = []
                for entry in os.listdir(inst_dir):
                    p = os.path.join(inst_dir, entry, "scribe.db")
                    if os.path.exists(p):
                        candidates.append((entry, p))
                if len(candidates) == 1:
                    db_path = candidates[0][1]
                    print(f"  → Instance unique détectée : {candidates[0][0]}")
                elif len(candidates) > 1:
                    print(f"  ERREUR : plusieurs instances trouvées sous data/instances/ :")
                    for sigle, p in candidates:
                        print(f"    - {sigle} → {p}")
                    print(f"  → Utilisez --db <chemin.db> pour préciser laquelle peupler.")
                    sys.exit(2)
        if db_path is None:
            print(f"  ERREUR : DB introuvable pour le port {port}.")
            print(f"  → L'instance a-t-elle été démarrée au moins une fois ?")
            print(f"  → Cherchez sous data/instances/<SIGLE>/scribe.db")
            sys.exit(2)
    if db_path:
        os.environ["DATABASE_URL"] = "sqlite:///" + os.path.abspath(db_path)
        print(f"  → DB cible : {db_path}")


_resolve_db_url(sys.argv)

from app.database import SessionLocal, engine, Base
import app.models
Base.metadata.create_all(bind=engine)

from app.models import (
    Hospital, UniteFonctionnelle, CapaciteReferentiel, CapaciteDeclaration,
    SitrepEntry, Decision, Presence, Consigne,
    User, ServiceStatus, TransfertPatient, MessageInterne,
    MainCouranteLog, RexEntry,
)


# ───────────────────────── Helpers ─────────────────────────
NOW = datetime.now(timezone.utc)


def ago(minutes=0, hours=0, days=0):
    """Datetime relatif à NOW (le seed time)."""
    return NOW - timedelta(minutes=minutes, hours=hours, days=days)


def in_future(minutes=0, hours=0):
    return NOW + timedelta(minutes=minutes, hours=hours)


def sha(p):
    return hashlib.sha256(p.encode()).hexdigest()


def banner(t):
    print(f"\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  {t}")
    print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# ───────────────────────── Seed ─────────────────────────
def seed():
    db = SessionLocal()
    try:
        # ──────────────────────────────────────────────────────────
        # 1. HOSPITALS
        # ──────────────────────────────────────────────────────────
        banner("1. Établissements")
        if not db.query(Hospital).first():
            db.add_all([
                Hospital(nom="Hôpital Saint-Exemple — Site Nord",
                         latitude=48.8566, longitude=2.3522),
                Hospital(nom="Hôpital Saint-Exemple — Site Sud",
                         latitude=48.7920, longitude=2.3260),
            ])
            db.commit()
            print("  ✓ 2 sites créés")
        h_nord = db.query(Hospital).filter_by(nom="Hôpital Saint-Exemple — Site Nord").first()
        h_sud  = db.query(Hospital).filter_by(nom="Hôpital Saint-Exemple — Site Sud").first()

        # ──────────────────────────────────────────────────────────
        # 2. UF + CAPACITÉ RÉFÉRENTIEL
        # ──────────────────────────────────────────────────────────
        banner("2. UF + référentiels capacitaires")
        # (code_uf, libelle, pole, hospital, lits_totaux, tension_1, tension_2)
        uf_data = [
            ("URG-A", "Urgences adultes",       "Pôle Urgences",     h_nord, 24, 4, 8),
            ("URG-P", "Urgences pédiatriques",  "Pôle Urgences",     h_nord, 16, 4, 6),
            ("REA-1", "Réanimation polyvalente","Pôle Réanimation",  h_nord, 18, 2, 4),
            ("USC",   "Soins continus",         "Pôle Réanimation",  h_nord, 12, 2, 4),
            ("PED-1", "Pédiatrie générale",     "Pôle Pédiatrie",    h_nord, 28, 4, 6),
            ("PED-N", "Néonatologie",           "Pôle Pédiatrie",    h_nord,  8, 2, 2),
            ("MED-A", "Médecine A",             "Pôle Médecine",     h_nord, 30, 4, 6),
            ("MED-B", "Médecine B",             "Pôle Médecine",     h_sud,  26, 4, 6),
            ("CHIR",  "Chirurgie viscérale",    "Pôle Chirurgie",    h_nord, 22, 4, 6),
            ("CARDIO","Cardiologie",            "Pôle Médecine",     h_nord, 24, 4, 6),
            ("MAT",   "Maternité",              "Pôle Femme-Enfant", h_sud,  18, 2, 4),
            ("GERIA", "Gériatrie aiguë",        "Pôle Gériatrie",    h_sud,  32, 4, 8),
        ]
        if not db.query(UniteFonctionnelle).first():
            for code, lib, pole, hosp, lits, _, _ in uf_data:
                db.add(UniteFonctionnelle(
                    code_uf=code, libelle=lib, pole=pole,
                    hospital_id=hosp.id, actif=True,
                ))
            db.commit()
            print(f"  ✓ {len(uf_data)} UF créées")
        if not db.query(CapaciteReferentiel).first():
            for code, lib, pole, hosp, lits, t1, t2 in uf_data:
                db.add(CapaciteReferentiel(
                    service_nom=lib, uf_code=code, pole=pole, site=hosp.nom,
                    capacite_totale=lits, tension_1=t1, tension_2=t2,
                ))
            db.commit()
            print(f"  ✓ {len(uf_data)} référentiels capacité créés")

        # ──────────────────────────────────────────────────────────
        # 3. UTILISATEURS
        # ──────────────────────────────────────────────────────────
        banner("3. Utilisateurs")
        users_data = [
            # (username, display_name, role, password)
            ("dircrise",   "Directeur de Crise",      "admin",       "changeme"),
            ("admin",      "Administrateur SCRIBE",   "admin",       "admin123"),
            ("m.lefevre",  "Marie LEFEVRE",           "admin",       "demo2026"),
            ("p.dubois",   "Paul DUBOIS",             "directeur",   "demo2026"),
            ("a.martin",   "Anne MARTIN",             "directeur",   "demo2026"),
            ("c.bernard",  "Dr Claire BERNARD",       "directeur",   "demo2026"),
            ("j.durand",   "Jean DURAND",             "observateur", "demo2026"),
            ("s.moreau",   "Sophie MOREAU",           "observateur", "demo2026"),
        ]
        for login, name, role, pwd in users_data:
            if db.query(User).filter_by(username=login).first():
                continue
            db.add(User(
                username=login, display_name=name, role=role,
                hashed_password=sha(pwd),
                active=True, must_change_password=False,
            ))
        db.commit()
        print(f"  ✓ Utilisateurs prêts ({len(users_data)} comptes)")

        # On récupère les IDs pour les messages
        user_by_login = {u.username: u for u in db.query(User).all()}

        # ──────────────────────────────────────────────────────────
        # 4. INCIDENTS (SitrepEntry)
        # ──────────────────────────────────────────────────────────
        banner("4. Incidents")
        if db.query(SitrepEntry).count() < 3:
            incidents = [
                # CYBER (5 incidents)
                dict(timestamp=ago(hours=3, minutes=13),
                     declarant_nom="Marie LEFEVRE",
                     directeur_crise="Directeur de Crise",
                     site_id=h_nord.nom, unite_fonctionnelle="SI — DSI",
                     type_crise="CYBER", urgency=4,
                     fait="Détection intrusion sur le SIH. Chiffrement de serveurs métier. DPI inaccessible.",
                     analyse="Ransomware probable type LockBit. Vecteur : VPN tiers maintenance non patché.",
                     moyens_engages="ANSSI alerté, cellule cyber activée, équipe DSI 24/7.",
                     actions_remediation="Isolement serveurs touchés, bascule mode dégradé papier.",
                     intervenant_nom="Paul DUBOIS",
                     intervenant_contact="06 12 34 56 78",
                     status="EN COURS", completion_percent=35,
                     estimated_resolution=in_future(hours=18),
                     impact_fonctionnel=True),
                dict(timestamp=ago(hours=2, minutes=58),
                     declarant_nom="Paul DUBOIS",
                     site_id=h_nord.nom, unite_fonctionnelle="Laboratoire de biologie",
                     type_crise="CYBER", urgency=3,
                     fait="SI de biologie en mode dégradé. Délais analyses urgentes x3.",
                     analyse="Conséquence de l'incident cyber principal.",
                     moyens_engages="Renforts biologistes, priorisation urgences vitales.",
                     actions_remediation="Procédure dégradée papier en cours.",
                     intervenant_nom="Dr Claire BERNARD",
                     status="EN COURS", completion_percent=50,
                     impact_fonctionnel=True),
                dict(timestamp=ago(hours=2, minutes=42),
                     declarant_nom="Sophie MOREAU",
                     site_id=h_nord.nom, unite_fonctionnelle="Standard téléphonique",
                     type_crise="CYBER", urgency=2,
                     fait="Messagerie interne KO. Communication radio uniquement.",
                     analyse="Serveur Exchange affecté par le ransomware.",
                     moyens_engages="Téléphonie de secours (talkie-walkies + lignes RTC).",
                     status="EN COURS", completion_percent=20,
                     impact_fonctionnel=True),
                dict(timestamp=ago(minutes=22),
                     declarant_nom="Marie LEFEVRE",
                     site_id=h_nord.nom, unite_fonctionnelle="SI — Sauvegarde",
                     type_crise="CYBER", urgency=2,
                     fait="Sauvegardes hors ligne validées intègres. Restauration possible.",
                     analyse="Sauvegardes du 24/05 23h59 saines. Perte limitée à 7h activité.",
                     moyens_engages="Équipe restauration, sandbox prête.",
                     actions_remediation="Phase 1 restauration dans 2h, après nettoyage SI.",
                     status="EN COURS", completion_percent=15),
                # SANITAIRE (3 incidents)
                dict(timestamp=ago(hours=2, minutes=15),
                     declarant_nom="Jean DURAND",
                     site_id=h_nord.nom, unite_fonctionnelle="Urgences pédiatriques",
                     type_crise="SANITAIRE", urgency=3,
                     fait="Afflux massif urgences pédia : 32 entrées depuis 06h, saturation. Bronchiolite ++.",
                     analyse="Pic épidémique régional bronchiolite VRS sur tout le territoire.",
                     moyens_engages="Tous pédiatres rappelés, USC renforcée.",
                     actions_remediation="Transferts demandés vers hôpitaux Sud, recherche lits Réa pédia.",
                     intervenant_nom="Dr Claire BERNARD",
                     status="EN COURS", completion_percent=45,
                     estimated_resolution=in_future(hours=12)),
                dict(timestamp=ago(minutes=45),
                     declarant_nom="Dr Claire BERNARD",
                     site_id=h_sud.nom, unite_fonctionnelle="Maternité",
                     type_crise="SANITAIRE", urgency=2,
                     fait="Surcharge maternité site Sud — 3 accouchements simultanés.",
                     moyens_engages="Renfort sage-femme de garde rappelée.",
                     status="EN COURS", completion_percent=30),
                dict(timestamp=ago(minutes=8),
                     declarant_nom="Jean DURAND",
                     site_id=h_nord.nom, unite_fonctionnelle="Pharmacie",
                     type_crise="SANITAIRE", urgency=1,
                     fait="Approvisionnement médicaments urgences confirmé pour 48h.",
                     status="RÉSOLU", completion_percent=100,
                     resolved_at=ago(minutes=5)),
                # MIXTE (1 incident principal)
                dict(timestamp=ago(hours=1, minutes=48),
                     declarant_nom="Directeur de Crise",
                     directeur_crise="Directeur de Crise",
                     site_id=h_nord.nom, unite_fonctionnelle="Direction générale",
                     type_crise="MIXTE", urgency=4,
                     fait="Plan Blanc activé — situation combinée cyber + afflux pédia.",
                     analyse="Double crise : SI dégradé + tension capacitaire. Doctrine ORSAN PRO.",
                     moyens_engages="Rappel personnels niveau 2. Cellule de crise à 08h00.",
                     actions_remediation="Communication ARS / Préfecture en cours.",
                     intervenant_nom="Directeur de Crise",
                     status="EN COURS", completion_percent=60,
                     impact_fonctionnel=True),
                dict(timestamp=ago(hours=1, minutes=20),
                     declarant_nom="Anne MARTIN",
                     site_id=h_nord.nom, unite_fonctionnelle="Direction RH",
                     type_crise="MIXTE", urgency=2,
                     fait="Rappel de 18 personnels effectué. 14 confirmés présents sous 2h.",
                     moyens_engages="Cellule RH mobilisée.",
                     status="EN COURS", completion_percent=75),
            ]
            for inc in incidents:
                db.add(SitrepEntry(**inc))
            db.commit()
            print(f"  ✓ {len(incidents)} incidents créés")

        # ──────────────────────────────────────────────────────────
        # 5. DÉCISIONS CELLULE DE CRISE
        # ──────────────────────────────────────────────────────────
        banner("5. Décisions cellule de crise")
        if db.query(Decision).count() < 3:
            decisions = [
                (ago(hours=1, minutes=30), "Activation Plan Blanc — niveau 2.",                                "Directeur de Crise", "Plan Blanc"),
                (ago(hours=1, minutes=15), "Rappel effectifs paramédicaux (18 personnes).",                    "Anne MARTIN",        "Plan Blanc"),
                (ago(hours=1, minutes=2),  "Isolation serveurs SIH compromis du réseau.",                      "Marie LEFEVRE",      "PCA"),
                (ago(minutes=55),          "Activation procédures dégradées papier : urgences, biologie, pharma.", "Paul DUBOIS",     "PCA"),
                (ago(minutes=42),          "Communication ARS et Préfecture (point situation 08h30).",         "Directeur de Crise", "ORSAN"),
                (ago(minutes=28),          "Recherche lits Réa pédia dans hôpitaux partenaires.",              "Dr Claire BERNARD",  "ORSAN"),
                (ago(minutes=15),          "Restriction des visites — site Nord uniquement.",                  "Directeur de Crise", "Plan Blanc"),
                (ago(minutes=5),           "Communication interne via radios + affichage papier.",             "Sophie MOREAU",      "Décision direction"),
            ]
            for ts, contenu, resp, base in decisions:
                db.add(Decision(timestamp=ts, contenu=contenu, responsable=resp,
                                base_reglementaire=base, statut_validation="VALIDÉ"))
            db.commit()
            print(f"  ✓ {len(decisions)} décisions")

        # ──────────────────────────────────────────────────────────
        # 6. PRÉSENCES CELLULE DE CRISE
        # ──────────────────────────────────────────────────────────
        banner("6. Présences cellule")
        if db.query(Presence).count() < 3:
            presences = [
                (ago(hours=1, minutes=30), "Directeur de Crise",  "Directeur de Crise"),
                (ago(hours=1, minutes=28), "Marie LEFEVRE",       "RSSI"),
                (ago(hours=1, minutes=27), "Paul DUBOIS",         "DSI"),
                (ago(hours=1, minutes=22), "Anne MARTIN",         "DRH"),
                (ago(hours=1, minutes=18), "Dr Claire BERNARD",   "Médecin coordinateur"),
                (ago(hours=1, minutes=15), "Jean DURAND",         "Cadre de garde"),
                (ago(hours=1, minutes=10), "Sophie MOREAU",       "Communication"),
                (ago(minutes=48),          "Cdt POMPIERS",        "Liaison SDIS"),
                (ago(minutes=42),          "Lt SAMU",             "Liaison SAMU"),
                (ago(minutes=20),          "Représentant ARS",    "Liaison ARS"),
                (ago(minutes=15),          "Pharm. P. ROUX",      "Pharmacien chef"),
                (ago(minutes=8),           "Préfecture",          "Liaison Préfecture"),
            ]
            for ts, nom, role in presences:
                db.add(Presence(timestamp=ts, nom=nom, role=role, action="ENTRÉE"))
            db.commit()
            print(f"  ✓ {len(presences)} présences")

        # ──────────────────────────────────────────────────────────
        # 7. CONSIGNES
        # ──────────────────────────────────────────────────────────
        banner("7. Consignes")
        if db.query(Consigne).count() < 1:
            consignes = [
                ("TOUS",                "🚨 Toute communication externe doit passer par la cellule communication."),
                ("TOUS",                "📵 SIH HS — utiliser uniquement les formulaires papier (classeur PCA pôles)."),
                ("Cellule de crise",    "📞 Numéros utiles : ANSSI 0800-XX, ARS 0800-XX, Préfecture standard."),
                ("Pôles soins",         "🩺 Priorité 1 : urgences vitales et réa. Priorité 2 : urgences non vitales."),
                ("Cellule de crise",    "📊 Point situation toutes les 30 min (salle Direction 2e étage)."),
            ]
            for pour, texte in consignes:
                db.add(Consigne(timestamp=ago(hours=1, minutes=25),
                                pour=pour, texte=texte, accuse=False))
            db.commit()
            print(f"  ✓ {len(consignes)} consignes")

        # ──────────────────────────────────────────────────────────
        # 8. DÉCLARATIONS CAPACITAIRES
        # ──────────────────────────────────────────────────────────
        banner("8. Déclarations capacitaires")
        if db.query(CapaciteDeclaration).count() < 3:
            # Map UF → (statut_lits, statut_rh, tension_activee, lits_h, lits_f, lits_i, lits_sup)
            tension_map = {
                "URG-P":  ("critique",    "critique",     2, 0, 0, 0, 4),
                "PED-1":  ("critique",    "tension",      2, 0, 0, 0, 2),
                "PED-N":  ("tension",     "complet",      1, 1, 1, 0, 0),
                "REA-1":  ("tension",     "complet",      1, 1, 0, 1, 0),
                "USC":    ("tension",     "complet",      1, 2, 1, 2, 0),
                "URG-A":  ("tension",     "complet",      1, 2, 2, 1, 0),
                "MED-A":  ("normal",      "complet",      0, 5, 4, 0, 0),
                "MED-B":  ("normal",      "complet",      0, 6, 5, 0, 0),
                "CHIR":   ("normal",      "complet",      0, 4, 3, 0, 0),
                "CARDIO": ("normal",      "complet",      0, 3, 3, 0, 0),
                "MAT":    ("tension",     "complet",      1, 0, 5, 0, 0),
                "GERIA":  ("normal",      "complet",      0, 7, 8, 0, 0),
            }
            refs = db.query(CapaciteReferentiel).all()
            count = 0
            for ref in refs:
                if ref.uf_code not in tension_map:
                    continue
                s_lits, s_rh, tension, lh, lf, li, lsup = tension_map[ref.uf_code]
                db.add(CapaciteDeclaration(
                    referentiel_id=ref.id,
                    horodatage=ago(minutes=18),
                    redacteur="Jean DURAND",
                    point="matin",
                    lits_vides_h=lh, lits_vides_f=lf, lits_vides_i=li,
                    tension_activee=tension, lits_sup=lsup,
                    statut_lits=s_lits, statut_rh=s_rh,
                ))
                count += 1
            db.commit()
            print(f"  ✓ {count} déclarations capacitaires")

        # ──────────────────────────────────────────────────────────
        # 9. SERVICES TRANSVERSES (SOINS)
        # ──────────────────────────────────────────────────────────
        banner("9. Services transverses")
        if db.query(ServiceStatus).count() < 3:
            services_transverses = [
                ("securite_physique", "Sécurité physique", "OK",       "RAS"),
                ("logistique",        "Logistique",        "OK",       "Approvisionnement médicaments confirmé 48h"),
                ("si_dpi",            "DPI (SIH)",         "CRITIQUE", "🚨 Inaccessible depuis 06h17 — mode papier"),
                ("si_msg",            "Messagerie",        "CRITIQUE", "🚨 HS — communication radio uniquement"),
                ("si_bio",            "SIL biologie",      "DEGRADE",  "Mode papier, délais x3"),
                ("restauration",      "Restauration",      "OK",       "Renfort plateaux Plan Blanc activé"),
                ("blanchisserie",     "Blanchisserie",     "OK",       "RAS"),
                ("pharmacie",         "Pharmacie",         "OK",       "Stock urgences confirmé 48h"),
            ]
            for sid, lib, statut, comm in services_transverses:
                db.add(ServiceStatus(service_id=sid, libelle=lib,
                                     statut=statut, commentaire=comm))
            db.commit()
            print(f"  ✓ {len(services_transverses)} services transverses")

        # ──────────────────────────────────────────────────────────
        # 10. TRANSFERTS
        # ──────────────────────────────────────────────────────────
        banner("10. Transferts inter-établissements")
        if db.query(TransfertPatient).count() < 1:
            def hist(*events):
                return json.dumps([
                    {"ts": ts.isoformat(), "from": frm, "to": to, "user": user}
                    for ts, frm, to, user in events
                ])
            transferts = [
                # Transfert 1 : EN_COURS (bronchiolite sévère vers CHU)
                dict(nom="DUPONT", prenom="Léa",
                     date_naissance="2024-11-03",
                     ipp="P-202411-0042",
                     unite_origine="URG-P (Urgences pédiatriques)",
                     etablissement_origine="Hôpital Saint-Exemple — Site Nord",
                     unite_destination="Réa pédiatrique",
                     etablissement_destination="CHU PARTENAIRE",
                     site_destination="CHU Partenaire — Site principal",
                     statut="EN_COURS", redacteur="Dr Claire BERNARD",
                     commentaire="Bronchiolite VRS sévère — détresse respiratoire. Sat 88% sous O2.",
                     horodatage_creation=ago(minutes=42),
                     horodatage_depart=ago(minutes=28),
                     eta=in_future(minutes=18).isoformat(),
                     historique_json=hist(
                         (ago(minutes=42), "", "EN_PREPARATION", "c.bernard"),
                         (ago(minutes=28), "EN_PREPARATION", "EN_COURS", "c.bernard"),
                     )),
                # Transfert 2 : EN_COURS (bronchiolite vers hôpital Est)
                dict(nom="MARTIN", prenom="Théo",
                     date_naissance="2023-06-15",
                     ipp="P-202306-0118",
                     unite_origine="URG-P (Urgences pédiatriques)",
                     etablissement_origine="Hôpital Saint-Exemple — Site Nord",
                     unite_destination="Pédiatrie",
                     etablissement_destination="HOPITAL EST",
                     site_destination="Hôpital de l'Est — Site Vauban",
                     statut="EN_COURS", redacteur="Dr Claire BERNARD",
                     commentaire="Bronchiolite — pas de place réa pédia, repli HopEst.",
                     horodatage_creation=ago(minutes=32),
                     horodatage_depart=ago(minutes=18),
                     eta=in_future(minutes=28).isoformat(),
                     historique_json=hist(
                         (ago(minutes=32), "", "EN_PREPARATION", "c.bernard"),
                         (ago(minutes=18), "EN_PREPARATION", "EN_COURS", "c.bernard"),
                     )),
                # Transfert 3 : ARRIVE (SCA cardio)
                dict(nom="ROUX", prenom="Camille",
                     date_naissance="1958-02-22",
                     ipp="A-195802-0451",
                     unite_origine="URG-A (Urgences adultes)",
                     etablissement_origine="Hôpital Saint-Exemple — Site Nord",
                     unite_destination="Cardiologie interventionnelle",
                     etablissement_destination="CHU PARTENAIRE",
                     site_destination="CHU Partenaire — Pôle cardio",
                     statut="ARRIVE", redacteur="Jean DURAND",
                     commentaire="SCA ST+ — orientation cardio interventionnelle, KT 09h05.",
                     horodatage_creation=ago(hours=1, minutes=18),
                     horodatage_depart=ago(hours=1, minutes=8),
                     horodatage_arrivee=ago(minutes=22),
                     eta=ago(minutes=22).isoformat(),
                     historique_json=hist(
                         (ago(hours=1, minutes=18), "", "EN_PREPARATION", "j.durand"),
                         (ago(hours=1, minutes=8),  "EN_PREPARATION", "EN_COURS", "j.durand"),
                         (ago(minutes=22),          "EN_COURS", "ARRIVE", "j.durand"),
                     )),
                # Transfert 4 : EN_PREPARATION
                dict(nom="MORIN", prenom="Lucas",
                     date_naissance="2022-09-11",
                     ipp="P-202209-0287",
                     unite_origine="URG-P (Urgences pédiatriques)",
                     etablissement_origine="Hôpital Saint-Exemple — Site Nord",
                     unite_destination="Pédiatrie",
                     etablissement_destination="HOPITAL EST",
                     site_destination="Hôpital de l'Est — Site Vauban",
                     statut="EN_PREPARATION", redacteur="Dr Claire BERNARD",
                     commentaire="Bronchiolite VRS, en attente ambulance.",
                     horodatage_creation=ago(minutes=14),
                     eta=in_future(hours=1, minutes=5).isoformat(),
                     historique_json=hist(
                         (ago(minutes=14), "", "EN_PREPARATION", "c.bernard"),
                     )),
            ]
            for t in transferts:
                db.add(TransfertPatient(**t))
            db.commit()
            print(f"  ✓ {len(transferts)} transferts")

        # ──────────────────────────────────────────────────────────
        # 11. MESSAGES CHAT CELLULE
        # ──────────────────────────────────────────────────────────
        banner("11. Messages chat cellule de crise")
        if db.query(MessageInterne).count() < 3:
            def msg(exp_login, dest_login, contenu, ts, sujet=None):
                exp = user_by_login.get(exp_login)
                dest = user_by_login.get(dest_login)
                if not exp:
                    return None
                return MessageInterne(
                    expediteur_id=exp.id,
                    expediteur_nom=exp.display_name,
                    destinataire_id=(dest.id if dest else None),
                    destinataire_nom=(dest.display_name if dest else "TOUS"),
                    sujet=sujet,
                    contenu=contenu,
                    created_at=ts,
                    lu=(ts < ago(minutes=10)),
                )
            messages = [
                msg("dircrise",  None,         "Cellule activée. Premier point situation dans 15 min.", ago(hours=1, minutes=30), "Activation cellule"),
                msg("m.lefevre", None,         "Confirmation : LockBit. Procédure ANSSI en cours.",     ago(hours=1, minutes=10)),
                msg("p.dubois",  "dircrise",   "Tous les serveurs critiques isolés. Mode dégradé OK.",  ago(hours=1, minutes=2)),
                msg("a.martin",  None,         "Rappel personnel : 14/18 confirmés. ETA renforts 09h30.", ago(minutes=55)),
                msg("c.bernard", None,         "URG-P saturée. Je commence recherche transferts.",      ago(minutes=48)),
                msg("c.bernard", None,         "1er transfert validé vers CHU Partenaire (Léa D., bronchiolite).", ago(minutes=42)),
                msg("j.durand",  None,         "SCA ST+ orienté cardio CHU Part. via SAMU.",            ago(minutes=38)),
                msg("s.moreau",  "dircrise",   "Communiqué ARS prêt. Validation ?",                     ago(minutes=32), "Communication ARS"),
                msg("dircrise",  "s.moreau",   "Validé. Diffusion ARS + Préf.",                         ago(minutes=30)),
                msg("m.lefevre", None,         "Backups intègres. Restauration phase 1 dans 2h.",       ago(minutes=22)),
                msg("c.bernard", None,         "2e transfert pédia vers HopEst (Théo M.).",             ago(minutes=18)),
                msg("c.bernard", None,         "3e transfert pédia en préparation (Lucas M.).",         ago(minutes=5)),
            ]
            count = 0
            for m in messages:
                if m is not None:
                    db.add(m); count += 1
            db.commit()
            print(f"  ✓ {count} messages")

        # ──────────────────────────────────────────────────────────
        # 12. MAIN COURANTE
        # ──────────────────────────────────────────────────────────
        banner("12. Main courante")
        if db.query(MainCouranteLog).count() < 3:
            logs = [
                (ago(hours=3, minutes=13), "Marie LEFEVRE",   "RSSI",            "INCIDENT",   "DÉTECTION",  "Alerte EDR : activité ransomware sur SRV-DPI-01"),
                (ago(hours=3, minutes=5),  "Paul DUBOIS",     "DSI",             "INCIDENT",   "ISOLEMENT",  "Isolation SRV-DPI-01 + 4 serveurs liés du réseau"),
                (ago(hours=2, minutes=42), "Sophie MOREAU",   "Communication",   "INCIDENT",   "BASCULE",    "Bascule téléphonie sur ligne RTC secours"),
                (ago(hours=1, minutes=45), "Directeur de Crise", "Direction",    "DECISION",   "ACTIVATION", "Plan Blanc niveau 2 — décision direction"),
                (ago(hours=1, minutes=30), "Directeur de Crise", "Direction",    "DECISION",   "ACTIVATION", "Cellule de crise activée, 7 acteurs présents"),
                (ago(hours=1, minutes=10), "Sophie MOREAU",   "Communication",   "MESSAGE",    "ENVOYÉ",     "Information ARS — point situation 30 min"),
                (ago(minutes=55),          "Anne MARTIN",     "DRH",             "DECISION",   "RAPPEL",     "Rappel 18 personnels — 14 confirmés"),
                (ago(minutes=42),          "Dr Claire BERNARD","Médecin coord", "TRANSFERT",  "CRÉÉ",       "Validation transfert n°2403-0001 (Léa DUPONT)"),
                (ago(minutes=22),          "Marie LEFEVRE",   "RSSI",            "INCIDENT",   "MODIFIÉ",    "Backups intègres confirmés"),
                (ago(minutes=8),           "Jean DURAND",     "Cadre de garde",  "INCIDENT",   "RÉSOLU",     "Stock urgences validé 48h"),
            ]
            for ts, auteur, role, cat, action, _msg in logs:
                db.add(MainCouranteLog(
                    timestamp=ts, auteur=auteur, auteur_role=role,
                    categorie=cat, action=action,
                ))
            db.commit()
            print(f"  ✓ {len(logs)} entrées main courante")

        # ──────────────────────────────────────────────────────────
        # 13. REX archivé
        # ──────────────────────────────────────────────────────────
        banner("13. REX archivé")
        if db.query(RexEntry).count() < 1:
            db.add(RexEntry(
                titre="Exercice cyber pédia — 12 mai 2026",
                type_crise="MIXTE",
                duree_minutes=180,
                nb_poles=4,
                nb_decisions=12,
                nb_jalons_total=24,
            ))
            db.commit()
            print("  ✓ 1 REX archivé")

        # ──────────────────────────────────────────────────────────
        # FIN
        # ──────────────────────────────────────────────────────────
        banner("✓ SCÉNARIO MOCKUP SEEDÉ AVEC SUCCÈS")
        print(f"  Scénario : Cyber + Bronchiolite — généré à {NOW.strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"  Comptes utiles :")
        print(f"    dircrise / changeme     (admin — Directeur de Crise)")
        print(f"    m.lefevre / demo2026    (RSSI)")
        print(f"    c.bernard / demo2026    (médecin coordinateur)")
        print()

    finally:
        db.close()


if __name__ == "__main__":
    seed()
