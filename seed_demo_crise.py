"""
seed_demo_crise.py — SCRIBE v2.0.4

Injecte un scénario démo de cyberattaque (ransomware LockBit) pour la
DÉMO 1 (Centre Hospitalier de Valmont). Permet aux nouveaux utilisateurs
qui clonent le repo de découvrir SCRIBE avec une crise déjà en cours,
plutôt qu'une instance vide.

Données injectées (toutes fictives, hôpital fictif "Valmont") :
  - 5 incidents en cascade (cyber + impact sanitaire)
  - 3 décisions de cellule de crise
  - 4 présences cellule
  - 3 consignes de relève
  - 2 messages internes

Aucune donnée patient réelle n'est jamais utilisée. Tous les noms,
identifiants et localisations sont fictifs.

Idempotent : si la DB contient déjà des incidents, le seed s'abstient
pour ne pas créer de doublons.
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, timezone

# Setup imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal, engine, Base
import app.models as models

# Fenêtre temporelle de la crise simulée (commence 2h dans le passé)
NOW = datetime.now(timezone.utc)
T0  = NOW - timedelta(hours=2)


def _t(minutes_after_t0: int) -> datetime:
    """Retourne l'horodatage UTC d'un événement, décalé de N minutes après T0."""
    return T0 + timedelta(minutes=minutes_after_t0)


def seed_crise(db) -> int:
    """Insère les données démo. Retourne le nombre d'éléments créés."""
    created = 0

    # ── 5 INCIDENTS EN CASCADE ───────────────────────────────────────────
    incidents = [
        dict(
            type_crise="CYBER",
            urgency=4,
            site_id="Site Principal",
            unite_fonctionnelle="DSI",
            fait="Détection ransomware LockBit sur 3 serveurs de fichiers. "
                 "Notes de rançon trouvées dans plusieurs partages. "
                 "Chiffrement actif observé.",
            analyse="Compromission probable depuis 48-72h via VPN expose. "
                    "SIH partiellement impacté. Système d'imagerie KO. "
                    "DPI accessible mais lecture seule.",
            declarant_nom="Karim Belkacem",
            status="EN_COURS",
            impact_fonctionnel=True,
            timestamp_creation=_t(0),
        ),
        dict(
            type_crise="CYBER",
            urgency=3,
            site_id="Site Principal",
            unite_fonctionnelle="DSI",
            fait="Isolation réseau effectuée : déconnexion VLAN serveurs. "
                 "Coupure liaison fibre site secondaire en mesure conservatoire.",
            analyse="Mesure technique d'urgence. Validée par RSSI et DSI. "
                    "Impact métier sur radiologie et biologie attendu.",
            declarant_nom="Karim Belkacem",
            status="RÉSOLU",
            impact_fonctionnel=True,
            timestamp_creation=_t(15),
        ),
        dict(
            type_crise="MIXTE",
            urgency=3,
            site_id="Site Principal",
            unite_fonctionnelle="URGENCES",
            fait="Bascule mode dégradé urgences : retour aux supports papier. "
                 "DPI inaccessible, plus d'antériorité patient consultable.",
            analyse="Activation procédure dégradée. Cadres de garde mobilisés "
                    "pour appui des équipes médicales aux urgences.",
            declarant_nom="Sophie Lambert",
            status="EN_COURS",
            impact_fonctionnel=True,
            timestamp_creation=_t(35),
        ),
        dict(
            type_crise="SANITAIRE",
            urgency=2,
            site_id="Site Principal",
            unite_fonctionnelle="IMAGERIE",
            fait="Imagerie médicale : examens programmés non urgents reportés. "
                 "Urgences vitales acheminées vers CH de Valmont-Sud.",
            analyse="Conséquence directe de l'isolation des serveurs PACS. "
                    "Convention d'entraide territoriale activée.",
            declarant_nom="Dr. Marc Renard",
            status="EN_COURS",
            impact_fonctionnel=True,
            timestamp_creation=_t(60),
        ),
        dict(
            type_crise="CYBER",
            urgency=2,
            site_id="Site Principal",
            unite_fonctionnelle="DSI",
            fait="CERT Santé contacté et notifié de l'incident. "
                 "Premiers échanges techniques avec leurs experts.",
            analyse="Notification réglementaire NIS2 dans les délais. "
                    "Appui CERT pour l'analyse forensique en cours.",
            declarant_nom="Karim Belkacem",
            status="RÉSOLU",
            impact_fonctionnel=False,
            timestamp_creation=_t(90),
        ),
    ]

    for inc_data in incidents:
        ts = inc_data.pop("timestamp_creation")
        inc = models.SitrepEntry(**inc_data)
        inc.timestamp = ts
        db.add(inc)
        created += 1

    # ── 4 PRÉSENCES CELLULE DE CRISE ─────────────────────────────────────
    presences = [
        dict(nom="Hélène Dubois", role="Directrice de l'établissement",
             action="Activation cellule de crise",
             timestamp_creation=_t(20)),
        dict(nom="Karim Belkacem", role="RSSI",
             action="Briefing cyber initial",
             timestamp_creation=_t(22)),
        dict(nom="Dr. Pierre Martin", role="Président CME",
             action="Coordination médicale",
             timestamp_creation=_t(25)),
        dict(nom="Sophie Lambert", role="Cadre supérieure de garde",
             action="Reporting opérationnel terrain",
             timestamp_creation=_t(40)),
    ]
    for p_data in presences:
        ts = p_data.pop("timestamp_creation")
        p = models.Presence(**p_data)
        p.timestamp = ts
        db.add(p)
        created += 1

    # ── 3 DÉCISIONS ──────────────────────────────────────────────────────
    decisions = [
        dict(contenu="Activation du Plan Blanc niveau 1 — coordination "
                     "renforcée des équipes de garde",
             responsable="Hélène Dubois",
             base_reglementaire="Plan Blanc",
             statut_validation="VALIDÉ",
             timestamp_creation=_t(25)),
        dict(contenu="Isolation réseau préventive : déconnexion serveurs "
                     "fichiers + coupure VPN externe",
             responsable="Karim Belkacem",
             base_reglementaire="NIS2 — mesures conservatoires",
             statut_validation="VALIDÉ",
             timestamp_creation=_t(15)),
        dict(contenu="Convention d'entraide territoriale activée avec "
                     "CH Valmont-Sud pour les urgences vitales imagerie",
             responsable="Hélène Dubois",
             base_reglementaire="ORSAN — entraide territoriale",
             statut_validation="VALIDÉ",
             timestamp_creation=_t(60)),
    ]
    for d_data in decisions:
        ts = d_data.pop("timestamp_creation")
        d = models.Decision(**d_data)
        d.timestamp = ts
        db.add(d)
        created += 1

    # ── 3 CONSIGNES DE RELÈVE ────────────────────────────────────────────
    consignes = [
        dict(pour="Cadre de garde nuit",
             texte="Maintenir la procédure dégradée urgences. "
                   "Pas de nouvelle programmation imagerie sans aval CME.",
             timestamp_creation=_t(95)),
        dict(pour="Astreinte DSI",
             texte="Surveiller la levée de l'isolation réseau prévue "
                   "demain 6h. Coordination avec CERT Santé.",
             timestamp_creation=_t(100)),
        dict(pour="Direction de garde",
             texte="Communication interne établie ce soir 18h. "
                   "Pas de communiqué externe avant validation Direction.",
             timestamp_creation=_t(110)),
    ]
    for c_data in consignes:
        ts = c_data.pop("timestamp_creation")
        c = models.Consigne(**c_data)
        c.timestamp = ts
        db.add(c)
        created += 1

    db.commit()
    return created


def main():
    print("[seed_demo_crise] Initialisation du scénario démo cyberattaque...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Idempotence : si déjà des incidents en DB, on ne re-seed pas
        n_existing = db.query(models.SitrepEntry).count()
        if n_existing > 0:
            print(f"[seed_demo_crise] {n_existing} incidents déjà présents — "
                  f"seed ignoré (idempotent).")
            return 0
        n_created = seed_crise(db)
        print(f"[seed_demo_crise] ✓ {n_created} éléments démo injectés "
              f"(5 incidents + 4 présences + 3 décisions + 3 consignes).")
        print("[seed_demo_crise] Scénario : Cyberattaque ransomware LockBit "
              "au CH de Valmont (fictif). Connectez-vous pour découvrir.")
        return 0
    except Exception as e:
        print(f"[seed_demo_crise] ⚠ Erreur : {type(e).__name__}: {e}")
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
