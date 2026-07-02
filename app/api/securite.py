"""Endpoints Sécurité — télémétrie (données) + tableau de bord (visuel).

- GET  /telemetrie  : agrégats JSON (require_admin)
- POST /reset       : purge les compteurs (require_admin)
- GET  /dashboard   : page HTML autonome (le shell est ouvert ; les données sont
                       protégées par le jeton admin envoyé en en-tête par le JS)
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.auth import require_admin
from app.api import sectelemetry

router = APIRouter()


@router.get("/telemetrie")
def get_telemetrie(_admin=Depends(require_admin)):
    return JSONResponse(sectelemetry.snapshot())


@router.post("/reset")
def reset_telemetrie(_admin=Depends(require_admin)):
    sectelemetry.reset()
    return {"ok": True}


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(_DASH_HTML)


_DASH_HTML = r"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCRIBE — Télémétrie sécurité</title>
<style>
:root{--blue:#003189;--red:#e1000f;--bg:#f6f7fb;--card:#fff;--bd:#e2e8f0;
      --tx:#0f172a;--mu:#64748b;--ok:#16a34a;--warn:#d97706;--mo:ui-monospace,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--tx);padding:18px;max-width:1200px;margin:0 auto}
h1{font-size:18px;color:var(--blue);display:flex;align-items:center;gap:10px}
.bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}
.controls{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--mu)}
button{font-family:inherit;font-size:12px;padding:6px 12px;border:1px solid var(--bd);
       background:var(--card);border-radius:6px;cursor:pointer;color:var(--tx)}
button:hover{background:#f1f5f9}
button.danger{border-color:#fca5a5;color:#dc2626}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}
.card .k{font-size:10px;letter-spacing:.5px;text-transform:uppercase;color:var(--mu);font-family:var(--mo)}
.card .v{font-size:26px;font-weight:700;margin-top:4px}
.card .v.red{color:var(--red)}
.card .sub{font-size:11px;color:var(--mu);margin-top:2px}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px 16px;margin-bottom:16px}
.panel h2{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mu);font-family:var(--mo);margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);vertical-align:top}
th{font-size:10px;text-transform:uppercase;color:var(--mu);font-family:var(--mo)}
td.mono,.ip{font-family:var(--mo)}
.tag{display:inline-block;font-family:var(--mo);font-size:10px;padding:1px 6px;border-radius:10px;background:#eef2ff;color:var(--blue);margin:1px}
.tag.r{background:#fee2e2;color:#dc2626}
.tag.w{background:#fef3c7;color:#b45309}
.gridbars{display:flex;flex-direction:column;gap:6px}
.rowbar{display:flex;align-items:center;gap:8px;font-size:12px}
.rowbar .lbl{flex:0 0 auto;max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--mo)}
.rowbar .track{flex:1;height:8px;background:#f1f5f9;border-radius:4px;overflow:hidden}
.rowbar .fill{height:100%;background:var(--red)}
.rowbar .n{flex:0 0 auto;color:var(--mu);font-family:var(--mo)}
.muted{color:var(--mu);font-size:12px}
svg{width:100%;height:120px;display:block}
.legend{font-size:10px;color:var(--mu);font-family:var(--mo);display:flex;gap:12px;margin-top:4px}
.dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:4px;vertical-align:middle}
#err{display:none;background:#fee2e2;color:#dc2626;padding:10px;border-radius:8px;font-size:13px;margin-bottom:12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:800px){.two{grid-template-columns:1fr}}
</style></head><body>
<div id="err"></div>
<div class="bar">
  <h1>🛡️ Télémétrie sécurité <span class="muted" style="font-weight:400;font-size:12px">— observation (aucun blocage)</span></h1>
  <div class="controls">
    <span id="since"></span>
    <label><input type="checkbox" id="auto" checked> auto 10s</label>
    <button onclick="load()">Rafraîchir</button>
    <button class="danger" onclick="doReset()">Réinitialiser</button>
  </div>
</div>

<div class="cards" id="cards"></div>

<div class="panel">
  <h2>Activité (24 h) — total vs suspect</h2>
  <svg id="spark" viewBox="0 0 720 120" preserveAspectRatio="none"></svg>
  <div class="legend"><span><span class="dot" style="background:#cbd5e1"></span>total</span><span><span class="dot" style="background:var(--red)"></span>suspect</span></div>
</div>

<div class="two">
  <div class="panel">
    <h2>IP suspectes (top)</h2>
    <table><thead><tr><th>IP</th><th>Suspect</th><th>Total</th><th>Motifs</th><th>Dernière</th></tr></thead>
    <tbody id="ips"></tbody></table>
  </div>
  <div class="panel">
    <h2>Chemins ciblés (top)</h2>
    <div class="gridbars" id="paths"></div>
  </div>
</div>

<div class="two">
  <div class="panel"><h2>Par motif</h2><div id="reasons"></div></div>
  <div class="panel"><h2>Codes HTTP</h2><div id="status"></div></div>
</div>

<div class="panel">
  <h2>Événements suspects récents</h2>
  <table><thead><tr><th>Heure (UTC)</th><th>IP</th><th>Méth.</th><th>Chemin</th><th>Code</th><th>Motif</th></tr></thead>
  <tbody id="events"></tbody></table>
</div>

<script>
function tok(){ try{ var p=new URLSearchParams(location.search); return p.get("token")||localStorage.getItem("scribe_token")||""; }catch(e){ return ""; } }
function esc(s){ return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
function showErr(m){ var e=document.getElementById("err"); e.textContent=m; e.style.display="block"; }

var REASON_LBL={chemin_scan:"Chemin de scan",agent_scan:"Agent de scan",methode_anormale:"Méthode anormale",sondage_404:"Sondage 404"};

function load(){
  fetch("/api/v1/securite/telemetrie",{headers:{Authorization:"Bearer "+tok()}})
  .then(function(r){ if(r.status===401||r.status===403){ showErr("Accès refusé — ouvrez cette page avec un jeton admin (?token=...)."); return null;} return r.ok?r.json():null; })
  .then(function(d){ if(!d) return; document.getElementById("err").style.display="none"; render(d); })
  .catch(function(e){ showErr("Erreur réseau : "+e.message); });
}

function render(d){
  document.getElementById("since").textContent = "depuis "+esc(d.since)+" · "+Math.floor(d.uptime_s/3600)+"h";
  var pct = d.total? Math.round(d.suspect*1000/d.total)/10 : 0;
  document.getElementById("cards").innerHTML =
    card("Requêtes",""+d.total,"") +
    card("Suspectes",""+d.suspect,pct+" % du trafic",true) +
    card("IP uniques",""+d.ip_uniques,"") +
    card("IP suspectes",""+d.ip_suspectes,"",d.ip_suspectes>0);

  // sparkline
  spark(d.hourly||[]);

  // top IPs
  document.getElementById("ips").innerHTML = (d.top_ips||[]).map(function(x){
    return "<tr><td class='ip'>"+esc(x.ip)+"</td><td><b style='color:var(--red)'>"+x.suspect+"</b></td><td>"+x.total+"</td><td>"+
      (x.reasons||[]).map(function(r){return "<span class='tag r'>"+esc(REASON_LBL[r]||r)+"</span>";}).join("")+
      "</td><td class='mono'>"+esc((x.last||"").replace("T"," ").replace("Z",""))+"</td></tr>";
  }).join("") || "<tr><td colspan='5' class='muted'>Aucune IP suspecte pour l'instant.</td></tr>";

  // top paths
  var paths=d.top_paths||[]; var mx=paths.reduce(function(a,b){return Math.max(a,b.count);},1);
  document.getElementById("paths").innerHTML = paths.map(function(x){
    return "<div class='rowbar'><span class='lbl' title='"+esc(x.path)+"'>"+esc(x.path)+"</span>"+
      "<span class='track'><span class='fill' style='width:"+Math.round(x.count*100/mx)+"%'></span></span>"+
      "<span class='n'>"+x.count+"</span></div>";
  }).join("") || "<span class='muted'>Rien à signaler.</span>";

  // reasons
  document.getElementById("reasons").innerHTML = (d.reasons||[]).map(function(x){
    return "<span class='tag r'>"+esc(REASON_LBL[x.reason]||x.reason)+" · "+x.count+"</span>";
  }).join(" ") || "<span class='muted'>—</span>";

  // status
  document.getElementById("status").innerHTML = (d.status||[]).map(function(x){
    var cls = x.status[0]==="2"?"":(x.status[0]==="4"?"w":"r");
    return "<span class='tag "+cls+"'>"+esc(x.status)+" · "+x.count+"</span>";
  }).join(" ") || "<span class='muted'>—</span>";

  // events
  document.getElementById("events").innerHTML = (d.events||[]).map(function(e){
    return "<tr><td class='mono'>"+esc((e.at||"").replace("T"," ").replace("Z",""))+"</td>"+
      "<td class='ip'>"+esc(e.ip)+"</td><td class='mono'>"+esc(e.method)+"</td>"+
      "<td class='mono' title='"+esc(e.ua)+"'>"+esc(e.path)+"</td>"+
      "<td><span class='tag "+(String(e.status)[0]==="4"?"w":"r")+"'>"+esc(e.status)+"</span></td>"+
      "<td>"+esc(REASON_LBL[e.reason]||e.reason)+"</td></tr>";
  }).join("") || "<tr><td colspan='6' class='muted'>Aucun événement suspect capté.</td></tr>";
}

function card(k,v,sub,red){
  return "<div class='card'><div class='k'>"+esc(k)+"</div><div class='v"+(red?" red":"")+"'>"+esc(v)+"</div>"+
    (sub?"<div class='sub'>"+esc(sub)+"</div>":"")+"</div>";
}

function spark(h){
  var W=720,H=120,pad=4; var n=h.length||1; var bw=W/Math.max(n,1);
  var mx=h.reduce(function(a,b){return Math.max(a,b.total);},1);
  var s="";
  h.forEach(function(b,i){
    var x=i*bw; var ht=Math.round((b.total/mx)*(H-2*pad));
    var hs=Math.round((b.suspect/mx)*(H-2*pad));
    s+="<rect x='"+(x+1)+"' y='"+(H-pad-ht)+"' width='"+(bw-2)+"' height='"+ht+"' fill='#cbd5e1'></rect>";
    if(hs>0) s+="<rect x='"+(x+1)+"' y='"+(H-pad-hs)+"' width='"+(bw-2)+"' height='"+hs+"' fill='#e1000f'></rect>";
  });
  document.getElementById("spark").innerHTML=s;
}

function doReset(){
  if(!confirm("Réinitialiser tous les compteurs de télémétrie ?")) return;
  fetch("/api/v1/securite/reset",{method:"POST",headers:{Authorization:"Bearer "+tok()}})
    .then(function(r){ if(r.ok) load(); else showErr("Réinitialisation refusée (admin requis)."); });
}

var timer=null;
function tick(){ if(document.getElementById("auto").checked) load(); }
document.getElementById("auto").addEventListener("change",function(){});
setInterval(tick,10000);
load();
</script>
</body></html>"""
