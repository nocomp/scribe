"""
app/api/mfa.py — SCRIBE v2315
MFA TOTP (RFC 6238) activable par l'utilisateur ou imposable par l'admin.

Flow d'activation (user) :
  1. POST /api/v1/mfa/setup       → génère secret + QR code data-URL
  2. L'user scanne le QR avec Google Authenticator / Aegis / 2FAS
  3. POST /api/v1/mfa/verify-setup avec le 1er code → MFA activé +
     10 codes de backup retournés (affichés une seule fois)

Flow login avec MFA :
  1. POST /api/v1/auth/login (username + password)
     → si mfa_enabled=true, réponse = {require_mfa: true, mfa_token: XXX}
     → mfa_token est un JWT courte durée (5 min) qui prouve que
       username+password sont bons
  2. POST /api/v1/mfa/verify avec mfa_token + code → JWT final

Les codes de backup sont à usage unique. Utilisables à la place du TOTP.

Désactivation :
  - L'user peut désactiver son propre MFA (POST /mfa/disable + password)
  - L'admin peut forcer la réinitialisation (POST /admin/users/{id}/mfa-reset)
"""
from __future__ import annotations
import base64, io, json, secrets

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import create_access_token, get_current_user, verify_password
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/v1/mfa", tags=["MFA"])


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _generate_backup_codes(n: int = 10) -> list[str]:
    """Génère N codes de backup à 8 caractères, format XXXX-XXXX."""
    out = []
    for _ in range(n):
        code = secrets.token_hex(4).upper()   # 8 hex chars
        out.append(f"{code[:4]}-{code[4:]}")
    return out


def _verify_totp(secret: str, code: str, drift: int = 1) -> bool:
    """Vérifie un code TOTP avec tolérance ±drift périodes (30s chacune)."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=drift)
    except Exception:
        return False


def _consume_backup_code(user: User, code: str, db: Session) -> bool:
    """Tente de consommer un code de backup. Retourne True si valide."""
    if not user.mfa_backup_codes:
        return False
    code_norm = code.strip().upper().replace(" ", "")
    # Accepter avec ou sans tiret
    if "-" not in code_norm and len(code_norm) == 8:
        code_norm = code_norm[:4] + "-" + code_norm[4:]
    try:
        codes = json.loads(user.mfa_backup_codes)
    except Exception:
        return False
    if code_norm in codes:
        codes.remove(code_norm)
        user.mfa_backup_codes = json.dumps(codes)
        db.commit()
        return True
    return False


def _qr_data_url(uri: str) -> str:
    """Génère un QR code en PNG base64 data-URL pour affichage inline."""
    img = qrcode.make(uri, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ──────────────────────────────────────────────────────────────────────
# Schémas
# ──────────────────────────────────────────────────────────────────────

class SetupOut(BaseModel):
    secret: str
    uri: str           # otpauth://totp/... pour import manuel
    qr_data_url: str   # PNG base64 pour affichage img src=


class VerifyIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=20)


class VerifyOut(BaseModel):
    ok: bool
    backup_codes: list[str] | None = None


class DisableIn(BaseModel):
    password: str


class StatusOut(BaseModel):
    enabled: bool
    setup_pending: bool    # secret généré mais activation pas confirmée
    backup_codes_remaining: int


# ──────────────────────────────────────────────────────────────────────
# Routes — User
# ──────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=StatusOut)
def mfa_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """État MFA de l'utilisateur courant."""
    if not user:
        raise HTTPException(401)
    try:
        codes = json.loads(user.mfa_backup_codes or "[]")
    except Exception:
        codes = []
    return StatusOut(
        enabled=bool(user.mfa_enabled),
        setup_pending=bool(user.mfa_secret and not user.mfa_enabled),
        backup_codes_remaining=len(codes),
    )


@router.post("/setup", response_model=SetupOut)
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Génère un nouveau secret et renvoie le QR à scanner.
    Ne bloque pas le login tant que verify-setup n'a pas été confirmé."""
    if not user:
        raise HTTPException(401)
    if user.mfa_enabled:
        raise HTTPException(400, "MFA déjà activé. Désactivez-le avant de régénérer.")
    # Générer nouveau secret
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    db.commit()
    # Construire l'URI otpauth compatible tous les authenticators
    issuer = "SCRIBE"
    label = f"{issuer}:{user.username}"
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name=issuer
    )
    return SetupOut(secret=secret, uri=uri, qr_data_url=_qr_data_url(uri))


@router.post("/verify-setup", response_model=VerifyOut)
def mfa_verify_setup(
    body: VerifyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirme l'activation du MFA avec le premier code TOTP.
    Retourne les codes de backup à afficher une seule fois."""
    if not user:
        raise HTTPException(401)
    if not user.mfa_secret:
        raise HTTPException(400, "Aucun setup en cours. Appelez /setup d'abord.")
    if user.mfa_enabled:
        raise HTTPException(400, "MFA déjà activé.")
    if not _verify_totp(user.mfa_secret, body.code):
        raise HTTPException(400, "Code incorrect. Vérifiez l'heure de l'appareil.")
    # Activer + générer codes de backup
    user.mfa_enabled = True
    backup = _generate_backup_codes(10)
    user.mfa_backup_codes = json.dumps(backup)
    db.commit()
    return VerifyOut(ok=True, backup_codes=backup)


@router.post("/disable")
def mfa_disable(
    body: DisableIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Désactive le MFA de l'utilisateur. Requiert le mot de passe en confirmation."""
    if not user:
        raise HTTPException(401)
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(403, "Mot de passe incorrect.")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    db.commit()
    return {"ok": True}


@router.post("/regenerate-backup-codes", response_model=VerifyOut)
def mfa_regenerate_backup(
    body: VerifyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Régénère les codes de backup. Requiert un code TOTP valide."""
    if not user:
        raise HTTPException(401)
    if not user.mfa_enabled:
        raise HTTPException(400, "MFA non activé")
    if not _verify_totp(user.mfa_secret, body.code):
        raise HTTPException(400, "Code TOTP incorrect")
    backup = _generate_backup_codes(10)
    user.mfa_backup_codes = json.dumps(backup)
    db.commit()
    return VerifyOut(ok=True, backup_codes=backup)


# ──────────────────────────────────────────────────────────────────────
# Routes — Login phase 2 (after password OK)
# ──────────────────────────────────────────────────────────────────────

class MfaLoginIn(BaseModel):
    mfa_token: str   # JWT court émis par /auth/login quand MFA requis
    code: str        # code TOTP ou code de backup


@router.post("/verify")
def mfa_verify_login(body: MfaLoginIn, db: Session = Depends(get_db)):
    """Phase 2 du login MFA : l'user envoie le mfa_token (reçu de /auth/login)
    + son code TOTP ou un code de backup. Retourne le JWT de session normal."""
    # Décoder le mfa_token pour retrouver l'user_id
    from app.api.auth import decode_token
    try:
        payload = decode_token(body.mfa_token)
    except Exception:
        raise HTTPException(401, "Token MFA invalide ou expiré")
    if payload.get("scope") != "mfa_pending":
        raise HTTPException(401, "Token MFA invalide")
    user_id = int(payload.get("sub") or 0)
    user = db.query(User).filter(User.id == user_id, User.active == True).first()
    if not user or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(401, "MFA non configuré pour cet utilisateur")

    # Vérifier le code : TOTP d'abord, puis backup
    ok = _verify_totp(user.mfa_secret, body.code)
    used_backup = False
    if not ok:
        if _consume_backup_code(user, body.code, db):
            ok = True
            used_backup = True
    if not ok:
        raise HTTPException(403, "Code incorrect")

    # Émettre le JWT de session final (utilise le même create_access_token
    # que le flow normal)
    token = create_access_token(user.id, user.username, user.role)
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        },
        "used_backup_code": used_backup,
    }
