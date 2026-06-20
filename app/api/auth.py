"""
api/auth.py — Authentification SCRIBE v2.0.0
Comptes locaux (pas LDAP) : admin crée les directeurs via /admin
JWT + bcrypt + rate limiting
"""
import os, secrets, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.database import get_db
from app.models import User, Notification

router   = APIRouter()
security = HTTPBearer(auto_error=False)

# SECRET_KEY : depuis env var SCRIBE_SECRET (recommandé), sinon généré
# aléatoirement et persisté dans data/.scribe_secret (chmod 600).
# Plus de dérivation déterministe depuis le chemin (faille C1 audit pré-ANSSI).
import logging as _logging_sec
_logger_sec = _logging_sec.getLogger("scribe.auth")

def _load_or_generate_secret() -> str:
    """Charge SCRIBE_SECRET depuis env, sinon depuis data/.scribe_secret,
    sinon génère un secret aléatoire de 64 octets et le persiste."""
    import pathlib, secrets as _secrets, stat as _stat
    env_secret = os.getenv("SCRIBE_SECRET")
    if env_secret:
        return env_secret
    project_root = pathlib.Path(__file__).resolve().parent.parent.parent
    secret_file = project_root / "data" / ".scribe_secret"
    if secret_file.exists():
        try:
            sec = secret_file.read_text(encoding="utf-8").strip()
            if sec and len(sec) >= 32:
                return sec
        except Exception:
            pass
    # Génération
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    new_secret = _secrets.token_urlsafe(64)
    secret_file.write_text(new_secret, encoding="utf-8")
    try:
        os.chmod(secret_file, 0o600)
    except Exception:
        pass
    _logger_sec.warning(
        "⚠️  SCRIBE_SECRET non défini en environnement. "
        "Secret aléatoire généré dans %s (chmod 600). "
        "En production, définissez SCRIBE_SECRET dans les variables d'environnement.",
        secret_file
    )
    return new_secret

SECRET_KEY = _load_or_generate_secret()
ALGORITHM  = "HS256"
# v2.5.0 patch sécurité : TTL réduit de 72h → 8h par défaut (configurable)
# Pour les crises longues (G7), augmenter via SCRIBE_TOKEN_TTL_HOURS
TOKEN_TTL  = int(os.getenv("SCRIBE_TOKEN_TTL_HOURS", "8"))

# Credentials admin : SCRIBE_ADMIN_PASS doit être défini (fail-fast)
ADMIN_USER = os.getenv("SCRIBE_ADMIN_USER", "dircrise")
ADMIN_PASS = os.getenv("SCRIBE_ADMIN_PASS")
if not ADMIN_PASS:
    # Mode dev : générer un mdp aléatoire et l'afficher dans les logs
    # Mode prod : définir SCRIBE_ADMIN_PASS et SCRIBE_REQUIRE_ADMIN_PASS=1
    if os.getenv("SCRIBE_REQUIRE_ADMIN_PASS") == "1":
        raise RuntimeError(
            "SCRIBE_ADMIN_PASS non défini. Définissez un mot de passe fort "
            "(>= 12 caractères) dans les variables d'environnement avant "
            "de démarrer SCRIBE en production."
        )
    import secrets as _secrets2
    ADMIN_PASS = _secrets2.token_urlsafe(16)
    _logger_sec.warning(
        "⚠️  SCRIBE_ADMIN_PASS non défini. Mot de passe admin généré : %s "
        "(à conserver ou redéfinir via env var SCRIBE_ADMIN_PASS).",
        ADMIN_PASS
    )
elif len(ADMIN_PASS) < 8:
    _logger_sec.warning(
        "⚠️  SCRIBE_ADMIN_PASS fait moins de 8 caractères. "
        "Utilisez un mot de passe fort (>= 12 caractères recommandés)."
    )

# ── Hachage : bcrypt en lib DIRECTE (immunisé contre la dérive passlib/bcrypt) ─
# h61 — On n'utilise plus passlib pour bcrypt : avec bcrypt>=4.1, passlib 1.7.4
# casse (AttributeError __about__) → _hash plantait silencieusement. La lib bcrypt
# directe est stable. Le repli SHA-256 reste pour migrer les anciens comptes.
import bcrypt as _bcrypt
import hashlib as _hashlib

def _hash(pw: str) -> str:
    """Hache avec bcrypt (lib directe). Tronque à 72 octets (limite bcrypt)."""
    return _bcrypt.hashpw(pw.encode("utf-8")[:72], _bcrypt.gensalt()).decode("utf-8")

def _verify(pw: str, hashed: str) -> bool:
    """Vérifie bcrypt ET accepte les anciens hashes SHA-256 (migration transparente)."""
    if not hashed:
        return False
    try:
        if hashed.startswith("$2"):
            return _bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        pass
    # Repli / legacy : SHA-256 sans sel
    try:
        return _hashlib.sha256(pw.encode("utf-8")).hexdigest() == hashed
    except Exception:
        return False

# ── Rate limiting login (en mémoire, sans dépendance externe) ─────────────────
_login_attempts: dict = defaultdict(list)  # ip → [timestamps]
_LOGIN_MAX   = 10   # tentatives max
_LOGIN_WINDOW = 60  # secondes
_LOCKOUT     = 300  # lockout 5 min après dépassement

def _check_rate_limit(ip: str):
    now = time.time()
    attempts = _login_attempts[ip]
    # Nettoyer les anciennes tentatives
    attempts = [t for t in attempts if now - t < _LOGIN_WINDOW]
    _login_attempts[ip] = attempts
    if len(attempts) >= _LOGIN_MAX:
        oldest = attempts[0]
        wait = int(_LOCKOUT - (now - oldest))
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Trop de tentatives. Réessayez dans {wait}s.",
                headers={"Retry-After": str(wait)}
            )
    attempts.append(now)


# ── Helpers ──────────────────────────────────────────────

def _make_token(user_id: int, username: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL)
    return jwt.encode({"sub": str(user_id), "username": username, "role": role, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# v2315 — Alias publics pour que le module MFA puisse réutiliser
# le même mécanisme de token/hash sans dupliquer.
create_access_token = _make_token
decode_token        = _decode_token
verify_password     = _verify

def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not creds:
        return None
    try:
        payload = _decode_token(creds.credentials)
        uid = int(payload["sub"])
        return db.query(User).filter(User.id == uid, User.active == True).first()
    except (JWTError, Exception):
        return None

def require_admin(user: Optional[User] = Depends(get_current_user)):
    if not user or user.role != "admin":  # seul le groupe admin a accès
        raise HTTPException(status_code=403, detail="Accès admin requis")
    return user


def require_user(user: Optional[User] = Depends(get_current_user)):
    """h61 — Garde d'authentification strict : 401 si aucun token valide.
    À appliquer sur tout endpoint de données (règle « rien avant login »).
    get_current_user renvoie None sans token ; les routes qui se contentaient de
    `Depends(get_current_user)` sans vérifier None laissaient fuiter les données."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    if getattr(user, "must_change_password", False):
        # h64 — Verrou SERVEUR du changement de mot de passe. Tant que le mdp
        # n'est pas changé, aucun accès aux données : ça ferme le contournement
        # du popup côté client (un simple reload sautait la modale).
        # L'endpoint POST /change-password dépend de get_current_user (et non de
        # require_user) → il reste accessible pour effectuer le changement.
        raise HTTPException(status_code=403, detail="PASSWORD_CHANGE_REQUIRED")
    return user


# v3.4 (h34) — Système de rôles RGPD-compliant.
# Permet de restreindre l'accès à une route à certains rôles applicatifs.
# Le rôle 'admin' court-circuite toujours les checks (il a tous les droits).
#
# Usage :
#   @router.get("/brancardage/missions")
#   def list_missions(user: User = Depends(require_role("soignant"))):
#       ...
#
# Plusieurs rôles autorisés :
#   user: User = Depends(require_role("soignant", "cellule_crise"))
def require_role(*allowed_roles: str):
    """Factory : retourne une dépendance qui exige un des rôles listés.

    Le rôle 'admin' est implicitement autorisé partout (super-utilisateur).
    Si l'utilisateur n'est pas connecté ou n'a pas le bon rôle → 403.

    Cette fonction sert d'autorisation. L'authentification (token JWT)
    est faite en amont par get_current_user.
    """
    def _checker(user: Optional[User] = Depends(get_current_user)) -> User:
        if not user:
            raise HTTPException(status_code=401, detail="Non authentifié")
        # 'admin' a tous les droits applicatifs
        if user.role == "admin":
            return user
        if user.role not in allowed_roles:
            _logger_sec.info(
                f"require_role: accès refusé pour user={user.username} "
                f"role={user.role}, allowed={allowed_roles}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Cette ressource n'est pas accessible à votre rôle ({user.role})"
            )
        return user
    return _checker


# Valeurs canoniques des rôles. Utilisé pour valider les inputs admin.
ROLES_CANONIQUES = ("admin", "cellule_crise", "soignant")


# ── Schémas ──────────────────────────────────────────────

class LoginIn(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username:     str
    display_name: str
    password:     str
    role:         str = "collaborateur"
    perimetre:    Optional[str] = None
    # v3000h41 — Coordonnées de contact (notifications mail/SMS)
    email:        Optional[str] = None
    telephone:    Optional[str] = None

class UserOut(BaseModel):
    id: int; username: str; display_name: str; role: str
    perimetre: Optional[str]; active: bool
    # v3000h41 — Exposer les coordonnées de contact pour l'admin
    email: Optional[str] = None
    telephone: Optional[str] = None
    # v2315 — Exposer l'état MFA pour la gestion admin
    mfa_enabled: Optional[bool] = False
    class Config: from_attributes = True

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    password:     Optional[str] = None
    role:         Optional[str] = None
    perimetre:    Optional[str] = None
    active:       Optional[bool] = None
    # v3000h41 — Coordonnées de contact. Chaîne vide = effacer la valeur.
    email:        Optional[str] = None
    telephone:    Optional[str] = None


# ── Initialisation compte admin ──────────────────────────

def ensure_admin(db: Session):
    """Crée ou synchronise le compte admin. Hash bcrypt toujours à jour."""
    existing = db.query(User).filter(User.username == ADMIN_USER).first()
    if not existing:
        # v3.4 (h38c) — En mode prod, l'admin est créé avec un mdp par
        # défaut connu publiquement (Scribe2026!). On force le changement
        # à la première connexion pour sécurité minimale.
        # En MODE EXERCICE, on ne force PAS : le mdp est fixe et le
        # collecteur animateur doit pouvoir se logger.
        is_exercice = os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1"
        admin = User(
            username=ADMIN_USER,
            display_name="Directeur de Crise",
            role="admin",
            hashed_password=_hash(ADMIN_PASS),
            active=True
        )
        try:
            admin.must_change_password = (not is_exercice) and (
                os.getenv("SCRIBE_ADMIN_MUST_CHANGE", "1") != "0")
        except Exception:
            pass
        db.add(admin)
        db.commit()
    else:
        # Migrer SHA-256 → bcrypt si le hash n'est pas encore bcrypt
        if not existing.hashed_password.startswith("$2"):
            existing.hashed_password = _hash(ADMIN_PASS)
            db.commit()
        # v3.4 (h38d) — Rétrofit : si un admin existant utilise encore le
        # mdp par défaut (Scribe2026!), forcer `must_change_password=True`
        # au prochain login. Hors mode exercice.
        # Ce code s'applique UNE FOIS : dès que l'admin a changé son mdp,
        # `verify_password(ADMIN_PASS, hash)` est False → on ne touche
        # plus à `must_change_password` (l'utilisateur reste libre).
        is_exercice = os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1"
        if (os.getenv("SCRIBE_ADMIN_MUST_CHANGE", "1") != "0") and not is_exercice \
                and ADMIN_PASS and verify_password(ADMIN_PASS, existing.hashed_password):
            try:
                if not getattr(existing, "must_change_password", False):
                    existing.must_change_password = True
                    db.commit()
            except Exception:
                pass
        # v3.0.0 — En MODE EXERCICE uniquement : forcer la resynchronisation du
        # mot de passe admin sur ADMIN_PASS. Raison : le mdp exercice est fixe et
        # non secret ("Exercice2026!"), et le collecteur animateur DOIT pouvoir se
        # logger pour injecter les stimuli. Si la DB exercice a été créée avec un
        # ancien mdp (random), le login échouait → 0 stimulus. Ce forçage ne
        # s'applique JAMAIS en production (SCRIBE_EXERCICE_MODE != 1) pour ne pas
        # écraser un mot de passe admin légitimement modifié.
        elif os.getenv("SCRIBE_EXERCICE_MODE", "0") == "1" and ADMIN_PASS:
            if not verify_password(ADMIN_PASS, existing.hashed_password):
                existing.hashed_password = _hash(ADMIN_PASS)
                existing.active = True
                db.commit()
            # h60 — En mode exercice, JAMAIS de changement de mot de passe forcé.
            # On lève le flag sur tous les comptes : couvre l'admin, les comptes
            # importés, et les DB exercice créées avant ce correctif.
            try:
                changed = db.query(User).filter(
                    User.must_change_password == True   # noqa: E712
                ).update({User.must_change_password: False}, synchronize_session=False)
                if changed:
                    db.commit()
            except Exception:
                db.rollback()


# ── Endpoints ────────────────────────────────────────────

@router.get("/login-config")
def login_config():
    """Textes configurables de la mire de login. Public, sans auth."""
    import os, json, pathlib
    from config import LOGIN

    subtitle = LOGIN["subtitle"]
    try:
        cfg_js = os.environ.get(
            "SCRIBE_CONFIG_JS",
            str(pathlib.Path(__file__).resolve().parent.parent.parent / "app" / "static" / "config.js")
        )
        if pathlib.Path(cfg_js).exists():
            raw = pathlib.Path(cfg_js).read_text(encoding="utf-8")
            start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
            cfg = json.loads(raw[start:raw.rfind(";")])
            nom = cfg.get("etablissement", {}).get("nom", "")
            if nom:
                subtitle = f"{nom} — Crisis OS"
    except Exception:
        pass

    return {
        "subtitle":    subtitle,
        "footer_text": LOGIN["footer_text"],
        "credit":      LOGIN["credit"],
    }

@router.post("/login")
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    # Rate limiting par IP
    client_ip = getattr(request.client, "host", "unknown")
    _check_rate_limit(client_ip)
    # S'assurer que le compte admin existe et a un hash bcrypt
    ensure_admin(db)
    user = db.query(User).filter(User.username == body.username, User.active == True).first()
    # Message d'erreur identique (évite l'énumération de comptes)
    if not user or not _verify(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    # Migrer SHA-256 → bcrypt à la prochaine connexion réussie
    if not user.hashed_password.startswith("$2"):
        user.hashed_password = _hash(body.password)
        db.commit()

    # v2315 — Si MFA activé, ne pas renvoyer le JWT final directement.
    # Émettre un mfa_token courte durée (5 min) que le client devra
    # échanger contre un vrai JWT via POST /api/v1/mfa/verify après
    # avoir fourni un code TOTP ou de backup.
    if bool(getattr(user, "mfa_enabled", False)):
        import time
        mfa_payload = {
            "sub": str(user.id),
            "username": user.username,
            "scope": "mfa_pending",   # marque ce JWT comme "pas encore valide pour l'API"
            "exp": int(time.time()) + 300,  # 5 minutes
        }
        mfa_token = jwt.encode(mfa_payload, SECRET_KEY, algorithm=ALGORITHM)
        return {
            "require_mfa": True,
            "mfa_token": mfa_token,
            "username": user.username,  # rappel pour UI, pas sensible
        }

    token = _make_token(user.id, user.username, user.role)
    # Vider les tentatives en cas de succès
    _login_attempts.pop(client_ip, None)
    return {"token": token, "user": {"id": user.id, "username": user.username,
            "display_name": user.display_name, "role": user.role, "perimetre": user.perimetre,
            "must_change_password": bool(getattr(user, "must_change_password", False))}}

@router.get("/me")
def me(user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "role": user.role, "perimetre": user.perimetre,
            "must_change_password": bool(getattr(user, "must_change_password", False))}


# v3.4 (h38) — Changement de mot de passe par l'utilisateur lui-même.
# Utilisé notamment pour le flow "première connexion" : si l'utilisateur a
# must_change_password=True, l'UI lui présente une modale de changement
# obligatoire AVANT d'entrer dans l'application.
class _ChangePwdBody(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
def change_password(
    body: _ChangePwdBody,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    if not _verify(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    # Politique minimale : 8 caractères, ne doit pas être l'identique de l'ancien
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit faire au moins 8 caractères")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent de l'ancien")
    user.hashed_password = _hash(body.new_password)
    user.must_change_password = False
    db.commit()
    _logger_sec.info(f"password_change: user={user.username} id={user.id}")
    return {"ok": True, "must_change_password": False}


# v3000h41 — Synchronisation des coordonnées de contact vers le plugin
# notifications. Quand l'admin renseigne l'email / le téléphone d'un compte,
# on crée (ou met à jour) une souscription "mail" / "sms" pour cet utilisateur,
# afin que le dispatcher de notifications puisse réellement l'atteindre dès que
# le backend SMTP ou SMS est configuré.
#
# Conception défensive :
#   - Le plugin notifications est OPTIONNEL : tout est encapsulé dans un
#     try/except large. Si le plugin (ou sa table) n'existe pas, on ne lève
#     jamais d'erreur — la création/édition de compte n'en dépend pas.
#   - On reconnaît les souscriptions auto-gérées via le label "auto:contact"
#     pour ne JAMAIS écraser une souscription saisie manuellement par
#     l'utilisateur (mail perso, numéro d'astreinte alternatif, etc.).
#   - Si la coordonnée est effacée (None), la souscription auto correspondante
#     est désactivée (active=False) plutôt que supprimée, pour conserver l'audit.
_AUTO_CONTACT_LABEL = "auto:contact"

def _sync_contact_subscriptions(db: Session, u: User) -> None:
    try:
        from plugins.notifications.models import NotifSubscription
    except Exception:
        return  # plugin notifications absent → rien à faire

    def _upsert(kind: str, target: Optional[str]) -> None:
        try:
            sub = (db.query(NotifSubscription)
                     .filter(NotifSubscription.user_id == u.id,
                             NotifSubscription.channel_kind == kind,
                             NotifSubscription.label == _AUTO_CONTACT_LABEL)
                     .first())
            if target:
                if sub:
                    sub.target = target
                    sub.active = True
                else:
                    db.add(NotifSubscription(
                        user_id=u.id, channel_kind=kind,
                        target=target, label=_AUTO_CONTACT_LABEL,
                        min_urgency=2, active=True,
                    ))
            elif sub:
                sub.active = False  # coordonnée effacée → on coupe le canal auto
        except Exception:
            pass

    try:
        _upsert("mail", (u.email or "").strip() or None)
        _upsert("sms",  (u.telephone or "").strip() or None)
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass


@router.get("/users", response_model=List[UserOut])
def list_users(user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    """Liste tous les utilisateurs actifs — accessible à tout utilisateur authentifié (nécessaire pour la messagerie)."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    return db.query(User).filter(User.active == True).order_by(User.display_name).all()

@router.post("/users", response_model=UserOut)
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Nom d'utilisateur déjà pris")
    u = User(username=body.username, display_name=body.display_name,
             role=body.role, hashed_password=_hash(body.password),  # bcrypt
             perimetre=body.perimetre,
             email=(body.email or None), telephone=(body.telephone or None),
             active=True)
    db.add(u); db.commit(); db.refresh(u)
    _sync_contact_subscriptions(db, u)
    return u

@router.put("/users/{uid}", response_model=UserOut)
def update_user(uid: int, body: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404, "Utilisateur non trouvé")
    if body.display_name is not None: u.display_name = body.display_name
    if body.password     is not None: u.hashed_password = _hash(body.password)
    if body.role         is not None:
        # v3.4 (h34) — Valider le rôle (anti-typo, anti-rôle inconnu).
        if body.role not in ROLES_CANONIQUES:
            raise HTTPException(
                400,
                f"Rôle invalide '{body.role}'. Rôles autorisés : {', '.join(ROLES_CANONIQUES)}"
            )
        # Empêcher un admin de se rétrograder lui-même (anti-lockout).
        if u.id == admin.id and u.role == "admin" and body.role != "admin":
            raise HTTPException(
                400,
                "Impossible de retirer votre propre rôle admin. "
                "Demandez à un autre administrateur."
            )
        _logger_sec.info(
            f"role_change: {admin.username} a modifié {u.username} : "
            f"{u.role} → {body.role}"
        )
        u.role = body.role
    if body.perimetre    is not None: u.perimetre = body.perimetre
    if body.active       is not None: u.active = body.active
    # v3000h41 — Coordonnées de contact. Chaîne vide => on efface (None).
    contact_changed = False
    if body.email     is not None:
        u.email = body.email.strip() or None;     contact_changed = True
    if body.telephone is not None:
        u.telephone = body.telephone.strip() or None; contact_changed = True
    db.commit(); db.refresh(u)
    if contact_changed:
        _sync_contact_subscriptions(db, u)
    return u

@router.delete("/users/{uid}")
def delete_user(uid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404, "Utilisateur non trouvé")
    db.delete(u); db.commit()
    return {"status": "deleted"}

# v2315 — Réinitialisation MFA par un admin (cas de perte de téléphone).
# L'utilisateur perd son setup MFA et devra refaire la configuration
# complète (nouveau QR, nouveau téléphone) lors de sa prochaine connexion.
# Les codes de backup existants sont supprimés. L'admin ne peut pas
# réinitialiser son propre MFA par cette route (prévention d'auto-lockout) ;
# pour désactiver le sien il utilise /mfa/disable avec son mot de passe.
@router.post("/users/{uid}/mfa-reset")
def admin_mfa_reset(uid: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == uid).first()
    if not u: raise HTTPException(404, "Utilisateur non trouvé")
    if u.id == admin.id:
        raise HTTPException(400, "Utilise /mfa/disable pour ton propre compte (password requis)")
    u.mfa_enabled = False
    u.mfa_secret = None
    u.mfa_backup_codes = None
    db.commit()
    return {"ok": True, "username": u.username, "message": "MFA réinitialisé — l'utilisateur devra refaire la configuration"}

# ── NOTIFICATIONS ────────────────────────────────────────

@router.get("/notifications")
def get_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: raise HTTPException(401)
    notifs = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.timestamp.desc()).limit(50).all()
    return [{"id": n.id, "titre": n.titre, "message": n.message,
             "type_notif": n.type_notif, "incident_id": n.incident_id,
             "task_id": n.task_id, "lu": n.lu,
             "timestamp": n.timestamp.isoformat() if n.timestamp else None}
            for n in notifs]

@router.get("/notifications/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return {"count": 0}
    c = db.query(Notification).filter(Notification.user_id == user.id, Notification.lu == False).count()
    return {"count": c}

@router.put("/notifications/{nid}/read")
def mark_read(nid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: raise HTTPException(401)
    n = db.query(Notification).filter(Notification.id == nid, Notification.user_id == user.id).first()
    if n: n.lu = True; db.commit()
    return {"status": "ok"}

@router.put("/notifications/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: raise HTTPException(401)
    db.query(Notification).filter(Notification.user_id == user.id, Notification.lu == False).update({"lu": True})
    db.commit()
    return {"status": "ok"}


# ── Helper global : notifier les directeurs concernés ────

def notify_incident(db: Session, incident, action: str = "INCIDENT"):
    """Hook appelé à la création d'un incident.

    v2.3.88 — Ne crée PLUS de notification inbox pour les incidents.
    Auparavant, chaque incident créait une Notification inbox pour tous
    les directeurs → pollution massive de l'inbox, confusion avec les
    vrais messages internes (messagerie).

    Maintenant :
    - Les incidents apparaissent dans l'onglet INCIDENTS (badge sur le bouton).
    - L'inbox ne contient que les vrais messages (messagerie, mentions chat,
      décisions à valider).
    - Les canaux multi-canal (mail/push/SMS) du plugin notifications prennent
      le relais pour alerter les personnes hors SCRIBE.

    Cette fonction est gardée comme hook vide pour compatibilité, au cas où
    du code ailleurs l'importerait. Si on a besoin d'hooks par-incident
    (webhook externe, ARS, etc.), c'est ici qu'on les ajoutera.
    """
    # Noop volontaire — voir docstring.
    # Les canaux de notification sont désormais gérés par le plugin
    # notifications (app/api/sitrep.py appelle dispatcher.notify_sync).
    return


@router.get("/annuaire-messagerie")
def annuaire_messagerie(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne tous les utilisateurs actifs pour l'annuaire de messagerie."""
    users = db.query(User).filter(User.active == True).order_by(User.display_name).all()
    result = []
    for u in users:
        if u.id == (current_user.id if current_user else -1):
            continue
        # Extraire le site depuis le username (convention: service_demo_SITE ou service_SITE)
        import re
        site_match = re.search(r'_demo_(.+)$', u.username) or re.search(r'_([a-z0-9]{3,14})$', u.username)
        site_tag = site_match.group(1) if site_match else ""
        result.append({
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name or u.username,
            "role": u.role,
            "site_tag": site_tag,
        })
    return result


@router.post("/heartbeat")
def heartbeat(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ping de présence — appelé toutes les 30s par le frontend."""
    if not current_user:
        raise HTTPException(401)
    from app.models import UserOnlineStatus
    from datetime import datetime, timezone
    existing = db.query(UserOnlineStatus).filter_by(user_id=current_user.id).first()
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_seen = now
        existing.username = current_user.username
    else:
        db.add(UserOnlineStatus(
            user_id=current_user.id,
            username=current_user.username,
            last_seen=now,
        ))
    db.commit()
    return {"ok": True}


@router.get("/annuaire-messagerie")
def annuaire_messagerie(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Annuaire complet avec statut en ligne pour la messagerie interne."""
    from app.models import UserOnlineStatus
    from datetime import datetime, timezone
    import re as _re

    users = db.query(User).filter(User.active == True).order_by(User.display_name).all()

    # Récupérer les statuts en ligne
    statuses = {s.user_id: s.last_seen for s in db.query(UserOnlineStatus).all()}
    now = datetime.now(timezone.utc)

    result = []
    for u in users:
        if u.id == (current_user.id if current_user else -1):
            continue
        # Extraire site tag depuis username
        m = _re.search(r'_demo_(.+)$', u.username) or _re.search(r'_([a-z0-9_]{3,20})$', u.username)
        if m:
            site_tag = m.group(1)
        elif u.username in ('dircrise', 'admin') or u.role in ('admin', 'directeur'):
            # Compte admin/direction : tag = sigle de l'établissement courant
            import os as _os, json as _json, pathlib as _pl
            try:
                cfg_js = _os.environ.get("SCRIBE_CONFIG_JS", "")
                if cfg_js and _pl.Path(cfg_js).exists():
                    raw = _pl.Path(cfg_js).read_text(encoding="utf-8")
                    start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
                    _cfg = _json.loads(raw[start:raw.rfind(";")])
                    site_tag = (_cfg.get("etablissement",{}).get("sigle","") or "").lower()
                else:
                    site_tag = "direction"
            except Exception:
                site_tag = "direction"
        else:
            site_tag = ""

        # Extraire service depuis display_name ou username
        dn = u.display_name or u.username
        service = dn.split(" — ")[0] if " — " in dn else dn

        # Statut en ligne
        last = statuses.get(u.id)
        inactivity_label = ""
        if last is None:
            online = "never"
        else:
            try:
                delta = (now - last).total_seconds()
            except TypeError:
                from datetime import timezone as _tz
                last_aware = last.replace(tzinfo=_tz.utc) if last.tzinfo is None else last
                delta = (now - last_aware).total_seconds()

            if delta < 120:
                online = "online"          # vert : actif maintenant
                inactivity_label = "En ligne"
            elif delta < 86400:
                online = "today"           # bleu : connecté aujourd'hui
                # Calculer le label d'inactivité
                if delta < 3600:
                    mins = int(delta // 60)
                    inactivity_label = f"Inactif depuis {mins}min"
                else:
                    hrs = int(delta // 3600)
                    mins = int((delta % 3600) // 60)
                    inactivity_label = f"Inactif depuis {hrs}h{mins:02d}"
            else:
                online = "offline"         # gris : jamais ou > 24h
                inactivity_label = ""

        result.append({
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name or u.username,
            "service": service,
            "role": u.role,
            "site_tag": site_tag,
            "online": online,
            "inactivity_label": inactivity_label,
        })
    return result


@router.get("/annuaire-public")
def annuaire_public(db: Session = Depends(get_db)):
    """Annuaire public de l'établissement — pas d'auth requise, pour la messagerie inter-GHT.
    Ne retourne que les infos non-sensibles."""
    import re as _re, os as _os, json as _json, pathlib as _pl
    # Lire le sigle depuis config.js
    sigle = "?"
    try:
        cfg_js = _os.environ.get("SCRIBE_CONFIG_JS", "")
        if cfg_js and _pl.Path(cfg_js).exists():
            raw = _pl.Path(cfg_js).read_text(encoding="utf-8")
            start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
            _cfg = _json.loads(raw[start:raw.rfind(";")])
            sigle = (_cfg.get("etablissement",{}).get("sigle","") or "?").upper()
            nom_etab = (_cfg.get("etablissement",{}).get("nom","") or sigle)
    except Exception:
        nom_etab = sigle

    users = db.query(User).filter(User.active == True).order_by(User.display_name).all()
    result = []
    for u in users:
        m = _re.search(r'_demo_(.+)$', u.username) or _re.search(r'_([a-z0-9_]{3,20})$', u.username)
        site_tag = m.group(1) if m else sigle.lower()
        service = (u.display_name or u.username).split(" — ")[0]
        result.append({
            "display_name": u.display_name or u.username,
            "username": u.username,
            "service": service,
            "role": u.role,
            "site_tag": site_tag,
            "ght_sigle": sigle,
            "ght_nom": nom_etab,
        })
    return {"sigle": sigle, "nom": nom_etab, "contacts": result}
