import os, sys, tempfile, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import backup

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "src.db")
dst = os.path.join(tmp, "dst.db")   # base VIERGE (n'existe pas encore)

# --- 1) Base source qui imite SCRIBE ---
con = sqlite3.connect(src); c = con.cursor()
c.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE,
             hashed_password TEXT, role TEXT, active INTEGER)""")
c.execute("""CREATE TABLE unites_fonctionnelles (id INTEGER PRIMARY KEY, uf_code TEXT,
             libelle TEXT, pole TEXT, active INTEGER)""")
c.execute("""CREATE TABLE chat_salons (id INTEGER PRIMARY KEY, nom TEXT, type TEXT)""")
c.execute("""CREATE TABLE notif_channel (id INTEGER PRIMARY KEY, kind TEXT, label TEXT,
             enabled INTEGER, config_json TEXT)""")
c.executemany("INSERT INTO users(username,hashed_password,role,active) VALUES (?,?,?,?)",
   [("dircrise","$2b$12$abcdefHASHvalue","cellule",1),
    ("animateur","$2b$12$zzzHASHanim","animateur",1),
    ("vieuxcompte","$2b$12$old",  "soignant",0)])
c.executemany("INSERT INTO unites_fonctionnelles(uf_code,libelle,pole,active) VALUES (?,?,?,?)",
   [("REA01","Réanimation","Urgences/Réa",1),("MAT01","Maternité","Femme-Mère-Enfant",1)])
c.executemany("INSERT INTO chat_salons(nom,type) VALUES (?,?)",
   [("Cellule de crise","local"),("Coordination GHT","territorial")])
c.execute("INSERT INTO notif_channel(kind,label,enabled,config_json) VALUES (?,?,?,?)",
   ("sms","SMS opérateur",1,'{"api_key":"SECRET-OVH-123","sender":"SCRIBE"}'))
con.commit(); con.close()

PWD = "MotDePasseFort!2026"
CFG = {"config_chag.xml": "<etablissement nom='Démo'/>"}

# --- 2) Collecte -> chiffrement -> (archive) ---
payload = backup.collect({"instance": src}, config_files=CFG)
blob = backup.make_encrypted_zip(payload, PWD)
print(f"Archive chiffrée : {len(blob)} octets")

# --- 3) Mauvais mot de passe rejeté ---
try:
    backup.read_encrypted_zip(blob, "mauvais")
    print("✗ ERREUR: mauvais mot de passe accepté !"); raise SystemExit(1)
except Exception:
    print("✓ Mauvais mot de passe rejeté")

# --- 4) Lecture + restauration sur base VIERGE ---
restored = backup.read_encrypted_zip(blob, PWD)
backup.restore(restored, {"instance": dst}, config_dir=tmp)

# --- 5) Vérifications ---
def rows(db, q): 
    cc=sqlite3.connect(db); cc.row_factory=sqlite3.Row; r=[dict(x) for x in cc.execute(q)]; cc.close(); return r

ok=True
for tbl in ["users","unites_fonctionnelles","chat_salons","notif_channel"]:
    a=rows(src,f"SELECT * FROM {tbl} ORDER BY id"); b=rows(dst,f"SELECT * FROM {tbl} ORDER BY id")
    same = a==b
    ok &= same
    print(f"  {tbl:24} source={len(a):<2} restauré={len(b):<2} {'✓ identique' if same else '✗ DIFFÈRE'}")

# vérifs ciblées plug-and-play
u=rows(dst,"SELECT * FROM users WHERE username='dircrise'")[0]
assert u["hashed_password"].startswith("$2b$"), "hash perdu"
assert u["active"]==1
inactif=rows(dst,"SELECT active FROM users WHERE username='vieuxcompte'")[0]["active"]
assert inactif==0, "état actif/inactif perdu"
secret=rows(dst,"SELECT config_json FROM notif_channel")[0]["config_json"]
assert "SECRET-OVH-123" in secret, "secret canal notif perdu"
cfg=open(os.path.join(tmp,"config_chag.xml")).read()
assert "Démo" in cfg, "config non restaurée"
print("✓ Hash bcrypt, état actif/inactif, secret de canal et config : tous restaurés")

print("\n" + ("✅ CYCLE COMPLET VALIDÉ — sauvegarde plug-and-play opérationnelle" if ok else "❌ ÉCHEC"))
raise SystemExit(0 if ok else 1)
