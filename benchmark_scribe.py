#!/usr/bin/env python3
"""
SCRIBE — Health-check / Benchmark
=================================

Vérifie de bout en bout les fonctionnalités de SCRIBE : socle instance,
inter-instances, instance↔supervision, et (à venir) mode exercice. Chaque check
fait une ACTION puis une VÉRIFICATION (relit l'effet) et produit PASS/FAIL/WARN/SKIP
avec la preuve (code HTTP, extrait de réponse).

Usage :
    # Tester une pile DÉJÀ lancée (ex. démo) :
    python3 benchmark_scribe.py \
        --collecteur http://127.0.0.1:9000 \
        --instances  http://127.0.0.1:8000,http://127.0.0.1:8001 \
        --user dircrise --password 'Scribe2026!'

    # Tout orchestrer (lance une pile dédiée jetable, teste, arrête) :
    python3 benchmark_scribe.py --auto

Sorties : rapport console + bench_reports/healthcheck_<horodatage>.{html,json}
Rétention : les rapports de plus de --keep-days jours sont purgés à chaque run.

NB : ce script est NON destructif sur les cibles passées en --collecteur/--instances
SI elles sont dédiées. En --auto, il lance une pile JETABLE (DBs/ports isolés) et ne
touche jamais la prod. Ne pas pointer --instances vers la prod réelle (il crée des
incidents/transferts/messages de test).
"""
import argparse
import datetime as _dt
import html as _html
import io
import json
import os
import signal
import socket
import subprocess
import sys
import time
import zipfile

try:
    import httpx
except ImportError:
    print("httpx requis : pip install httpx", file=sys.stderr)
    sys.exit(2)

# ─────────────────────────────────────────────────────────────────────────────
# Chemins d'API (centralisés pour ajustement facile au 1er run)
# ─────────────────────────────────────────────────────────────────────────────
EP = {
    "health":        "/health",
    "version":       "/api/v1/version",
    "login":         "/api/v1/auth/login",
    "sitrep_post":   "/api/v1/sitrep/post",
    "sitrep_list":   "/api/v1/sitrep/history",
    "msg_create":    "/api/v1/messagerie/messages",
    "msg_inbox":     "/api/v1/messagerie/messages?box=inbox",
    "msg_reply":     "/api/v1/messagerie/messages/{id}/reply",
    "msg_read":      "/api/v1/messagerie/messages/{id}/lire",
    "capacite_list": "/api/v1/capacite/referentiel",
    "decl_post":     "/api/v1/federation/declaration",
    "transfert":     "/api/v1/transferts",
    "archive_post":  "/api/v1/archiver-crise",
    "archive_dl":    "/api/v1/telecharger-archive",
    "coll_summary":  "/api/summary",
    "coll_central":  "/api/admin/central-config",
}

# Champs interdits dans toute remontée collecteur (RGPD : aucune donnée patient)
RGPD_FORBIDDEN = ("nom", "prenom", "ipp", "date_naissance", "nom_jeune_fille", "nir")


# ─────────────────────────────────────────────────────────────────────────────
# Moteur de rapport
# ─────────────────────────────────────────────────────────────────────────────
class Reporter:
    COLORS = {"PASS": "\033[92m", "FAIL": "\033[91m", "WARN": "\033[93m",
              "SKIP": "\033[90m", "_end": "\033[0m"}

    def __init__(self):
        self.results = []   # {section, name, status, detail, http, ms}
        self.started = _dt.datetime.now()

    def add(self, section, name, status, detail="", http=None, ms=None):
        self.results.append({"section": section, "name": name, "status": status,
                             "detail": str(detail)[:500], "http": http, "ms": ms})
        c = self.COLORS.get(status, "")
        e = self.COLORS["_end"]
        h = f" [{http}]" if http is not None else ""
        print(f"  {c}{status:<4}{e} {section} › {name}{h}"
              + (f"  — {detail}" if detail and status in ("FAIL", "WARN") else ""))

    def check(self, section, name, ok, detail="", http=None, warn=False):
        self.add(section, name, "PASS" if ok else ("WARN" if warn else "FAIL"),
                 detail, http)
        return ok

    def skip(self, section, name, detail=""):
        self.add(section, name, "SKIP", detail)

    # ── synthèse ───────────────────────────────────────────────────────────
    def counts(self):
        c = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for r in self.results:
            c[r["status"]] = c.get(r["status"], 0) + 1
        return c

    def health_color(self):
        c = self.counts()
        if c["FAIL"]:
            return "rouge"
        if c["WARN"]:
            return "orange"
        return "vert"

    def to_json(self):
        return {
            "horodatage": self.started.isoformat(),
            "duree_s": round((_dt.datetime.now() - self.started).total_seconds(), 1),
            "couleur": self.health_color(),
            "compteurs": self.counts(),
            "resultats": self.results,
        }

    def to_html(self):
        c = self.counts()
        col = {"vert": "#15803d", "orange": "#d97706", "rouge": "#dc2626"}[self.health_color()]
        rows = []
        cur = None
        for r in self.results:
            if r["section"] != cur:
                cur = r["section"]
                rows.append(f'<tr><td colspan="4" style="background:#f1f5f9;font-weight:700;'
                            f'padding:8px 10px">{_html.escape(cur)}</td></tr>')
            badge = {"PASS": "#15803d", "FAIL": "#dc2626", "WARN": "#d97706", "SKIP": "#94a3b8"}[r["status"]]
            http = f'<span style="color:#64748b">{r["http"]}</span>' if r["http"] is not None else ""
            rows.append(
                f'<tr style="border-bottom:1px solid #e2e8f0">'
                f'<td style="padding:6px 10px"><span style="background:{badge};color:#fff;'
                f'border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700">{r["status"]}</span></td>'
                f'<td style="padding:6px 10px">{_html.escape(r["name"])}</td>'
                f'<td style="padding:6px 10px;text-align:center">{http}</td>'
                f'<td style="padding:6px 10px;color:#64748b;font-size:12px">{_html.escape(r["detail"])}</td></tr>')
        return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>SCRIBE Health — {self.started:%Y-%m-%d %H:%M}</title>
<style>body{{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
.hd{{background:#003189;color:#fff;padding:18px 24px}}.dot{{display:inline-block;width:14px;height:14px;
border-radius:50%;background:{col};margin-right:8px;vertical-align:middle}}
table{{border-collapse:collapse;width:100%;background:#fff}}.wrap{{max-width:1000px;margin:20px auto;padding:0 16px}}
.kpi{{display:inline-block;margin-right:18px;font-size:14px}}</style></head><body>
<div class="hd"><h1 style="margin:0;font-size:18px"><span class="dot"></span>SCRIBE Health — {self.health_color().upper()}</h1>
<div style="margin-top:6px;font-size:13px;opacity:.9">{self.started:%Y-%m-%d %H:%M:%S} — durée {round((_dt.datetime.now()-self.started).total_seconds(),1)}s</div></div>
<div class="wrap"><p>
<span class="kpi" style="color:#15803d">✓ {c['PASS']} PASS</span>
<span class="kpi" style="color:#dc2626">✗ {c['FAIL']} FAIL</span>
<span class="kpi" style="color:#d97706">⚠ {c['WARN']} WARN</span>
<span class="kpi" style="color:#94a3b8">– {c['SKIP']} SKIP</span></p>
<table><thead><tr style="background:#0f172a;color:#fff">
<th style="padding:8px 10px;text-align:left">État</th><th style="padding:8px 10px;text-align:left">Contrôle</th>
<th style="padding:8px 10px">HTTP</th><th style="padding:8px 10px;text-align:left">Détail</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers HTTP
# ─────────────────────────────────────────────────────────────────────────────
def login(client, user, password):
    try:
        r = client.post(EP["login"], json={"username": user, "password": password}, timeout=10)
        if r.status_code < 300:
            j = r.json()
            return (j.get("token") or j.get("access_token")), r.status_code, (j.get("user") or {})
        return None, r.status_code, {}
    except Exception as e:
        return None, str(e), {}


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _tail_log(path, n=50):
    """Remonte les lignes pertinentes du log d'une instance (diagnostic auth)."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-n:]
    except Exception:
        return ""
    keys = ("admin", "généré", "genere", "bcrypt", "passlib", "rror",
            "Traceback", "ensure_admin", "ADMIN", "SCRIBE_ADMIN", "Identifiants")
    rel = [l.rstrip() for l in lines if any(k in l for k in keys)]
    out = rel[-8:] if rel else [l.rstrip() for l in lines[-5:]]
    return "\n".join(out)[:900]


# ─────────────────────────────────────────────────────────────────────────────
# Checks — SOCLE INSTANCE
# ─────────────────────────────────────────────────────────────────────────────
def checks_instance(rep, base, label, user, password, log_path=None):
    sec = f"Instance {label}"
    client = httpx.Client(base_url=base, timeout=15, follow_redirects=True)

    # Santé
    try:
        r = client.get(EP["health"])
        rep.check(sec, "santé /health", r.status_code < 400, http=r.status_code)
    except Exception as e:
        rep.check(sec, "santé /health", False, detail=e)
        return  # instance injoignable → on arrête les checks de cette instance

    # Auth : mauvais mot de passe rejeté
    _, code, _ = login(client, user, "MAUVAIS_MDP_BENCH")
    rep.check(sec, "auth refuse mauvais mot de passe", code == 401, http=code)

    # Auth : login OK (avec diagnostic log si échec)
    tok, code, me = login(client, user, password)
    if not tok:
        diag = _tail_log(log_path)
        rep.add(sec, "auth login OK", "FAIL", detail=(diag.replace("\n", " ⏎ ") or f"HTTP {code}"), http=code)
        if diag:
            print("      ↳ log instance (diagnostic) :")
            for ln in diag.splitlines():
                print("        " + ln)
        client.close()
        return
    rep.check(sec, "auth login OK", True, http=code)
    H = _hdr(tok)

    # Sécurité : login obligatoire — aucune donnée ne doit sortir sans token.
    for name, path in [("incidents", EP["sitrep_list"]),
                       ("capacité référentiel", EP["capacite_list"]),
                       ("capacité export-CSV", "/api/v1/capacite/export-csv"),
                       ("messagerie", EP["msg_inbox"])]:
        try:
            rr = client.get(path)  # volontairement SANS en-tête d'auth
            if rr.status_code == 200:
                rep.add(sec, f"sécurité : {name} accessible SANS token", "WARN",
                        detail="200 sans authentification — donnée exposée avant login ?",
                        http=rr.status_code)
            else:
                rep.check(sec, f"sécurité : {name} refusé sans token",
                          rr.status_code in (401, 403), http=rr.status_code)
        except Exception as e:
            rep.check(sec, f"sécurité : {name} sans token", False, detail=e)

    # Incident : créer puis relire
    marker = f"BENCH-{label}-{int(time.time())}"
    try:
        r = client.post(EP["sitrep_post"], headers=H, json={
            "declarant_nom": "banc", "site_id": label, "fait": marker,
            "analyse": "check banc", "urgency": 2, "type_crise": "TECHNIQUE"})
        created = r.status_code < 300
        rep.check(sec, "incident créé", created, http=r.status_code,
                  detail="" if created else r.text[:160])
        if created:
            r2 = client.get(EP["sitrep_list"], headers=H)
            found = r2.status_code < 300 and marker in r2.text
            rep.check(sec, "incident relu (présent dans l'historique)", found, http=r2.status_code)
    except Exception as e:
        rep.check(sec, "incident créé/relu", False, detail=e)

    # Capacité : référentiel lisible
    try:
        r = client.get(EP["capacite_list"], headers=H)
        rep.check(sec, "capacité référentiel lisible", r.status_code < 300, http=r.status_code)
    except Exception as e:
        rep.check(sec, "capacité référentiel lisible", False, detail=e)

    # Messagerie : envoyer (à soi-même) → boîte → lire → répondre
    _check_messagerie_cycle(rep, sec, client, H, me)

    # Archivage de crise + vérification du ZIP
    _check_archive_zip(rep, sec, client, H)

    client.close()


def _check_messagerie_cycle(rep, sec, client, H, me):
    uid = (me or {}).get("id")
    if not uid:
        rep.skip(sec, "messagerie : cycle (id utilisateur inconnu)")
        return
    sujet = f"BENCH-MSG-{int(time.time())}"
    dest = json.dumps([{"type": "user", "value": uid}])
    try:
        # endpoint multipart (Form) : destinataires_json + au moins un destinataire
        r = client.post(EP["msg_create"], headers=H, data={
            "canal": "interne", "sujet": sujet, "contenu": "message de banc",
            "destinataires_json": dest})
        if not rep.check(sec, "messagerie : message envoyé", r.status_code < 300,
                         http=r.status_code, detail="" if r.status_code < 300 else r.text[:160]):
            return
        # envoyé à soi-même → doit apparaître en réception
        r2 = client.get(EP["msg_inbox"], headers=H)
        present = r2.status_code < 300 and sujet in r2.text
        rep.check(sec, "messagerie : message reçu en boîte", present, http=r2.status_code, warn=not present)
        mid = None
        try:
            j = r.json(); mid = j.get("id") or (j.get("message") or {}).get("id")
        except Exception:
            pass
        if mid:
            rl = client.post(EP["msg_read"].format(id=mid), headers=H)
            rep.check(sec, "messagerie : marqué lu", rl.status_code < 300, http=rl.status_code, warn=True)
            rr = client.post(EP["msg_reply"].format(id=mid), headers=H, data={"contenu": "réponse de banc"})
            rep.check(sec, "messagerie : réponse postée", rr.status_code < 300, http=rr.status_code, warn=True)
        else:
            rep.skip(sec, "messagerie : lire/répondre (id introuvable)")
    except Exception as e:
        rep.check(sec, "messagerie : cycle", False, detail=e)


def _check_archive_zip(rep, sec, client, H):
    """Archive la crise courante puis vérifie que le ZIP est valide et lisible."""
    try:
        r = client.post(EP["archive_post"], headers=H)
        if r.status_code == 404:
            rep.skip(sec, "archive crise (endpoint non monté dans cette build — à brancher)")
            return
        if not rep.check(sec, "archive crise : générée", r.status_code < 300, http=r.status_code):
            return
        nom = None
        try:
            j = r.json()
            nom = j.get("nom") or j.get("fichier") or j.get("archive") or os.path.basename(j.get("chemin", ""))
        except Exception:
            pass
        if not nom:
            rep.skip(sec, "archive crise : vérif ZIP (nom non renvoyé)")
            return
        rd = client.get(EP["archive_dl"], headers=H, params={"nom": nom})
        if not rep.check(sec, "archive crise : téléchargée", rd.status_code < 300, http=rd.status_code):
            return
        content = rd.content
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            bad = zf.testzip()
            entries = zf.namelist()
            ok = bad is None and len(entries) > 0
            rep.check(sec, f"archive crise : ZIP valide ({len(entries)} fichiers)", ok,
                      detail="" if ok else f"corruption: {bad}")
        except Exception as e:
            rep.check(sec, "archive crise : ZIP valide", False, detail=f"ZIP illisible: {e}")
    except Exception as e:
        rep.check(sec, "archive crise", False, detail=e)


# ─────────────────────────────────────────────────────────────────────────────
# Checks — SUPERVISION (collecteur)
# ─────────────────────────────────────────────────────────────────────────────
def checks_collecteur(rep, base, admin_token):
    sec = "Supervision"
    client = httpx.Client(base_url=base, timeout=15, follow_redirects=True)
    try:
        r = client.get(EP["health"])
        rep.check(sec, "santé collecteur", r.status_code < 400, http=r.status_code)
    except Exception as e:
        rep.check(sec, "santé collecteur", False, detail=e)
        client.close()
        return

    H = _hdr(admin_token) if admin_token else {}
    # Summary + RGPD
    try:
        r = client.get(EP["coll_summary"], headers=H)
        ok = r.status_code < 300
        rep.check(sec, "summary collecteur", ok, http=r.status_code)
        if ok:
            body = r.text.lower()
            leak = [f for f in RGPD_FORBIDDEN if f"\"{f}\"" in body]
            rep.check(sec, "RGPD : aucune donnée patient dans le summary", not leak,
                      detail=("champs détectés: " + ",".join(leak)) if leak else "")
    except Exception as e:
        rep.check(sec, "summary collecteur", False, detail=e)

    # Config centrale admin (lecture masquée)
    if admin_token:
        try:
            r = client.get(EP["coll_central"], headers=H)
            rep.check(sec, "config centrale lisible (admin)", r.status_code < 300, http=r.status_code, warn=True)
        except Exception as e:
            rep.check(sec, "config centrale lisible (admin)", False, detail=e, warn=True)
    else:
        rep.skip(sec, "config centrale (pas de token admin fourni)")
    client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Checks — INTER-INSTANCES (transfert A → B via collecteur)
# ─────────────────────────────────────────────────────────────────────────────
def checks_inter_instances(rep, instances, user, password):
    sec = "Inter-instances"
    if len(instances) < 2:
        rep.skip(sec, "transfert A→B (moins de 2 instances)")
        return
    a, b = instances[0], instances[1]
    ca = httpx.Client(base_url=a["url"], timeout=15, follow_redirects=True)
    tok, _, _ = login(ca, user, password)
    if not tok:
        rep.skip(sec, "transfert A→B (login A KO)")
        ca.close()
        return
    try:
        r = ca.post(EP["transfert"], headers=_hdr(tok), json={
            "unite_origine": "URGENCES", "etablissement_origine": a["label"],
            "unite_destination": "URGENCES", "etablissement_destination": b["label"],
            "redacteur": "banc", "statut": "EN_COURS", "nom": "Patient banc"})
        rep.check(sec, f"transfert {a['label']}→{b['label']} créé", r.status_code < 300, http=r.status_code)
        # vérif côté B : à compléter (kanban entrant via collecteur) — placeholder informatif
        rep.skip(sec, f"transfert visible côté {b['label']} (vérif fédération à brancher)")
    except Exception as e:
        rep.check(sec, "transfert A→B", False, detail=e)
    ca.close()


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration --auto (lance une pile JETABLE)
# ─────────────────────────────────────────────────────────────────────────────
def _free_port(p):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _wait_health(url, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(url + EP["health"], timeout=3).status_code < 400:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


class Orchestrator:
    """Lance collecteur + N instances en subprocess, DBs/ports isolés. JETABLE."""
    def __init__(self, root, base_port=8800, coll_port=9800,
                 admin_user="dircrise", admin_pass="Scribe2026!"):
        self.root = root
        self.base_port = base_port
        self.coll_port = coll_port
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.admin_token = "BENCH-ADMIN-TOKEN"
        self.procs = []
        self.workdir = os.path.join(root, "bench_run")
        os.makedirs(self.workdir, exist_ok=True)

    def _python(self):
        return sys.executable or "python3"

    def _spawn(self, name, env, args):
        log = open(os.path.join(self.workdir, f"{name}.log"), "w")
        p = subprocess.Popen(args, cwd=self.root, env=env,
                              stdout=log, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL)
        self.procs.append((name, p, log))
        return p

    def start(self, n_instances=2):
        # Repartir de DB FRAÎCHES à chaque run : sinon un admin créé lors d'un run
        # précédent (ex. avec bcrypt cassé → hash invalide) persiste, et
        # ensure_admin ne réécrit pas le mot de passe d'un admin existant → 401.
        import glob as _glob
        for _db in _glob.glob(os.path.join(self.workdir, "*.db")):
            try:
                os.remove(_db)
            except Exception:
                pass
        launched = []
        # Instances
        for i in range(n_instances):
            port = self.base_port + i
            env = os.environ.copy()
            env.update({
                "SCRIBE_PORT": str(port),
                "DATABASE_URL": f"sqlite:///{self.workdir}/bench_inst_{port}.db",
                "SCRIBE_PORT_CLEANUP_ALL": "0",
                # admin connu → l'auth du banc fonctionne (sinon mdp aléatoire)
                "SCRIBE_ADMIN_USER": self.admin_user,
                "SCRIBE_ADMIN_PASS": self.admin_pass,
                # pas de changement de mdp forcé sur la pile jetable (sinon le
                # verrou serveur h64 renverrait 403 sur tous les checks de données)
                "SCRIBE_ADMIN_MUST_CHANGE": "0",
            })
            self._spawn(f"inst_{port}", env, [self._python(), "main.py"])
            launched.append({"url": f"http://127.0.0.1:{port}", "label": f"BENCH{i+1}",
                             "port": port,
                             "log": os.path.join(self.workdir, f"inst_{port}.log")})
        # Collecteur
        coll_env = os.environ.copy()
        coll_env.update({"COLLECTEUR_PORT": str(self.coll_port),     # ← bon nom de variable
                         "ADMIN_TOKEN": self.admin_token,
                         "SCRIBE_SECRET": "bench-secret"})
        coll_path = os.path.join(self.root, "collecteur", "collecteur.py")
        if os.path.exists(coll_path):
            self._spawn("collecteur", coll_env, [self._python(), coll_path])
        coll_url = f"http://127.0.0.1:{self.coll_port}"
        # Attendre la santé
        for inst in launched:
            if not _wait_health(inst["url"]):
                print(f"  ⚠ instance {inst['port']} pas prête (voir {self.workdir}/inst_{inst['port']}.log)")
        if os.path.exists(coll_path):
            _wait_health(coll_url, timeout=25)
        return launched, coll_url, self.admin_token

    def stop(self):
        for name, p, log in self.procs:
            try:
                p.send_signal(signal.SIGTERM)
                p.wait(timeout=8)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            finally:
                try:
                    log.close()
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# Rapports : écriture + rétention
# ─────────────────────────────────────────────────────────────────────────────
def write_reports(rep, report_dir, keep_days):
    os.makedirs(report_dir, exist_ok=True)
    stamp = rep.started.strftime("%Y%m%d_%H%M%S")
    html_path = os.path.join(report_dir, f"healthcheck_{stamp}.html")
    json_path = os.path.join(report_dir, f"healthcheck_{stamp}.json")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(rep.to_html())
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rep.to_json(), f, ensure_ascii=False, indent=2)
    # rétention
    cutoff = time.time() - keep_days * 86400
    purged = 0
    for fn in os.listdir(report_dir):
        if fn.startswith("healthcheck_"):
            fp = os.path.join(report_dir, fn)
            try:
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
                    purged += 1
            except Exception:
                pass
    return html_path, json_path, purged


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="SCRIBE health-check / benchmark")
    ap.add_argument("--auto", action="store_true", help="Lance une pile jetable, teste, arrête")
    ap.add_argument("--collecteur", default="")
    ap.add_argument("--instances", default="", help="URLs séparées par des virgules")
    ap.add_argument("--admin-token", default=os.getenv("ADMIN_TOKEN", ""))
    ap.add_argument("--user", default="dircrise")
    ap.add_argument("--password", default="Scribe2026!")
    ap.add_argument("--report-dir", default="bench_reports")
    ap.add_argument("--keep-days", type=int, default=7)
    args = ap.parse_args()

    rep = Reporter()
    orch = None
    print(f"\n=== SCRIBE health-check — {rep.started:%Y-%m-%d %H:%M:%S} ===\n")

    instances = []
    coll_url = args.collecteur

    if args.auto:
        print("Mode --auto : lancement d'une pile jetable…")
        orch = Orchestrator(os.path.dirname(os.path.abspath(__file__)),
                            admin_user=args.user, admin_pass=args.password)
        launched, coll_url, coll_token = orch.start(n_instances=2)
        instances = launched
        if not args.admin_token:
            args.admin_token = coll_token
    else:
        for i, u in enumerate([x.strip() for x in args.instances.split(",") if x.strip()]):
            instances.append({"url": u, "label": f"INST{i+1}", "port": None})

    try:
        if not instances and not coll_url:
            print("Rien à tester : fournir --auto ou --collecteur/--instances.")
            return 2
        for inst in instances:
            checks_instance(rep, inst["url"], inst["label"], args.user, args.password,
                            log_path=inst.get("log"))
        if coll_url:
            checks_collecteur(rep, coll_url, args.admin_token)
        checks_inter_instances(rep, instances, args.user, args.password)
        # Mode exercice : à brancher en phase 2 (pile :8565 + :8660/8661)
        rep.skip("Exercice", "pile exercice (phase 2)")
    finally:
        if orch:
            print("\nArrêt de la pile jetable…")
            orch.stop()

    html_path, json_path, purged = write_reports(rep, args.report_dir, args.keep_days)
    c = rep.counts()
    print(f"\n=== Bilan : {c['PASS']} PASS / {c['FAIL']} FAIL / {c['WARN']} WARN / {c['SKIP']} SKIP "
          f"— santé : {rep.health_color().upper()} ===")
    print(f"Rapport HTML : {html_path}")
    print(f"Rapport JSON : {json_path}" + (f"  (purge : {purged} ancien(s))" if purged else ""))
    return 1 if c["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
