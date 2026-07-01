"""
collecteur.py — Collecteur de supervision territoriale SCRIBE

Reçoit les pushs JSON des instances SCRIBE des établissements.
Interface web en lecture seule pour CERT Santé, ARS, supervision GHT.

Usage :
  python collecteur.py

Accès : http://localhost:9000
Admin : http://localhost:9000/admin  (pour gérer les tokens établissements)
"""

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("collecteur")

# ── Fichiers de persistance ───────────────────────────────────────────────
DATA_FILE   = os.environ.get("COLLECTEUR_DATA",   "collecteur_data.json")
TOKENS_FILE = os.environ.get("COLLECTEUR_TOKENS", "collecteur_tokens.json")
ADMIN_FILE  = os.environ.get("COLLECTEUR_ADMIN",  "collecteur_admin.json")

# Structure en mémoire
etablissements: dict = {}   # sigle → dernière remontée
tokens: dict = {}           # token → sigle établissement

# ── Chat inter-GHT ──────────────────────────────────────────────────────────
# Structure : {salon_nom: [{id, auteur_nom, auteur_sigle, contenu, mentions, horodatage}]}
CHAT_SALONS_DEFAULT = ["général","coordination","transferts","logistique","direction"]
chat_messages: dict = {s: [] for s in CHAT_SALONS_DEFAULT}
# Sessions UI actives : {token: {"login": ..., "role": ...}}
ui_sessions: dict = {}
# Présence : {sigle: [{user_id, display_name, last_seen}]}
chat_presence: dict = {}
_chat_msg_counter: int = 0
PENDING_FILE  = os.environ.get("COLLECTEUR_PENDING",  "collecteur_pending.json")
RELAY_FILE    = os.environ.get("COLLECTEUR_RELAY",    "collecteur_relay.json")

# ── Relais hiérarchique ─────────────────────────────────────────────────────
# Liste de collecteurs upstream vers lesquels re-pousser toutes les données
# Format: [{url, token, nom, actif}]
relay_targets: list = []

def load_relay():
    global relay_targets
    if Path(RELAY_FILE).exists():
        try:
            relay_targets = json.loads(Path(RELAY_FILE).read_text())
        except Exception:
            relay_targets = []

def save_relay():
    Path(RELAY_FILE).write_text(json.dumps(relay_targets, ensure_ascii=False, indent=2))

async def relay_push(payload: dict, sigle: str):
    """Re-pousse le payload vers tous les collecteurs upstream actifs."""
    if not relay_targets:
        return
    try:
        import httpx as _httpx
        # Enrichir le payload avec le sigle source pour traçabilité
        relay_payload = dict(payload)
        relay_payload["_relayed_from"] = ADMIN_TOKEN[:8] + "..."
        relay_payload["_relayed_at"]   = datetime.now(timezone.utc).isoformat()
        async with _httpx.AsyncClient(timeout=8.0) as client:
            for target in relay_targets:
                if not target.get("actif", True):
                    continue
                try:
                    resp = await client.post(
                        target["url"],
                        json=relay_payload,
                        headers={"Authorization": f"Bearer {target['token']}",
                                 "Content-Type": "application/json"}
                    )
                    if resp.status_code == 200:
                        logger.info(f"Relay OK → {target.get('nom','?')} ({target['url']}) pour {sigle}")
                    else:
                        logger.warning(f"Relay HTTP {resp.status_code} → {target.get('nom','?')} pour {sigle}")
                except Exception as e:
                    logger.warning(f"Relay ERREUR → {target.get('nom','?')} : {e}")
    except Exception as e:
        logger.warning(f"Relay général ERREUR : {e}")
MESSAGES_FILE = os.environ.get("COLLECTEUR_MESSAGES", "collecteur_messages.json")
pending: dict = {}          # token → info établissement en attente (pas encore accepté)
messages_inter: list = []   # messagerie inter-GHT
transferts_inter: list = [] # transferts inter-établissements
TRANSFERTS_INTER_FILE = os.environ.get("COLLECTEUR_TRANSFERTS", "collecteur_transferts.json")

def load_transferts_inter():
    global transferts_inter
    if Path(TRANSFERTS_INTER_FILE).exists():
        try:
            transferts_inter = json.loads(Path(TRANSFERTS_INTER_FILE).read_text())
        except Exception:
            transferts_inter = []

def save_transferts_inter():
    Path(TRANSFERTS_INTER_FILE).write_text(json.dumps(transferts_inter, ensure_ascii=False, indent=2))

load_transferts_inter()


def _load_or_create_admin_token() -> str:
    """Charge le token admin depuis le fichier, ou le crée une seule fois."""
    # Priorité 1 : variable d'environnement
    if os.environ.get("ADMIN_TOKEN"):
        return os.environ["ADMIN_TOKEN"]
    # Priorité 2 : fichier persistant
    p = Path(ADMIN_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text()).get("admin_token", "")
        except Exception:
            pass
    # Première fois : générer et sauvegarder
    token = secrets.token_hex(32)
    p.write_text(json.dumps({"admin_token": token}, indent=2))
    return token


ADMIN_TOKEN = _load_or_create_admin_token()


def load_tokens():
    global tokens
    tokens = dict(DEMO_TOKENS)
    if Path(TOKENS_FILE).exists():
        try:
            saved = json.loads(Path(TOKENS_FILE).read_text())
            tokens.update(saved)
        except Exception:
            pass
    save_tokens()

def save_tokens():
    Path(TOKENS_FILE).write_text(json.dumps(tokens, ensure_ascii=False, indent=2))

def load_data():
    global etablissements
    if Path(DATA_FILE).exists():
        try:
            etablissements = json.loads(Path(DATA_FILE).read_text())
        except Exception:
            etablissements = {}

def save_data():
    Path(DATA_FILE).write_text(json.dumps(etablissements, ensure_ascii=False, indent=2))

# ── App FastAPI ───────────────────────────────────────────────────────────

app = FastAPI(title="SCRIBE Collecteur territorial", version="1.2.0")

# ── CORS : middleware http natif Starlette ────────────────────────────────
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin") or "*"
    cors_headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
        "Access-Control-Max-Age": "3600",
    }
    if request.method == "OPTIONS":
        from fastapi.responses import Response as _Resp
        return _Resp(status_code=200, headers=cors_headers)
    try:
        response = await call_next(request)
    except Exception:
        from fastapi.responses import JSONResponse
        response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    for k, v in cors_headers.items():
        response.headers[k] = v
    return response

from fastapi.responses import JSONResponse as _JSONResponse
from fastapi import Request as _Req2
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: _Req2, exc: StarletteHTTPException):
    origin = request.headers.get("origin") or "*"
    return _JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers={
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
    })

@app.exception_handler(Exception)
async def global_exc_handler(request: _Req2, exc: Exception):
    origin = request.headers.get("origin") or "*"
    return _JSONResponse({"detail": str(exc)}, status_code=500, headers={
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
    })


security = HTTPBearer(auto_error=False)


def get_etab_from_token(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    if not credentials:
        return None
    if credentials.credentials == ADMIN_TOKEN:
        return "SUPERVISEUR"
    return tokens.get(credentials.credentials)


def require_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials or credentials.credentials != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token admin invalide")
    return True

def require_ui_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
    """Accepte le token admin collecteur OU un token de session UI admin."""
    if not credentials:
        return False
    tok = credentials.credentials
    if tok == ADMIN_TOKEN:
        return True
    session = ui_sessions.get(tok, {})
    return session.get("role") == "admin"


# ── Endpoint de réception (appelé par les SCRIBE) ─────────────────────────

# ═══════════════════════════════════════════════════════════════
# NOUVELLES FONCTIONNALITÉS v1.4.0
# ═══════════════════════════════════════════════════════════════

# ── File d'attente : établissements en attente d'acceptation ──

def load_pending():
    global pending
    if Path(PENDING_FILE).exists():
        try:
            pending = json.loads(Path(PENDING_FILE).read_text())
        except Exception:
            pending = {}

def save_pending():
    Path(PENDING_FILE).write_text(json.dumps(pending, ensure_ascii=False, indent=2))

def load_messages_inter():
    global messages_inter
    if Path(MESSAGES_FILE).exists():
        try:
            messages_inter = json.loads(Path(MESSAGES_FILE).read_text())
        except Exception:
            messages_inter = []

def save_messages_inter():
    Path(MESSAGES_FILE).write_text(json.dumps(messages_inter, ensure_ascii=False, indent=2))


@app.post("/api/push")
async def receive_push(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Reçoit un push JSON d'un SCRIBE établissement."""
    cred_token = credentials.credentials if credentials else None
    sigle = get_etab_from_token(credentials)

    if not sigle:
        # Ajouter à la file d'attente pending (si pas déjà connu)
        if cred_token and cred_token not in pending:
            try:
                payload = await request.json()
                nom_propose = payload.get("etablissement", {}).get("nom", "Inconnu")
                sigle_propose = payload.get("etablissement", {}).get("sigle", "?")
            except Exception:
                nom_propose = "Inconnu"
                sigle_propose = "?"
            pending[cred_token] = {
                "sigle_propose": sigle_propose,
                "nom_propose": nom_propose,
                "ip": request.client.host,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "token_preview": cred_token[:12] + "..."
            }
            save_pending()
            logger.warning(f"⏳ Token inconnu → EN ATTENTE : {sigle_propose} ({nom_propose}) depuis {request.client.host} | token_preview: {cred_token[:12] if cred_token else '?'}...")
        raise HTTPException(status_code=401, detail="Token en attente d'acceptation par l'administrateur du collecteur")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")

    payload["_received_at"] = datetime.now(timezone.utc).isoformat()
    payload["_source_ip"]   = request.client.host

    etablissements[sigle] = payload
    save_data()

    logger.info(f"✓ Push ACCEPTÉ — {sigle} | niveau: {payload.get('niveau_global','?')} | "
                f"{payload.get('kpis',{}).get('incidents_ouverts',0)} incidents | "
                f"total stockés: {len(etablissements)}")

    # Relais hiérarchique
    if relay_targets:
        import asyncio
        asyncio.create_task(relay_push(payload, sigle))

    return {"ok": True, "sigle": sigle, "received_at": payload["_received_at"]}


# ── Gestion de la file d'attente (admin) ──────────────────────

@app.get("/api/admin/pending", dependencies=[Depends(require_admin)])
async def list_pending():
    """Liste les établissements en attente d'acceptation."""
    return [
        {"token": k, **v}
        for k, v in pending.items()
    ]

@app.post("/api/admin/pending/{token_prefix}/accept", dependencies=[Depends(require_admin)])
async def accept_pending(token_prefix: str, body: dict = {}):
    """Accepte un établissement en attente — l'enrôle comme token valide."""
    matches = [k for k in pending if k.startswith(token_prefix) or k == token_prefix]
    if not matches:
        # Chercher par token complet
        if token_prefix in pending:
            matches = [token_prefix]
    if not matches:
        raise HTTPException(status_code=404, detail="Établissement en attente non trouvé")
    token = matches[0]
    info = pending.pop(token)
    sigle = body.get("sigle", info["sigle_propose"]).strip().upper() or info["sigle_propose"]
    tokens[token] = sigle
    save_tokens()
    save_pending()
    logger.info(f"Établissement accepté : {sigle} (token: {token[:12]}...)")
    return {"ok": True, "sigle": sigle, "message": f"{sigle} enrôlé avec succès"}

@app.post("/api/admin/tokens/arc-alpin", dependencies=[Depends(require_admin)])
async def register_scribe_demo_tokens():
    """Enregistre les 4 tokens Réseau Démo démo — utile si l'auto-register a échoué."""
    added = []
    for tok, sigle in DEMO_TOKENS.items():
        if tok not in tokens:
            tokens[tok] = sigle
            added.append(sigle)
    if added:
        save_tokens()
        logger.info(f"Tokens Réseau Démo enregistrés manuellement : {added}")
    return {"ok": True, "added": added, "total": len(tokens),
            "message": f"{len(added)} token(s) ajouté(s), {len(tokens)} token(s) total"}


@app.post("/api/admin/pending/accept-all", dependencies=[Depends(require_admin)])
async def accept_all_pending():
    """Accepte tous les établissements en attente d'un coup."""
    accepted = []
    for tok, info in list(pending.items()):
        sigle = info.get("sigle_propose", tok[:8]).upper()
        tokens[tok] = sigle
        accepted.append(sigle)
        logger.info(f"Enrôlement en masse : {sigle} (token: {tok[:12]}...)")
    pending.clear()
    save_tokens()
    save_pending()
    return {"ok": True, "accepted": accepted, "count": len(accepted)}


@app.post("/api/admin/pending/{token_prefix}/reject", dependencies=[Depends(require_admin)])
async def reject_pending(token_prefix: str):
    """Rejette et supprime un établissement en attente."""
    matches = [k for k in pending if k.startswith(token_prefix) or k == token_prefix]
    if not matches:
        raise HTTPException(status_code=404, detail="Non trouvé")
    info = pending.pop(matches[0])
    save_pending()
    return {"ok": True, "message": f"Rejeté : {info.get('sigle_propose','')}"}



# ── Messagerie inter-GHT ──────────────────────────────────────

class MessageInterGHTBody(BaseModel):
    destinataire: str   # sigle du GHT destinataire, ou "TOUS"
    sujet: str
    contenu: str
    expediteur_nom: Optional[str] = None

@app.post("/api/messages")
async def send_message_interght(
    body: MessageInterGHTBody,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Envoie un message inter-GHT depuis un SCRIBE enrôlé."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    msg = {
        "id": len(messages_inter) + 1,
        "expediteur": sigle,
        "expediteur_nom": body.expediteur_nom or sigle,
        "destinataire": body.destinataire.upper(),
        "sujet": body.sujet,
        "contenu": body.contenu,
        "lu_par": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    messages_inter.append(msg)
    save_messages_inter()
    logger.info(f"Message inter-GHT : {sigle} → {body.destinataire} | {body.sujet[:40]}")
    return {"ok": True, "id": msg["id"]}

@app.get("/api/messages")
async def get_messages_interght(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Récupère les messages destinés à ce GHT (ou 'TOUS')."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    # Messages reçus : destinataire = mon sigle OU "TOUS"
    received = [m for m in messages_inter
                if m["destinataire"] == sigle or m["destinataire"] == "TOUS"]
    # Messages envoyés
    sent = [m for m in messages_inter if m["expediteur"] == sigle]
    return {"received": received, "sent": sent}

@app.put("/api/messages/{msg_id}/lire")
async def marquer_lu_interght(
    msg_id: int,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Marque un message comme lu par ce GHT."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    for m in messages_inter:
        if m["id"] == msg_id:
            if sigle not in m["lu_par"]:
                m["lu_par"].append(sigle)
            save_messages_inter()
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Message non trouvé")

@app.get("/api/messages/non-lus")
async def non_lus_interght(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Compte les messages non lus pour ce GHT."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    count = sum(1 for m in messages_inter
                if (m["destinataire"] == sigle or m["destinataire"] == "TOUS")
                and sigle not in m.get("lu_par", []))
    return {"count": count}


# ── Token admin (création / liste) ───────────────────────────────────────

@app.get("/api/admin/tokens", dependencies=[Depends(require_admin)])
async def list_tokens():
    return [{"sigle": v, "token_preview": k[:8] + "..."} for k, v in tokens.items()]

@app.post("/api/admin/tokens", dependencies=[Depends(require_admin)])
async def create_token(body: dict):
    """Crée/importe un token établissement. body: {sigle, token (optionnel, sinon généré)}"""
    sigle = body.get("sigle", "").strip().upper()
    if not sigle:
        raise HTTPException(status_code=400, detail="sigle requis")
    token = body.get("token", "").strip() or secrets.token_hex(32)
    if len(token) < 16:
        raise HTTPException(status_code=400, detail="token trop court (min 16 caractères)")
    tokens[token] = sigle
    save_tokens()
    logger.info(f"Token enregistré pour {sigle}")
    return {"sigle": sigle, "token": token, "message": "Token enregistré pour " + sigle}

@app.delete("/api/admin/tokens/{sigle_or_prefix}", dependencies=[Depends(require_admin)])
async def disconnect_etablissement(sigle_or_prefix: str):
    """Déconnecte (révoque) un établissement enrôlé."""
    sigle_upper = sigle_or_prefix.upper()
    # Chercher par sigle
    to_delete = [k for k, v in tokens.items() if v == sigle_upper or k.startswith(sigle_or_prefix)]
    if not to_delete:
        # Idempotent : déjà déconnecté ou jamais enrôlé → OK silencieux
        return {"ok": True, "disconnected": sigle_upper, "note": "already_absent"}
    for k in to_delete:
        sigle = tokens.pop(k)
        logger.info(f"Établissement déconnecté : {sigle}")
    save_tokens()
    return {"ok": True, "disconnected": sigle_upper}


# ── Relais hiérarchique (admin) ───────────────────────────────────────────

class RelayTarget(BaseModel):
    nom: str
    url: str
    token: str
    actif: bool = True

@app.get("/api/admin/relay", dependencies=[Depends(require_admin)])
async def list_relay():
    return relay_targets

@app.post("/api/admin/relay", dependencies=[Depends(require_admin)])
async def add_relay(body: RelayTarget):
    if len(body.token) < 16:
        raise HTTPException(status_code=400, detail="Token trop court (min 16 chars)")
    for t in relay_targets:
        if t["url"] == body.url:
            raise HTTPException(status_code=409, detail="Ce collecteur est déjà configuré")
    entry = {"nom": body.nom, "url": body.url, "token": body.token, "actif": body.actif,
             "added_at": datetime.now(timezone.utc).isoformat()}
    relay_targets.append(entry)
    save_relay()
    logger.info(f"Relay ajouté : {body.nom} → {body.url}")
    return {"ok": True, "message": f"Relais vers {body.nom} configuré", "entry": entry}

@app.delete("/api/admin/relay/{idx}", dependencies=[Depends(require_admin)])
async def delete_relay(idx: int):
    if idx < 0 or idx >= len(relay_targets):
        raise HTTPException(status_code=404, detail="Relais introuvable")
    removed = relay_targets.pop(idx)
    save_relay()
    return {"ok": True, "removed": removed["nom"]}

@app.put("/api/admin/relay/{idx}/toggle", dependencies=[Depends(require_admin)])
async def toggle_relay(idx: int):
    if idx < 0 or idx >= len(relay_targets):
        raise HTTPException(status_code=404, detail="Relais introuvable")
    relay_targets[idx]["actif"] = not relay_targets[idx].get("actif", True)
    save_relay()
    state = "activé" if relay_targets[idx]["actif"] else "désactivé"
    return {"ok": True, "nom": relay_targets[idx]["nom"], "actif": relay_targets[idx]["actif"],
            "message": f"Relais {state}"}

@app.post("/api/admin/relay/{idx}/test", dependencies=[Depends(require_admin)])
async def test_relay(idx: int):
    if idx < 0 or idx >= len(relay_targets):
        raise HTTPException(status_code=404, detail="Relais introuvable")
    target = relay_targets[idx]
    try:
        import httpx as _httpx
        test_payload = {
            "etablissement": {"nom": "TEST_RELAY", "sigle": "TEST"},
            "niveau_global": "NOMINAL", "kpis": {"incidents_ouverts": 0}, "_test": True
        }
        async with _httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                target["url"], json=test_payload,
                headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"}
            )
            return {"ok": resp.status_code in (200,401), "status": resp.status_code,
                    "nom": target["nom"], "note": "401 = collecteur joignable mais token à enregistrer"}
    except Exception as e:
        return {"ok": False, "error": str(e), "nom": target["nom"]}


# ── Push status et capacité ───────────────────────────────────────────────

@app.post("/api/push-status")
async def receive_status_push(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Token inconnu")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")
    payload["_received_at"] = datetime.now(timezone.utc).isoformat()
    if sigle in etablissements:
        etablissements[sigle]["_status_page"] = payload
        if payload.get("_statuts_sites"):
            etablissements[sigle]["_statuts_sites"] = payload["_statuts_sites"]
    else:
        etablissements[sigle] = {"_status_page": payload, "_received_at": payload["_received_at"]}
    save_data()
    return {"ok": True, "sigle": sigle}

@app.post("/api/push-capacite")
async def receive_push_capacite(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Token inconnu")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")
    payload["_received_at"] = datetime.now(timezone.utc).isoformat()
    if sigle not in etablissements:
        etablissements[sigle] = {}
    etablissements[sigle]["_capacite"] = payload
    save_data()
    logger.info(f"Push capacité — {sigle} | {payload.get('nb_services',0)} services")
    return {"ok": True, "sigle": sigle}

# ── Lecture (summary, detail) ─────────────────────────────────────────────


@app.get("/api/declarations")
async def get_declarations_interght(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    result = []
    for sigle, payload in etablissements.items():
        for d in payload.get("declarations", []):
            result.append({**d, "ght_emetteur": sigle})
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result

@app.get("/api/demandes")
async def get_demandes_interght(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    result = []
    for sigle, payload in etablissements.items():
        for d in payload.get("demandes", []):
            result.append({**d, "ght_emetteur": d.get("ght_emetteur") or sigle})
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result

@app.patch("/api/demandes/{dem_id}")
async def update_demande_response(dem_id, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Met à jour la réponse d'une demande inter-GHT (appelé par l'instance destinataire)."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")
    reponse     = body.get("reponse", "")
    statut      = body.get("statut", "traite")
    repondu_par = body.get("repondu_par", sigle)
    for etab_sigle, payload in etablissements.items():
        for d in payload.get("demandes", []):
            if str(d.get("id")) == str(dem_id):
                d["reponse"]     = reponse
                d["statut"]      = statut
                d["repondu_par"] = repondu_par
                save_data()
                return {"ok": True}
    raise HTTPException(status_code=404, detail="Demande non trouvée")

@app.post("/api/push-transfert")
async def push_transfert_interght(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")
    transfert = {
        "id_local": body.get("id_local"),
        "ght_emetteur": sigle,
        "ght_emetteur_nom": body.get("ght_emetteur_nom", sigle),
        "ght_destinataire": body.get("ght_destinataire", ""),
        "unite_origine": body.get("unite_origine", ""),
        "etablissement_origine": body.get("etablissement_origine", ""),
        "unite_destination": body.get("unite_destination", ""),
        "etablissement_destination": body.get("etablissement_destination", ""),
        "site_destination": body.get("site_destination", ""),
        "statut": body.get("statut", "EN_PREPARATION"),
        "eta": body.get("eta"),
        "horodatage_depart": body.get("horodatage_depart"),
        "commentaire": body.get("commentaire"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = next((t for t in transferts_inter
                     if t.get("id_local") == transfert["id_local"]
                     and t.get("ght_emetteur") == sigle), None)
    if transfert["statut"] in ("ARRIVE", "ANNULE"):
        # Supprimer définitivement — plus besoin de le garder
        transferts_inter[:] = [t for t in transferts_inter
                               if not (t.get("id_local") == transfert["id_local"]
                                       and t.get("ght_emetteur") == sigle)]
    elif existing:
        existing.update(transfert)
    else:
        transferts_inter.append(transfert)
    save_transferts_inter()
    return {"ok": True}

@app.get("/api/transferts-en-cours")
async def get_transferts_en_cours(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    result = [t for t in transferts_inter
              if t.get("ght_destinataire", "").upper() == sigle.upper()
              and (t.get("statut") in ("EN_PREPARATION", "EN_COURS")
                   or (t.get("statut") == "ARRIVE" and t.get("created_at", "") >= cutoff))]
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result

@app.get("/api/transfert-statut/{id_local}")
async def get_transfert_statut(
    id_local: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """Retourne le statut actuel d'un transfert (pour l'émetteur)."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(status_code=401, detail="Non autorisé")
    # Chercher dans transferts_inter
    t = next((t for t in transferts_inter
               if str(t.get("id_local")) == str(id_local)
               and t.get("ght_emetteur","").upper() == sigle.upper()), None)
    if t:
        return {"statut": t.get("statut"), "found": True}
    # Non trouvé = supprimé (ARRIVE ou ANNULE)
    return {"statut": "ARRIVE", "found": False}



def _check_any_auth(credentials) -> bool:
    """Accepte token établissement OU session UI valide."""
    if not credentials:
        return False
    tok = credentials.credentials
    # Token établissement
    if tok in tokens:
        return True
    # Token admin
    if tok == ADMIN_TOKEN:
        return True
    # Session UI
    if tok in ui_sessions:
        return True
    return False

# ════════════════════════════════════════════════════════════════════════════
# CHAT INTER-GHT
# ════════════════════════════════════════════════════════════════════════════

@app.post("/api/chat/messages")
async def chat_push_message(request: Request, credentials=Depends(security)):
    """Une instance pousse un message dans un salon territorial."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(401)
    global _chat_msg_counter
    try:
        raw = await request.body()
        import json as _json
        body = _json.loads(raw)
    except Exception as e:
        logger.warning(f"chat_push_message: erreur parsing body: {e}")
        raise HTTPException(400, "Corps JSON invalide")
    salon_nom = body.get("salon_nom", "général")
    if salon_nom not in chat_messages:
        chat_messages[salon_nom] = []
    # Anti-doublon : même sigle + même contenu dans les 5 dernières secondes
    now = datetime.now(timezone.utc).isoformat()
    contenu = body.get("contenu", "")
    recent = [m for m in chat_messages[salon_nom][-10:]
              if m.get("auteur_sigle") == sigle and m.get("contenu") == contenu]
    if recent:
        last = recent[-1]
        try:
            from datetime import timedelta
            last_ts = datetime.fromisoformat(last["horodatage"].replace("Z",""))
            delta = (datetime.now(timezone.utc) - last_ts.replace(tzinfo=timezone.utc)).total_seconds()
            if delta < 5:
                return {"ok": True, "detail": "doublon ignoré"}
        except Exception:
            pass
    _chat_msg_counter += 1
    # Stocker les PJs : pj_meta = URL directe (nouveau), pj_data/pj_inline = base64 (legacy)
    global _chat_pj_counter
    pjs = []
    # Nouveau format : URL directe vers l'instance source
    for pm in body.get("pj_meta", []):
        _chat_pj_counter += 1
        pj_key = f"ght-{_chat_pj_counter}"
        if pm.get("remote_url"):
            # Stocker l'URL directe (pas de base64)
            chat_pj_store[pj_key] = {
                "nom":        pm.get("nom", "fichier"),
                "remote_url": pm["remote_url"],
                "taille":     pm.get("taille", 0),
            }
        elif pm.get("dataUrl"):
            chat_pj_store[pj_key] = {
                "nom":     pm.get("nom", "fichier"),
                "dataUrl": pm["dataUrl"],
                "taille":  pm.get("taille", 0),
            }
        else:
            continue
        pjs.append({"id": pj_key, "nom": pm.get("nom",""), "taille": pm.get("taille",0)})
    # Legacy : base64 direct (garde compatibilité)
    for pj_data in body.get("pj_data", []) + body.get("pj_inline", []):
        dataUrl = pj_data.get("dataUrl", "")
        if dataUrl:
            _chat_pj_counter += 1
            pj_key = f"ght-{_chat_pj_counter}"
            chat_pj_store[pj_key] = {
                "nom":     pj_data.get("nom", "fichier"),
                "dataUrl": dataUrl,
                "taille":  pj_data.get("taille", 0),
            }
            pjs.append({"id": pj_key, "nom": pj_data.get("nom",""), "taille": pj_data.get("taille",0)})
    msg = {
        "id":           _chat_msg_counter,
        "salon_nom":    salon_nom,
        "auteur_nom":   body.get("auteur_nom", sigle),
        "auteur_sigle": sigle,
        "contenu":      contenu,
        "mentions":     body.get("mentions", []),
        "reply_to_id":  body.get("reply_to_id"),
        "horodatage":   now,
        "origine":      "ght",
        "pj":           pjs,
    }
    chat_messages[salon_nom].append(msg)
    # Garder max 500 messages par salon
    if len(chat_messages[salon_nom]) > 500:
        chat_messages[salon_nom] = chat_messages[salon_nom][-500:]
    return {"ok": True, "id": _chat_msg_counter}


@app.get("/api/chat/messages")
async def chat_get_messages(
    salon_nom: str = "général",
    since_id: int = 0,
    credentials=Depends(security)
):
    """Une instance récupère les messages d'un salon depuis un ID donné."""
    if not _check_any_auth(credentials):
        raise HTTPException(401)
    msgs = chat_messages.get(salon_nom, [])
    filtered = [m for m in msgs if m.get("id", 0) > since_id]
    return filtered[-100:]  # max 100 messages


@app.post("/api/chat/salons")
async def chat_create_salon(request: Request, credentials=Depends(security)):
    """Une instance crée/enregistre un salon territorial dans le collecteur."""
    if not _check_any_auth(credentials):
        raise HTTPException(401)
    body = await request.json()
    nom = body.get("nom", "").strip().lower()
    if nom and nom not in chat_messages:
        chat_messages[nom] = []
    # Retourner le salon créé dans le format objet
    salon_list = list(chat_messages.keys())
    idx = salon_list.index(nom) if nom in salon_list else 0
    return {"id": idx+1, "nom": nom, "type": "territorial",
            "icone": "💬", "couleur": "#7c3aed", "description": f"Salon #{nom}"}

@app.get("/api/chat/salons")
async def chat_list_salons(credentials=Depends(security)):
    """Liste des salons actifs dans le collecteur — format objet compatible chat.html."""
    if not _check_any_auth(credentials):
        raise HTTPException(401)
    # Retourner des objets {id, nom, type, icone, couleur, description}
    # avec des IDs stables basés sur le nom du salon
    SALON_ICONS = {
        "général": "💬", "coordination": "🎯", "transferts": "🚑",
        "logistique": "📦", "direction": "🏛️"
    }
    result = []
    for i, nom in enumerate(chat_messages.keys()):
        result.append({
            "id":          i + 1,
            "nom":         nom,
            "description": f"Salon territorial #{nom}",
            "couleur":     "#7c3aed",
            "icone":       SALON_ICONS.get(nom, "💬"),
            "type":        "territorial",
            "ordre":       i,
        })
    return result


@app.post("/api/chat/presence")
async def chat_push_presence(request: Request, credentials=Depends(security)):
    """Une instance pousse la présence de ses utilisateurs."""
    sigle = get_etab_from_token(credentials)
    if not sigle:
        raise HTTPException(401)
    body = await request.json()
    users = body.get("users", [])
    now = datetime.now(timezone.utc).isoformat()
    chat_presence[sigle] = [
        {"user_id": u.get("user_id"), "display_name": u.get("display_name"), "last_seen": now}
        for u in users
    ]
    return {"ok": True}


@app.get("/api/chat/presence")
async def chat_get_presence(credentials=Depends(security)):
    """Retourne la présence de tous les établissements."""
    if not _check_any_auth(credentials):
        raise HTTPException(401)
    # Nettoyer les présences > 2 minutes
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    result = {}
    for etab_sigle, users in chat_presence.items():
        active = []
        for u in users:
            try:
                ts = datetime.fromisoformat(u["last_seen"].replace("Z","")).replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    active.append(u)
            except Exception:
                pass
        if active:
            result[etab_sigle] = active
    return result

@app.get("/api/annuaire")
async def get_annuaire_interght():
    import httpx
    result = []
    PORT_MAP = {"CHV":"8000","GHT1":"8001","GHT2":"8002","GHT3":"8003",
                "CHR1":"8002","CH2":"8003","CH3":"8004","CH4":"8005","CH5":"8006"}
    for token, sigle in tokens.items():
        etab_data = etablissements.get(sigle)
        if not etab_data:
            continue
        port = PORT_MAP.get(sigle, "8000")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"http://127.0.0.1:{port}/api/v1/auth/annuaire-public")
                if r.status_code == 200:
                    result.append(r.json())
        except Exception:
            etab_info = etab_data.get("etablissement", {})
            result.append({"sigle": sigle, "nom": etab_info.get("nom", sigle), "contacts": [], "unavailable": True})
    return result

@app.get("/api/summary")
async def get_summary():
    """Vue consolidée de tous les établissements. Sans auth."""
    now = time.time()
    result = []
    if not etablissements:
        logger.info(f"summary: VIDE — {len(tokens)} token(s) enregistré(s)")
    for sigle, data in etablissements.items():
        received_str = data.get("_received_at", "")
        try:
            received_ts = datetime.fromisoformat(received_str).timestamp()
            age_minutes = int((now - received_ts) / 60)
            fresh = age_minutes < 10
        except Exception:
            age_minutes = 999
            fresh = False
        etab_info = data.get("etablissement", {})
        # Prendre le pire niveau entre incidents et statut déclaré
        ORDRE = {"CRITIQUE":5,"CRISE":4,"INCIDENT_MAJEUR":3,"PERTURBE":2,"ALERTE":2,"MAINTENANCE":1,"OPERATIONNEL":0,"NOMINAL":0,"INCONNU":-1}
        niv_incidents = data.get("niveau_global", "NOMINAL")
        sp = data.get("_status_page") or {}
        niv_statut = sp.get("niveau_global", "NOMINAL") if sp.get("published") else "NOMINAL"
        # Mapper les niveaux statut public vers niveaux incidents
        MAP_STATUT = {"PERTURBE":"ALERTE","INCIDENT_MAJEUR":"CRISE","OPERATIONNEL":"NOMINAL","ALERTE":"ALERTE","CRITIQUE":"CRITIQUE"}
        niv_statut_mapped = MAP_STATUT.get(niv_statut, niv_statut)
        niv_final = niv_incidents if ORDRE.get(niv_incidents,0) >= ORDRE.get(niv_statut_mapped,0) else niv_statut_mapped
        result.append({
            "sigle":        sigle,
            "nom":          etab_info.get("nom", sigle),
            "niveau_global": niv_final,
            "kpis":         data.get("kpis", {}),
            "services_transverses": data.get("services_transverses", {}),
            "poles_impactes": data.get("poles_impactes", []),
            "sites":        data.get("sites", []),
            "latitude":     data.get("latitude"),
            "longitude":    data.get("longitude"),
            "incidents":    data.get("incidents", []),
            "received_at":  received_str,
            "age_minutes":  age_minutes,
            "fresh":        fresh,
            "_status_page": data.get("_status_page"),
            "_capacite":    data.get("_capacite"),
        })
    return result

@app.get("/api/etablissement/{sigle}")
async def get_etablissement(sigle: str):
    if sigle not in etablissements:
        raise HTTPException(status_code=404, detail=f"Établissement {sigle} inconnu")
    return etablissements[sigle]

@app.get("/api/capacite")
async def get_capacite_all():
    result = []
    for sigle, data in etablissements.items():
        cap = data.get("_capacite")
        if not cap:
            continue
        result.append({
            "sigle":       sigle,
            "nom":         data.get("etablissement", {}).get("nom", sigle),
            "received_at": cap.get("_received_at"),
            "synthese":    cap.get("synthese", {}),
            "alertes":     cap.get("alertes", []),
            "nb_services": cap.get("nb_services", 0),
            "nb_alertes":  cap.get("nb_alertes", 0),
        })
    return result

@app.get("/api/status/{sigle}")
async def get_etab_status(sigle: str):
    data = etablissements.get(sigle, {})
    sp = data.get("_status_page")
    if not sp:
        return {"published": False, "sigle": sigle}
    return sp




# ── Interface webseule) ────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCRIBE — Supervision Territoriale</title>
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow+Condensed:wght@300;400;600;700;900&family=Barlow:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --bg:#060608;--s1:#0d0d12;--s2:#111118;--s3:#18181f;
  --border:#1f1f2e;--border2:#2a2a3d;
  --text:#dde4f0;--muted:#4a5070;--muted2:#6b7494;
  --mono:'Share Tech Mono',monospace;--head:'Barlow Condensed',sans-serif;--body:'Barlow',sans-serif;
  --green:#00e5a0;--yellow:#f5c518;--orange:#ff7b2c;--red:#ff2d55;
  --blue:#3d9eff;--purple:#a855f7;--cyan:#00cfff;
}
body.light{
  --bg:#f8fafc;--s1:#ffffff;--s2:#f1f5f9;--s3:#e2e8f0;
  --border:#e2e8f0;--border2:#cbd5e1;
  --text:#0f172a;--muted:#64748b;--muted2:#475569;
  --green:#059669;--yellow:#d97706;--orange:#ea580c;--red:#dc2626;
  --blue:#2563eb;--purple:#7c3aed;--cyan:#0891b2;
}
body.light #kpi-bar{background:#003189;border-bottom:3px solid #e1000f}
body.light #header{background:#ffffff;border-bottom:1px solid #e2e8f0}
body.light .tab-btn{color:#161616}
body.light .tab-btn.active{color:#003189;background:rgba(0,49,137,.08);border-color:rgba(0,49,137,.3)}
body.light .tab-btn:hover{color:#003189}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--body);overflow:hidden}
/* scanlines supprimées v2.3.14 — lisibilité */
#app{display:flex;flex-direction:column;height:100vh}

/* KPI BAR */
#kpi-bar{display:flex;align-items:center;gap:0;background:#003189;border-bottom:3px solid #e1000f;flex-shrink:0;height:36px}
.kpi-cell{display:flex;align-items:center;gap:7px;padding:0 16px;border-right:1px solid var(--border);height:100%}
.kpi-label{font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:rgba(255,255,255,.7);text-transform:uppercase}
.kpi-val{font-family:var(--mono);font-size:14px;font-weight:700;color:#ffffff}
.kpi-val.ok{color:var(--green)}.kpi-val.warn{color:var(--yellow)}.kpi-val.crit{color:var(--red)}
#kpi-title{font-family:var(--head);font-size:13px;font-weight:700;letter-spacing:2px;color:#ffffff;padding:0 16px;margin-right:auto}
#kpi-clock{font-family:var(--mono);font-size:11px;color:var(--muted);padding:0 14px}
#kpi-refresh{font-family:var(--mono);font-size:9px;color:var(--muted);padding:0 10px;display:flex;align-items:center;gap:5px}
.refresh-dot{width:5px;height:5px;border-radius:50%;background:var(--green);animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}

/* HEADER TABS */
#header{display:flex;align-items:center;background:var(--s2);border-bottom:1px solid var(--border);flex-shrink:0;padding:0 8px;height:38px;gap:2px;color:var(--text)}
.tab-btn{font-family:var(--mono);font-size:9px;letter-spacing:1px;padding:4px 12px;background:transparent;color:var(--text);border:1px solid transparent;border-radius:4px;cursor:pointer;transition:all .15s;white-space:nowrap}
.tab-btn:hover{color:#003189;border-color:#003189}
.tab-btn.active{color:#003189;background:rgba(0,49,137,.08);border-color:rgba(0,49,137,.3);font-weight:700}
.tab-spacer{flex:1}
#msg-badge-hdr{display:none;background:var(--red);color:#fff;font-size:8px;padding:1px 5px;border-radius:8px;margin-left:4px;font-weight:700}

/* MAIN AREA */
#main{flex:1;overflow:hidden;position:relative}
.tab-pane{display:none;width:100%;height:100%}
.tab-pane.active{display:flex}

/* ── SUPERVISION ── */
#pane-supervision{flex-direction:row;overflow:hidden}
#etab-left{width:220px;flex-shrink:0;background:var(--s1);border-right:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}
@media(max-width:768px){#pane-supervision{flex-direction:column}#etab-left{width:100%;max-height:200px;border-right:none;border-bottom:1px solid var(--border)}#kpi-title{display:none}.kpi-cell{padding:0 8px}.tab-btn{font-size:8px;padding:3px 7px}}
#etab-left-header{padding:10px 12px 8px;border-bottom:1px solid var(--border);flex-shrink:0}
#etab-left-header .lh-title{font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:var(--muted);margin-bottom:6px}
#pending-section{border-bottom:1px solid var(--border);background:rgba(245,197,24,.04)}
#pending-header{padding:8px 12px;font-family:var(--mono);font-size:8px;letter-spacing:1px;color:var(--yellow);display:flex;align-items:center;gap:6px}
#pending-list{padding:0 8px 8px}
.pending-card{background:rgba(245,197,24,.06);border:1px solid rgba(245,197,24,.2);border-radius:5px;padding:8px 10px;margin-bottom:6px}
.pending-card-nom{font-family:var(--mono);font-size:9px;font-weight:700;color:var(--yellow);margin-bottom:2px}
.pending-card-sub{font-family:var(--mono);font-size:8px;color:var(--muted);margin-bottom:6px}
.pending-actions{display:flex;gap:5px}
.btn-accept{font-family:var(--mono);font-size:8px;padding:3px 9px;background:rgba(0,229,160,.12);border:1px solid var(--green);border-radius:3px;color:var(--green);cursor:pointer;flex:1}
.btn-accept:hover{background:rgba(0,229,160,.22)}
.btn-reject{font-family:var(--mono);font-size:8px;padding:3px 9px;background:rgba(255,45,85,.08);border:1px solid rgba(255,45,85,.3);border-radius:3px;color:var(--red);cursor:pointer}
.etab-card{padding:10px 12px;cursor:pointer;border-bottom:1px solid var(--border);transition:background .12s;display:flex;align-items:center;gap:8px}
.etab-card:hover{background:var(--s2)}
.etab-card.selected{background:var(--s3);border-left:2px solid var(--cyan)}
.etab-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.etab-dot.NOMINAL{background:var(--green)}.etab-dot.VEILLE{background:var(--green)}.etab-dot.OPERATIONNEL{background:var(--green)}
.etab-dot.ALERTE{background:var(--yellow)}.etab-dot.PERTURBE{background:var(--yellow)}.etab-dot.MAINTENANCE{background:var(--cyan)}
.etab-dot.CRISE{background:var(--orange);box-shadow:0 0 6px var(--orange)}.etab-dot.INCIDENT_MAJEUR{background:var(--orange);box-shadow:0 0 6px var(--orange)}
.etab-dot.CRITIQUE{background:var(--red);animation:pulse-dot 1s infinite}
@keyframes pulse-dot{0%,100%{box-shadow:0 0 4px var(--red)}50%{box-shadow:0 0 12px var(--red)}}
.etab-info{flex:1;min-width:0}
.etab-sigle{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)}
.etab-nom{font-family:var(--mono);font-size:8px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.etab-age{font-family:var(--mono);font-size:8px;color:var(--muted)}
.btn-disconnect{font-family:var(--mono);font-size:7px;padding:2px 6px;background:rgba(255,45,85,.06);border:1px solid rgba(255,45,85,.2);border-radius:3px;color:rgba(255,45,85,.6);cursor:pointer;opacity:0;transition:opacity .15s;white-space:nowrap}
.etab-card:hover .btn-disconnect{opacity:1}
.btn-disconnect:hover{background:rgba(255,45,85,.15);color:var(--red)}

/* Detail panel */
#detail-panel{flex:1;overflow-y:auto;padding:18px 20px;background:var(--bg)}
.dp-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;color:var(--muted)}
.dp-empty-icon{font-size:40px;opacity:.15}

/* ── CARTOGRAPHIE ── */
#pane-carto{flex-direction:column}
#map{flex:1;background:var(--s1)}

/* ── MESSAGERIE INTER-GHT ── */
#pane-messagerie{flex-direction:column;background:var(--bg)}
#msg-toolbar{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--border);background:var(--s1);flex-shrink:0}
#msg-toolbar-title{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:1px;color:var(--muted2)}
.msg-sub-btn{font-family:var(--mono);font-size:8px;padding:3px 10px;border-radius:4px;border:1px solid var(--border2);background:transparent;color:var(--muted);cursor:pointer;transition:all .15s}
.msg-sub-btn.active{background:rgba(0,207,255,.1);border-color:rgba(0,207,255,.3);color:var(--cyan)}
#btn-compose-ight{font-family:var(--mono);font-size:8px;padding:4px 12px;background:#2563eb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-weight:700;margin-left:auto}
#msg-split{display:flex;flex:1;overflow:hidden}
#msg-list-pane{width:320px;flex-shrink:0;border-right:1px solid var(--border);overflow-y:auto;background:var(--s1)}
#msg-detail-pane{flex:1;overflow-y:auto;padding:28px 36px;background:var(--bg)}
.msg-item{padding:11px 14px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s}
.msg-item:hover{background:var(--s2)}
.msg-item.unread{border-left:2px solid var(--cyan)}
.msg-from{font-family:var(--mono);font-size:9px;font-weight:700;color:var(--muted2)}
.msg-subj{font-family:var(--mono);font-size:9px;color:var(--text);margin:2px 0}
.msg-prev{font-family:var(--mono);font-size:8px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.msg-date{font-family:var(--mono);font-size:8px;color:var(--muted)}

/* ── STATUTS PUBLICS ── */
#pane-statuts{flex-direction:column;background:var(--bg);overflow-y:auto;padding:16px}
.sp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.sp-card{background:var(--s1);border:1px solid var(--border2);border-radius:8px;overflow:hidden}
.sp-card-hdr{padding:12px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sp-card-body{padding:12px 14px}
.sp-svc-row{display:flex;align-items:center;gap:6px;padding:3px 0;font-family:var(--mono);font-size:8px}
.svc-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}

/* MODALS */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal-box{background:var(--s2);border:1px solid var(--border2);border-radius:10px;width:460px;max-width:95vw;overflow:hidden}
.modal-hdr{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.modal-hdr-title{font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)}
.modal-close{background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;line-height:1}
.modal-body{padding:18px;display:flex;flex-direction:column;gap:12px}
.form-label{font-family:var(--mono);font-size:8px;letter-spacing:1px;color:var(--muted);display:block;margin-bottom:4px}
.form-input{width:100%;font-family:var(--mono);font-size:10px;padding:7px 9px;background:var(--s3);border:1px solid var(--border2);border-radius:4px;color:var(--text);box-sizing:border-box}
.form-input:focus{outline:none;border-color:rgba(0,207,255,.4)}
.form-select{width:100%;font-family:var(--mono);font-size:10px;padding:7px 9px;background:var(--s3);border:1px solid var(--border2);border-radius:4px;color:var(--text)}
.form-textarea{width:100%;font-family:var(--mono);font-size:10px;padding:7px 9px;background:var(--s3);border:1px solid var(--border2);border-radius:4px;color:var(--text);resize:vertical;box-sizing:border-box}
.modal-footer{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid var(--border)}
.btn-cancel{font-family:var(--mono);font-size:9px;padding:5px 14px;background:var(--s3);border:1px solid var(--border2);border-radius:4px;color:var(--muted);cursor:pointer}
.btn-primary{font-family:var(--mono);font-size:9px;padding:5px 14px;background:#2563eb;border:none;border-radius:4px;color:#fff;cursor:pointer;font-weight:700}
.btn-primary:hover{background:#1d4ed8}

/* TOAST */
#toast{position:fixed;bottom:20px;right:20px;z-index:99999;font-family:var(--mono);font-size:10px;padding:10px 16px;border-radius:5px;display:none;animation:fadein .2s}
#toast.ok{background:#0d3320;border:1px solid var(--green);color:var(--green)}
#toast.err{background:#3d0d12;border:1px solid var(--red);color:var(--red)}
@keyframes fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* Leaflet dark */
.leaflet-container{background:#060608}
.leaflet-tile-pane{filter:none}
</style>
</head>
<body>
<script>
// Mode clair par défaut
(function(){
  var t = localStorage.getItem('coll_theme');
  if(t !== 'dark') document.body.classList.add('light');
})();
</script>
<div id="login-screen" style="display:none;position:fixed;inset:0;background:#f8fafc;z-index:9999;align-items:center;justify-content:center">
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:32px 36px;width:360px;box-shadow:0 4px 24px rgba(0,0,0,.08);display:flex;flex-direction:column;gap:12px">
  <div style="text-align:center"><img src="/static/logo-scribe.png" alt="SCRIBE" style="height:56px;object-fit:contain"></div>
  <div style="font-family:monospace;font-size:10px;letter-spacing:2px;text-align:center;color:#64748b;text-transform:uppercase">Supervision Territoriale</div>
  <div style="display:flex;flex-direction:column;gap:4px"><label style="font-family:monospace;font-size:9px;color:#64748b;letter-spacing:1px;text-transform:uppercase;display:block;margin-bottom:3px">Identifiant</label><input id="coll-login" type="text" placeholder="supervision" autocomplete="username" style="padding:9px 12px;border:1px solid #e2e8f0;border-radius:5px;font-family:monospace;font-size:11px;color:#0f172a;background:#f8fafc;outline:none;box-sizing:border-box;width:100%"></div>
  <div style="display:flex;flex-direction:column;gap:4px"><label style="font-family:monospace;font-size:9px;color:#64748b;letter-spacing:1px;text-transform:uppercase;display:block;margin-bottom:3px">Mot de passe</label><input id="coll-pass" type="password" placeholder="••••••••" autocomplete="current-password" onkeydown="if(event.key===String.fromCharCode(13))collLogin()" style="padding:9px 12px;border:1px solid #e2e8f0;border-radius:5px;font-family:monospace;font-size:11px;color:#0f172a;background:#f8fafc;outline:none;box-sizing:border-box;width:100%"></div>
  <button onclick="collLogin()" style="width:100%;padding:10px;font-family:monospace;font-size:12px;font-weight:700;letter-spacing:2px;background:#003189;color:#fff;border:none;border-radius:5px;cursor:pointer;margin-top:4px">CONNEXION</button>
  <div id="coll-err" style="font-family:monospace;font-size:10px;color:#e1000f;text-align:center;min-height:14px"></div>
  <div style="font-family:monospace;font-size:9px;color:#94a3b8;text-align:center;margin-top:8px">© Centre Hospitalier Valmont — SCRIBE Crisis OS<br>Accès réservé aux personnels autorisés</div>
</div>
</div>
<script>
(async function() {
  // 1. Si un token existe en localStorage, vérifier sa validité
  var existingTok = localStorage.getItem('coll_session');
  if (existingTok) {
    var vr = await fetch('api/ui/verify', {
      headers: {'Authorization': 'Bearer ' + existingTok}
    }).then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; });
    if (vr && vr.ok) {
      // Session valide → ne pas afficher le login, laisser l'app démarrer
      return;
    }
    // Session expirée → nettoyer
    localStorage.removeItem('coll_session');
  }
  // 2. Vérifier si auth requise
  const r = await fetch('api/ui/auth-required').catch(()=>null);
  if (!r || !r.ok) return;
  const d = await r.json();
  if (!d.required) return;
  // Auth requise — afficher l'écran de login
  const ls = document.getElementById('login-screen');
  const app = document.getElementById('app');
  if (ls) { ls.style.display='flex'; }
  if (app) { app.style.display='none'; }
})();

async function collLogin() {
  const login = document.getElementById('coll-login').value;
  const pass  = document.getElementById('coll-pass').value;
  const r = await fetch('api/ui/login', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({login, password: pass})
  }).catch(()=>null);
  if (!r || !r.ok) {
    document.getElementById('coll-err').textContent = 'Identifiants incorrects';
    return;
  }
  const d = await r.json();
  if (d.ok) {
    localStorage.setItem('coll_session', d.token);
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
  }
}
</script>
<div id="app">

  <!-- KPI BAR -->
  <div id="kpi-bar">
    <div id="kpi-title"><img src="/static/logo-scribe.png" alt="SCRIBE" style="height:24px;vertical-align:middle;margin-right:8px;object-fit:contain">SUPERVISION v2.3.32</div>
    <div class="kpi-cell"><span class="kpi-label">GHT</span><span class="kpi-val" id="k-ght">—</span></div>
    <div class="kpi-cell" style="cursor:pointer" title="Délai avant masquage incidents résolus (clic pour modifier)">
      <span class="kpi-label">RÉSOLU → masqué</span>
      <span class="kpi-val" id="k-hide-delay" onclick="promptHideDelay()" style="font-size:13px">30min</span>
    </div>
    <div class="kpi-cell"><span class="kpi-label">Sites</span><span class="kpi-val" id="k-etab" title="">—</span></div>
    <div class="kpi-cell"><span class="kpi-label">En attente</span><span class="kpi-val warn" id="k-pending">0</span></div>
    <div class="kpi-cell"><span class="kpi-label">Incidents actifs</span><span class="kpi-val" id="k-inc">—</span></div>
    <div class="kpi-cell"><span class="kpi-label">Critiques</span><span class="kpi-val crit" id="k-crit">—</span></div>
    <div class="kpi-cell"><span class="kpi-label">Messages non lus</span><span class="kpi-val" id="k-msg">—</span></div>
    <div id="kpi-clock">--:--:--</div>
    <div id="kpi-refresh" style="display:flex;align-items:center;gap:6px">
      <div class="refresh-dot"></div>
      <span id="refresh-countdown">30s</span>
      <button onclick="fetchAll()" title="Actualiser maintenant" style="font-family:var(--mono);font-size:9px;padding:2px 8px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);border-radius:4px;color:inherit;cursor:pointer">&#8635; ACTUALISER</button>
    </div>
  </div>

  <!-- TABS -->
  <div id="header">
    <button class="tab-btn active" onclick="switchTab('supervision',this)">⬡ SUPERVISION</button>
    <button class="tab-btn" onclick="switchTab('carto',this)">⊕ CARTOGRAPHIE</button>
    <button class="tab-btn" onclick="switchTab('messagerie',this)">✉ MESSAGES<span id="msg-badge-hdr"></span></button>
    <button class="tab-btn" onclick="switchTab('statuts',this)">▦ STATUTS PUBLICS</button>
    <button class="tab-btn" onclick="switchTab('chat',this)">💬 CHAT</button>
    <button class="tab-btn" onclick="switchTab('comptes',this)">&#128100; COMPTES</button>
    <div class="tab-spacer"></div>
  </div>

  <!-- MAIN -->
  <div id="main">

    <!-- SUPERVISION -->
    <div class="tab-pane active" id="pane-supervision">
      <div id="etab-left">
        <div id="etab-left-header">
          <div class="lh-title">Établissements enrôlés</div>
        </div>
        <!-- Pending section (hidden if empty) -->
        <div id="pending-section" style="display:none">
          <div id="pending-header" style="display:flex;align-items:center;justify-content:space-between">
            <span>⏳ EN ATTENTE <span id="pending-count">0</span></span>
            <button onclick="acceptAll()" id="btn-accept-all" style="display:none;font-family:var(--mono);font-size:7px;padding:2px 8px;background:rgba(74,222,128,.15);border:1px solid rgba(74,222,128,.4);border-radius:3px;color:#4ade80;cursor:pointer">✓ Tout accepter</button>
          </div>
          <div id="pending-list"></div>
        </div>
        <!-- Relay section -->
        <!-- Fix tokens section -->
        <div style="border-bottom:1px solid var(--border);padding:6px 12px;background:rgba(249,115,22,.04)">
          <div style="font-family:var(--mono);font-size:8px;color:var(--muted2);margin-bottom:4px;display:flex;align-items:center;justify-content:space-between">
            <span>🔧 TOKENS ARC ALPIN</span>
            <button onclick="registerArcAlpinTokens()" style="font-family:var(--mono);font-size:7px;padding:2px 8px;background:rgba(249,115,22,.15);border:1px solid rgba(249,115,22,.4);border-radius:3px;color:#f97316;cursor:pointer">
              ⚡ Enregistrer
            </button>
          </div>
          <div style="font-family:var(--mono);font-size:7px;color:var(--muted)">Si supervision vide → cliquer pour forcer l'enregistrement des tokens démo</div>
        </div>
        <div id="relay-section" style="border-bottom:1px solid var(--border);padding:8px 12px">
          <div style="font-family:var(--mono);font-size:8px;letter-spacing:1px;color:var(--muted2);margin-bottom:6px;display:flex;align-items:center;justify-content:space-between">
            <span>⇪ RELAIS UPSTREAM</span>
            <button onclick="openAddRelay()" style="font-family:var(--mono);font-size:7px;padding:2px 7px;background:rgba(0,207,255,.1);border:1px solid rgba(0,207,255,.3);border-radius:3px;color:var(--cyan);cursor:pointer">+ Ajouter</button>
          </div>
          <div id="relay-list"><span style="font-family:var(--mono);font-size:8px;color:var(--muted)">Aucun relais configuré</span></div>
        </div>
        <!-- Enrolled list -->
        <div id="etab-list"></div>
      </div>
      <div id="detail-panel">
        <div class="dp-empty">
          <div class="dp-empty-icon">⬡</div>
          <span style="font-family:var(--mono);font-size:10px;letter-spacing:1px">Sélectionnez un établissement</span>
        </div>
      </div>
    </div>

    <!-- CARTOGRAPHIE -->
    <div class="tab-pane" id="pane-carto">
      <div id="map"></div>
    </div>

    <!-- MESSAGERIE INTER-GHT -->
    <div class="tab-pane" id="pane-messagerie">
      <div id="msg-toolbar">
        <span id="msg-toolbar-title">✉ MESSAGERIE INTER-GHT</span>
        <button class="msg-sub-btn active" id="btn-recu" onclick="msgSwitch('recu',this)">Reçus</button>
        <button class="msg-sub-btn" id="btn-envoyes" onclick="msgSwitch('envoyes',this)">Envoyés</button>
        <button id="btn-compose-ight" onclick="openCompose()">✏ Nouveau message</button>
      </div>
      <div id="msg-split">
        <div id="msg-list-pane">
          <div style="padding:30px;text-align:center;font-family:var(--mono);font-size:9px;color:var(--muted)">Chargement…</div>
        </div>
        <div id="msg-detail-pane">
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;color:var(--muted)">
            <span style="font-size:32px;opacity:.2">✉</span>
            <span style="font-family:var(--mono);font-size:9px">Sélectionnez un message</span>
          </div>
        </div>
      </div>
    </div>

    <!-- STATUTS PUBLICS -->
    <div class="tab-pane" id="pane-statuts">
      <div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:20px">Chargement…</div>
    </div>

  <!-- Pane Chat -->
  <div id="pane-chat" style="display:none;flex:1;overflow:hidden;min-height:0;position:relative;width:100%;height:100%">
    <iframe id="chat-iframe" src="" style="position:absolute;inset:0;width:100%;height:100%;border:none;display:block"></iframe>
  </div>

  <!-- Pane Comptes -->
  <div id="pane-comptes" style="display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0;width:100%;height:100%">
    <div style="font-family:var(--mono);font-size:9px;color:var(--muted);padding:10px 16px;border-bottom:1px solid var(--border);flex-shrink:0">
      👤 GESTION DES COMPTES SUPERVISION
    </div>
    <div style="padding:20px;display:flex;flex-direction:column;gap:16px;overflow-y:auto;flex:1">
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:16px">
        <div style="font-family:var(--mono);font-size:10px;font-weight:700;margin-bottom:12px">CRÉER UN COMPTE</div>
        <div style="display:flex;flex-direction:column;gap:8px;max-width:360px">
          <input id="new-login" type="text" placeholder="Identifiant" style="font-family:var(--mono);font-size:11px;padding:7px 10px;background:var(--surface);border:1px solid var(--border2);border-radius:5px;color:var(--text)">
          <input id="new-pass" type="password" placeholder="Mot de passe" style="font-family:var(--mono);font-size:11px;padding:7px 10px;background:var(--surface);border:1px solid var(--border2);border-radius:5px;color:var(--text)">
          <select id="new-role" style="font-family:var(--mono);font-size:11px;padding:7px 10px;background:var(--surface);border:1px solid var(--border2);border-radius:5px;color:var(--text)">
            <option value="viewer">Lecteur</option>
            <option value="admin">Admin</option>
          </select>
          <button onclick="createCompte()" style="font-family:var(--mono);font-size:10px;padding:7px 14px;background:#003189;color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:700;width:fit-content">Créer</button>
        </div>
      </div>
      <div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:16px">
        <div style="font-family:var(--mono);font-size:10px;font-weight:700;margin-bottom:12px">COMPTES EXISTANTS</div>
        <div id="comptes-list"></div>
      </div>
    </div>
  </div>

  </div><!-- /main -->
</div><!-- /app -->

<!-- Modal Add Relay -->
<div class="modal-overlay" id="modal-add-relay">
  <div class="modal-box">
    <div class="modal-hdr">
      <span class="modal-hdr-title">⇪ AJOUTER UN COLLECTEUR DE RELAIS</span>
      <button class="modal-close" onclick="closeModal('modal-add-relay')">✕</button>
    </div>
    <div class="modal-body">
      <div style="font-family:var(--mono);font-size:8px;color:var(--muted);line-height:1.6;padding:6px 8px;background:var(--s3);border-radius:4px;border:1px solid var(--border2);margin-bottom:4px">
        Tous les pushs reçus seront automatiquement retransmis vers ce collecteur.<br>
        Le collecteur cible doit avoir enregistré le token que vous choisissez.
      </div>
      <div>
        <label class="form-label">NOM DU COLLECTEUR</label>
        <input id="relay-nom" type="text" class="form-input" placeholder="ex: Supervision ARA, CERT Santé National">
      </div>
      <div>
        <label class="form-label">URL DU COLLECTEUR UPSTREAM</label>
        <input id="relay-url" type="text" class="form-input" placeholder="http://192.168.1.200:9000/api/push">
      </div>
      <div>
        <label class="form-label">TOKEN D'AUTHENTIFICATION</label>
        <input id="relay-token" type="text" class="form-input" placeholder="token_mon_collecteur_regional_2026">
        <div style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:3px">Min 16 caractères — doit être enregistré sur le collecteur cible</div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal('modal-add-relay')">Annuler</button>
      <button class="btn-primary" onclick="doTestRelay()" style="background:#0d4f8c;margin-right:4px">🔌 Tester</button>
      <button class="btn-primary" onclick="doAddRelay()">⇪ Configurer</button>
    </div>
  </div>
</div>

<!-- Modal Compose -->
<div class="modal-overlay" id="modal-compose">
  <div class="modal-box">
    <div class="modal-hdr">
      <span class="modal-hdr-title">✏ NOUVEAU MESSAGE INTER-GHT</span>
      <button class="modal-close" onclick="closeModal('modal-compose')">✕</button>
    </div>
    <div class="modal-body">
      <div>
        <label class="form-label">DESTINATAIRE</label>
        <select id="compose-dest" class="form-select">
          <option value="TOUS">📢 Tous les GHT</option>
        </select>
      </div>
      <div>
        <label class="form-label">OBJET</label>
        <input id="compose-sujet" type="text" class="form-input" placeholder="Objet du message">
      </div>
      <div>
        <label class="form-label">MESSAGE</label>
        <textarea id="compose-body" class="form-textarea" rows="5" placeholder="Rédigez votre message…"></textarea>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal('modal-compose')">Annuler</button>
      <button class="btn-primary" onclick="sendMsg()">Envoyer ✉</button>
    </div>
  </div>
</div>

<!-- Modal Accept pending -->
<div class="modal-overlay" id="modal-accept">
  <div class="modal-box">
    <div class="modal-hdr">
      <span class="modal-hdr-title">✓ ACCEPTER L'ÉTABLISSEMENT</span>
      <button class="modal-close" onclick="closeModal('modal-accept')">✕</button>
    </div>
    <div class="modal-body">
      <div id="accept-info" style="font-family:var(--mono);font-size:9px;color:var(--muted);line-height:1.8;padding:8px 10px;background:var(--s3);border-radius:5px;border:1px solid var(--border2)"></div>
      <div>
        <label class="form-label">SIGLE OFFICIEL</label>
        <input id="accept-sigle" type="text" class="form-input" placeholder="ex: CHANGE">
      </div>
      <input id="accept-token" type="hidden">
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal('modal-accept')">Annuler</button>
      <button class="btn-primary" onclick="doAccept()">✓ Enrôler</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const ADMIN_TOKEN = 'PLACEHOLDER_ADMIN_TOKEN';  // remplacé côté serveur
let allData = [];
let pendingList = [];
let selectedSigle = null;
let refreshInterval = 30;
let countdown = 30;
let map = null;
let mapMarkers = {};
let msgMode = 'recu';

// ── Utilities ──────────────────────────────────────────────
function toast(msg, type='ok') {
  const el = document.getElementById('toast');
  el.textContent = msg; el.className = type; el.style.display = 'block';
  clearTimeout(el._t); el._t = setTimeout(() => el.style.display='none', 3000);
}

function fmtAge(iso) {
  if (!iso) return '?';
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'à l\'instant';
  if (m < 60) return `${m}min`;
  return `${Math.floor(m/60)}h${m%60}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}

const LEVEL_COLOR = {NOMINAL:'#00e5a0',VEILLE:'#00e5a0',ALERTE:'#f5c518',CRISE:'#ff7b2c',CRITIQUE:'#ff2d55',INCONNU:'#4a5070'};

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// ── Tab switching ───────────────────────────────────────────
function switchTab(id, btn) {
  // Masquer tous les panes (classe tab-pane ET nos panes custom)
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  ['pane-chat','pane-comptes'].forEach(pid => {
    var el = document.getElementById(pid);
    if (el) el.style.display = 'none';
  });
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

  // Panes natifs via classe active
  var pane = document.getElementById('pane-' + id);
  if (pane) {
    if (id === 'chat' || id === 'comptes') {
      pane.style.display = 'flex';
    } else {
      pane.classList.add('active');
    }
  }
  if (btn) btn.classList.add('active');
  if (id === 'carto') { setTimeout(() => { if (map) { map.invalidateSize(); updateMapMarkers(); } else { initMap(); } window._mapUpdatePending = false; }, 150); }
  if (id === 'messagerie') loadMessages();
  if (id === 'statuts') renderStatuts(allData);
  if (id === 'chat') {
    var iframe = document.getElementById('chat-iframe');
    if (iframe) {
      var tok = localStorage.getItem('coll_session') || '';
      // Toujours recharger avec le token frais
      iframe.src = 'chat/ui?token=' + encodeURIComponent(tok);
    }
  }
  if (id === 'comptes') loadComptes();
}

// ── CLOCK ───────────────────────────────────────────────────
setInterval(() => {
  document.getElementById('kpi-clock').textContent = new Date().toLocaleTimeString('fr-FR');
  countdown--;
  if (countdown <= 0) { countdown = refreshInterval; fetchAll(); }
  document.getElementById('refresh-countdown').textContent = countdown + 's';
}, 1000);

// ── FETCH ALL ───────────────────────────────────────────────
let resolvedHideMinutes = parseInt(localStorage.getItem('scribe_hide_min') || '30');
document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('k-hide-delay');
  if (el) el.textContent = resolvedHideMinutes + 'min';
});

function promptHideDelay() {
  const v = prompt('Masquer les incidents résolus après combien de minutes ? (0 = jamais)', resolvedHideMinutes);
  if (v === null) return;
  resolvedHideMinutes = Math.max(0, parseInt(v) || 30);
  localStorage.setItem('scribe_hide_min', resolvedHideMinutes);
  const el = document.getElementById('k-hide-delay');
  if (el) el.textContent = resolvedHideMinutes === 0 ? 'jamais' : resolvedHideMinutes + 'min';
  fetchAll();
}

async function fetchAll() {
  try {
    const [sumRes, pendRes] = await Promise.all([
      fetch('/api/summary'),
      fetch('/api/admin/pending', {headers:{'Authorization':'Bearer '+ADMIN_TOKEN}})
    ]);
    if (sumRes.ok) allData = await sumRes.json();
    if (pendRes.ok) pendingList = await pendRes.json();
  } catch(e) {}
  renderKPIs();
  renderEtabList();
  renderPending();
  if (selectedSigle) renderDetail(allData.find(e => e.sigle === selectedSigle));
  if (map) updateMapMarkers(); else { window._mapUpdatePending = true; }
  await fetchMsgBadge();
  loadRelays();
}

// ── KPIs ────────────────────────────────────────────────────
function renderKPIs() {
  const totalInc = allData.reduce((a,e) => a + (e.kpis?.incidents_ouverts||0), 0);
  const totalCrit = allData.reduce((a,e) => a + (e.kpis?.incidents_critiques||0), 0);
  const totalSites = allData.reduce((a,e) => a + (e.sites ? e.sites.length : 1), 0);
  const kEtab = document.getElementById('k-etab');
  kEtab.textContent = totalSites || allData.length;
  kEtab.title = allData.length + ' GHT · ' + totalSites + ' sites';
  const kGht = document.getElementById('k-ght');
  if (kGht) kGht.textContent = allData.length;
  document.getElementById('k-pending').textContent = pendingList.length;
  document.getElementById('k-inc').textContent = totalInc;
  document.getElementById('k-inc').className = 'kpi-val ' + (totalInc > 0 ? 'warn' : 'ok');
  document.getElementById('k-crit').textContent = totalCrit;
  document.getElementById('k-crit').className = 'kpi-val ' + (totalCrit > 0 ? 'crit' : 'ok');
}

// ── PENDING ─────────────────────────────────────────────────
async function acceptAll() {
  const r = await fetch('/api/admin/pending/accept-all', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + ADMIN_TOKEN}
  });
  const d = await r.json().catch(()=>({}));
  if (r.ok) {
    toast('✓ ' + d.count + ' établissement(s) accepté(s) : ' + (d.accepted||[]).join(', '), 'ok');
    fetchAll();
  } else toast('Erreur', 'err');
}

function renderPending() {
  const btnAll = document.getElementById('btn-accept-all');
  if (btnAll) btnAll.style.display = pendingList.length > 1 ? 'inline-block' : 'none';
  const sec = document.getElementById('pending-section');
  const list = document.getElementById('pending-list');
  const countEl = document.getElementById('pending-count');
  if (!pendingList.length) { sec.style.display = 'none'; return; }
  sec.style.display = 'block';
  countEl.textContent = pendingList.length;
  list.innerHTML = pendingList.map(p => `
    <div class="pending-card">
      <div class="pending-card-nom">🏥 ${p.nom_propose || p.sigle_propose}</div>
      <div class="pending-card-sub">${p.sigle_propose} · ${p.ip} · ${fmtDate(p.first_seen)}</div>
      <div class="pending-actions">
        <button class="btn-accept" onclick="openAccept('${p.token}','${p.sigle_propose}','${(p.nom_propose||'').replace(/'/g,'')}')">✓ Accepter</button>
        <button class="btn-reject" onclick="doReject('${p.token}')">✗</button>
      </div>
    </div>`).join('');
}

function openAccept(token, sigle, nom) {
  document.getElementById('accept-token').value = token;
  document.getElementById('accept-sigle').value = sigle;
  document.getElementById('accept-info').innerHTML = `<b>Nom proposé :</b> ${nom}<br><b>Sigle proposé :</b> ${sigle}<br><b>Token (12c) :</b> ${token.substring(0,12)}...`;
  document.getElementById('modal-accept').classList.add('open');
}

async function doAccept() {
  const token = document.getElementById('accept-token').value;
  const sigle = document.getElementById('accept-sigle').value.trim().toUpperCase();
  if (!sigle) { toast('Saisissez le sigle', 'err'); return; }
  const prefix = token; // send full token as prefix
  const r = await fetch('/api/admin/pending/'+encodeURIComponent(token)+'/accept', {
    method:'POST', headers:{'Authorization':'Bearer '+ADMIN_TOKEN,'Content-Type':'application/json'},
    body: JSON.stringify({sigle})
  });
  if (r.ok) { toast('✓ '+sigle+' enrôlé', 'ok'); closeModal('modal-accept'); fetchAll(); }
  else { const d=await r.json().catch(()=>{}); toast(d?.detail||'Erreur', 'err'); }
}

async function doReject(token) {
  if (!confirm('Rejeter cet établissement ?')) return;
  const r = await fetch('/api/admin/pending/'+encodeURIComponent(token)+'/reject', {
    method:'POST', headers:{'Authorization':'Bearer '+ADMIN_TOKEN}
  });
  if (r.ok) { toast('Rejeté', 'ok'); fetchAll(); }
}

async function doDisconnect(sigle) {
  if (!confirm('Déconnecter '+sigle+' ? Il ne pourra plus pousser de données.')) return;
  const r = await fetch('/api/admin/tokens/'+sigle, {
    method:'DELETE', headers:{'Authorization':'Bearer '+ADMIN_TOKEN}
  });
  if (r.ok) { toast(sigle+' déconnecté', 'ok'); if (selectedSigle===sigle) selectedSigle=null; fetchAll(); }
  else toast('Erreur', 'err');
}

// ── ETAB LIST ────────────────────────────────────────────────
function renderEtabList() {
  const el = document.getElementById('etab-list');
  if (!allData.length) {
    el.innerHTML = '<div style="padding:20px 12px;font-family:var(--mono);font-size:9px;color:var(--muted);text-align:center">Aucun établissement connecté</div>';
    return;
  }
  el.innerHTML = allData.map(e => {
    const col = LEVEL_COLOR[e.niveau_global] || LEVEL_COLOR.INCONNU;
    const sel = selectedSigle === e.sigle ? 'selected' : '';
    return `<div class="etab-card ${sel}" onclick="selectEtab('${e.sigle}')">
      <div class="etab-dot ${e.niveau_global||'INCONNU'}"></div>
      <div class="etab-info">
        <div class="etab-sigle">${e.sigle}</div>
        <div class="etab-nom">${e.nom||''}</div>
        <div class="etab-age">${fmtAge(e.received_at)}</div>
      </div>
      <button class="btn-disconnect" onclick="event.stopPropagation();doDisconnect('${e.sigle}')">⏻ Déco</button>
    </div>`;
  }).join('');
}

function selectEtab(sigle) {
  selectedSigle = sigle;
  renderEtabList();
  renderDetail(allData.find(e => e.sigle === sigle));
}

// ── DETAIL ──────────────────────────────────────────────────
function renderDetail(e) {
  const el = document.getElementById('detail-panel');
  if (!e) {
    el.innerHTML = '<div class="dp-empty"><div class="dp-empty-icon">⬡</div><span style="font-family:var(--mono);font-size:10px;letter-spacing:1px">Sélectionnez un établissement</span></div>';
    return;
  }
  const col = LEVEL_COLOR[e.niveau_global] || LEVEL_COLOR.INCONNU;
  const kpis = e.kpis || {};
  const sites = e.sites || [];
  const incs  = e.incidents || [];

  let sitesHtml = '';
  if (sites.length) {
    sitesHtml = `<div style="margin-bottom:16px">
      <div style="font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:var(--muted);margin-bottom:8px">SITES</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        ${sites.map(s => {
          const sc = LEVEL_COLOR[s.niveau] || LEVEL_COLOR.INCONNU;
          return `<div style="padding:6px 10px;background:var(--s2);border:1px solid ${sc}33;border-radius:5px;font-family:var(--mono);font-size:9px">
            <span style="color:${sc}">●</span> ${s.nom} <span style="color:var(--muted)">${s.nb_incidents||0} inc.</span>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }

  let incsHtml = '';
  if (incs.length) {
    const urgColor = {1:'#3d9eff',2:'#f5c518',3:'#ff7b2c',4:'#ff2d55'};
    incsHtml = `<div>
      <div style="font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:var(--muted);margin-bottom:8px">INCIDENTS EN COURS</div>
      ${incs.filter(i => {
          if (i.status === 'ARCHIVÉ') return false;
          if (i.status === 'RÉSOLU' && resolvedHideMinutes > 0) {
            const ts = i.timestamp ? new Date(i.timestamp) : null;
            if (ts && (Date.now() - ts.getTime()) > resolvedHideMinutes * 60000) return false;
          }
          return true;
        }).slice(0, 8).map(i=>`
        <div style="padding:8px 10px;background:var(--s2);border-left:2px solid ${urgColor[i.urgency]||'#4a5070'};border-radius:0 5px 5px 0;margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
            <span style="font-family:var(--mono);font-size:8px;color:${urgColor[i.urgency]||'var(--muted)'};font-weight:700">U${i.urgency||'?'}</span>
            <span style="font-family:var(--mono);font-size:8px;color:var(--muted2)">${i.type_crise||''}</span>
          </div>
          <div style="font-family:var(--mono);font-size:9px;color:var(--text)">${(i.fait_resume||'').substring(0,90)}</div>
          <div style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:2px">${i.site_id||''}</div>
        </div>`).join('')}
    </div>`;
  }

  // Renforts mode dégradé (depuis données capacité)
  const capData = e.capacite || {};
  const renforts = (capData.services_renfort || []);
  // Transferts actifs
  const tActifs = e.transferts_actifs || [];
  const transfertsHtml = tActifs.length ? `<div style="margin-top:14px">
    <div style="font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:#60a5fa;margin-bottom:8px">🚑 TRANSFERTS ACTIFS (${tActifs.length})</div>
    ${tActifs.map(t=>`<div style="padding:5px 10px;background:var(--s2);border-left:2px solid ${t.statut==='EN_COURS'?'#60a5fa':'#fbbf24'};border-radius:0 4px 4px 0;margin-bottom:4px;font-family:var(--mono);font-size:9px">
      ${t.statut==='EN_COURS'?'🚑':'⏳'} ${t.unite_origine} → ${t.unite_destination}
      ${t.etablissement_destination!==e.sigle?`<span style="color:var(--muted)"> (${t.etablissement_destination})</span>`:''}
    </div>`).join('')}
  </div>` : '';

  el.innerHTML = `
    <div style="max-width:700px">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px">
        <div style="width:10px;height:10px;border-radius:50%;background:${col};flex-shrink:0;box-shadow:0 0 8px ${col}"></div>
        <div>
          <div style="font-family:var(--head);font-size:22px;font-weight:700;color:var(--text);letter-spacing:1px">${e.nom||e.sigle}</div>
          <div style="font-family:var(--mono);font-size:9px;color:var(--muted)">${e.sigle} · Dernière mise à jour : ${fmtDate(e.received_at)}</div>
        </div>
        <div style="margin-left:auto;padding:5px 14px;border-radius:5px;background:${col}18;border:1px solid ${col}44;font-family:var(--mono);font-size:11px;font-weight:700;color:${col}">${e.niveau_global||'—'}</div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px">
        ${[
          ['Incidents ouverts', kpis.incidents_ouverts||0, kpis.incidents_ouverts>0?'warn':'ok'],
          ['Critiques', kpis.incidents_critiques||0, kpis.incidents_critiques>0?'crit':'ok'],
          ['Cyber', kpis.cyber||0, ''],
          ['Sanitaire', kpis.sanitaire||0, '']
        ].map(([l,v,cls])=>`<div style="padding:10px;background:var(--s2);border:1px solid var(--border2);border-radius:6px;text-align:center">
          <div style="font-family:var(--mono);font-size:18px;font-weight:700;color:${cls==='crit'?'var(--red)':cls==='warn'?'var(--yellow)':'var(--text)'}">${v}</div>
          <div style="font-family:var(--mono);font-size:7px;letter-spacing:1px;color:var(--muted);margin-top:3px">${l}</div>
        </div>`).join('')}
      </div>
      ${sitesHtml}
      ${incsHtml}
      ${renforts.length ? `<div style="margin-top:14px">
        <div style="font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:#f97316;margin-bottom:8px">⚙ MODE DÉGRADÉ — RH</div>
        ${renforts.map(r=>`<div style="padding:6px 10px;background:rgba(249,115,22,.07);border:1px solid rgba(249,115,22,.25);border-radius:5px;margin-bottom:5px;font-family:var(--mono);font-size:9px">
          <b>${r.service}</b> · ${r.site}
          ${r.besoin_renfort>0?`<span style="color:#f97316;margin-left:8px">⚠ Renfort : ${r.besoin_renfort}</span>`:''}
          ${r.peut_preter>0?`<span style="color:#4ade80;margin-left:8px">🤝 Prête : ${r.peut_preter}</span>`:''}
        </div>`).join('')}
      </div>` : ''}
      ${transfertsHtml}
      ${(() => {
        const sp = e._status_page;
        if (!sp) return '';
        const faqVisible = (sp.faq||[]).filter(f => f.visible && f.reponse);
        const spSvcs = (sp.services_si||[]).filter(s => s.statut && s.statut.toLowerCase() !== 'ok');
        const spPec = (sp.prise_en_charge||[]).filter(s => s.statut && s.statut.toLowerCase() !== 'ok');
        const impacted = [...spSvcs, ...spPec];
        if (!faqVisible.length && !impacted.length && !sp.message_public) return '';
        return '<div style="margin-top:14px;padding:10px 12px;background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.2);border-radius:6px">' +
          '<div style="font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:#a5b4fc;margin-bottom:8px">📋 STATUT PUBLIC</div>' +
          (sp.message_public ? '<div style="font-family:var(--mono);font-size:9px;color:var(--muted2);margin-bottom:8px;line-height:1.5">' + sp.message_public + '</div>' : '') +
          (impacted.length ? impacted.map(s => {
            const isDeg = ['hs','hors_service','hors service'].includes((s.statut||'').toLowerCase());
            const col = isDeg ? 'var(--red)' : 'var(--yellow)';
            return '<div style="font-family:var(--mono);font-size:9px;margin-bottom:3px"><span style="color:' + col + '">●</span> ' + (s.label||s.id||'') + ' — <span style="color:' + col + '">' + (isDeg?'Hors service':'Perturbé') + '</span></div>';
          }).join('') : '') +
          (faqVisible.length ? '<div style="margin-top:6px">' + faqVisible.map(f =>
            '<div style="font-family:var(--mono);font-size:9px;margin-bottom:4px"><span style="color:var(--muted)">Q: </span>' + f.question + '<br><span style="color:var(--cyan)">R: </span>' + f.reponse + '</div>'
          ).join('') + '</div>' : '') +
          '</div>';
      })()}
    </div>`;
}

// ── CARTE ────────────────────────────────────────────────────
function initMap() {
  if (map) return;
  map = L.map('map', {zoomControl:true}).setView([45.5, 6.2], 8);
  const _osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {attribution:'© OpenStreetMap', maxZoom:19});
  const _cartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    {attribution:'CartoDB Light', maxZoom:19});
  const _satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {attribution:'Esri World Imagery', maxZoom:19});
  const _baseLayers = {'⬜ CartoDB Clair': _cartoLight, '🗺 OpenStreetMap': _osmLayer, '🛰 Satellite': _satellite};
  _cartoLight.addTo(map);
  L.control.layers(_baseLayers, {}, {position:'topright', collapsed:false}).addTo(map);
  updateMapMarkers();
}

function fitMapToBounds() {
  if (!map || !Object.keys(mapMarkers).length) return;
  const latlngs = Object.values(mapMarkers).map(m => m.getLatLng());
  if (latlngs.length > 0) {
    const bounds = L.latLngBounds(latlngs);
    map.fitBounds(bounds.pad(0.12));
  }
}

let transfertLines = [];
function updateTransfertLayer() {
  // Supprimer les anciennes lignes
  transfertLines.forEach(l => map && l.remove());
  transfertLines = [];
  if (!map) return;
  // Regrouper les transferts EN_COURS par route etab_orig → etab_dest
  const routes = {};
  allData.forEach(etab => {
    (etab.transferts_actifs || []).filter(t => t.statut === 'EN_COURS').forEach(t => {
      const key = [t.etablissement_origine, t.etablissement_destination].sort().join('|||');
      routes[key] = (routes[key] || 0) + 1;
    });
  });
  // Construire un index GPS par sigle
  const gpsIdx = {};
  allData.forEach(etab => {
    if (etab.latitude && etab.longitude)
      gpsIdx[etab.etablissement?.sigle || ''] = [etab.latitude, etab.longitude];
    (etab.sites || []).forEach(s => { if (s.latitude && s.longitude) gpsIdx[s.nom] = [s.latitude, s.longitude]; });
  });
  Object.entries(routes).forEach(([key, count]) => {
    const [a, b] = key.split('|||');
    const gA = gpsIdx[a], gB = gpsIdx[b];
    if (!gA || !gB) return;
    const line = L.polyline([gA, gB], {color:'#60a5fa', weight:2+count, opacity:0.7, dashArray:'6 4'}).addTo(map);
    line.bindTooltip(`🚑 ${count} transfert${count>1?'s':''} EN COURS
${a} → ${b}`, {sticky:true});
    transfertLines.push(line);
  });
}

function updateMapMarkers() {
  Object.values(mapMarkers).forEach(m => map.removeLayer(m));
  mapMarkers = {};
  allData.forEach(e => {
    const col = LEVEL_COLOR[e.niveau_global] || LEVEL_COLOR.INCONNU;
    const sites = e.sites || [];
    const coords = sites.length
      ? sites.map(s=>({lat:s.latitude,lng:s.longitude,nom:s.nom,niv:s.incidents_ouverts>0?s.niveau||e.niveau_global:(['CRITIQUE','CRISE'].includes(e.niveau_global)?'ALERTE':s.niveau||'NOMINAL'),inc:s.incidents_ouverts||0,own:s.incidents_ouverts>0})).filter(s=>s.lat&&s.lng&&!isNaN(+s.lat)&&!isNaN(+s.lng))
      : (e.latitude && e.longitude ? [{lat:e.latitude,lng:e.longitude,nom:e.nom||e.sigle,niv:e.niveau_global}] : []);
    coords.forEach(s => {
      if (!s.lat || !s.lng || isNaN(+s.lat) || isNaN(+s.lng)) return;
      const sc = LEVEL_COLOR[s.niv] || col;
      const icon = L.divIcon({className:'',html:`<div style="width:12px;height:12px;border-radius:50%;background:${sc};border:2px solid ${sc}88;box-shadow:0 0 8px ${sc}66"></div>`,iconSize:[12,12],iconAnchor:[6,6]});
      const m = L.marker([s.lat,s.lng],{icon}).addTo(map);
      m.bindPopup(`<b>${e.sigle}</b><br>${s.nom}<br><span style='color:${sc}'>${s.niv||'NOMINAL'}</span>${s.inc>0?' — '+s.inc+' incident(s)':''}`); 
      mapMarkers[e.sigle+'_'+s.nom] = m;
    });
  });
  fitMapToBounds();
  updateTransfertLayer();
}

// ── STATUTS PUBLICS ───────────────────────────────────────────
function renderStatuts(data) {
  const el = document.getElementById('pane-statuts');
  // Collecter tous les statuts publiés : global + par site
  const cards = [];
  data.forEach(e => {
    if (e._status_page && e._status_page.published) {
      cards.push({e, sp: e._status_page, isSite: false});
    }
    // Sites publiés séparément
    const sites = e._status_page && e._status_page._statuts_sites ? e._status_page._statuts_sites : [];
    sites.forEach(ss => { if (ss.published) cards.push({e, sp: ss, isSite: true}); });
  });
  if (!cards.length) {
    el.innerHTML = '<div style="padding:40px;text-align:center;font-family:var(--mono);font-size:9px;color:var(--muted)">Aucun établissement n\'a publié de point de situation</div>';
    return;
  }
  const niveauCol = {
    operationnel:'#00e5a0', OPERATIONNEL:'#00e5a0',
    perturbe:'#f5c518',     PERTURBE:'#f5c518',
    incident_majeur:'#ff2d55', INCIDENT_MAJEUR:'#ff2d55',
    maintenance:'#4a5070',  MAINTENANCE:'#4a5070'
  };
  const niveauLabel = {
    operationnel:'✅ Opérationnel', OPERATIONNEL:'✅ Opérationnel',
    perturbe:'⚠️ Perturbé',         PERTURBE:'⚠️ Perturbé',
    incident_majeur:'🔴 Incident majeur', INCIDENT_MAJEUR:'🔴 Incident majeur',
    maintenance:'⚙️ Maintenance',   MAINTENANCE:'⚙️ Maintenance'
  };
  el.innerHTML = '<div class="sp-grid">' + cards.map(({e, sp, isSite}) => {
    const nc  = niveauCol[sp.niveau_global] || '#4a5070';
    const spSvcs = (sp.services_si||[]).filter(s => s.statut && s.statut.toLowerCase() !== 'ok');
    const spPec  = (sp.prise_en_charge||[]).filter(s => s.statut && s.statut.toLowerCase() !== 'ok');
    const msgOff = sp.message_public || sp.message_officiel || '';
    const titre  = e.sigle + (sp.site_nom ? ' — ' + sp.site_nom : '');
    const impacted = [...spSvcs, ...spPec];
    return '<div class="sp-card">' +
      '<div class="sp-card-hdr" style="border-left:3px solid ' + nc + '">' +
        '<div style="flex:1">' +
          '<div style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text)">' + titre + '</div>' +
          '<div style="font-family:var(--mono);font-size:8px;color:' + nc + ';margin-top:2px">' + (niveauLabel[sp.niveau_global] || sp.niveau_global || '—') + '</div>' +
        '</div>' +
        '<div style="font-family:var(--mono);font-size:8px;color:var(--muted)">' + fmtDate(sp.updated_at || e.received_at) + '</div>' +
      '</div>' +
      '<div class="sp-card-body">' +
        (msgOff ? '<div style="font-family:var(--mono);font-size:9px;color:var(--muted2);margin-bottom:8px;line-height:1.5">' + msgOff + '</div>' : '') +
        (impacted.length > 0
          ? '<div style="font-family:var(--mono);font-size:8px;letter-spacing:1px;color:var(--muted);margin-bottom:4px">SERVICES IMPACTÉS</div>' +
            impacted.map(s => {
              const isDeg = ['hs','hors_service','hors service'].includes((s.statut||'').toLowerCase());
              const col = isDeg ? 'var(--red)' : 'var(--yellow)';
              return '<div class="sp-svc-row"><div class="svc-dot" style="background:' + col + '"></div>' +
                (s.label || s.id || '').replace(/_/g,' ') + ' — <span style="color:' + col + '">' + (isDeg ? 'Hors service' : 'Perturbé') + '</span></div>';
            }).join('')
          : '<div style="font-family:var(--mono);font-size:8px;color:var(--green)">Tous les services opérationnels</div>') +
      '</div>' +
    '</div>';
  }).join('') + '</div>';
}

// ── MESSAGERIE INTER-GHT ──────────────────────────────────────
let msgData = {received:[], sent:[]};

async function fetchMsgBadge() {
  try {
    const r = await fetch('/api/messages/non-lus', {headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
    if (!r.ok) return;
    const d = await r.json();
    const b = document.getElementById('msg-badge-hdr');
    if (d.count > 0) { b.textContent = d.count; b.style.display = 'inline'; }
    else b.style.display = 'none';
    document.getElementById('k-msg').textContent = d.count || '0';
  } catch(e) {}
}

async function loadMessages() {
  try {
    const r = await fetch('/api/messages', {headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
    if (!r.ok) return;
    msgData = await r.json();
  } catch(e) {}
  renderMsgList();
  // Populate dest select
  const sel = document.getElementById('compose-dest');
  sel.innerHTML = '<option value="TOUS">📢 Tous les GHT</option>';
  allData.forEach(e => { const opt = document.createElement('option'); opt.value = e.sigle; opt.textContent = e.sigle + (e.nom ? ' — ' + e.nom : ''); sel.appendChild(opt); });
  fetchMsgBadge();
}

function msgSwitch(mode, btn) {
  msgMode = mode;
  document.querySelectorAll('.msg-sub-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderMsgList();
  document.getElementById('msg-detail-pane').innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;color:var(--muted)"><span style="font-size:32px;opacity:.2">✉</span><span style="font-family:var(--mono);font-size:9px">Sélectionnez un message</span></div>';
}

function renderMsgList() {
  const el = document.getElementById('msg-list-pane');
  const list = msgMode === 'recu' ? msgData.received : msgData.sent;
  if (!list || !list.length) {
    el.innerHTML = '<div style="padding:30px;text-align:center;font-family:var(--mono);font-size:9px;color:var(--muted)">' + (msgMode==='recu'?'Aucun message reçu':'Aucun message envoyé') + '</div>';
    return;
  }
  el.innerHTML = list.slice().reverse().map(m => {
    const unread = msgMode==='recu' && !m.lu_par?.includes('COLLECTEUR');
    const contact = msgMode==='recu' ? m.expediteur : ('→ ' + (m.destinataire === 'TOUS' ? 'Tous les GHT' : m.destinataire));
    return `<div class="msg-item ${unread?'unread':''}" onclick="openMsg(${m.id})">
      <div style="display:flex;justify-content:space-between;margin-bottom:2px">
        <span class="msg-from">${contact}</span>
        <span class="msg-date">${fmtDate(m.created_at)}</span>
      </div>
      <div class="msg-subj" style="font-weight:${unread?700:400}">${m.sujet||'(sans objet)'}</div>
      <div class="msg-prev">${(m.contenu||'').substring(0,60)}</div>
    </div>`;
  }).join('');
}

async function openMsg(id) {
  await fetch('/api/messages/'+id+'/lire', {method:'PUT', headers:{'Authorization':'Bearer '+ADMIN_TOKEN}}).catch(()=>{});
  const list = msgMode==='recu' ? msgData.received : msgData.sent;
  const m = list.find(x => x.id === id);
  if (!m) return;
  const el = document.getElementById('msg-detail-pane');
  el.innerHTML = `
    <div style="max-width:620px">
      <h2 style="font-family:var(--mono);font-size:14px;font-weight:700;color:var(--text);margin-bottom:14px">${m.sujet||'(sans objet)'}</h2>
      <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--s2);border:1px solid var(--border2);border-radius:7px;margin-bottom:20px">
        <div style="width:32px;height:32px;border-radius:50%;background:rgba(0,207,255,.1);display:flex;align-items:center;justify-content:center;font-size:14px">🏥</div>
        <div style="flex:1">
          <div style="font-family:var(--mono);font-size:9px;font-weight:700;color:var(--cyan)">${msgMode==='recu'?m.expediteur_nom||m.expediteur:'Vous'}</div>
          <div style="font-family:var(--mono);font-size:8px;color:var(--muted)">${msgMode==='recu'?'De':'À'} · ${fmtDate(m.created_at)}</div>
        </div>
      </div>
      <div style="font-family:var(--body);font-size:13px;line-height:1.75;color:var(--text);white-space:pre-wrap">${(m.contenu||'').replace(/</g,'&lt;')}</div>
    </div>`;
  await loadMessages();
}

function openCompose() {
  ['compose-sujet','compose-body'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
  document.getElementById('modal-compose').classList.add('open');
}

async function sendMsg() {
  const dest    = document.getElementById('compose-dest')?.value || 'TOUS';
  const sujet   = document.getElementById('compose-sujet')?.value?.trim() || '';
  const contenu = document.getElementById('compose-body')?.value?.trim() || '';
  if (!contenu) { toast('Message vide', 'err'); return; }
  const r = await fetch('/api/messages', {
    method:'POST',
    headers:{'Authorization':'Bearer '+ADMIN_TOKEN, 'Content-Type':'application/json'},
    body: JSON.stringify({destinataire:dest, sujet, contenu, expediteur_nom:'Collecteur GHT'})
  });
  if (r.ok) { toast('Message envoyé ✓', 'ok'); closeModal('modal-compose'); msgSwitch('envoyes', document.getElementById('btn-envoyes')); loadMessages(); }
  else toast('Erreur envoi', 'err');
}

// ── RELAIS UPSTREAM ──────────────────────────────────────────────────────────
async function loadRelays() {
  try {
    const r = await fetch('/api/admin/relay', {headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
    if (!r.ok) return;
    renderRelays(await r.json());
  } catch(e) {}
}
function renderRelays(relays) {
  const el = document.getElementById('relay-list');
  if (!el) return;
  if (!relays.length) { el.innerHTML = '<span style="font-family:var(--mono);font-size:8px;color:var(--muted)">Aucun relais configuré</span>'; return; }
  el.innerHTML = relays.map((r,i) => `<div style="padding:5px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:5px">
    <div style="width:6px;height:6px;border-radius:50%;background:${r.actif?'var(--green)':'var(--muted)'};flex-shrink:0"></div>
    <div style="flex:1;min-width:0"><div style="font-family:var(--mono);font-size:9px;color:var(--text);font-weight:700">${r.nom}</div>
    <div style="font-family:var(--mono);font-size:7px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.url}</div></div>
    <button onclick="toggleRelay(${i})" style="font-family:var(--mono);font-size:7px;padding:2px 5px;background:transparent;border:1px solid var(--border2);border-radius:3px;color:var(--muted);cursor:pointer">${r.actif?'⏸':'▶'}</button>
    <button onclick="testRelayIdx(${i})" style="font-family:var(--mono);font-size:7px;padding:2px 5px;background:transparent;border:1px solid var(--border2);border-radius:3px;color:var(--cyan);cursor:pointer">🔌</button>
    <button onclick="deleteRelay(${i})" style="font-family:var(--mono);font-size:7px;padding:2px 5px;background:transparent;border:1px solid rgba(255,45,85,.3);border-radius:3px;color:var(--red);cursor:pointer">✕</button>
  </div>`).join('');
}
async function registerArcAlpinTokens() {
  const r = await fetch('/api/admin/tokens/arc-alpin', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + ADMIN_TOKEN}
  });
  const d = await r.json().catch(()=>({}));
  if (r.ok) {
    const msg = d.added?.length > 0
      ? `✓ ${d.added.length} token(s) ajouté(s) : ${d.added.join(', ')} — total: ${d.total}`
      : `✓ Tokens déjà présents (total: ${d.total})`;
    toast(msg, 'ok');
    fetchAll();
  } else toast('Erreur : ' + (d.detail||r.status), 'err');
}

function openAddRelay() {
  ['relay-nom','relay-url','relay-token'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='';});
  document.getElementById('modal-add-relay').classList.add('open');
}
async function doAddRelay() {
  const nom=document.getElementById('relay-nom')?.value?.trim();
  const url=document.getElementById('relay-url')?.value?.trim();
  const token=document.getElementById('relay-token')?.value?.trim();
  if(!nom||!url||!token){toast('Tous les champs requis','err');return;}
  const r=await fetch('/api/admin/relay',{method:'POST',headers:{'Authorization':'Bearer '+ADMIN_TOKEN,'Content-Type':'application/json'},body:JSON.stringify({nom,url,token,actif:true})});
  const d=await r.json().catch(()=>({}));
  if(r.ok){toast('Relais configuré : '+nom,'ok');closeModal('modal-add-relay');loadRelays();}
  else toast(d.detail||'Erreur','err');
}
async function toggleRelay(idx) {
  const r=await fetch(`/api/admin/relay/${idx}/toggle`,{method:'PUT',headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
  const d=await r.json().catch(()=>({}));
  if(r.ok){toast(d.message,'ok');loadRelays();}
}
async function testRelayIdx(idx) {
  const r=await fetch(`/api/admin/relay/${idx}/test`,{method:'POST',headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
  const d=await r.json().catch(()=>({}));
  toast(d.ok?`✓ ${d.nom} joignable (${d.status})`:`✗ ${d.nom} : ${d.error||d.status}`,d.ok?'ok':'err');
}
async function deleteRelay(idx) {
  if(!confirm('Supprimer ce relais ?'))return;
  const r=await fetch(`/api/admin/relay/${idx}`,{method:'DELETE',headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
  if(r.ok){toast('Relais supprimé','ok');loadRelays();}
}

// ── INIT ─────────────────────────────────────────────────────
document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('click', e => { if(e.target===m) m.classList.remove('open'); }));
fetchAll();
setInterval(fetchAll, 30000);

// ── CHAT COLLECTEUR ─────────────────────────────────────────
var _chatCollSalon = null;
var _chatCollLastId = 0;
var _chatCollTimer = null;

async function loadChatColl() {
  var tok = localStorage.getItem('coll_session') || '';
  var r = await fetch('api/chat/salons', {headers: {Authorization: 'Bearer ' + tok}}).catch(function(){return null;});
  if (!r || !r.ok) return;
  var salons = await r.json();
  var box = document.getElementById('chat-coll-salons');
  if (box) {
    box.innerHTML = '';
    salons.forEach(function(s) {
      var btn = document.createElement('button');
      btn.textContent = '#' + s;
      btn.style.cssText = 'font-family:var(--mono);font-size:9px;padding:4px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:4px;cursor:pointer;margin:2px';
      btn.onclick = function() { openChatCollSalon(s); };
      box.appendChild(btn);
    });
    if (salons.length && !_chatCollSalon) openChatCollSalon(salons[0]);
  }
}


async function openChatCollSalon(nom) {
  _chatCollSalon = nom;
  _chatCollLastId = 0;
  if (_chatCollTimer) clearInterval(_chatCollTimer);
  // Mettre en évidence le salon actif
  var box = document.getElementById('chat-coll-salons');
  if (box) {
    box.querySelectorAll('button').forEach(function(btn) {
      btn.style.background = btn.textContent.trim() === ('#' + nom) ? 'rgba(0,49,137,.2)' : 'var(--surface2)';
      btn.style.borderColor = btn.textContent.trim() === ('#' + nom) ? '#003189' : 'var(--border)';
      btn.style.color = btn.textContent.trim() === ('#' + nom) ? '#003189' : '';
      btn.style.fontWeight = btn.textContent.trim() === ('#' + nom) ? '700' : '';
    });
  }
  // Vider le feed
  var feed = document.getElementById('chat-coll-feed');
  if (feed) feed.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);text-align:center;padding:20px">Chargement...</div>';
  document.getElementById('chat-coll-count').textContent = 'salon: #' + nom;
  fetchChatCollMessages();
  _chatCollTimer = setInterval(fetchChatCollMessages, 3000);
}

async function fetchChatCollMessages() {
  if (!_chatCollSalon) return;
  const r = await fetch('api/chat/messages?salon_nom=' + encodeURIComponent(_chatCollSalon) + '&since_id=' + _chatCollLastId,
    {headers: {Authorization: 'Bearer ' + (localStorage.getItem('coll_session') || '')}}).catch(()=>null);
  if (!r || !r.ok) return;
  const msgs = await r.json();
  const feed = document.getElementById('chat-coll-feed');
  if (!feed) return;
  if (!msgs.length) {
    if (_chatCollLastId === 0) {
      feed.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted);text-align:center;padding:30px;opacity:.6">Aucun message dans #' + _chatCollSalon + '</div>';
    }
    return;
  }
  if (_chatCollLastId === 0) feed.innerHTML = '';
  msgs.forEach(m => {
    if (m.id > _chatCollLastId) _chatCollLastId = m.id;
    const ts = m.horodatage ? new Date(m.horodatage.endsWith('Z') ? m.horodatage : m.horodatage + 'Z').toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}) : '';
    const div = document.createElement('div');
    div.style.cssText = 'padding:6px 10px;background:var(--surface2);border-radius:6px;border-left:3px solid #7c3aed';
    div.innerHTML = '<div style="font-family:var(--mono);font-size:9px;color:#7c3aed;margin-bottom:2px">' +
      (m.auteur_nom || '') + ' <span style="color:var(--muted)">' + ts + '</span></div>' +
      '<div style="font-size:12px">' + m.contenu.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</div>';
    feed.appendChild(div);
  });
  feed.scrollTop = feed.scrollHeight;
  document.getElementById('chat-coll-count').textContent = 'salon: #' + _chatCollSalon;
}

// ── GESTION COMPTES ────────────────────────────────────────
async function loadComptes() {
  var tok = localStorage.getItem('coll_session') || '';
  var r = await fetch('api/ui/users', {headers: {Authorization: 'Bearer ' + tok}}).catch(function(){return null;});
  if (!r || !r.ok) return;
  var users = await r.json();
  var list = document.getElementById('comptes-list');
  if (!list) return;
  list.innerHTML = '';
  if (!users.length) {
    list.innerHTML = '<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Aucun compte</div>';
    return;
  }
  users.forEach(function(u) {
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)';
    var badge = u.role === 'admin' ? 'rgba(0,49,137,.15)' : 'rgba(100,116,139,.15)';
    var html = '<span style="font-family:var(--mono);font-size:11px;flex:1">' + u.login + '</span>' +
      '<span style="font-family:var(--mono);font-size:9px;padding:2px 8px;background:' + badge + ';border-radius:10px">' + u.role + '</span>' +
      '<button style="font-family:var(--mono);font-size:9px;padding:3px 8px;background:none;border:1px solid var(--border);border-radius:4px;cursor:pointer">Changer mdp</button>';
    if (u.login !== 'supervision') {
      html += '<button style="font-family:var(--mono);font-size:9px;padding:3px 8px;background:rgba(239,68,68,.1);border:1px solid #ef4444;border-radius:4px;cursor:pointer;color:#ef4444">Supprimer</button>';
    }
    row.innerHTML = html;
    var btns = row.querySelectorAll('button');
    btns[0].onclick = function() { changePass(u.login); };
    if (btns[1]) btns[1].onclick = function() { deleteCompte(u.login); };
    list.appendChild(row);
  });
}


async function createCompte() {
  const login = document.getElementById('new-login').value.trim();
  const pass = document.getElementById('new-pass').value.trim();
  const role = document.getElementById('new-role').value;
  if (!login || !pass) { alert('Login et mot de passe requis'); return; }
  const r = await fetch('api/ui/users', {
    method: 'POST', headers: {Authorization:'Bearer '+localStorage.getItem('coll_session') || '','Content-Type':'application/json'},
    body: JSON.stringify({login, password: pass, role})
  }).catch(()=>null);
  if (r && r.ok) {
    document.getElementById('new-login').value = '';
    document.getElementById('new-pass').value = '';
    loadComptes();
  } else { alert('Erreur création'); }
}

async function deleteCompte(login) {
  if (!confirm('Supprimer le compte ' + login + ' ?')) return;
  const r = await fetch('api/ui/users/' + login, {
    method: 'DELETE', headers: {Authorization: 'Bearer ' + (localStorage.getItem('coll_session') || '')}
  }).catch(()=>null);
  if (r && r.ok) loadComptes();
}

async function changePass(login) {
  const np = prompt('Nouveau mot de passe pour ' + login + ' :');
  if (!np) return;
  const r = await fetch('api/ui/change-password', {
    method: 'POST', headers: {Authorization:'Bearer '+localStorage.getItem('coll_session') || '','Content-Type':'application/json'},
    body: JSON.stringify({login, new_password: np})
  }).catch(()=>null);
  if (r && r.ok) alert('Mot de passe modifié');
  else alert('Erreur');
}

</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html = DASHBOARD_HTML.replace("PLACEHOLDER_ADMIN_TOKEN", ADMIN_TOKEN)
    return HTMLResponse(content=html, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache", "Expires": "0"
    })


@app.get("/static/logo-scribe.png")
async def serve_logo():
    from fastapi.responses import FileResponse
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "static", "logo-scribe.png")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Logo non trouvé")

@app.get("/favicon.ico")
@app.get("/static/favicon.svg")
async def serve_favicon():
    """Favicon SVG SCRIBE — identique aux instances SCRIBE."""
    from fastapi.responses import FileResponse, Response
    import os
    # Chercher favicon.svg (identique aux instances SCRIBE)
    svg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "static", "favicon.svg")
    if os.path.exists(svg):
        return FileResponse(svg, media_type="image/svg+xml")
    # Fallback : logo PNG
    png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "static", "logo-scribe.png")
    if os.path.exists(png):
        return FileResponse(png, media_type="image/png")
    return Response(status_code=404)

CHAT_COLL_HTML = '<!DOCTYPE html>\n<html lang="fr">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>SCRIBE Chat</title>\n<style>\n:root{\n  --blue:#003189;--red:#e1000f;--bg:#f0f2f5;--s:#fff;--s2:#f1f5f9;\n  --bd:#e2e8f0;--tx:#0f172a;--mu:#64748b;--mo:monospace;\n  --online:#22c55e;--mention:#f97316;\n}\n*{box-sizing:border-box;margin:0;padding:0}\nhtml,body{height:100%;overflow:hidden;font-family:system-ui,sans-serif;background:var(--bg);color:var(--tx)}\n\n/* ── Layout ── */\n#chat-root{display:flex;height:100%;overflow:hidden}\n\n/* ── Colonne salons ── */\n#col-salons{\n  width:240px;flex-shrink:0;background:#1e2a3a;color:#e2e8f0;\n  display:flex;flex-direction:column;overflow:hidden;\n  transition:width .2s;\n}\n#col-salons.collapsed{width:0;overflow:hidden}\n#salon-header{\n  padding:14px 12px 10px;border-bottom:1px solid rgba(255,255,255,.1);flex-shrink:0;\n  display:flex;align-items:center;justify-content:space-between;\n}\n#salon-header h2{font-family:var(--mo);font-size:11px;font-weight:700;letter-spacing:1px;opacity:.7}\n#btn-new-salon{\n  width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.15);\n  border:none;color:#fff;cursor:pointer;font-size:16px;line-height:1;\n  display:flex;align-items:center;justify-content:center;\n}\n#btn-new-salon:hover{background:rgba(255,255,255,.25)}\n#salon-list{flex:1;overflow-y:auto;padding:8px 0}\n.salon-section-title{\n  font-family:var(--mo);font-size:8px;letter-spacing:2px;color:rgba(255,255,255,.4);\n  padding:10px 12px 4px;text-transform:uppercase;\n}\n.salon-item{\n  display:flex;align-items:center;gap:8px;padding:7px 12px;cursor:pointer;\n  border-radius:5px;margin:1px 6px;transition:background .1s;\n}\n.salon-item:hover{background:rgba(255,255,255,.08)}\n.salon-item.active{background:rgba(255,255,255,.15)}\n.salon-icon{font-size:14px;flex-shrink:0;width:20px;text-align:center}\n.salon-name{font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\n.salon-badge{\n  background:#e1000f;color:#fff;font-family:var(--mo);font-size:9px;\n  padding:1px 5px;border-radius:10px;min-width:18px;text-align:center;\n}\n.salon-ght-dot{\n  width:6px;height:6px;border-radius:50%;background:#7c3aed;flex-shrink:0;\n}\n\n/* ── Colonne présence ── */\n#col-presence{\n  width:200px;flex-shrink:0;background:var(--s);border-left:1px solid var(--bd);\n  display:flex;flex-direction:column;overflow:hidden;\n}\n#col-presence.hidden{display:none}\n#presence-header{\n  padding:12px;border-bottom:1px solid var(--bd);font-family:var(--mo);\n  font-size:9px;font-weight:700;letter-spacing:1px;color:var(--mu);\n  display:flex;align-items:center;justify-content:space-between;\n}\n#presence-list{flex:1;overflow-y:auto;padding:8px 0}\n.presence-etab{\n  font-family:var(--mo);font-size:8px;letter-spacing:1px;color:var(--mu);\n  padding:8px 12px 4px;text-transform:uppercase;\n}\n.presence-user{\n  display:flex;align-items:center;gap:8px;padding:5px 12px;font-size:11px;\n}\n.presence-dot{\n  width:8px;height:8px;border-radius:50%;background:var(--online);flex-shrink:0;\n}\n.presence-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}\n\n/* ── Zone centrale ── */\n#col-main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}\n\n#chat-topbar{\n  padding:10px 14px;border-bottom:1px solid var(--bd);background:var(--s);\n  display:flex;align-items:center;gap:10px;flex-shrink:0;\n}\n#btn-toggle-salons{\n  background:none;border:none;cursor:pointer;font-size:18px;color:var(--mu);padding:2px 6px;\n  border-radius:4px;display:none;\n}\n#chat-salon-title{font-size:14px;font-weight:700;flex:1}\n#chat-salon-desc{font-family:var(--mo);font-size:9px;color:var(--mu)}\n.topbar-btn{\n  font-family:var(--mo);font-size:9px;padding:4px 10px;border-radius:4px;\n  border:1px solid var(--bd);background:var(--s2);cursor:pointer;color:var(--mu);\n  display:flex;align-items:center;gap:5px;\n}\n.topbar-btn:hover{background:var(--s);color:var(--tx)}\n\n/* ── Fil messages ── */\n#msg-feed{\n  flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:4px;\n  background:var(--bg);\n}\n.msg-group{margin-bottom:12px}\n.msg-author-line{\n  display:flex;align-items:baseline;gap:8px;margin-bottom:3px;padding-left:4px;\n}\n.msg-author{font-size:12px;font-weight:700;color:var(--blue)}\n.msg-author.ght{color:#7c3aed}\n.msg-time{font-family:var(--mo);font-size:9px;color:var(--mu)}\n.msg-bubble{\n  background:var(--s);border-radius:0 8px 8px 8px;padding:8px 12px;\n  font-size:13px;line-height:1.5;max-width:100%;word-break:break-word;\n  box-shadow:0 1px 2px rgba(0,0,0,.06);\n}\n.msg-bubble.own{background:#dbeafe;border-radius:8px 0 8px 8px}\n.msg-bubble.ght{background:#ede9fe}\n.msg-bubble.supprime{opacity:.5;font-style:italic}\n.msg-mention{color:var(--mention);font-weight:700}\n.msg-reply-preview{\n  background:rgba(0,0,0,.05);border-left:3px solid var(--mu);\n  padding:4px 8px;border-radius:0 4px 4px 0;margin-bottom:6px;\n  font-size:11px;color:var(--mu);cursor:pointer;\n}\n.msg-reply-preview strong{color:var(--tx);display:block;font-size:10px;margin-bottom:2px}\n.msg-pj{\n  display:flex;align-items:center;gap:8px;margin-top:6px;\n  padding:6px 10px;background:var(--s2);border-radius:6px;\n  font-size:11px;cursor:pointer;\n}\n.msg-pj:hover{background:var(--bd)}\n.msg-pj-icon{font-size:16px}\n.msg-actions{\n  display:none;gap:4px;margin-left:4px;\n}\n.msg-group:hover .msg-actions{display:flex}\n.msg-action-btn{\n  font-size:11px;padding:2px 6px;background:var(--s2);border:1px solid var(--bd);\n  border-radius:4px;cursor:pointer;color:var(--mu);\n}\n.msg-action-btn:hover{background:var(--s);color:var(--tx)}\n.msg-row{display:flex;align-items:flex-start;gap:6px}\n.msg-row .msg-bubble{flex:1}\n\n/* ── Barre saisie ── */\n#input-zone{\n  padding:12px 14px;border-top:1px solid var(--bd);background:var(--s);flex-shrink:0;\n}\n#reply-bar{\n  display:none;background:var(--s2);border-left:3px solid var(--blue);\n  padding:5px 10px;border-radius:0 4px 4px 0;margin-bottom:8px;\n  font-size:11px;color:var(--mu);\n}\n#reply-bar strong{color:var(--tx);font-size:10px}\n#reply-cancel{\n  float:right;background:none;border:none;cursor:pointer;color:var(--mu);font-size:14px;\n}\n#autocomplete-box{\n  display:none;background:var(--s);border:1px solid var(--bd);border-radius:6px;\n  box-shadow:0 4px 16px rgba(0,0,0,.1);max-height:180px;overflow-y:auto;\n  margin-bottom:6px;\n}\n.autocomplete-item{\n  padding:7px 12px;cursor:pointer;font-size:12px;display:flex;align-items:center;gap:8px;\n}\n.autocomplete-item:hover{background:var(--s2)}\n.autocomplete-item.selected{background:#dbeafe}\n#input-row{display:flex;gap:8px;align-items:flex-end}\n#msg-input{\n  flex:1;font-family:var(--mono,monospace);font-size:13px;padding:8px 12px;\n  border:1px solid var(--bd);border-radius:20px;resize:none;max-height:120px;\n  background:var(--s2);color:var(--tx);outline:none;line-height:1.4;\n}\n#msg-input:focus{border-color:var(--blue);background:var(--s)}\n#btn-pj{\n  width:36px;height:36px;border-radius:50%;background:var(--s2);border:1px solid var(--bd);\n  cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;\n  flex-shrink:0;\n}\n#btn-pj:hover{background:var(--s)}\n#btn-send{\n  width:36px;height:36px;border-radius:50%;background:var(--blue);border:none;\n  color:#fff;cursor:pointer;font-size:16px;display:flex;align-items:center;\n  justify-content:center;flex-shrink:0;\n}\n#btn-send:hover{opacity:.85}\n#pj-input{display:none}\n\n/* ── Modal nouveau salon ── */\n#modal-salon{\n  display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;\n  align-items:center;justify-content:center;\n}\n.modal-box{\n  background:var(--s);border-radius:10px;width:420px;max-width:95vw;overflow:hidden;\n}\n.modal-hdr{\n  padding:16px 20px;border-bottom:1px solid var(--bd);display:flex;\n  align-items:center;justify-content:space-between;\n}\n.modal-hdr h3{font-family:var(--mo);font-size:11px;font-weight:700}\n.modal-close{background:none;border:none;cursor:pointer;font-size:18px;color:var(--mu)}\n.modal-body{padding:20px;display:flex;flex-direction:column;gap:12px}\n.mff{display:flex;flex-direction:column;gap:4px}\n.mff label{font-family:var(--mo);font-size:9px;color:var(--mu);text-transform:uppercase}\n.mff input,.mff select,.mff textarea{\n  font-family:var(--mo);font-size:11px;padding:7px 10px;\n  background:var(--s2);border:1px solid var(--bd);border-radius:5px;color:var(--tx);\n}\n.color-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}\n.color-dot{\n  width:26px;height:26px;border-radius:50%;cursor:pointer;\n  border:3px solid transparent;transition:border-color .1s;\n}\n.color-dot.sel{border-color:var(--tx)}\n.modal-footer{\n  padding:12px 20px;border-top:1px solid var(--bd);display:flex;justify-content:flex-end;gap:8px;\n}\n.btn-primary{\n  font-family:var(--mo);font-size:10px;padding:7px 16px;background:var(--blue);\n  color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:700;\n}\n.btn-secondary{\n  font-family:var(--mo);font-size:10px;padding:7px 16px;background:var(--s2);\n  color:var(--mu);border:1px solid var(--bd);border-radius:5px;cursor:pointer;\n}\n\n.msg-pj-img img {\n  max-width:300px;max-height:200px;border-radius:6px;\n  cursor:pointer;display:block;margin-top:4px;\n}\n/* ── Toast ── */\n#toast{\n  position:fixed;bottom:16px;right:16px;font-family:var(--mo);font-size:11px;\n  padding:8px 14px;border-radius:5px;display:none;z-index:99999;\n}\n#toast.ok{background:#dcfce7;color:#15803d;border:1px solid #86efac}\n#toast.err{background:#fee2e2;color:#dc2626;border:1px solid #fca5a5}\n\n/* ── Responsive mobile ── */\n@media(max-width:640px){\n  #col-presence{display:none}\n  #col-salons{position:absolute;z-index:100;height:100%;left:-240px;transition:left .2s}\n  #col-salons.mobile-open{left:0}\n  #btn-toggle-salons{display:flex !important}\n  #chat-root{position:relative}\n}\n@media(max-width:900px){\n  #col-presence{width:160px}\n}\n</style>\n</head>\n<body>\n<div id="chat-root">\n\n  <!-- Salons -->\n  <div id="col-salons">\n    <div id="salon-header">\n      <h2>SALONS</h2>\n      <button id="btn-new-salon" onclick="chat_openNewSalon()" title="Nouveau salon">+</button>\n    </div>\n    <div id="salon-list">\n      <div style="font-family:monospace;font-size:10px;color:rgba(255,255,255,.4);padding:20px;text-align:center">Chargement...</div>\n    </div>\n  </div>\n\n  <!-- Zone principale -->\n  <div id="col-main">\n    <div id="chat-topbar">\n      <button id="btn-toggle-salons" onclick="chat_toggleSalons()" title="Salons">&#9776;</button>\n      <div style="flex:1">\n        <div id="chat-salon-title">Sélectionnez un salon</div>\n        <div id="chat-salon-desc"></div>\n      </div>\n      <button class="topbar-btn" onclick="chat_openPresence()" title="Personnes connectées">\n        <span id="presence-count">0</span> en ligne\n      </button>\n      <button class="topbar-btn" onclick="chat_popout()" title="Ouvrir dans une fenêtre">&#x26F6;</button>\n    </div>\n\n    <div id="msg-feed">\n      <div style="font-family:monospace;font-size:10px;color:var(--mu);text-align:center;padding:40px">\n        Sélectionnez un salon pour commencer\n      </div>\n    </div>\n\n    <div id="input-zone">\n      <div id="pending-pjs" style="display:none;flex-wrap:wrap;gap:6px;padding:6px 0;margin-bottom:6px;overflow-x:auto"></div>\n      <div id="reply-bar">\n        <button id="reply-cancel" onclick="chat_cancelReply()">&#x2715;</button>\n        <strong id="reply-author"></strong>\n        <span id="reply-preview"></span>\n      </div>\n      <div id="autocomplete-box"></div>\n      <div style="display:flex;gap:4px;margin-bottom:4px;flex-wrap:wrap;align-items:center">\n        <button onclick="chat_toggleEmoji()" title="Emojis" id="btn-emoji" style="font-size:14px;padding:2px 7px;background:var(--s2);border:1px solid var(--bd);border-radius:4px;cursor:pointer">&#128512;</button>\n        <button onclick="chat_fmt(\'**\',\'**\')" title="Gras" style="font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 7px;background:var(--s2);border:1px solid var(--bd);border-radius:4px;cursor:pointer">B</button>\n        <button onclick="chat_fmt(\'_\',\'_\')" title="Italique" style="font-family:var(--mono);font-size:10px;font-style:italic;padding:2px 7px;background:var(--s2);border:1px solid var(--bd);border-radius:4px;cursor:pointer">I</button>\n        <button onclick="chat_fmt(\'[rouge]\',\'[/rouge]\')" title="Rouge" style="font-size:10px;padding:2px 7px;background:rgba(239,68,68,.15);border:1px solid #ef4444;border-radius:4px;cursor:pointer;color:#ef4444;font-weight:700">&#9679;</button>\n        <button onclick="chat_fmt(\'[vert]\',\'[/vert]\')" title="Vert" style="font-size:10px;padding:2px 7px;background:rgba(34,197,94,.15);border:1px solid #22c55e;border-radius:4px;cursor:pointer;color:#22c55e;font-weight:700">&#9679;</button>\n        <button onclick="chat_fmt(\'[orange]\',\'[/orange]\')" title="Orange" style="font-size:10px;padding:2px 7px;background:rgba(249,115,22,.15);border:1px solid #f97316;border-radius:4px;cursor:pointer;color:#f97316;font-weight:700">&#9679;</button>\n        <button onclick="chat_fmt(\'[code]\',\'[/code]\')" title="Code [code]...[/code]" style="font-family:monospace;font-size:10px;padding:2px 7px;background:var(--s2);border:1px solid var(--bd);border-radius:4px;cursor:pointer">&lt;&gt;</button>\n        <button onclick="chat_fmt(\'---URGENT---\',\'---\')" title="Urgent" style="font-family:var(--mono);font-size:9px;padding:2px 7px;background:rgba(239,68,68,.15);border:1px solid #ef4444;border-radius:4px;cursor:pointer;color:#ef4444;font-weight:700">&#128680; URGENT</button>\n      </div>\n      <div id="emoji-picker" style="display:none;flex-wrap:wrap;gap:4px;padding:8px;background:var(--s);border:1px solid var(--bd);border-radius:8px;margin-bottom:6px;max-height:120px;overflow-y:auto;font-size:18px"><span onclick="chat_insertEmoji(\'😀\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😀</span><span onclick="chat_insertEmoji(\'😊\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😊</span><span onclick="chat_insertEmoji(\'😅\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😅</span><span onclick="chat_insertEmoji(\'😂\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😂</span><span onclick="chat_insertEmoji(\'🤣\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🤣</span><span onclick="chat_insertEmoji(\'😍\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😍</span><span onclick="chat_insertEmoji(\'🥰\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🥰</span><span onclick="chat_insertEmoji(\'😎\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😎</span><span onclick="chat_insertEmoji(\'🤔\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🤔</span><span onclick="chat_insertEmoji(\'😮\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😮</span><span onclick="chat_insertEmoji(\'😱\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😱</span><span onclick="chat_insertEmoji(\'😭\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😭</span><span onclick="chat_insertEmoji(\'😡\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">😡</span><span onclick="chat_insertEmoji(\'🤒\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🤒</span><span onclick="chat_insertEmoji(\'👍\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">👍</span><span onclick="chat_insertEmoji(\'👎\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">👎</span><span onclick="chat_insertEmoji(\'👋\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">👋</span><span onclick="chat_insertEmoji(\'🙏\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🙏</span><span onclick="chat_insertEmoji(\'💪\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">💪</span><span onclick="chat_insertEmoji(\'✅\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">✅</span><span onclick="chat_insertEmoji(\'❌\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">❌</span><span onclick="chat_insertEmoji(\'⚠️\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">⚠️</span><span onclick="chat_insertEmoji(\'🚨\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🚨</span><span onclick="chat_insertEmoji(\'🏥\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🏥</span><span onclick="chat_insertEmoji(\'🚑\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🚑</span><span onclick="chat_insertEmoji(\'💉\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">💉</span><span onclick="chat_insertEmoji(\'🩺\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🩺</span><span onclick="chat_insertEmoji(\'📋\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">📋</span><span onclick="chat_insertEmoji(\'📞\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">📞</span><span onclick="chat_insertEmoji(\'🔴\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🔴</span><span onclick="chat_insertEmoji(\'🟠\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🟠</span><span onclick="chat_insertEmoji(\'🟡\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🟡</span><span onclick="chat_insertEmoji(\'🟢\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🟢</span><span onclick="chat_insertEmoji(\'🔵\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🔵</span><span onclick="chat_insertEmoji(\'⭐\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">⭐</span><span onclick="chat_insertEmoji(\'🔥\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🔥</span><span onclick="chat_insertEmoji(\'💡\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">💡</span><span onclick="chat_insertEmoji(\'📢\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">📢</span><span onclick="chat_insertEmoji(\'🔔\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🔔</span><span onclick="chat_insertEmoji(\'🕐\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">🕐</span><span onclick="chat_insertEmoji(\'📍\')" style="cursor:pointer;padding:2px 3px;border-radius:3px" onmouseover="this.style.background=\'var(--s2)\'" onmouseout="this.style.background=\'\'">📍</span></div>\n      <div id="input-row">\n        <textarea id="msg-input" rows="1" placeholder="Message... (@mention)"\n          oninput="chat_onInput(this)" onkeydown="chat_onKeydown(event)"></textarea>\n        <input type="file" id="pj-input" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.txt,.csv,.png,.jpg,.jpeg,.gif,.webp" onchange="chat_uploadPJ(this)">\n        <button id="btn-pj" onclick="document.getElementById(\'pj-input\').click()" title="Piece jointe">&#128206;</button>\n        <button id="btn-send" onclick="chat_send()" title="Envoyer">&#10148;</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- Présence -->\n  <div id="col-presence">\n    <div id="presence-header">\n      CONNECTES\n      <button style="background:none;border:none;cursor:pointer;font-size:14px;color:var(--mu)" onclick="chat_closePresence()">&#x2715;</button>\n    </div>\n    <div id="presence-list"></div>\n  </div>\n\n</div>\n\n<!-- Modal nouveau salon -->\n<div id="modal-salon">\n  <div class="modal-box">\n    <div class="modal-hdr">\n      <h3>NOUVEAU SALON</h3>\n      <button class="modal-close" onclick="chat_closeNewSalon()">&#x2715;</button>\n    </div>\n    <div class="modal-body">\n      <div class="mff">\n        <label>Nom du salon *</label>\n        <input type="text" id="ns-nom" placeholder="ex: pharmacie-urgence">\n      </div>\n      <div class="mff">\n        <label>Description</label>\n        <input type="text" id="ns-desc" placeholder="À quoi sert ce salon ?">\n      </div>\n      <div class="mff">\n        <label>Type</label>\n        <select id="ns-type">\n          <option value="local">Local (cet établissement uniquement)</option>\n          <option value="territorial">Territorial (visible par tous les GHTs)</option>\n        </select>\n      </div>\n      <div class="mff">\n        <label>Couleur</label>\n        <div class="color-row" id="color-row">\n          <div class="color-dot sel" data-c="#003189" style="background:#003189" onclick="chat_selColor(this)"></div>\n          <div class="color-dot" data-c="#16a34a" style="background:#16a34a" onclick="chat_selColor(this)"></div>\n          <div class="color-dot" data-c="#d97706" style="background:#d97706" onclick="chat_selColor(this)"></div>\n          <div class="color-dot" data-c="#7c3aed" style="background:#7c3aed" onclick="chat_selColor(this)"></div>\n          <div class="color-dot" data-c="#dc2626" style="background:#dc2626" onclick="chat_selColor(this)"></div>\n          <div class="color-dot" data-c="#0891b2" style="background:#0891b2" onclick="chat_selColor(this)"></div>\n        </div>\n        <input type="hidden" id="ns-color" value="#003189">\n      </div>\n      <div class="mff">\n        <label>Icone (emoji)</label>\n        <input type="text" id="ns-icon" value="💬" maxlength="2" style="width:60px">\n      </div>\n    </div>\n    <div class="modal-footer">\n      <button class="btn-secondary" onclick="chat_closeNewSalon()">Annuler</button>\n      <button class="btn-primary" onclick="chat_createSalon()">Créer le salon</button>\n    </div>\n  </div>\n</div>\n\n<div id="toast"></div>\n\n<script>\nvar _tok = function() {\n  try {\n    var params = new URLSearchParams(window.location.search);\n    var t = params.get("token");\n    if (t) return t;\n    try { t = window.parent.localStorage.getItem("scribe_token"); if (t) return t; } catch(e2) {}\n    return localStorage.getItem("scribe_token") || "";\n  } catch(e) { return ""; }\n};\nvar _api = function(url, opts) {\n  opts = opts || {};\n  opts.headers = opts.headers || {};\n  opts.headers["Authorization"] = "Bearer " + _tok();\n  if (opts.body && !opts.headers["Content-Type"]) {\n    opts.headers["Content-Type"] = "application/json";\n  }\n  return fetch(url, opts);\n};\n\nvar _toast = function(msg, type) {\n  var el = document.getElementById("toast");\n  el.textContent = msg;\n  el.className = type || "ok";\n  el.style.display = "block";\n  clearTimeout(el._t);\n  el._t = setTimeout(function() { el.style.display = "none"; }, 3000);\n};\n\nvar _esc = function(s) {\n  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");\n};\n\n// ── État global ──────────────────────────────────────────────────────────────\nvar _salons = [];\nvar _pjMap = {};     // id → nom fichier\nvar _msgMap = {};    // msgKey → message objet\nvar _pendingPJs = []; // [{id, nom, taille, ext, dataUrl}] — PJs pré-uploadées\nvar _fedBase = "";      // URL base du collecteur\nvar _fedToken = "";     // token fédération\nvar _chatSyncIds = {};  // salon_nom → dernier id collecteur vu\nvar _syncReady = false; // collecteur configuré\nvar _mysigle = "";   // sigle de l\'instance locale\nvar _currentSalon = null;\nvar _messages = [];\nvar _presence = {};\nvar _replyTo = null;\nvar _autocompleteUsers = [];\nvar _autocompleteIdx = -1;\nvar _lastMsgId = 0;\nvar _pollTimer = null;\nvar _pingTimer = null;\nvar _newColor = "#003189";\nvar _myUserId = null;\n\n// ── Init ─────────────────────────────────────────────────────────────────────\nfunction chat_init() {\n  chat_loadPresence();\n  chat_loadSalons();\n  _pingTimer = setInterval(chat_ping, 30000);\n  chat_ping();\n  // Charger la config fédération pour la sync chat inter-GHT\n  _api("/api/coll/fed-status").then(function(r) {\n    return r.ok ? r.json() : null;\n  }).then(function(fed) {\n    if (fed && fed.ready && fed.collecteur_url) {\n      _fedBase = fed.collecteur_url.replace("/api/push", "");\n      _fedToken = fed.token || "";\n      _syncReady = true;\n      // Démarrer la sync toutes les 3 secondes\n      setInterval(chat_syncCollecteur, 3000);\n      // Présence inter-GHT toutes les 30 secondes\n      setInterval(chat_pushPresence, 30000);\n      chat_pushPresence();\n    }\n  }).catch(function(){});\n\n  // Vérifier que le token est disponible\n  if (!_tok()) {\n    var list = document.getElementById("salon-list");\n    if (list) list.innerHTML = "<div style=\'color:#f87171;font-size:10px;padding:12px;font-family:monospace\'>Token absent — rechargez la page SCRIBE</div>";\n    console.error("SCRIBE Chat: token JWT manquant");\n    return;\n  }\n\n  // Charger les utilisateurs pour l\'autocomplétion\n  _api("/api/coll/users").then(function(r) {\n    return r.ok ? r.json() : [];\n  }).then(function(users) {\n    _autocompleteUsers = users;\n  }).catch(function(){});\n  // Récupérer l\'utilisateur courant et le sigle local\n  _api("/api/coll/me").then(function(r) {\n    return r.ok ? r.json() : null;\n  }).then(function(u) {\n    if (u) _myUserId = u.id;\n  }).catch(function(){});\n  // Le sigle est dans /api/coll/fed-status → "etablissement"\n  _api("/api/coll/fed-status").then(function(r) {\n    return r.ok ? r.json() : null;\n  }).then(function(fed) {\n    if (fed && fed.etablissement) _mysigle = fed.etablissement || "";\n  }).catch(function(){});\n}\n\n// ── Salons ───────────────────────────────────────────────────────────────────\nfunction chat_loadSalons() {\n  var list = document.getElementById("salon-list");\n  _api("/api/chat/salons").then(function(r) {\n    if (!r.ok) {\n      if (list) list.innerHTML = "<div style=\'color:#f87171;font-size:10px;padding:12px;font-family:monospace\'>Erreur " + r.status + " — rechargement dans 5s</div>";\n      setTimeout(chat_loadSalons, 5000);\n      return [];\n    }\n    return r.json();\n  }).then(function(data) {\n    if (!data || !data.length) return;\n    _salons = data;\n    chat_renderSalons();\n    if (!_currentSalon && data.length > 0) {\n      chat_openSalon(data[0]);\n    }\n  }).catch(function(e) {\n    if (list) list.innerHTML = "<div style=\'color:#f87171;font-size:10px;padding:12px;font-family:monospace\'>Connexion impossible — rechargement dans 5s</div>";\n    setTimeout(chat_loadSalons, 5000);\n  });\n}\n\nfunction chat_renderSalons() {\n  var list = document.getElementById("salon-list");\n  var terr = _salons.filter(function(s) { return s.type === "territorial"; });\n  var local = _salons.filter(function(s) { return s.type === "local"; });\n\n  var html = "";\n  if (terr.length) {\n    html += "<div class=\'salon-section-title\'>&#127760; Territorial G7</div>";\n    html += terr.map(chat_renderSalonItem).join("");\n  }\n  if (local.length) {\n    html += "<div class=\'salon-section-title\'>&#127973; Mon établissement</div>";\n    html += local.map(chat_renderSalonItem).join("");\n  }\n  list.innerHTML = html;\n}\n\nfunction chat_renderSalonItem(s) {\n  var active = _currentSalon && _currentSalon.id === s.id ? " active" : "";\n  var col = s.couleur || "#7c3aed";\n  var ght = s.type === "territorial"\n    ? "<div class=\'salon-ght-dot\' style=\'background:" + col + "\'></div>"\n    : "";\n  var activeStyle = (active && s.couleur)\n    ? " style=\'border-left:3px solid " + col + ";background:rgba(0,0,0,.15)\'"\n    : "";\n  return "<div class=\'salon-item" + active + "\' data-salon-id=\'" + s.id + "\'" + activeStyle + " onclick=\'chat_openSalonById(" + s.id + ")\'>" +\n    "<span class=\'salon-icon\'>" + _esc(s.icone) + "</span>" +\n    "<span class=\'salon-name\' style=\'color:" + (active ? col : "") + "\'>#" + _esc(s.nom) + "</span>" +\n    ght +\n  "</div>";\n}\n\nfunction chat_openSalonById(id) {\n  var s = _salons.find(function(x) { return x.id === id; });\n  if (s) chat_openSalon(s);\n}\n\nfunction chat_openSalon(sJson) {\n  var s = typeof sJson === "string" ? JSON.parse(sJson) : sJson;\n  // Stopper le poll AVANT de changer de salon\n  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }\n  _currentSalon = s;\n  _lastMsgId = 0;\n  _messages = [];\n\n  document.getElementById("chat-salon-title").textContent = "#" + s.nom;\n  document.getElementById("chat-salon-desc").textContent = s.description || "";\n\n  // Vider le feed immédiatement pour feedback visuel\n  var feed = document.getElementById("msg-feed");\n  if (feed) feed.innerHTML = "<div style=\'font-family:monospace;font-size:10px;color:var(--mu);text-align:center;padding:40px\'>Chargement...</div>";\n\n  chat_renderSalons();\n  // Charger les messages puis relancer le poll\n  chat_loadMessages(true, function() {\n    _pollTimer = setInterval(chat_pollMessages, 3000);\n  });\n\n  // Sur mobile, fermer le panneau salons\n  if (window.innerWidth <= 640) {\n    document.getElementById("col-salons").classList.remove("mobile-open");\n  }\n}\n\n// ── Messages ─────────────────────────────────────────────────────────────────\nfunction chat_loadMessages(reset, callback) {\n  if (!_currentSalon) { if (callback) callback(); return; }\n  var url = "/api/chat/salons/" + _currentSalon.id + "/messages?limit=50";\n  _api(url).then(function(r) {\n    return r.ok ? r.json() : [];\n  }).then(function(data) {\n    if (reset) {\n      _messages = data;\n      chat_renderMessages(true);\n    } else {\n      var newMsgs = data.filter(function(m) { return m.id > _lastMsgId; });\n      if (newMsgs.length) {\n        _messages = _messages.concat(newMsgs);\n        newMsgs.forEach(function(m) { chat_appendMessage(m); });\n      }\n    }\n    if (data.length) {\n      _lastMsgId = Math.max.apply(null, data.map(function(m) { return m.id; }));\n    }\n    if (callback) callback();\n  }).catch(function() { if (callback) callback(); });\n}\n\nfunction chat_pollMessages() {\n  if (!_currentSalon) return;\n  var url = "/api/chat/salons/" + _currentSalon.id + "/messages?limit=20";\n  _api(url).then(function(r) {\n    return r.ok ? r.json() : [];\n  }).then(function(data) {\n    var newMsgs = data.filter(function(m) { return m.id > _lastMsgId; });\n    if (newMsgs.length) {\n      newMsgs.forEach(function(m) {\n        _messages.push(m);\n        chat_appendMessage(m);\n      });\n      _lastMsgId = Math.max.apply(null, data.map(function(m) { return m.id; }));\n    }\n  }).catch(function(){});\n}\n\nfunction chat_renderMessages(scrollBottom) {\n  var feed = document.getElementById("msg-feed");\n  if (!_messages.length) {\n    feed.innerHTML = "<div style=\'font-family:monospace;font-size:10px;color:var(--mu);text-align:center;padding:40px\'>Aucun message — soyez le premier !</div>";\n    return;\n  }\n  feed.innerHTML = "";\n  _messages.forEach(function(m) { chat_appendMessage(m); });\n  if (scrollBottom) { feed.scrollTop = feed.scrollHeight; }\n}\n\nfunction chat_appendMessage(m) {\n  var feed = document.getElementById("msg-feed");\n  var isOwn = m.auteur_id && m.auteur_id === _myUserId;\n  var isGHT = m.origine === "ght";\n  var atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;\n\n  var replyHtml = "";\n  if (m.reply_to) {\n    var replyText = (m.reply_to.contenu || "").replace(/<[^>]+>/g,"").substring(0, 100);\n    replyHtml = "<div class=\'msg-reply-preview\' onclick=\'chat_scrollTo(" + m.reply_to.id + ")\' style=\'cursor:pointer\'>" +\n      "<strong style=\'display:block;margin-bottom:2px;color:var(--blue)\'>" + _esc(m.reply_to.auteur_nom) + "</strong>" +\n      "<span style=\'opacity:.8\'>" + _esc(replyText) + (replyText.length >= 100 ? "…" : "") + "</span>" +\n    "</div>";\n  }\n\n  // Formater le contenu avec mentions\n  var contenu = _esc(m.contenu);\n  // Mise en forme : gras, italique, couleurs, code, urgent\n  contenu = contenu\n    .replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>")\n    .replace(/_([^_]+)_/g, "<em>$1</em>")\n    .replace(/\\[code\\](.*?)\\[\\/code\\]/g, "<code style=\'background:rgba(0,0,0,.1);padding:1px 4px;border-radius:3px;font-family:monospace\'>$1</code>")\n    .replace(/\\[rouge\\](.*?)\\[\\/rouge\\]/g, "<span style=\'color:#ef4444;font-weight:600\'>$1</span>")\n    .replace(/\\[vert\\](.*?)\\[\\/vert\\]/g, "<span style=\'color:#22c55e;font-weight:600\'>$1</span>")\n    .replace(/\\[orange\\](.*?)\\[\\/orange\\]/g, "<span style=\'color:#f97316;font-weight:600\'>$1</span>")\n    .replace(/---URGENT---(.*?)---/g, "<span style=\'background:#ef4444;color:#fff;padding:2px 8px;border-radius:4px;font-weight:700\'>&#128680; URGENT $1</span>");\n  // URLs cliquables\n  contenu = contenu.replace(/(https?:\\/\\/[^\\s<>"]+)/g,\n    "<a href=\'$1\' target=\'_blank\' rel=\'noopener\' style=\'color:var(--blue);text-decoration:underline\'>$1</a>");\n  contenu = contenu.replace(/@([\\w\\-\\[\\]]+)/g, "<span class=\'msg-mention\'>@$1</span>");\n\n  var pjHtml = "";\n  if (m.pj && m.pj.length) {\n    pjHtml = m.pj.map(function(p) {\n      var ext = p.nom.split(".").pop().toUpperCase();\n      _pjMap[p.id] = p.nom;\n      var isImage = ["PNG","JPG","JPEG","GIF","WEBP","SVG"].indexOf(ext) >= 0;\n      // PJ inter-GHT (id commence par "ght-") → URL du collecteur\n      var isGhtPj = String(p.id).indexOf("ght-") === 0;\n      var pjUrl = isGhtPj\n        ? (_fedBase + "/api/chat/pj/" + p.id + "?token=" + _fedToken)\n        : ("/api/chat/pj/" + p.id + "?token=" + _tok());\n      if (isImage) {\n        return "<div class=\'msg-pj-img\' data-pj-id=\'" + p.id + "\'>" +\n          "<img src=\'" + pjUrl + "\' " +\n          "style=\'max-width:300px;max-height:200px;border-radius:6px;cursor:pointer;display:block;margin-top:4px\' " +\n          "onclick=\'chat_downloadPJExtUrl(" + JSON.stringify(pjUrl) + "," + JSON.stringify(p.nom) + ")\' " +\n          "onerror=\'this.remove()\' " +\n          "alt=\'" + _esc(p.nom) + "\'></div>";\n      }\n      return "<div class=\'msg-pj\' data-pj-id=\'" + p.id + "\' onclick=\'chat_downloadPJExtUrl(" + JSON.stringify(pjUrl) + "," + JSON.stringify(p.nom) + ")\'>" +\n        "<span class=\'msg-pj-icon\'>&#128206;</span>" +\n        "<span style=\'flex:1;font-size:11px\'>" + _esc(p.nom) + "</span>" +\n        "<span style=\'font-family:monospace;font-size:9px;color:var(--mu)\'>" + ext + " " + Math.round(p.taille/1024) + "Ko</span>" +\n      "</div>";\n    }).join("");\n  }\n\n  var bubbleClass = "msg-bubble" + (isOwn ? " own" : "") + (isGHT ? " ght" : "") + (m.supprime ? " supprime" : "");\n  var authorClass = "msg-author" + (isGHT ? " ght" : "");\n\n  var ts = "";\n  if (m.horodatage) {\n    try {\n      var tsStr = m.horodatage;\n      // Normaliser : ajouter Z si absent, remplacer espace par T\n      if (tsStr.indexOf("Z") < 0 && tsStr.indexOf("+") < 0) tsStr = tsStr.replace(" ", "T") + "Z";\n      var d = new Date(tsStr);\n      if (!isNaN(d.getTime())) {\n        ts = d.toLocaleTimeString("fr-FR", {hour:"2-digit",minute:"2-digit"});\n      }\n    } catch(e) {}\n  }\n\n  var actionsHtml = "";\n  if (!m.supprime) {\n    var msgKey = "mk_" + String(m.id).replace(/[^a-zA-Z0-9]/g, "_");\n    _msgMap[msgKey] = m;\n    actionsHtml = "<div class=\'msg-actions\'>" +\n      "<button class=\'msg-action-btn\' data-mkey=\'" + msgKey + "\' onclick=\'chat_replyToKey(this.dataset.mkey)\'>&#8617; R&eacute;pondre</button>";\n    if (isOwn) {\n      actionsHtml += "<button class=\'msg-action-btn\' style=\'color:#dc2626\' data-mkey=\'" + msgKey + "\' onclick=\'chat_deleteMsgKey(this.dataset.mkey)\'>Supprimer</button>";\n    }\n    actionsHtml += "</div>";\n  }\n\n  var div = document.createElement("div");\n  div.className = "msg-group";\n  div.id = "msg-" + m.id;\n  div.innerHTML = "<div class=\'msg-author-line\'>" +\n      "<span class=\'" + authorClass + "\'>" + _esc(m.auteur_nom) + "</span>" +\n      "<span class=\'msg-time\'>" + ts + (isGHT ? " &#127760;" : "") + "</span>" +\n      actionsHtml +\n    "</div>" +\n    "<div class=\'msg-row\'>" +\n      "<div class=\'" + bubbleClass + "\'>" +\n        replyHtml +\n        "<div>" + contenu + "</div>" +\n        pjHtml +\n      "</div>" +\n    "</div>";\n\n  feed.appendChild(div);\n  if (atBottom) { feed.scrollTop = feed.scrollHeight; }\n\n  // Notification si message mentionne l\'utilisateur courant\n  var myName = _autocompleteUsers && _autocompleteUsers.length\n    ? null : null; // On utilise display_name via presence\n  var myDisplay = "";\n  Object.values(_presence).forEach(function(arr) {\n    arr.forEach(function(u) { if (!myDisplay) myDisplay = u.display_name; });\n  });\n  var isMentioned = myDisplay && m.mentions && m.mentions.some(function(mn) {\n    return mn.toLowerCase() === myDisplay.toLowerCase();\n  });\n  if (isMentioned || (m.auteur_sigle && m.auteur_sigle !== (_mysigle || ""))) {\n    // Envoyer un event au parent (index.html) pour le badge\n    try {\n      window.parent.postMessage({type: "scribe-chat-new-msg", mentioned: isMentioned}, "*");\n    } catch(e) {}\n  }\n}\n\nfunction chat_scrollTo(msgId) {\n  var el = document.getElementById("msg-" + msgId);\n  if (el) { el.scrollIntoView({behavior:"smooth", block:"center"}); }\n}\n\n// ── Envoi ────────────────────────────────────────────────────────────────────\nfunction chat_send() {\n  if (!_currentSalon) { _toast("Sélectionnez un salon", "err"); return; }\n  var inp = document.getElementById("msg-input");\n  var contenu = inp.value.trim();\n  if (!contenu && !_pendingPJs.length) return; // Autoriser envoi si PJs\n\n  // Extraire les mentions\n  var mentions = [];\n  var re = /@([\\w\\-\\[\\]]+)/g;\n  var m;\n  while ((m = re.exec(contenu)) !== null) { mentions.push(m[1]); }\n\n  // Séparer les PJs inline (dataUrl) des PJs uploadées (id serveur)\n  var inlinePJs = _pendingPJs.filter(function(p) { return p.inline; });\n  var serverPJs = _pendingPJs.filter(function(p) { return !p.inline; });\n  var body = {\n    contenu: contenu,\n    mentions: mentions,\n    reply_to_id: (_replyTo && !isNaN(parseInt(_replyTo.id))) ? parseInt(_replyTo.id) : null,\n    pj_ids: serverPJs.map(function(p) { return p.id; }),\n    pj_inline: inlinePJs.map(function(p) {\n      return {nom: p.nom, taille: p.taille, dataUrl: p.dataUrl};\n    }),\n  };\n\n  _api("/api/chat/salons/" + _currentSalon.id + "/messages", {\n    method: "POST", body: JSON.stringify(body)\n  }).then(function(r) {\n    return r.ok ? r.json() : Promise.reject(r.status);\n  }).then(function(msg) {\n    inp.value = "";\n    inp.style.height = "auto";\n    chat_cancelReply();\n    // Si PJs → recharger le message depuis l\'API pour avoir les PJs à jour\n    if (msg.pj && msg.pj.length) {\n      _messages.push(msg);\n      if (msg.id > _lastMsgId) _lastMsgId = msg.id;\n      chat_appendMessage(msg);\n    } else {\n      _messages.push(msg);\n      if (msg.id > _lastMsgId) _lastMsgId = msg.id;\n      chat_appendMessage(msg);\n    }\n    document.getElementById("msg-feed").scrollTop = 9999999;\n    document.getElementById("autocomplete-box").style.display = "none";\n    // Sauvegarder les PJs avant vidage pour le push collecteur\n    var _pendingPJsSent = _pendingPJs.slice();\n    // Vider les PJs en attente\n    _pendingPJs = [];\n    chat_renderPendingPJs();\n    // Pousser vers le collecteur si salon territorial et sync active\n    if (_syncReady && _currentSalon && _currentSalon.type === "territorial") {\n      // NE PAS envoyer les images en base64 → trop lourd, cause CORS+500\n      // Envoyer uniquement les métadonnées avec URL directe vers cette instance\n      var srcOrigin = window.location.origin;\n      // URL directe vers chaque PJ sur cette instance (sans base64)\n      var pjsMeta = (msg.pj || []).map(function(p) {\n        var pjUrl = srcOrigin + "/api/chat/pj/" + p.id + "?token=" + _fedToken;\n        return {nom: p.nom, taille: p.taille, remote_url: pjUrl};\n      });\n      fetch(_fedBase + "/api/chat/messages", {\n        method: "POST",\n        headers: {Authorization: "Bearer " + _fedToken, "Content-Type": "application/json"},\n        body: JSON.stringify({\n          salon_nom:    _currentSalon.nom,\n          auteur_nom:   msg.auteur_nom,\n          auteur_sigle: msg.auteur_sigle,\n          contenu:      msg.contenu,\n          mentions:     msg.mentions || [],\n          pj_meta:      pjsMeta,\n        })\n      }).catch(function(){});\n   }\n  }).catch(function(e) {\n    _toast("Erreur envoi : " + e, "err");\n  });\n}\n\nfunction chat_onKeydown(e) {\n  var ac = document.getElementById("autocomplete-box");\n  var items = ac.querySelectorAll(".autocomplete-item");\n\n  if (ac.style.display !== "none" && items.length) {\n    if (e.key === "ArrowDown") {\n      e.preventDefault();\n      _autocompleteIdx = Math.min(_autocompleteIdx + 1, items.length - 1);\n      items.forEach(function(el, i) { el.classList.toggle("selected", i === _autocompleteIdx); });\n      return;\n    }\n    if (e.key === "ArrowUp") {\n      e.preventDefault();\n      _autocompleteIdx = Math.max(_autocompleteIdx - 1, 0);\n      items.forEach(function(el, i) { el.classList.toggle("selected", i === _autocompleteIdx); });\n      return;\n    }\n    if (e.key === "Tab" || e.key === "Enter") {\n      if (_autocompleteIdx >= 0 && items[_autocompleteIdx]) {\n        e.preventDefault();\n        items[_autocompleteIdx].click();\n        return;\n      }\n    }\n    if (e.key === "Escape") {\n      ac.style.display = "none";\n      return;\n    }\n  }\n\n  if (e.key === "Enter" && !e.shiftKey) {\n    e.preventDefault();\n    chat_send();\n  }\n}\n\nfunction chat_onInput(el) {\n  // Auto-resize\n  el.style.height = "auto";\n  el.style.height = Math.min(el.scrollHeight, 120) + "px";\n  // Autocomplétion @mention\n  var val = el.value;\n  var cursor = el.selectionStart;\n  var before = val.substring(0, cursor);\n  var atMatch = before.match(/@([\\w\\-]*)$/);\n  if (atMatch) {\n    var query = atMatch[1].toLowerCase();\n    chat_showAutocomplete(query, before.lastIndexOf("@"), cursor);\n  } else {\n    document.getElementById("autocomplete-box").style.display = "none";\n  }\n}\n\nfunction chat_showAutocomplete(query, atPos, cursor) {\n  var results = [];\n  var q = (query || "").toLowerCase();\n  // Uniquement les utilisateurs CONNECTES (présence locale + GHT)\n  var allConnected = {};\n  // Présence locale\n  Object.values(_presence).forEach(function(arr) {\n    arr.forEach(function(u) { allConnected[u.display_name] = {label: u.display_name, icon: "👤"}; });\n  });\n  // Présence inter-GHT\n  Object.values(_presenceGHT || {}).forEach(function(arr) {\n    arr.forEach(function(u) { allConnected[u.display_name] = {label: u.display_name, icon: "🌐"}; });\n  });\n  Object.values(allConnected).forEach(function(u) {\n    if (!q || u.label.toLowerCase().includes(q)) {\n      results.push({label: u.label, value: u.label, icon: u.icon});\n    }\n  });\n  // Établissements connectés\n  Object.keys(Object.assign({}, _presence, _presenceGHT || {})).forEach(function(s) {\n    if (!q || s.toLowerCase().includes(q)) {\n      results.push({label: s + " (établissement)", value: s, icon: "🏥"});\n    }\n  });\n\n  results = results.slice(0, 8);\n  var ac = document.getElementById("autocomplete-box");\n  if (!results.length) { ac.style.display = "none"; return; }\n\n  _autocompleteIdx = -1;\n  // Assigner aux variables GLOBALES (pas var → shadowing)\n  _acResults = results;\n  _acAtPos = atPos;\n  _acCursor = cursor;\n  ac.innerHTML = results.map(function(r, i) {\n    return "<div class=\'autocomplete-item\' data-ac-idx=\'" + i + "\' onclick=\'chat_pickMentionIdx(" + i + ")\'>" +\n      r.icon + " " + _esc(r.label) + "</div>";\n  }).join("");\n  ac.style.display = "block";\n}\n\nvar _acResults = [];\nvar _acAtPos = 0;\nvar _acCursor = 0;\n\nfunction chat_toggleEmoji() {\n  var p = document.getElementById("emoji-picker");\n  if (p) p.style.display = p.style.display === "none" ? "flex" : "none";\n}\n\nfunction chat_insertEmoji(e) {\n  var inp = document.getElementById("msg-input");\n  if (!inp) return;\n  var pos = inp.selectionStart || inp.value.length;\n  inp.value = inp.value.substring(0, pos) + e + inp.value.substring(pos);\n  inp.focus();\n  inp.selectionStart = inp.selectionEnd = pos + e.length;\n  inp.style.height = "auto";\n  inp.style.height = Math.min(inp.scrollHeight, 120) + "px";\n  document.getElementById("emoji-picker").style.display = "none";\n}\n\nfunction chat_fmt(before, after) {\n  var inp = document.getElementById("msg-input");\n  if (!inp) return;\n  var start = inp.selectionStart, end = inp.selectionEnd;\n  var sel = inp.value.substring(start, end) || "texte";\n  inp.value = inp.value.substring(0, start) + before + sel + after + inp.value.substring(end);\n  inp.focus();\n  inp.selectionStart = start + before.length;\n  inp.selectionEnd = start + before.length + sel.length;\n  inp.style.height = "auto";\n  inp.style.height = Math.min(inp.scrollHeight, 120) + "px";\n}\n\nfunction chat_pickMentionIdx(idx) {\n  var r = _acResults[idx];\n  if (r) chat_pickMention(r.value, _acAtPos, _acCursor);\n}\n\nfunction chat_pickMention(val, atPos, cursor) {\n  var inp = document.getElementById("msg-input");\n  var before = inp.value.substring(0, atPos);\n  var after = inp.value.substring(cursor);\n  inp.value = before + "@" + val + " " + after;\n  inp.focus();\n  document.getElementById("autocomplete-box").style.display = "none";\n  _autocompleteIdx = -1;\n}\n\n// ── Répondre ─────────────────────────────────────────────────────────────────\nfunction chat_replyToId(id) {\n  var m = _messages.find(function(x) { return String(x.id) === String(id); });\n  if (m) chat_replyTo(m);\n}\n\nfunction chat_replyToKey(key) {\n  var m = _msgMap[key];\n  if (m) chat_replyTo(m);\n}\n\nfunction chat_deleteMsgKey(key) {\n  var m = _msgMap[key];\n  if (!m) return;\n  if (String(m.id).indexOf("coll-") === 0) {\n    alert("Impossible de supprimer un message d un autre etablissement.");\n    return;\n  }\n  chat_deleteMsg(m.id);\n}\n\nfunction chat_replyTo(mJson) {\n  var m = typeof mJson === "string" ? JSON.parse(mJson) : mJson;\n  _replyTo = m;\n  var authorEl = document.getElementById("reply-author");\n  var previewEl = document.getElementById("reply-preview");\n  if (authorEl) authorEl.textContent = m.auteur_nom;\n  if (previewEl) {\n    var preview = (m.contenu || "").replace(/<[^>]+>/g, "").substring(0, 80);\n    previewEl.textContent = preview + (m.contenu && m.contenu.length > 80 ? "…" : "");\n  }\n  var bar = document.getElementById("reply-bar");\n  if (bar) bar.style.display = "block";\n  document.getElementById("msg-input").focus();\n}\n\nfunction chat_cancelReply() {\n  _replyTo = null;\n  document.getElementById("reply-bar").style.display = "none";\n  document.getElementById("reply-author").textContent = "";\n  document.getElementById("reply-preview").textContent = "";\n}\n\n// ── Supprimer message ─────────────────────────────────────────────────────────\nfunction chat_deleteMsg(msgId) {\n  if (!confirm("Supprimer ce message ?")) return;\n  _api("/api/chat/salons/" + _currentSalon.id + "/messages/" + msgId, {method:"DELETE"})\n    .then(function(r) {\n      if (r.ok) {\n        var el = document.getElementById("msg-" + msgId);\n        if (el) {\n          var bubble = el.querySelector(".msg-bubble");\n          if (bubble) { bubble.textContent = "_(message supprimé)_"; bubble.classList.add("supprime"); }\n        }\n      } else { _toast("Erreur suppression", "err"); }\n    });\n}\n\n// ── Pièces jointes ────────────────────────────────────────────────────────────\nfunction chat_uploadPJ(input) {\n  if (!_currentSalon) { _toast("Sélectionnez un salon", "err"); return; }\n  var files = Array.from(input.files || []);\n  if (!files.length) return;\n  input.value = "";\n\n  files.forEach(function(file) {\n    var reader = new FileReader();\n    reader.onload = function(e) {\n      var dataUrl = e.target.result;\n      var ext = (file.name.split(".").pop() || "").toUpperCase();\n      // Mode inline : stocker le dataUrl directement sans pré-upload\n      // (compatible collecteur ET instances SCRIBE avec images lourdes)\n      var fakePj = {\n        id: "inline-" + Date.now() + "-" + Math.random().toString(36).slice(2),\n        nom: file.name,\n        taille: file.size,\n        ext: ext,\n        dataUrl: dataUrl,\n        inline: true,\n      };\n      _pendingPJs.push(fakePj);\n      chat_renderPendingPJs();\n    };\n    reader.readAsDataURL(file);\n  });\n}\n\nfunction chat_renderPendingPJs() {\n  var zone = document.getElementById("pending-pjs");\n  if (!zone) return;\n  if (!_pendingPJs.length) { zone.style.display = "none"; zone.innerHTML = ""; return; }\n  zone.style.display = "flex";\n  zone.innerHTML = _pendingPJs.map(function(pj, i) {\n    var isImg = ["JPG","JPEG","PNG","GIF","WEBP","SVG"].indexOf((pj.ext||"").toUpperCase()) >= 0;\n    var preview = isImg\n      ? "<img src=\'" + pj.dataUrl + "\' style=\'height:60px;border-radius:4px;object-fit:cover\'>"\n      : "<span style=\'font-size:20px\'>&#128206;</span>";\n    return "<div style=\'position:relative;display:inline-flex;flex-direction:column;align-items:center;gap:2px;background:var(--s2);border:1px solid var(--bd);border-radius:6px;padding:6px 8px;font-size:10px;max-width:80px\'>" +\n      preview +\n      "<span style=\'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70px;font-family:monospace\'>" + _esc(pj.nom) + "</span>" +\n      "<button onclick=\'chat_removePendingPJ(" + i + ")\' style=\'position:absolute;top:-6px;right:-6px;width:16px;height:16px;border-radius:50%;background:#ef4444;color:#fff;border:none;cursor:pointer;font-size:10px;line-height:1;display:flex;align-items:center;justify-content:center\'>&#x2715;</button>" +\n    "</div>";\n  }).join("");\n}\n\nfunction chat_removePendingPJ(idx) {\n  _pendingPJs.splice(idx, 1);\n  chat_renderPendingPJs();\n}\n\nfunction chat_downloadPJExtUrl(url, nom) {\n  var a = document.createElement("a");\n  a.href = url;\n  a.download = nom || "fichier";\n  a.click();\n}\n\nfunction chat_downloadPJById(pjId) {\n  var nom = _pjMap[pjId] || "fichier";\n  chat_downloadPJ(pjId, nom);\n}\n\nfunction chat_downloadPJ(pjId, nom) {\n  var a = document.createElement("a");\n  a.href = "/api/chat/pj/" + pjId + "?token=" + _tok();\n  a.download = nom;\n  a.click();\n}\n\n// ── Présence ─────────────────────────────────────────────────────────────────\nfunction chat_ping() {\n  _api("/api/chat/presence/ping", {method:"POST"}).catch(function(){});\n}\n\nfunction chat_loadPresence() {\n  _api("/api/chat/presence").then(function(r) {\n    return r.ok ? r.json() : {};\n  }).then(function(data) {\n    _presence = data;\n    chat_renderPresenceMerged();\n  }).catch(function(){});\n  setTimeout(chat_loadPresence, 15000);\n  // Aussi pinger la présence locale\n  chat_ping();\n}\n\nfunction chat_renderPresence() {\n  var list = document.getElementById("presence-list");\n  var html = "";\n  Object.entries(_presence).sort().forEach(function(entry) {\n    var sigle = entry[0], users = entry[1];\n    html += "<div class=\'presence-etab\'>" + _esc(sigle) + " (" + users.length + ")</div>";\n    users.forEach(function(u) {\n      html += "<div class=\'presence-user\'><div class=\'presence-dot\'></div><div class=\'presence-name\'>" + _esc(u.display_name) + "</div></div>";\n    });\n  });\n  list.innerHTML = html || "<div style=\'font-family:monospace;font-size:10px;color:var(--mu);padding:16px;text-align:center\'>Aucun utilisateur connecté</div>";\n}\n\nfunction chat_openPresence() {\n  var col = document.getElementById("col-presence");\n  col.classList.toggle("hidden");\n}\n\nfunction chat_closePresence() {\n  document.getElementById("col-presence").classList.add("hidden");\n}\n\n// ── Nouveau salon ─────────────────────────────────────────────────────────────\nfunction chat_openNewSalon() {\n  document.getElementById("modal-salon").style.display = "flex";\n  document.getElementById("ns-nom").value = "";\n  document.getElementById("ns-desc").value = "";\n  document.getElementById("ns-type").value = "local";\n  document.getElementById("ns-icon").value = "💬";\n  document.getElementById("ns-color").value = "#003189";\n  document.querySelectorAll(".color-dot").forEach(function(d) { d.classList.remove("sel"); });\n  var first = document.querySelector(".color-dot");\n  if (first) first.classList.add("sel");\n}\n\nfunction chat_closeNewSalon() {\n  document.getElementById("modal-salon").style.display = "none";\n}\n\nfunction chat_selColor(el) {\n  document.querySelectorAll(".color-dot").forEach(function(d) { d.classList.remove("sel"); });\n  el.classList.add("sel");\n  document.getElementById("ns-color").value = el.dataset.c;\n  _newColor = el.dataset.c;\n}\n\nfunction chat_createSalon() {\n  var nom = document.getElementById("ns-nom").value.trim();\n  if (!nom) { _toast("Nom requis", "err"); return; }\n  var type = document.getElementById("ns-type").value;\n  var body = {\n    nom: nom,\n    description: document.getElementById("ns-desc").value.trim() || null,\n    type: type,\n    couleur: document.getElementById("ns-color").value,\n    icone: document.getElementById("ns-icon").value || "💬"\n  };\n  _api("/api/chat/salons", {method:"POST", body:JSON.stringify(body)})\n    .then(function(r) { return r.ok ? r.json() : Promise.reject(r.status); })\n    .then(function(s) {\n      _toast("Salon #" + s.nom + " créé !", "ok");\n      chat_closeNewSalon();\n      // Si salon territorial : pousser vers le collecteur (qu\'il soit syncReady ou pas)\n      if (type === "territorial") {\n        // Récupérer l\'URL du collecteur depuis fed-status\n        _api("/api/coll/fed-status").then(function(fr) {\n          return fr.ok ? fr.json() : null;\n        }).then(function(fed) {\n          if (fed && fed.collecteur_url) {\n            var fedBase = fed.collecteur_url.replace("/api/push", "");\n            var fedToken = fed.token || "";\n            fetch(fedBase + "/api/chat/salons", {\n              method: "POST",\n              headers: {Authorization: "Bearer " + fedToken, "Content-Type": "application/json"},\n              body: JSON.stringify({nom: s.nom})\n            }).catch(function(){});\n          }\n        }).catch(function(){});\n      }\n      chat_loadSalons();\n    }).catch(function(e) { _toast("Erreur création : " + e, "err"); });\n}\n\n// ── Mobile ────────────────────────────────────────────────────────────────────\nfunction chat_toggleSalons() {\n  document.getElementById("col-salons").classList.toggle("mobile-open");\n}\n\n// ── Popout ────────────────────────────────────────────────────────────────────\nfunction chat_popout() {\n  var token = _tok();\n  var salon = _currentSalon ? "&salon=" + _currentSalon.id : "";\n  window.open("/api/chat/ui/popout?token=" + encodeURIComponent(token) + salon, "_blank",\n    "width=900,height=700,menubar=no,toolbar=no,scrollbars=yes");\n}\n\n// ── Exposer dans window ───────────────────────────────────────────────────────\n\n// ── Sync inter-GHT via collecteur ─────────────────────────────────────────\nfunction chat_syncCollecteur() {\n  if (!_syncReady) return;\n  // Sync des salons territoriaux du collecteur\n  fetch(_fedBase + "/api/chat/salons", {\n    headers: {Authorization: "Bearer " + _fedToken}\n  }).then(function(r) { return r.ok ? r.json() : []; })\n  .then(function(collSalons) {\n    collSalons.forEach(function(cs) {\n      // Si salon territorial pas encore local → le créer\n      var exists = _salons.some(function(s) { return s.nom === cs.nom && s.type === "territorial"; });\n      if (!exists && cs.nom) {\n        _api("/api/chat/salons", {\n          method: "POST",\n          body: JSON.stringify({nom: cs.nom, type: "territorial", icone: cs.icone || "💬",\n                                couleur: cs.couleur || "#7c3aed", description: cs.description || ""})\n        }).then(function(r) {\n          if (r.ok) chat_loadSalons();\n        }).catch(function(){});\n      }\n    });\n  }).catch(function(){});\n  if (!_currentSalon) return;\n  var salonNom = _currentSalon.nom;\n  var sinceId = _chatSyncIds[salonNom] || 0;\n\n  // 1. Pull : récupérer les nouveaux messages du collecteur\n  fetch(_fedBase + "/api/chat/messages?salon_nom=" + encodeURIComponent(salonNom) + "&since_id=" + sinceId, {\n    headers: {Authorization: "Bearer " + _fedToken}\n  }).then(function(r) {\n    return r.ok ? r.json() : [];\n  }).then(function(msgs) {\n    msgs.forEach(function(m) {\n      // Ignorer nos propres messages (déjà dans le feed)\n      var sigleLocal = _mysigle || "";\n      if (m.auteur_sigle === sigleLocal) return;\n      // Vérifier si déjà affiché\n      if (document.getElementById("msg-coll-" + m.id)) return;\n      // Créer un pseudo-message au format local\n      var pseudo = {\n        id:           "coll-" + m.id,\n        salon_id:     _currentSalon ? _currentSalon.id : 0,\n        auteur_id:    null,\n        auteur_nom:   m.auteur_nom,\n        auteur_sigle: m.auteur_sigle,\n        contenu:      m.contenu,\n        mentions:     m.mentions || [],\n        reply_to:     null,\n        horodatage:   m.horodatage,\n        supprime:     false,\n        origine:      "ght",\n        pj:           m.pj || [],\n      };\n      _messages.push(pseudo);\n      chat_appendMessage(pseudo);\n      if (m.id > (_chatSyncIds[salonNom] || 0)) {\n        _chatSyncIds[salonNom] = m.id;\n      }\n    });\n  }).catch(function(){});\n\n  // 2. Pull présence inter-GHT\n  fetch(_fedBase + "/api/chat/presence", {\n    headers: {Authorization: "Bearer " + _fedToken}\n  }).then(function(r) {\n    return r.ok ? r.json() : {};\n  }).then(function(data) {\n    // Merger avec la présence locale\n    _presenceGHT = data;\n    chat_renderPresenceMerged();\n  }).catch(function(){});\n}\n\nvar _presenceGHT = {};\n\nfunction chat_pushPresence() {\n  if (!_syncReady) return;\n  // Pousser la présence locale vers le collecteur\n  var users = Object.values(_presence).reduce(function(acc, arr) {\n    return acc.concat(arr);\n  }, []);\n  if (!users.length) return;\n  fetch(_fedBase + "/api/chat/presence", {\n    method: "POST",\n    headers: {Authorization: "Bearer " + _fedToken, "Content-Type": "application/json"},\n    body: JSON.stringify({users: users})\n  }).catch(function(){});\n}\n\nfunction chat_renderPresenceMerged() {\n  // Fusionner présence locale + GHT\n  var merged = {};\n  // Locale\n  Object.entries(_presence).forEach(function(e) {\n    merged[e[0]] = (merged[e[0]] || []).concat(e[1]);\n  });\n  // GHT (autres établissements)\n  Object.entries(_presenceGHT).forEach(function(e) {\n    var sigle = e[0];\n    var users = e[1];\n    // Éviter les doublons avec le sigle local\n    var sigleLocal = _mysigle || "";\n    if (sigle === sigleLocal) return; // déjà dans la présence locale\n    merged[sigle] = (merged[sigle] || []).concat(users);\n  });\n\n  var list = document.getElementById("presence-list");\n  if (!list) return;\n  var total = 0;\n  var html = "";\n  Object.keys(merged).sort().forEach(function(sigle) {\n    var users = merged[sigle];\n    if (!users.length) return;\n    total += users.length;\n    html += "<div class=\'presence-etab\'>" + sigle + " (" + users.length + ")</div>";\n    users.forEach(function(u) {\n      html += "<div class=\'presence-user\'><div class=\'presence-dot\'></div><div class=\'presence-name\'>" + _esc(u.display_name) + "</div></div>";\n    });\n  });\n  list.innerHTML = html || "<div style=\'font-family:monospace;font-size:10px;color:var(--mu);padding:16px;text-align:center\'>Aucun utilisateur connecté</div>";\n  var el = document.getElementById("presence-count");\n  if (el) el.textContent = total;\n}\n\nwindow.chat_init            = chat_init;\nwindow.chat_openSalonById   = chat_openSalonById;\nwindow.chat_openSalon       = chat_openSalon;\nwindow.chat_send            = chat_send;\nwindow.chat_onInput         = chat_onInput;\nwindow.chat_onKeydown       = chat_onKeydown;\nwindow.chat_pickMention     = chat_pickMention;\nwindow.chat_replyToId       = chat_replyToId;\nwindow.chat_replyToKey      = chat_replyToKey;\nwindow.chat_deleteMsgKey    = chat_deleteMsgKey;\nwindow.chat_toggleEmoji     = chat_toggleEmoji;\nwindow.chat_insertEmoji     = chat_insertEmoji;\nwindow.chat_fmt             = chat_fmt;\nwindow.chat_pickMentionIdx  = chat_pickMentionIdx;\nwindow.chat_replyTo         = chat_replyTo;\nwindow.chat_cancelReply     = chat_cancelReply;\nwindow.chat_deleteMsg       = chat_deleteMsg;\nwindow.chat_uploadPJ        = chat_uploadPJ;\nwindow.chat_downloadPJExtUrl = chat_downloadPJExtUrl;\nwindow.chat_downloadPJById  = chat_downloadPJById;\nwindow.chat_removePendingPJ = chat_removePendingPJ;\nwindow.chat_renderPendingPJs = chat_renderPendingPJs;\nwindow.chat_downloadPJ      = chat_downloadPJ;\nwindow.chat_scrollTo        = chat_scrollTo;\nwindow.chat_openNewSalon    = chat_openNewSalon;\nwindow.chat_closeNewSalon   = chat_closeNewSalon;\nwindow.chat_selColor        = chat_selColor;\nwindow.chat_createSalon     = chat_createSalon;\nwindow.chat_toggleSalons    = chat_toggleSalons;\nwindow.chat_popout          = chat_popout;\nwindow.chat_syncCollecteur  = chat_syncCollecteur;\nwindow.chat_pushPresence    = chat_pushPresence;\nwindow.chat_openPresence    = chat_openPresence;\nwindow.chat_closePresence   = chat_closePresence;\n\nwindow.addEventListener("load", chat_init);\n</script>\n</body>\n</html>'

@app.get("/chat/ui", response_class=HTMLResponse)
async def chat_ui_coll(token: str = "", credentials=Depends(security)):
    """Sert le chat pour la supervision. Vérifie la session et injecte l'ADMIN_TOKEN."""
    # Vérifier que l'appelant est authentifié (session UI ou admin)
    # Accepter le token ADMIN_TOKEN OU un token de session valide
    # Si ui_sessions est vide (redémarrage), accepter quand même si token fourni
    # (la page supervisor est déjà derrière auth)
    ok = False
    tok_to_check = token or (credentials.credentials if credentials else "")
    if tok_to_check == ADMIN_TOKEN:
        ok = True
    elif tok_to_check in ui_sessions:
        ok = True
    elif tok_to_check:
        # Token fourni mais session expirée → accepter quand même
        # (l'utilisateur est déjà dans l'interface supervisor)
        ok = True
    if not ok:
        raise HTTPException(401, "Aucun token fourni")
    # Injecter l'ADMIN_TOKEN pour que le chat puisse appeler les routes /api/chat/*
    import html as _h
    tok_inject = (
        "<script>"
        "window._COLL_TOKEN=" + repr(ADMIN_TOKEN) + ";"
        "</script>"
    )
    patched = CHAT_COLL_HTML.replace(
        "var _tok = function() {",
        "var _tok = function() { try { if(window._COLL_TOKEN) return window._COLL_TOKEN; } catch(e){} "
    )
    return HTMLResponse(tok_inject + patched)

@app.get("/api/coll/me")
async def coll_me(credentials=Depends(security)):
    if not credentials: raise HTTPException(401)
    tok = credentials.credentials
    # Accepter ADMIN_TOKEN → retourner utilisateur supervision
    if tok == ADMIN_TOKEN:
        return {"id": 0, "username": "supervision", "display_name": "Supervision", "role": "admin"}
    sess = ui_sessions.get(tok, {})
    if not sess: raise HTTPException(401)
    return {"id": 0, "username": sess.get("login","supervision"),
            "display_name": sess.get("login","Supervision").capitalize(), "role": sess.get("role","viewer")}

@app.get("/api/coll/users")
async def coll_users(credentials=Depends(security)):
    if not _check_any_auth(credentials): raise HTTPException(401)
    auth = load_ui_auth()
    return [{"id": i, "username": u["login"], "display_name": u["login"].capitalize(), "active": True}
            for i, u in enumerate(auth.get("users", []))]

@app.get("/api/coll/fed-status")
async def coll_fed_status(credentials=Depends(security)):
    if not _check_any_auth(credentials): raise HTTPException(401)
    return {"ready": False, "enabled": False, "etablissement": "SUPERVISION"}

@app.post("/api/chat/presence/ping")
async def chat_presence_ping(request: Request, credentials=Depends(security)):
    """Ping de présence pour le chat — accepte tokens établissements ET JWT SCRIBE."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    tok = credentials.credentials if credentials else ""
    # Token établissement enregistré
    sigle = tokens.get(tok)
    if sigle:
        display = body.get("display_name", sigle)
        uid = body.get("user_id", 0)
    else:
        # JWT SCRIBE ou token admin → supervision
        if tok == ADMIN_TOKEN:
            sigle = "SUPERVISION"
            display = "Supervision"
            uid = 0
        elif tok in ui_sessions:
            sigle = "SUPERVISION"
            sess = ui_sessions[tok]
            display = sess.get("login", "supervision").capitalize()
            uid = abs(hash(tok)) % 100000
        else:
            # Token JWT SCRIBE d'une instance non enregistrée → accepter quand même
            # Extraire le sigle du body si disponible
            sigle = body.get("sigle", "INCONNU")
            display = body.get("display_name", sigle)
            uid = body.get("user_id", 0)
    if not sigle:
        return {"ok": True}  # Silencieux si pas de sigle
    now = datetime.now(timezone.utc).isoformat()
    existing = chat_presence.get(sigle, [])
    existing = [u for u in existing if u.get("user_id") != uid]
    existing.append({"user_id": uid, "display_name": display, "last_seen": now})
    chat_presence[sigle] = existing
    return {"ok": True}

@app.get("/api/chat/pj/{pj_id}")
async def serve_chat_pj(pj_id: str, token: str = "", credentials=Depends(security)):
    """Sert une PJ stockée dans le collecteur (inter-GHT)."""
    tok = credentials.credentials if credentials else token
    if not _check_any_auth(credentials) and not (token and (token == ADMIN_TOKEN or token in ui_sessions)):
        raise HTTPException(401)
    pj = chat_pj_store.get(str(pj_id))
    if not pj:
        raise HTTPException(404, "PJ non trouvée")
    # Cas 1 : URL distante → redirect vers l'instance source
    if pj.get("remote_url"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=pj["remote_url"], status_code=302)
    # Cas 2 : dataUrl base64
    data_url = pj.get("dataUrl", "")
    if not data_url:
        raise HTTPException(404, "Données PJ manquantes")
    if "," in data_url:
        header, b64 = data_url.split(",", 1)
        mime = header.split(":")[1].split(";")[0] if ":" in header else "application/octet-stream"
    else:
        b64 = data_url
        mime = "application/octet-stream"
    import base64
    from fastapi.responses import Response as FResponse
    content = base64.b64decode(b64)
    return FResponse(content=content, media_type=mime,
                     headers={"Content-Disposition": f"inline; filename={pj['nom']}"})

@app.get("/api/chat/salons/{salon_id}/messages")
async def get_salon_messages_by_id(
    salon_id: int,
    limit: int = 50,
    credentials=Depends(security)
):
    """Récupère les messages d'un salon par ID (compatibilité chat.html)."""
    if not _check_any_auth(credentials):
        raise HTTPException(401)
    # Mapper l'ID vers le nom du salon
    salon_list = list(chat_messages.keys())
    idx = salon_id - 1  # IDs 1-based
    if idx < 0 or idx >= len(salon_list):
        raise HTTPException(404, f"Salon {salon_id} non trouvé")
    salon_nom = salon_list[idx]
    msgs = chat_messages.get(salon_nom, [])
    return msgs[-limit:]

@app.post("/api/chat/salons/{salon_id}/messages")
async def post_salon_message_by_id(
    salon_id: int,
    request: Request,
    credentials=Depends(security)
):
    """Poste un message dans un salon par ID (depuis le chat de supervision)."""
    global _chat_msg_counter
    if not _check_any_auth(credentials):
        raise HTTPException(401)
    # Mapper l'ID vers le nom
    salon_list = list(chat_messages.keys())
    idx = salon_id - 1
    if idx < 0 or idx >= len(salon_list):
        raise HTTPException(404, f"Salon {salon_id} non trouvé")
    salon_nom = salon_list[idx]
    body = await request.json()
    # Déterminer l'auteur depuis la session
    tok = credentials.credentials if credentials else ""
    if tok == ADMIN_TOKEN:
        auteur_nom = "Supervision"
    else:
        sess = ui_sessions.get(tok, {})
        auteur_nom = sess.get("login", "Supervision").capitalize()
    now = datetime.now(timezone.utc).isoformat()
    _chat_msg_counter += 1
    msg = {
        "id":           _chat_msg_counter,
        "salon_nom":    salon_nom,
        "auteur_nom":   auteur_nom,
        "auteur_sigle": "SUPERVISION",
        "contenu":      body.get("contenu", ""),
        "mentions":     body.get("mentions", []),
        "reply_to_id":  body.get("reply_to_id"),
        "reply_to":     None,
        "horodatage":   now,
        "origine":      "ght",
        "pj":           [],
        "supprime":     False,
    }
    if salon_nom not in chat_messages:
        chat_messages[salon_nom] = []
    chat_messages[salon_nom].append(msg)
    return msg

@app.get("/health")
def health():
    return {"status": "ok", "etablissements": len(etablissements),
            "tokens": len(tokens), "pending": len(pending)}


@app.get("/debug")
def debug():
    """Diagnostic — tokens, données, état complet."""
    return {
        "tokens_count":       len(tokens),
        "tokens_sigles":      list(tokens.values()),
        "etablissements":     list(etablissements.keys()),
        "pending_count":      len(pending),
        "pending_sigles":     [v.get("sigle_propose","?") for v in pending.values()],
        "data_file":          str(Path(DATA_FILE).resolve()),
        "tokens_file":        str(Path(TOKENS_FILE).resolve()),
        "tokens_file_exists": Path(TOKENS_FILE).exists(),
        "data_file_exists":   Path(DATA_FILE).exists(),
    }


# ── Auth interface web (optionnelle) ─────────────────────────────────────
UI_AUTH_FILE = "collecteur_ui_auth.json"

def load_ui_auth() -> dict:
    """Charge la config login UI depuis le fichier JSON si présent."""
    if Path(UI_AUTH_FILE).exists():
        try:
            return json.loads(Path(UI_AUTH_FILE).read_text())
        except Exception:
            pass
    # Login par défaut si pas de fichier
    import hashlib
    return {
        "login": "supervision",
        "password_hash": hashlib.sha256("Scribe2026!".encode()).hexdigest(),
        "users": [{"login": "supervision", "role": "admin", "password_hash": "0a0da7eef0453b6cbd142fcf25f7ac63081c9cb920cba999c1a3a80d1f25dfda"}]
    }

def check_ui_credentials(login: str, password: str) -> bool:
    """Vérifie login/mot de passe de l'interface web."""
    auth = load_ui_auth()
    if not auth:
        return True
    import hashlib
    h = hashlib.sha256(password.encode()).hexdigest()
    # Vérifier dans la liste users si elle existe
    users = auth.get("users", [])
    if users:
        return any(u.get("login") == login and u.get("password_hash") == h for u in users)
    # Fallback legacy
    return auth.get("login") == login and auth.get("password_hash") == h




# ════════════════════════════════════════════════════════════════════════════
# GESTION COMPTES SUPERVISION
# ════════════════════════════════════════════════════════════════════════════

def save_ui_auth(auth: dict):
    Path(UI_AUTH_FILE).write_text(json.dumps(auth, ensure_ascii=False, indent=2))

@app.get("/api/ui/users")
async def list_ui_users(credentials=Depends(security)):
    """Liste les comptes de l'interface web."""
    if not require_ui_admin(credentials):
        raise HTTPException(401)
    auth = load_ui_auth()
    users = auth.get("users", [{"login": auth.get("login","supervision"), "role":"admin"}])
    return [{"login": u["login"], "role": u.get("role","viewer")} for u in users]

@app.post("/api/ui/users")
async def create_ui_user(request: Request, credentials=Depends(security)):
    """Crée un compte supervision."""
    if not require_ui_admin(credentials):
        raise HTTPException(401)
    body = await request.json()
    login = body.get("login","").strip()
    password = body.get("password","").strip()
    role = body.get("role","viewer")
    if not login or not password:
        raise HTTPException(400, "Login et mot de passe requis")
    auth = load_ui_auth()
    users = auth.get("users", [{"login": auth.get("login","supervision"), "role":"admin",
                                "password_hash": auth.get("password_hash","")}])
    if any(u["login"] == login for u in users):
        raise HTTPException(409, "Login déjà utilisé")
    import hashlib
    users.append({"login": login, "role": role,
                  "password_hash": hashlib.sha256(password.encode()).hexdigest()})
    auth["users"] = users
    save_ui_auth(auth)
    return {"ok": True}

@app.delete("/api/ui/users/{login}")
async def delete_ui_user(login: str, credentials=Depends(security)):
    """Supprime un compte supervision."""
    if not require_ui_admin(credentials):
        raise HTTPException(401)
    auth = load_ui_auth()
    users = auth.get("users", [])
    auth["users"] = [u for u in users if u["login"] != login]
    save_ui_auth(auth)
    return {"ok": True}

@app.post("/api/ui/change-password")
async def change_ui_password(request: Request, credentials=Depends(security)):
    """Change le mot de passe d'un compte supervision."""
    if not require_ui_admin(credentials):
        raise HTTPException(401)
    body = await request.json()
    login = body.get("login","").strip()
    new_pass = body.get("new_password","").strip()
    if not login or not new_pass:
        raise HTTPException(400, "Login et nouveau mot de passe requis")
    auth = load_ui_auth()
    import hashlib
    h = hashlib.sha256(new_pass.encode()).hexdigest()
    users = auth.get("users", [{"login": auth.get("login",""), "role":"admin",
                                "password_hash": auth.get("password_hash","")}])
    for u in users:
        if u["login"] == login:
            u["password_hash"] = h
            break
    else:
        raise HTTPException(404, "Utilisateur introuvable")
    auth["users"] = users
    # Compatibilité legacy
    if auth.get("login") == login:
        auth["password_hash"] = h
    save_ui_auth(auth)
    return {"ok": True}

@app.post("/api/ui/login")
async def ui_login(request: Request):
    """Authentification interface web du collecteur."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "JSON invalide")
    login = body.get("login","")
    password = body.get("password","")
    auth = load_ui_auth()
    if not auth:
        return {"ok": True, "token": "no-auth"}  # Pas de protection
    if check_ui_credentials(login, password):
        session_token = secrets.token_hex(16)
        # Stocker la session en mémoire
        auth_info = load_ui_auth()
        users = auth_info.get("users", [])
        role = next((u.get("role","viewer") for u in users if u.get("login")==login), "viewer")
        ui_sessions[session_token] = {"login": login, "role": role}
        return {"ok": True, "token": session_token}
    raise HTTPException(status_code=401, detail="Identifiants invalides")


@app.get("/api/ui/auth-required")
def auth_required():
    """Indique si l'interface nécessite une authentification."""
    auth = load_ui_auth()
    return {"required": bool(auth), "login": auth.get("login","") if auth else ""}

@app.get("/api/ui/verify")
def verify_session(credentials=Depends(security)):
    """Vérifie qu'un token de session est toujours valide."""
    if not credentials:
        raise HTTPException(401)
    tok = credentials.credentials
    if tok == ADMIN_TOKEN or tok in ui_sessions:
        sess = ui_sessions.get(tok, {"login": "admin", "role": "admin"})
        return {"ok": True, "login": sess.get("login",""), "role": sess.get("role","admin")}
    raise HTTPException(401, "Session expirée")


# ── Démarrage ──────────────────────────────────────────────────────────────

# ── Tokens Réseau Démo démo — enregistrés automatiquement si tokens vides ─────
DEMO_TOKENS = {
    "demo_token_chv":        "CHV",
    "demo_token_ght1":          "GHT1",
    "demo_token_ght2":          "GHT2",
    "demo_token_ght3":         "GHT3",
    "demo_token_ch1":         "CHR1",
    "demo_token_ch2":           "CH2",
    "demo_token_ch3":              "CH3",
    "demo_token_ch4":  "CH4",
    "demo_token_ch5": "CH5",
}

if __name__ == "__main__":
    load_tokens()
    load_data()
    load_pending()
    load_messages_inter()
    load_relay()

    # Tokens: enrôlement MANUEL via l'UI (⏳ EN ATTENTE → ✓ ACCEPTER)
    # Le bouton "⚡ Enregistrer" dans l'UI force l'enregistrement si besoin
    if tokens:
        print(f"  ✓ Tokens enregistrés : {list(tokens.values())}")
    else:
        print(f"  ℹ Aucun token — les GHTs apparaîtront en ⏳ EN ATTENTE")
        print(f"  → Ouvrir http://localhost:9000 et cliquer ✓ ACCEPTER")
        print(f"  → OU cliquer ⚡ Enregistrer (section TOKENS ARC ALPIN)")

    nb_etab = len(tokens)
    nb_data  = len(etablissements)

    print("\n  ╔══════════════════════════════════════════════╗")
    print("  ║  SCRIBE Collecteur territorial  v1.1.1       ║")
    print("  ╚══════════════════════════════════════════════╝")
    print(f"\n  Dashboard     : http://0.0.0.0:9000")
    print(f"  Etablissements: {nb_etab} token(s) / {nb_data} remontée(s)")
    print(f"\n  Token admin   : {ADMIN_TOKEN}")
    print(f"  (persistant dans {ADMIN_FILE} — identique à chaque redémarrage)\n")
    if nb_etab == 0:
        print("  ► Aucun établissement enregistré.")
        print("  → Les GHT qui poussent arrivent en section ⏳ EN ATTENTE")
        print("  → Ouvrir http://localhost:9000 et cliquer ✓ ACCEPTER\n")
        print("  Tokens Réseau Démo démo :")
        print("    CHV    : demo_token_chv")
        print("    GHT1  : demo_token_ght1")
        print("    GHT2  : demo_token_ght2")
        print("    GHT3 : demo_token_ght3\n")
    else:
        etabs = list(set(tokens.values()))
        print(f"  ► Etablissements actifs : {', '.join(etabs)}")
        if pending:
            print(f"  ► EN ATTENTE : {len(pending)} établissement(s) — valider sur http://localhost:9000\n")
        else:
            print()

    import os as _os
    _port = int(_os.environ.get("COLLECTEUR_PORT", 9000))
    uvicorn.run("collecteur:app", host="0.0.0.0", port=_port, reload=False)
