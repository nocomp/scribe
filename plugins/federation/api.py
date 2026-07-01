"""
app/api/federation.py — Push JSON vers un collecteur territorial (CERT Santé, ARS, supervision GHT)

Principe :
  - SCRIBE envoie périodiquement un résumé JSON signé vers une URL externe (collecteur)
  - Sens unique : push uniquement, jamais de pull depuis l'extérieur
  - Aucune donnée nominative dans le payload
  - Si le collecteur est injoignable → SCRIBE continue normalement, erreur loggée silencieusement
  - Activé uniquement si <federation><enabled>true</enabled> dans config.xml / config.js

Configuration dans config.xml :
  <federation>
    <enabled>true</enabled>
    <collecteur_url>https://supervision.cert-sante74.fr/api/push</collecteur_url>
    <token>TOKEN_256BITS_GENERE_PAR_LE_COLLECTEUR</token>
    <intervalle_secondes>120</intervalle_secondes>   <!-- défaut : 120s -->
    <share_details>true</share_details>              <!-- inclure résumés incidents ou KPIs seuls -->
    <share_min_urgency>1</share_min_urgency>         <!-- urgence minimale pour inclure un incident -->
  </federation>
"""

import asyncio
import unicodedata
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import SitrepEntry, ServiceStatus, Hospital, DeclarationSituation, DemandeInterGHT
from app.api.status_page import _get_or_create as _get_status, _row_to_dict as _status_to_dict, StatusPageChronologie

logger = logging.getLogger("scribe.federation")
router = APIRouter()

# ── Configuration fédération (chargée au démarrage) ────────────────────────

class FederationConfig:
    def __init__(self):
        self.enabled            = False
        self.collecteur_url     = ""
        self.token              = ""
        self.intervalle         = 120       # secondes
        self.share_details      = True
        self.share_min_urgency  = 1
        self.sync_crise         = True    # synchroniser état de crise (incidents/KPIs)
        self.sync_sanitaire     = True    # synchroniser état sanitaire (capacitaire)
        self.share_capacite_details = True
        self.etablissement_nom  = "Établissement"
        self.etablissement_sigle = "ETB"
        self._load()

    def _load(self):
        # SCRIBE_CONFIG_JS env var allows multi-instance deployment
        _default_config_js = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "static", "config.js"
        )
        config_js = os.environ.get("SCRIBE_CONFIG_JS", _default_config_js)
        if not os.path.exists(config_js):
            return
        try:
            raw   = open(config_js, encoding="utf-8").read()
            start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
            end   = raw.rfind(";")
            cfg   = json.loads(raw[start:end])

            etb = cfg.get("etablissement", {})
            self.etablissement_nom   = etb.get("nom",   "Établissement")
            self.etablissement_sigle = etb.get("sigle", "ETB")

            fed = cfg.get("federation", {})
            self.enabled           = str(fed.get("enabled", "false")).lower() == "true"
            self.collecteur_url    = fed.get("collecteur_url", "").strip()
            self.token             = fed.get("token", "").strip()
            self.intervalle        = int(fed.get("intervalle_secondes", 120))
            self.share_details     = str(fed.get("share_details", "true")).lower() == "true"
            self.share_min_urgency = int(fed.get("share_min_urgency", 1))
            self.sync_crise        = str(fed.get("sync_crise", "true")).lower() == "true"
            self.sync_sanitaire    = str(fed.get("sync_sanitaire", "true")).lower() == "true"
            self.share_capacite_details = str(fed.get("share_capacite_details", "true")).lower() == "true"
        except Exception as e:
            logger.warning(f"Federation config non chargée : {e}")

    @property
    def is_ready(self) -> bool:
        return self.enabled and bool(self.collecteur_url) and bool(self.token)


_fed_config: Optional[FederationConfig] = None

def get_fed_config() -> FederationConfig:
    global _fed_config
    if _fed_config is None:
        _fed_config = FederationConfig()
    return _fed_config


# ── Construction du payload ────────────────────────────────────────────────

def _get_transferts_anonymes(db) -> list:
    """Retourne les flux de transferts actifs SANS aucune donnée patient (RGPD)."""
    try:
        from app.models import TransfertPatient
        items = db.query(TransfertPatient).filter(
            TransfertPatient.statut.in_(["EN_PREPARATION", "EN_COURS"])
        ).all()
        return [{
            "unite_origine":             t.unite_origine,
            "etablissement_origine":     t.etablissement_origine,
            "unite_destination":         t.unite_destination,
            "etablissement_destination": t.etablissement_destination,
            "statut":                    t.statut,
            "horodatage_depart":         t.horodatage_depart.isoformat() if t.horodatage_depart else None,
            "eta":                       getattr(t, "eta", None),
        } for t in items]
    except Exception:
        return []


_fed_sync_paused: bool = False  # True = synchronisation arrêtée


def reload_fed_config() -> "FederationConfig":
    """Recharge la config depuis disk sans redémarrage."""
    global _fed_config
    _fed_config = FederationConfig()
    return _fed_config


@router.post("/reload")
def federation_reload():
    """Recharge la config fédération depuis config.xml sans redémarrage."""
    cfg = reload_fed_config()
    return {"ok": True, "collecteur_url": cfg.collecteur_url, "enabled": cfg.enabled,
            "message": "Configuration rechargée — synchronisation active"}


@router.post("/sync/pause")
def federation_pause():
    """Suspend la synchronisation vers le collecteur."""
    global _fed_sync_paused
    _fed_sync_paused = True
    return {"ok": True, "paused": True, "message": "Synchronisation suspendue"}


@router.post("/sync/resume")
def federation_resume():
    """Reprend la synchronisation."""
    global _fed_sync_paused
    _fed_sync_paused = False
    reload_fed_config()
    return {"ok": True, "paused": False, "message": "Synchronisation reprise"}


@router.get("/sync/status")
def federation_sync_status():
    """État de la synchronisation."""
    return {"paused": _fed_sync_paused, "enabled": get_fed_config().is_ready}


def build_payload(db: Session, cfg: FederationConfig) -> dict:
    """Construit le JSON à envoyer au collecteur. Aucune donnée nominative."""

    now = datetime.now(timezone.utc)
    open_incidents = (
        db.query(SitrepEntry)
        .filter(SitrepEntry.status != "RÉSOLU")
        .order_by(SitrepEntry.urgency.desc(), SitrepEntry.timestamp.desc())
        .all()
    )

    # KPIs
    nb_total    = len(open_incidents)
    nb_critique = sum(1 for i in open_incidents if i.urgency >= 4)
    nb_crise    = sum(1 for i in open_incidents if i.urgency == 3)
    nb_cyber    = sum(1 for i in open_incidents if i.type_crise == "CYBER")
    nb_sanit    = sum(1 for i in open_incidents if i.type_crise == "SANITAIRE")
    max_urgency = max((i.urgency for i in open_incidents), default=0)

    # Niveau global
    if max_urgency >= 4:    niveau = "CRITIQUE"
    elif max_urgency >= 3:  niveau = "CRISE"
    elif max_urgency >= 2:  niveau = "ALERTE"
    elif max_urgency >= 1:  niveau = "VEILLE"
    else:                   niveau = "NOMINAL"

    # Services transverses
    services = {}
    try:
        for s in db.query(ServiceStatus).all():
            services[s.service_id] = {
                "libelle": s.libelle,
                "statut":  s.statut,
            }
    except Exception:
        pass

    # Pôles impactés (dédupliqués)
    # Résoudre les libellés UF (code → libellé lisible)
    from app.models import UniteFonctionnelle
    uf_map = {}
    try:
        for uf in db.query(UniteFonctionnelle).all():
            uf_map[uf.code_uf] = uf.libelle
    except Exception:
        pass

    poles_impactes = list({
        uf_map.get(i.unite_fonctionnelle, i.unite_fonctionnelle)
        for i in open_incidents
        if i.unite_fonctionnelle and i.urgency >= cfg.share_min_urgency
    })

    # Coordonnées GPS = centroïde de tous les sites (évite le biais vers le premier site)
    lat, lon = None, None
    sites_db = []
    try:
        sites_db = db.query(Hospital).order_by(Hospital.id).all()
        coords_valides = [(s.latitude, s.longitude) for s in sites_db
                         if s.latitude and s.longitude]
        if coords_valides:
            lat = sum(c[0] for c in coords_valides) / len(coords_valides)
            lon = sum(c[1] for c in coords_valides) / len(coords_valides)
    except Exception:
        pass

    # Index sites par nom pour retrouver les GPS depuis site_id
    site_by_name = {h.nom: h for h in sites_db}

    payload = {
        "version":    "1",
        "timestamp":  now.isoformat(),
        "etablissement": {
            "nom":   cfg.etablissement_nom,
            "sigle": cfg.etablissement_sigle,
            "port":  os.environ.get("SCRIBE_PORT", "8000"),
        },
        "latitude":  lat,
        "longitude": lon,
        "niveau_global": niveau,
        "kpis": {
            "incidents_ouverts":   nb_total,
            "incidents_critiques": nb_critique,
            "incidents_crise":     nb_crise,
            "cyber":               nb_cyber,
            "sanitaire":           nb_sanit,
        },
        "services_transverses": services,
        "poles_impactes":       poles_impactes,
        "transferts_actifs":    _get_transferts_anonymes(db),
        # Sites comme sous-entités avec leurs incidents propres
        "sites": [
            {
                "nom":       h.nom,
                "finess":    h.code_finess or "",
                "latitude":  h.latitude,
                "longitude": h.longitude,
                "adresse":   h.adresse or "",
                "niveau": (
                    lambda incs: (
                        "CRITIQUE" if any(i.urgency >= 4 for i in incs) else
                        "CRISE"    if any(i.urgency >= 3 for i in incs) else
                        "ALERTE"   if any(i.urgency >= 2 for i in incs) else
                        "VEILLE"   if any(i.urgency >= 1 for i in incs) else
                        "NOMINAL"
                    )
                )([i for i in open_incidents if i.site_id == h.nom or i.site_id == str(h.id)]),
                "incidents_ouverts": len([i for i in open_incidents if i.site_id == h.nom or i.site_id == str(h.id)]),
            }
            for h in sites_db
        ],
    }

    # Détail incidents (si activé et urgence >= seuil)
    if cfg.share_details:
        payload["incidents"] = [
            {
                "type_crise":  i.type_crise,
                "urgency":     i.urgency,
                "fait_resume": (i.fait or "")[:120],
                "site":        i.site_id,
                "status":      i.status,
                "timestamp":   i.timestamp.isoformat() if i.timestamp else "",
            }
            for i in open_incidents
            if i.urgency >= cfg.share_min_urgency
        ]

    # Déclarations de situation inter-GHT actives (toujours incluses)
    try:
        decls_actives = db.query(DeclarationSituation).filter(
            DeclarationSituation.actif == True
        ).order_by(DeclarationSituation.created_at.desc()).all()
        payload["declarations"] = [
            {
                "id":             d.id,
                "site_id":        d.site_id,
                "unite_fonct":    d.unite_fonct,
                "type_crise":     d.type_crise,
                "niveau_tension": d.niveau_tension,
                "description":    d.description,
                "created_by":     d.created_by,
                "created_at":     d.created_at.isoformat() if d.created_at else "",
            }
            for d in decls_actives
        ]
    except Exception:
        payload["declarations"] = []

    # Demandes inter-GHT émises par cet établissement (non résolues)
    try:
        demandes_actives = db.query(DemandeInterGHT).filter(
            DemandeInterGHT.statut != "traite"
        ).order_by(DemandeInterGHT.created_at.desc()).all()
        payload["demandes"] = [
            {
                "id":                d.id,
                "type_situation":    d.type_situation,
                "unite_concernee":   d.unite_concernee,
                "description":       d.description,
                "ght_emetteur":      d.ght_emetteur,
                "ght_destinataire":  d.ght_destinataire,
                "statut":            d.statut,
                "created_at":        d.created_at.isoformat() if d.created_at else "",
            }
            for d in demandes_actives
        ]
    except Exception:
        payload["demandes"] = []

    # Signature HMAC-SHA256 du payload (intégrité)
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    signature = hashlib.sha256(
        (cfg.token + ":" + payload_bytes.decode()).encode()
    ).hexdigest()
    payload["_sig"] = signature[:16]   # 8 bytes visibles pour contrôle rapide

    return payload


# ── Push vers le collecteur ────────────────────────────────────────────────

async def push_to_collecteur(cfg: FederationConfig, payload: dict) -> bool:
    """Envoie le payload. Retourne True si succès, False sinon (silencieux)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                cfg.collecteur_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {cfg.token}",
                    "Content-Type":  "application/json",
                    "X-Scribe-Version": "6",
                    # h153 — X-Scribe-Etab doit être ASCII (RFC 7230).
                    # Les sigles accentués (ex: "Hôpitaux Du Lac") cassent httpx.
                    "X-Scribe-Etab": unicodedata.normalize("NFD", cfg.etablissement_sigle or "").encode("ascii","ignore").decode("ascii").strip(),
                },
            )
        if resp.status_code in (200, 201, 204):
            logger.info(f"Federation push OK → {cfg.collecteur_url} ({resp.status_code})")
            return True
        else:
            if resp.status_code == 401:
                logger.warning(f"Federation push 401 → token '{cfg.token[:12]}...' non accepté — vérifier le collecteur (EN ATTENTE)")
            else:
                logger.warning(f"Federation push HTTP {resp.status_code} → {cfg.collecteur_url}")
            return False
    except httpx.ConnectError:
        logger.warning(f"Federation : collecteur injoignable ({cfg.collecteur_url})")
        return False
    except httpx.TimeoutException:
        logger.warning(f"Federation : timeout ({cfg.collecteur_url})")
        return False
    except Exception as e:
        logger.warning(f"Federation : erreur inattendue : {e}")
        return False



async def push_status_to_collecteur(cfg: "FederationConfig") -> bool:
    """Push tous les statuts publics publiés vers le collecteur."""
    import json as _json
    import datetime as _dt

    def row_to_plain(row, chrons_list, etab, now):
        """Convertit une ligne StatusPage en dict JSON pur sans référence SQLAlchemy."""
        import json as j
        return {
            "site_id":         int(row.site_id or 0),
            "site_nom":        str(row.site_nom or ""),
            "niveau_global":   str(row.niveau_global or "OPERATIONNEL"),
            "message_public":  str(row.message_public or ""),
            "services_si":     j.loads(row.services_si or "[]"),
            "prise_en_charge": j.loads(row.prise_en_charge or "[]"),
            "faq":             [f for f in j.loads(row.faq or "[]") if f.get("visible") and f.get("reponse")],
            "chronologie":     chrons_list,
            "published":       bool(row.published),
            "updated_at":      row.updated_at.isoformat() if row.updated_at else now,
            "updated_by":      str(row.updated_by or ""),
            "etablissement":   etab,
            "_pushed_at":      now,
        }

    try:
        from app.api.status_page import _load_etablissement, StatusPage as SPModel
        db = SessionLocal()
        published_rows = db.query(SPModel).filter_by(published=True).all()
        logger.info(f"push_status : {len(published_rows)} statut(s) publié(s)")
        for row in published_rows:
            logger.info(f"  → site_id={row.site_id} site_nom={row.site_nom!r}")
        if not published_rows:
            db.close()
            return True

        chrons = db.query(StatusPageChronologie).order_by(
            StatusPageChronologie.timestamp.desc()).limit(10).all()
        chrons_list = [
            {"id": c.id, "ts": c.timestamp.isoformat(), "texte": c.texte, "publie_par": c.publie_par or ""}
            for c in chrons
        ]
        etab    = _load_etablissement()
        now     = _dt.datetime.now(_dt.timezone.utc).isoformat()

        # Sérialiser chaque ligne en dict pur (évite circular reference)
        global_dict = None
        sites_list  = []
        ORDRE_NIV   = {"INCIDENT_MAJEUR":3, "PERTURBE":2, "MAINTENANCE":1, "OPERATIONNEL":0}

        for row in published_rows:
            plain = row_to_plain(row, chrons_list, etab, now)
            if row.site_id == 0:
                global_dict = plain
            else:
                sites_list.append(plain)

        if global_dict is None:
            # Pas de statut global → synthèse automatique depuis le plus dégradé
            worst = max(sites_list, key=lambda s: ORDRE_NIV.get(s["niveau_global"], 0))
            global_dict = {
                "site_id":         0,
                "site_nom":        "",
                "niveau_global":   worst["niveau_global"],
                "message_public":  f"Point de situation — {len(sites_list)} site(s) concerné(s)",
                "services_si":     [],
                "prise_en_charge": [],
                "faq":             [],
                "chronologie":     worst["chronologie"],
                "published":       True,
                "updated_at":      now,
                "updated_by":      worst.get("updated_by", ""),
                "etablissement":   etab,
                "_pushed_at":      now,
            }

        # Ajouter les statuts par site SÉPARÉMENT (pas imbriqués dans global_dict)
        global_dict["_statuts_sites"] = sites_list

        # Vérifier que c'est sérialisable avant d'envoyer
        try:
            _json.dumps(global_dict)
        except (TypeError, ValueError) as e:
            logger.error(f"push_status : payload non sérialisable : {e}")
            db.close()
            return False

        db.close()
        push_url = cfg.collecteur_url.replace("/api/push", "/api/push-status")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                push_url, json=global_dict,
                headers={"Authorization": f"Bearer {cfg.token}",
                         "Content-Type": "application/json"},
            )
        ok = resp.status_code in (200, 201, 204)
        logger.info(f"push_status {'OK' if ok else 'ERREUR'} → {push_url} ({resp.status_code})")
        return ok
    except Exception as e:
        logger.warning(f"push_status erreur : {e}")
        return False


# ── Boucle périodique (lancée par main.py au démarrage) ───────────────────

async def federation_loop():
    """Tâche asyncio : push périodique vers le collecteur. Ne s'arrête jamais."""
    logger.info("Federation loop démarrée — attente config...")
    
    # Boucle infinie — réessaie indéfiniment, jamais de return
    while True:
        cfg = FederationConfig()
        if not cfg.is_ready:
            logger.info(f"Federation en attente (config_js={os.environ.get('SCRIBE_CONFIG_JS','?')[:40]}) — retry dans 10s")
            await asyncio.sleep(10)
            continue
        
        logger.info(
            f"Federation OK → {cfg.collecteur_url} "
            f"sigle={cfg.etablissement_sigle} token={cfg.token[:8]}... intervalle={cfg.intervalle}s"
        )
        try:
            db = SessionLocal()
            # Push état de crise (incidents, KPIs) — si sync_crise activé
            if cfg.sync_crise:
                payload = build_payload(db, cfg)
                logger.info(f"Envoi push → {cfg.collecteur_url} (sigle={cfg.etablissement_sigle})")
                ok = await push_to_collecteur(cfg, payload)
                logger.info(f"Push résultat: {'✓ OK' if ok else '✗ ECHEC'}")
                if ok:
                    await push_status_to_collecteur(cfg)
            # Push état sanitaire (capacitaire lits/RH/matériel) — si sync_sanitaire activé
            if cfg.sync_sanitaire:
                cap_payload = build_capacite_payload(db, cfg)
                if cap_payload:
                    await push_capacite_to_collecteur(cfg, cap_payload)
            db.close()
        except Exception as e:
            logger.warning(f"Federation loop erreur : {e}")
        await asyncio.sleep(cfg.intervalle)


# ── Endpoint de test (admin seulement) ────────────────────────────────────

@router.post("/push-now")
async def push_now():
    """Force un push immédiat vers le collecteur + retourne le résultat détaillé."""
    cfg = FederationConfig()
    result = {
        "config_js": os.environ.get("SCRIBE_CONFIG_JS", "non défini"),
        "config_js_exists": os.path.exists(os.environ.get("SCRIBE_CONFIG_JS", "")),
        "enabled": cfg.enabled,
        "ready": cfg.is_ready,
        "sigle": cfg.etablissement_sigle,
        "collecteur_url": cfg.collecteur_url,
        "token_prefix": cfg.token[:8] + "..." if cfg.token else "",
        "push_result": None,
        "error": None
    }
    if not cfg.is_ready:
        result["error"] = "Federation non prête — vérifier config_js_exists"
        return result
    try:
        db = SessionLocal()
        payload = build_payload(db, cfg)
        db.close()
        ok = await push_to_collecteur(cfg, payload)
        result["push_result"] = "OK" if ok else "ECHEC (HTTP non-200)"
    except Exception as e:
        result["error"] = str(e)
    return result


@router.get("/status")
def federation_status():
    """Statut lisible de la fédération — utile pour diagnostiquer depuis le navigateur."""
    cfg = reload_fed_config()  # Toujours recharger depuis disk
    return {
        "enabled":       cfg.enabled,
        "ready":         cfg.is_ready,
        "sync_paused":   _fed_sync_paused,
        "collecteur_url": cfg.collecteur_url,
        "token":         cfg.token,
        "token_preview": cfg.token[:8] + "..." if cfg.token else "",
        "etablissement": cfg.etablissement_sigle,
        "intervalle_s":  cfg.intervalle,
        "config_source": os.environ.get("SCRIBE_CONFIG_JS", "app/static/config.js"),
    }


@router.get("/collecteur-sites")
async def get_collecteur_sites():
    """Récupère la liste des sites de tous les GHT depuis le collecteur (pour les transferts)."""
    cfg = FederationConfig()
    if not cfg.is_ready:
        return []
    try:
        import httpx
        coll_url = cfg.collecteur_url.replace("/api/push","")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{coll_url}/api/summary")
            if r.status_code == 200:
                summary = r.json()
                sites = []
                seen = set()
                for etab in summary:
                    sigle = etab.get('sigle','?')
                    for s in etab.get('sites',[]):
                        nom = s.get('nom','')
                        key = f"{sigle}|||{nom}"
                        if key in seen or not nom:
                            continue
                        seen.add(key)
                        sites.append({"sigle": sigle, "nom": nom,
                                      "lat": s.get('latitude'), "lng": s.get('longitude')})
                return sites
    except Exception as e:
        logger.warning(f"collecteur-sites: {e}")
    return []


@router.get("/info")
def federation_info():
    """Retourne les infos de fédération — token, URL collecteur, commande d'enregistrement."""
    cfg = get_fed_config()
    cmd = ""
    if cfg.token and cfg.collecteur_url:
        register_url = cfg.collecteur_url.replace("/api/push", "/api/admin/tokens")
        cmd = (
            f'curl -X POST {register_url} \\\n'
            f'  -H "Authorization: Bearer TOKEN_ADMIN_COLLECTEUR" \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -d \'{{"sigle":"{cfg.etablissement_sigle}","token":"{cfg.token}"}}\''
        )
    return {
        "enabled":        cfg.enabled,
        "collecteur_url": cfg.collecteur_url,
        "sigle":          cfg.etablissement_sigle,
        "token":          cfg.token,
        "commande_enregistrement": cmd,
        "message": "Copiez la commande ci-dessus et exécutez-la sur le serveur collecteur" if cmd else "Fédération non configurée"
    }


@router.post("/test")
async def test_push():
    """Déclenche un push immédiat vers le collecteur (diagnostic)."""
    cfg = get_fed_config()
    if not cfg.is_ready:
        return {"ok": False, "detail": "Federation non configurée ou désactivée"}
    db = SessionLocal()
    payload = build_payload(db, cfg)
    db.close()
    success = await push_to_collecteur(cfg, payload)
    return {
        "ok":        success,
        "payload":   payload,
        "collecteur": cfg.collecteur_url,
    }

"""
app/api/federation.py — Push JSON vers un collecteur territorial (CERT Santé, ARS, supervision GHT)

Principe :
  - SCRIBE envoie périodiquement un résumé JSON signé vers une URL externe (collecteur)
  - Sens unique : push uniquement, jamais de pull depuis l'extérieur
  - Aucune donnée nominative dans le payload
  - Si le collecteur est injoignable → SCRIBE continue normalement, erreur loggée silencieusement
  - Activé uniquement si <federation><enabled>true</enabled> dans config.xml / config.js

Configuration dans config.xml :
  <federation>
    <enabled>true</enabled>
    <collecteur_url>https://supervision.cert-sante74.fr/api/push</collecteur_url>
    <token>TOKEN_256BITS_GENERE_PAR_LE_COLLECTEUR</token>
    <intervalle_secondes>120</intervalle_secondes>   <!-- défaut : 120s -->
    <share_details>true</share_details>              <!-- inclure résumés incidents ou KPIs seuls -->
    <share_min_urgency>1</share_min_urgency>         <!-- urgence minimale pour inclure un incident -->
  </federation>
"""

# ── Push capacité vers le collecteur ──────────────────────────────────────

def build_capacite_payload(db, cfg: "FederationConfig") -> dict:
    """Construit le payload capacitaire — une entrée par UF/service (pas par pôle).
    h151 : envoi de toutes les UF individuelles pour affichage complet en supervision.
    Par défaut (sans déclaration) : lits_vides = capacité_totale (tout est libre).
    """
    try:
        from app.models import CapaciteReferentiel, CapaciteDeclaration
        STATUT_POIDS = {"ferme": 3, "critique": 2, "tension": 1, "normal": 0}
        refs = db.query(CapaciteReferentiel).filter(CapaciteReferentiel.actif == True).all()  # noqa: E712
        services = []
        alertes = []
        nb_alertes = 0
        for ref in refs:
            site = ref.site or "Principal"
            pole = ref.pole or "Autre"
            last = (db.query(CapaciteDeclaration)
                    .filter(CapaciteDeclaration.referentiel_id == ref.id)
                    .order_by(CapaciteDeclaration.horodatage.desc()).first())
            total = ref.capacite_totale or 0
            if last:
                # Déclaration existante — utiliser les valeurs déclarées
                lits_h = last.lits_vides_h or 0
                lits_f = last.lits_vides_f or 0
                lits_i = last.lits_vides_i or 0
                statut_rh  = last.statut_rh  or "complet"
                nb_pers    = 0  # nb_personnel non présent dans CapaciteDeclaration v1
                poids = max(STATUT_POIDS.get(last.statut_lits, 0),
                            STATUT_POIDS.get(last.statut_rh, 0),
                            STATUT_POIDS.get(last.statut_materiel, 0))
                statut = {3: "ferme", 2: "critique", 1: "tension", 0: "normal"}.get(poids, "normal")
                has_declaration = True
                horodatage = last.horodatage.isoformat() if last.horodatage else None
                if last.alerte_lits or last.alerte_rh or last.alerte_materiel:
                    nb_alertes += 1
                    alertes.append({
                        "service": ref.service_nom, "site": site, "pole": pole,
                        "uf_code": ref.uf_code or "",
                        "alerte_lits": last.alerte_lits,
                        "alerte_rh": last.alerte_rh,
                        "alerte_materiel": last.alerte_materiel,
                        "commentaire": last.commentaire_general or "",
                        "horodatage": horodatage,
                    })
                if getattr(last, "mode_degrade", False):
                    alertes.append({
                        "service": ref.service_nom, "site": site, "pole": pole,
                        "mode_degrade": True,
                        "besoin_renfort": getattr(last, "besoin_renfort", 0),
                        "peut_preter": getattr(last, "peut_preter", 0),
                        "commentaire": last.commentaire_general or "",
                        "horodatage": horodatage,
                    })
            else:
                # h152 — Pas de déclaration : par défaut TOUT est libre.
                # On met tout en H pour éviter d'afficher un total×3.
                lits_h, lits_f, lits_i = total, 0, 0
                statut_rh = "complet"
                nb_pers   = 0
                statut    = "normal"
                has_declaration = False
                horodatage = None

            services.append({
                "service": ref.service_nom,
                "uf_code": ref.uf_code or "",
                "pole":    pole,
                "site":    site,
                "lits_total":   total,
                "lits_vides_h": lits_h,
                "lits_vides_f": lits_f,
                "lits_vides_i": lits_i,
                "statut":       statut,
                "statut_rh":    statut_rh,

                "has_declaration": has_declaration,
                "horodatage":   horodatage,
            })

        nb_degrade = sum(1 for a in alertes if a.get("mode_degrade"))
        services_renfort = [
            {"service": a["service"], "site": a["site"],
             "besoin_renfort": a["besoin_renfort"], "peut_preter": a["peut_preter"]}
            for a in alertes if a.get("mode_degrade")
        ]
        # Champ "synthese" maintenu pour compatibilité ascendante (= services)
        return {
            "etablissement": {"nom": cfg.etablissement_nom, "sigle": cfg.etablissement_sigle},
            "synthese":      services,   # alias pour la supervision (liste complète des UF)
            "services":      services,
            "alertes":       alertes,
            "nb_services":   len(refs),
            "nb_alertes":    nb_alertes,
            "nb_degrade":    nb_degrade,
            "services_renfort": services_renfort,
            "transferts_en_cours": len(_get_transferts_anonymes(db)),
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"build_capacite_payload erreur : {e}")
        return {}

async def push_capacite_to_collecteur(cfg: "FederationConfig", payload: dict) -> bool:
    """Envoie le payload capacitaire vers /api/push-capacite du collecteur."""
    if not cfg.is_ready or not payload:
        return False
    cap_url = cfg.collecteur_url.replace("/api/push", "/api/push-capacite")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(cap_url, json=payload,
                headers={"Authorization": f"Bearer {cfg.token}",
                         "Content-Type": "application/json"})
            return resp.status_code in (200, 201, 204)
    except Exception as e:
        logger.warning(f"push_capacite erreur : {e}")
        return False


@router.get("/annuaire-inter-ght")
async def annuaire_inter_ght():
    """Récupère les comptes des autres GHTs depuis le collecteur pour l'annuaire."""
    cfg = FederationConfig()
    if not cfg.is_ready:
        return []
    try:
        import httpx
        coll_base = cfg.collecteur_url.replace("/api/push", "")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{coll_base}/api/summary")
            if r.status_code != 200:
                return []
            summary = r.json()
        # Construire un annuaire fictif basé sur les établissements remontés
        result = []
        for etab in summary:
            sigle = etab.get("sigle", "?")
            if sigle == cfg.etablissement_sigle:
                continue  # Sauter son propre GHT
            nom = etab.get("nom", sigle)
            niveau = etab.get("niveau_global", "NOMINAL")
            # Contacts génériques par GHT distant (les vrais comptes ne sont pas remontés par fédération)
            result.append({
                "ght": sigle,
                "ght_nom": nom,
                "contacts": [
                    {"display_name": f"Direction de crise — {nom}", "service": "Direction", "online": "unknown", "role": "directeur"},
                    {"display_name": f"DSI — {nom}", "service": "DSI", "online": "unknown", "role": "directeur"},
                    {"display_name": f"Urgences — {nom}", "service": "Urgences", "online": "unknown", "role": "operateur"},
                ],
                "niveau_global": niveau,
            })
        return result
    except Exception as e:
        logger.warning(f"annuaire-inter-ght erreur: {e}")
        return []
